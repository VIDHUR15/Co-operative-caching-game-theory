"""
edge_node.py

A real edge cache server. Run several of these as separate
processes (different ports) to form a real cooperative
caching network - they genuinely talk to each other over
HTTP, genuinely cache real content in memory, and genuinely
decide whether to cooperate using real measured latency fed
into the same formula as game_theory.py.

Run with:
    python live/edge_node.py --name EdgeA --port 6001 \\
        --peers http://127.0.0.1:6002 \\
        --origin http://127.0.0.1:6000 \\
        --capacity 5

Endpoints
---------
GET /fetch/<article>        Client-facing: get this content,
                             serving from local cache, a
                             cooperative peer, or the origin.
GET /peer_check/<article>   Peer-facing: "do you have this,
                             and how big is it?" - no content
                             transfer, just real metadata.
GET /peer_fetch/<article>   Peer-facing: give me your real
                             cached copy of this content.
GET /health                 Used by other nodes to measure
                             real round-trip time to this one.
GET /stats                  Real cumulative stats + current
                             cache contents + a log of recent
                             requests and why each one was
                             decided the way it was.
"""

import argparse
import time
from collections import deque

import requests
from flask import Flask, jsonify

from cache_store import LRUCache
from cooperation import ping, should_cooperate


app = Flask(__name__)

# Configured at startup via main()
NODE_NAME = "edge"
PEERS = []
ORIGIN_URL = None
cache = None

# Real per-node stats
stats = {
    "local_hits": 0,
    "cooperative_hits": 0,
    "origin_requests": 0
}

recent_log = deque(maxlen=50)

# Real measured round-trip times, refreshed periodically
# rather than on every single request.
_ping_cache = {}
_PING_TTL_SECONDS = 5


def get_latency_ms(base_url):
    """
    Returns a real measured round-trip time to base_url,
    reusing a recent measurement if still fresh.
    """

    now = time.time()

    cached = _ping_cache.get(base_url)
    if cached and (now - cached[0]) < _PING_TTL_SECONDS:
        return cached[1]

    latency = ping(base_url)

    if latency is not None:
        _ping_cache[base_url] = (now, latency)

    return latency


@app.route("/fetch/<path:article>")
def fetch(article):

    start = time.perf_counter()

    # ------------------------------------------------------
    # 1. Local cache
    # ------------------------------------------------------

    local = cache.get(article)

    if local is not None:
        content, size_mb = local
        stats["local_hits"] += 1

        elapsed_ms = (time.perf_counter() - start) * 1000

        recent_log.appendleft({
            "article": article,
            "result": "local_hit",
            "size_mb": round(size_mb, 4),
            "latency_ms": round(elapsed_ms, 2)
        })

        return jsonify({
            "article": article,
            "source": "local_cache",
            "size_mb": round(size_mb, 4),
            "latency_ms": round(elapsed_ms, 2),
            "content_preview": content[:200]
        })

    # ------------------------------------------------------
    # 2. Cooperative peers - real metadata check first, then
    #    a real cooperation decision using real measured
    #    latency, before committing to a real transfer.
    # ------------------------------------------------------

    for peer_url in PEERS:

        try:
            check = requests.get(
                f"{peer_url}/peer_check/{article}", timeout=2
            )
            check.raise_for_status()
            info = check.json()
        except requests.exceptions.RequestException:
            continue

        if not info.get("cached"):
            continue

        real_size_mb = info["size_mb"]

        peer_latency = get_latency_ms(peer_url)
        origin_latency = get_latency_ms(ORIGIN_URL)

        if peer_latency is None or origin_latency is None:
            continue

        cooperate = should_cooperate(
            peer_latency_ms=peer_latency,
            origin_latency_ms=origin_latency,
            content_size_mb=real_size_mb
        )

        if not cooperate:
            recent_log.appendleft({
                "article": article,
                "result": "declined_cooperation",
                "peer": peer_url,
                "reasoning": (
                    f"peer_latency={peer_latency:.1f}ms "
                    f"origin_latency={origin_latency:.1f}ms "
                    f"size={real_size_mb:.4f}MB - not worth it"
                )
            })
            continue

        try:
            fetch_start = time.perf_counter()
            peer_response = requests.get(
                f"{peer_url}/peer_fetch/{article}", timeout=5
            )
            peer_response.raise_for_status()
            peer_data = peer_response.json()
        except requests.exceptions.RequestException:
            continue

        elapsed_ms = (time.perf_counter() - start) * 1000

        content = peer_data["content"]
        size_mb = peer_data["size_mb"]

        cache.put(article, content, size_mb)
        stats["cooperative_hits"] += 1

        recent_log.appendleft({
            "article": article,
            "result": "cooperative_hit",
            "peer": peer_url,
            "size_mb": round(size_mb, 4),
            "latency_ms": round(elapsed_ms, 2),
            "reasoning": (
                f"peer_latency={peer_latency:.1f}ms < "
                f"origin_latency={origin_latency:.1f}ms for "
                f"{size_mb:.4f}MB - worth cooperating"
            )
        })

        return jsonify({
            "article": article,
            "source": f"cooperative_peer:{peer_url}",
            "size_mb": round(size_mb, 4),
            "latency_ms": round(elapsed_ms, 2),
            "content_preview": content[:200]
        })

    # ------------------------------------------------------
    # 3. Origin (real Wikipedia fetch, or its fallback)
    # ------------------------------------------------------

    try:
        origin_response = requests.get(
            f"{ORIGIN_URL}/origin/{article}", timeout=10
        )
        origin_response.raise_for_status()
        origin_data = origin_response.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 502

    content = origin_data["content"]
    size_mb = origin_data["size_mb"]

    cache.put(article, content, size_mb)
    stats["origin_requests"] += 1

    elapsed_ms = (time.perf_counter() - start) * 1000

    recent_log.appendleft({
        "article": article,
        "result": "origin_request",
        "origin_source": origin_data["source"],
        "size_mb": round(size_mb, 4),
        "latency_ms": round(elapsed_ms, 2)
    })

    return jsonify({
        "article": article,
        "source": f"origin ({origin_data['source']})",
        "size_mb": round(size_mb, 4),
        "latency_ms": round(elapsed_ms, 2),
        "content_preview": content[:200]
    })


@app.route("/peer_check/<path:article>")
def peer_check(article):
    """
    Lightweight: does this node have the article cached, and
    how big is it? No content transfer.
    """

    local = cache.get(article)

    if local is None:
        return jsonify({"cached": False})

    content, size_mb = local
    return jsonify({"cached": True, "size_mb": round(size_mb, 4)})


@app.route("/peer_fetch/<path:article>")
def peer_fetch(article):
    """
    Full content transfer to a cooperating peer. Does not
    recurse to this node's own peers/origin.
    """

    local = cache.get(article)

    if local is None:
        return jsonify({"error": "not cached here"}), 404

    content, size_mb = local
    return jsonify({
        "article": article,
        "content": content,
        "size_mb": size_mb
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "node": NODE_NAME})


@app.route("/stats")
def get_stats():
    return jsonify({
        "node": NODE_NAME,
        "stats": stats,
        "cache_contents": cache.snapshot(),
        "cache_capacity": cache.capacity,
        "recent_log": list(recent_log)
    })


def main():

    global NODE_NAME, PEERS, ORIGIN_URL, cache

    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="edge")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--peers", default="",
        help="Comma-separated peer base URLs, e.g. "
             "http://127.0.0.1:6002"
    )
    parser.add_argument("--origin", required=True)
    parser.add_argument("--capacity", type=int, default=5)
    args = parser.parse_args()

    NODE_NAME = args.name
    PEERS = [p for p in args.peers.split(",") if p]
    ORIGIN_URL = args.origin
    cache = LRUCache(capacity=args.capacity)

    print(f"Edge node '{NODE_NAME}' starting on port {args.port}")
    print(f"  Peers: {PEERS or '(none)'}")
    print(f"  Origin: {ORIGIN_URL}")
    print(f"  Cache capacity: {args.capacity}")

    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
