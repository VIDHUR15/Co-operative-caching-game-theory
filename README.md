# Cooperative Caching Using Game Theory

A simulation of cooperative content caching in edge/CDN networks. Edge
servers choose peer retrieval or origin retrieval using a simplified
game-inspired payoff policy, an optional machine-learning layer predicts what to cache
before it's even requested, and everything is compared against a
non-cooperative baseline across a geographically realistic network.

## What this project does

- **Builds a CDN topology** (`topology.py`): an Origin server, regional
  PoPs, edge servers, and users, connected by links whose
  latency/bandwidth are derived from real great-circle distance between
  approximate real-world region coordinates (Ashburn VA, San Francisco,
  London, Singapore) rather than picked at random.
- **Selects peer retrieval with a simplified payoff policy** (`game_theory.py`):
  the actions mean "try retrieving from a peer" and "use origin". Connected
  peers remain willing to serve cached content regardless of their own route
  preference. A pairwise best-response calculation uses modeled transfer-time
  savings minus coordination cost, plus a 2 ms utility bonus when both prefer
  peer retrieval. This is not a sharing-permission or fairness game, and it
  does not prove globally optimal caching. The existing strategy names are
  retained for continuity.
- **Predicts what to cache** (`demand_predictor.py`): an optional
  `RandomForestClassifier` trained on request history predicts which
  content an edge is likely to need next, used to prefetch into free
  cache slots and to guide eviction (an "ML Cooperative" strategy,
  layered on top of the game-theoretic cooperation decision).
- **Runs and compares four strategies** (`simulation.py`,
  `main_analysis.py`): non-cooperative, always-cooperative, game-theoretic cooperative, and
  ML-cooperative, reporting hit rate, latency, bandwidth, and origin
  server load for each.
- **Web dashboard** (`app.py`, `templates/index.html`): the same
  four-way comparison, interactively configurable, in the browser.
- **A real, running version** (`live/`): actual Flask servers making
  actual HTTP calls to each other, caching real content in memory, and
  deciding whether to cooperate using real measured network latency —
  not a simulation. See `live/README.md`.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running it

**Web dashboard** (recommended — interactive):
```bash
python app.py
```
Then open `http://127.0.0.1:5000`. Configure number of requests, cache
capacity, and network size (edges/users per region), then click *Run
Simulation* to see all four strategies compared side by side.

**Command-line analysis** (prints results, shows matplotlib charts):
```bash
python main_analysis.py
```

**Individual modules** (each has a small demo in `if __name__ ==
"__main__"`):
```bash
python topology.py       # print the generated network topology
python game_theory.py    # print cooperation decisions per edge pair
python simulation.py     # run one simulation, print a summary
```

## Required Wikipedia dataset

The synthetic video catalog has been removed. Before starting the dashboard,
CLI analysis, tests, or scenario evaluation, download the Wikipedia catalog:

```bash
python data/fetch_wikipedia_dataset.py
python app.py
```

The downloader creates `data/wikipedia_content_catalog.csv`. The simulator
requires this file and stops with an actionable error if it is missing,
empty, or malformed; it never substitutes synthetic videos.
Optional arguments include `--date 2026-08-01 --top-n 30`.

Requests are still generated from the catalog's popularity counts, rather
than replayed from chronological logs. The existing downloader estimates
article sizes if a size lookup fails; removing that separate behavior is not
part of this video-catalog change.

Previously saved `evaluation_results/` describe the former synthetic-video
experiments. They are historical results, not Wikipedia results. Rerun the
scenario evaluation after downloading the CSV to obtain new results.

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```

## Known limitations

- **Cache freshness isn't modeled.** Cached content is treated as valid
  forever; a real CDN would need expiry/revalidation, which would add a
  baseline of unavoidable origin traffic even with a perfect cache.
- **End-to-end latency is dominated by the user→edge "last mile" link**,
  which no caching strategy can improve — so total latency improvements
  look modest even when the backend portion (the part caching actually
  controls) improves substantially. 
- **`coordination_overhead_ms` and `mutual_cooperation_bonus_ms`** in
  `game_theory.py` are reasoned estimates (a plausible extra-round-trip
  and a small tiebreaker for genuine ties), not measured constants.
- **The ML predictor mainly learns global content popularity**, since
  the request generator doesn't currently vary popularity by region.

## Project structure

```
topology.py              Network topology, links, real-geography distance model
game_theory.py            Cooperation decisions (payoff model)
simulation.py             Request simulation, 4 strategies, content catalog
demand_predictor.py       ML popularity prediction for the ML-cooperative strategy
main_analysis.py          CLI analysis: run + print + plot all 4 strategies
app.py                    Flask web dashboard
templates/index.html      Dashboard UI
data/fetch_wikipedia_dataset.py   Real dataset fetcher (run locally)
live/                      Real, running cooperative cache (not simulated) - see live/README.md
tests/                    Automated tests
requirements.txt
```

## Always-cooperative baseline

`strategy="always_cooperative"` implements ordinary cache sharing: local cache
first, then the first connected peer that has the item, then origin. It uses
LRU, does not invoke the game-theory decision, and does not train or prefetch
with ML. It uses the same topology, request seed, cache capacity, transfer
formulas, and cache updates as the existing comparison strategies.

The dashboard and CLI compare all four strategies, including game-theoretic
cooperation directly against always-cooperative sharing. Identical outcomes
are valid when game theory approves every useful transfer in a workload.

The baseline isolates ordinary sharing from selective peer retrieval. Current
results include the subsequent ML accounting and timeline corrections below.

## Peer selection and coordination accounting update

Game-theoretic and ML-cooperative requests rank connected peers by estimated
payload transfer time plus coordination cost. They apply the existing game
approval to each candidate and query approved peers in that order. A lookup
can transfer content only from that exact peer. Cache contents are inspected
only when the peer is queried; this is not a global cache-directory oracle.
Always-cooperative retains its first-available-peer order as the control.

Every queried peer, whether hit or miss, adds the same cost used by the game:
`2 * peer_link_latency + coordination_overhead_ms` (default overhead: 10 ms).
This is charged once per attempted peer for BOTH cooperative baselines, and
accumulates even if the final source is the origin. Rejected candidates are
local decisions from known topology metadata and incur no network query.
Local hits and non-cooperative requests incur no peer coordination cost.
Previously spent lookup costs are sunk when evaluating the next candidate.

Per-request traces now include payload_latency_ms, coordination_latency_ms,
peer_checks, peer_attempts and peer_decisions. Total latency includes both
payload delivery and coordination. Dashboard/CLI summaries show peer checks
and average coordination overhead. The 2 ms cooperation bonus is utility,
not a physical latency discount, and is not subtracted from measured time.

These are modeled latencies, not measurements. Control-message byte sizes
and CPU decision time are not modeled; the existing MB metric counts payload
traffic across links. The live HTTP demo is unchanged; it already
fetches from its selected peer and measures elapsed request-handling time.

## Controlled peer-link evaluation

Run `python evaluate_peer_scenarios.py` for 120 comparisons across fast, slow,
and mixed peer links (10 seeds, 1,000 requests per run). See
`evaluation_results/REPORT.md` for results, assumptions, and limitations;
`raw_results.json` records each run and `summary.json` records aggregate results.
The evaluation changes link conditions only, not policy implementations.

## Minimal ML correctness corrections

- Prefetching retains its existing timing and one-item/free-slot policy. It
  now models a synchronous origin → region → edge transfer before demand
  handling. Both payload hops, one origin access, and the full transfer delay
  are charged, whether or not the prefetched item is useful. No user-hop
  transfer is charged until the user actually receives content. Background
  overlap is not assumed.
- If the prefetched item is the current demand, it is an origin miss rather
  than a local hit, and that origin access is counted once. Later requests
  can legitimately hit the cached copy.
- `origin_requests` now includes ALL demand and prefetch origin accesses.
  `demand_origin_requests` counts demand outcomes needing origin retrieval
  (including just-in-time prefetch). Thus demand local hits + peer hits +
  demand_origin_requests equals total user requests. Total origin accesses
  can exceed user requests. `origin_request_rate` is the demand-miss rate.
- Per-request prefetch latency/traffic and prefetch origin accesses, plus
  their summary totals, expose the accounting. Total request latency includes
  synchronous prefetch delay. The dashboard and CLI show total origin accesses
  and prefetch counts separately.
- Model timestamps continue from the training log (201 after 200 training
  requests) for prediction, eviction, and observation. User-facing request
  IDs remain 1..N. Training and evaluation retain independent random streams.

No new model, payoff equations, agreement protocol, or tuned thresholds were
introduced. The 2 ms payoff bonus remains a stated modeling assumption, not a
physical latency reduction. Benefits of the policy cannot establish that game
theory is necessary compared with a simpler cost-aware retrieval rule.
