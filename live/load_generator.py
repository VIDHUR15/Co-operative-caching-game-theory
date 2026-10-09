"""
load_generator.py

Fires REAL HTTP requests at a running edge node, weighted by
the same popularity distribution simulation.py uses - real
Wikipedia articles if you've run
data/fetch_wikipedia_dataset.py, or the synthetic catalog
otherwise (in which case the origin will serve labeled
placeholder content, since e.g. "Video_A" isn't a real
Wikipedia article - the caching/cooperation mechanics are
still fully real either way).

Run with:
    python live/load_generator.py --edge http://127.0.0.1:6001 --requests 50
"""

import argparse
import os
import random
import sys
import time

import requests

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from simulation import CONTENT, CONTENT_POPULARITY_WEIGHTS, DATA_SOURCE


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--edge", default="http://127.0.0.1:6001")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()

    print(f"Content catalog: {DATA_SOURCE}")
    print(f"Sending {args.requests} real requests to {args.edge}\n")

    articles = list(CONTENT.keys())

    results = {"local_hit": 0, "cooperative_hit": 0, "origin": 0, "error": 0}

    for i in range(1, args.requests + 1):

        article = random.choices(
            articles, weights=CONTENT_POPULARITY_WEIGHTS, k=1
        )[0]

        try:
            response = requests.get(
                f"{args.edge}/fetch/{article}", timeout=10
            )
            response.raise_for_status()
            data = response.json()

            source = data["source"]

            if source == "local_cache":
                results["local_hit"] += 1
            elif source.startswith("cooperative_peer"):
                results["cooperative_hit"] += 1
            else:
                results["origin"] += 1

            print(
                f"[{i:3}/{args.requests}] {article[:40]:40} -> "
                f"{source:35} {data['latency_ms']:8.1f}ms"
            )

        except requests.exceptions.RequestException as e:
            results["error"] += 1
            print(f"[{i:3}/{args.requests}] {article[:40]:40} -> ERROR: {e}")

        time.sleep(args.delay)

    total = sum(results.values())
    print(f"\n{'='*50}")
    print("REAL RESULTS")
    print(f"{'='*50}")
    for key, count in results.items():
        pct = (100 * count / total) if total else 0
        print(f"  {key:18} {count:4}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
