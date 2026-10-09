"""
origin_server.py

The "origin" in the live cooperative caching system. Unlike
the simulation's CONTENT dict, this genuinely fetches real
Wikipedia article content over the internet when something
isn't cached anywhere in the edge network.

Run with:
    python live/origin_server.py --port 6000

If the real fetch fails (no internet, article doesn't exist,
Wikipedia unreachable), falls back to deterministic synthetic
content of a plausible size, clearly labeled as such in the
response and in /stats - so the rest of the system keeps
working and is testable even without internet access, but
you always know which mode served a given request.
"""

import argparse
import hashlib
import time

import requests
from flask import Flask, jsonify


app = Flask(__name__)

stats = {
    "real_fetches": 0,
    "fallback_fetches": 0,
    "requests": 0
}


def fetch_real_wikipedia_article(title):
    """
    Fetches the real HTML of a Wikipedia article. Returns
    (content, size_mb) or None if the fetch fails.
    """

    url = (
        f"https://en.wikipedia.org/api/rest_v1/page/html/"
        f"{title.replace(' ', '_')}"
    )

    try:
        response = requests.get(
            url,
            timeout=5,
            headers={
                "User-Agent": (
                    "cooperative-caching-live-demo/1.0 "
                    "(student research project)"
                )
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return None

    content = response.text
    size_mb = len(response.content) / (1024 * 1024)

    return content, size_mb


def generate_fallback_content(title):
    """
    Deterministic synthetic content used only when the real
    Wikipedia fetch fails. Size is derived from a hash of the
    title so it's stable across runs, and clearly not claimed
    to be real.
    """

    seed = int(hashlib.sha256(title.encode()).hexdigest(), 16)
    size_kb = 20 + (seed % 180)  # 20-200 KB, plausible article scale

    content = (
        f"[FALLBACK PLACEHOLDER CONTENT for '{title}' - real "
        f"Wikipedia fetch failed, likely no internet access]\n"
    ) * ((size_kb * 1024) // 100 + 1)

    size_mb = len(content.encode()) / (1024 * 1024)

    return content, size_mb


@app.route("/origin/<path:title>")
def get_article(title):

    stats["requests"] += 1
    start = time.perf_counter()

    real = fetch_real_wikipedia_article(title)

    if real is not None:
        content, size_mb = real
        source = "wikipedia_live"
        stats["real_fetches"] += 1
    else:
        content, size_mb = generate_fallback_content(title)
        source = "fallback_placeholder"
        stats["fallback_fetches"] += 1

    elapsed_ms = (time.perf_counter() - start) * 1000

    return jsonify({
        "article": title,
        "content": content,
        "size_mb": round(size_mb, 4),
        "source": source,
        "fetch_time_ms": round(elapsed_ms, 2)
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/stats")
def get_stats():
    return jsonify(stats)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=6000)
    args = parser.parse_args()

    print(f"Origin server starting on port {args.port}")
    print(
        "Will fetch REAL Wikipedia articles when internet is "
        "available; falls back to labeled placeholder content "
        "otherwise."
    )

    app.run(host="127.0.0.1", port=args.port, threaded=True)
