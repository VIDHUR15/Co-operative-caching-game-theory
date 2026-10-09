# Live Cooperative Caching System

An HTTP proof of concept with separate Flask origin and edge processes,
actual content transfers and in-memory caching. Its retrieval policy uses
measured health-endpoint round-trip latency, assumed bandwidths, and fixed
cost estimates. It is not an exact implementation of the simulator's
pairwise best-response rule, nor validation of its performance results.

## How it differs from the simulator

| | Simulator (`simulation.py`) | Live system (this folder) |
|---|---|---|
| Requests | Generated in a loop | Real HTTP requests, via `load_generator.py` or `curl` |
| Latency | Computed from a formula | Real measured round-trip time (`cooperation.ping()`) |
| Content | Sizes from a catalog | Real bytes, real Wikipedia HTML (or a labeled fallback) |
| Cache | A dict on a graph node | A real `LRUCache` in a real process's memory |
| Cooperation decision | `game_theory.py`, using simulated link data | `cooperation.py`, using **real measured latency** |

The live policy uses the same benefit-minus-cost idea, but requires positive
utility without the mutual-preference bonus. Decisions select the requester's
retrieval route; they do not grant or revoke a peer's permission to serve.

## Running it

Open **three terminals** from the project root:

```bash
# Terminal 1 - the origin (fetches real Wikipedia content)
python live/origin_server.py --port 6000

# Terminal 2 - edge node A
python live/edge_node.py --name EdgeA --port 6001 \
    --peers http://127.0.0.1:6002 --origin http://127.0.0.1:6000 --capacity 5

# Terminal 3 - edge node B
python live/edge_node.py --name EdgeB --port 6002 \
    --peers http://127.0.0.1:6001 --origin http://127.0.0.1:6000 --capacity 5
```

Then, in a fourth terminal, generate real traffic:

```bash
python live/load_generator.py --edge http://127.0.0.1:6001 --requests 50
```

Or try individual requests yourself:

```bash
curl http://127.0.0.1:6001/fetch/Python_(programming_language)
curl http://127.0.0.1:6001/stats
```

**For real Wikipedia content and a meaningful cooperation demo**, run
`python data/fetch_wikipedia_dataset.py` first (see the main README) so
the load generator sends real article names, and make sure the machine
running `origin_server.py` has internet access.

## Why cooperation may not trigger on localhost

If you run all three processes on the same machine, the peer and the
origin will have almost identical (sub-5ms) latency to each other —
there's no real advantage to asking a peer instead of the origin, so
the system will correctly, honestly decline to cooperate most of the
time. This isn't a bug: it's the real formula correctly recognizing
there's nothing to gain.

To see genuine cooperation happen, you need a genuine latency
asymmetry — which happens naturally once `origin_server.py` is
actually fetching over the real internet (typically 50–150ms) while
your edge nodes talk to each other over localhost (1–5ms). Run it this
way and watch `/stats`: cooperative hits should start appearing,
especially for larger articles.

## Endpoints

**Edge node** (`edge_node.py`):
- `GET /fetch/<article>` — client-facing; serves from local cache, a
  cooperating peer, or the origin.
- `GET /peer_check/<article>` — peer-facing; real metadata only
  (cached? what size?), no content transfer.
- `GET /peer_fetch/<article>` — peer-facing; real content transfer.
- `GET /health` — used by other nodes to measure real round-trip time.
- `GET /stats` — real cumulative hit/miss counts, current cache
  contents, and a log of the last 50 requests with the reasoning
  behind each cooperation decision.

**Origin** (`origin_server.py`):
- `GET /origin/<article>` — real Wikipedia fetch, or a clearly labeled
  synthetic fallback if unreachable.
- `GET /health`, `GET /stats`

## Known limitations

- Bandwidth isn't measured, only assumed (`cooperation.py`'s
  `assumed_peer_bandwidth_mbps` / `assumed_origin_bandwidth_mbps`) —
  measuring true available bandwidth would need an actual data
  transfer per decision, which isn't practical to do before every
  request. Latency, the part that varies most and drives most of the
  decision, is fully real and measured.
- This is a demonstration system (Flask's development server), not
  production infrastructure — no persistence, no auth, no TLS.
- Only tested with 2 edge nodes in one cooperative pair; more nodes
  should work (the code doesn't assume exactly 2), but hasn't been
  exercised beyond that.
