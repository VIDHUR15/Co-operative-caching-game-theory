"""
fetch_wikipedia_dataset.py

Pulls a REAL content-popularity dataset from Wikimedia's
official public APIs, and saves it as
data/wikipedia_content_catalog.csv for simulation.py to load.

This creates the required content catalog with:

    - Real article popularity: actual view counts for the
      most-viewed English Wikipedia articles on a given day,
      from the Wikimedia Pageviews API.

    - Real content size: the actual wikitext byte length of
      each article, from the MediaWiki Action API.

Why this script exists (and isn't run automatically)
------------------------------------------------------
Wikimedia does not publish raw per-request CDN logs (that
would be private user data). What they DO publish is
aggregated view-count statistics, which is the standard
real-world stand-in used in caching research for a
realistic, heavily-skewed (Zipf-like) content popularity
distribution - exactly what this project needs.

This script needs outbound internet access to
wikimedia.org, which the assistant's own sandboxed tools do
not have in this environment. Run it yourself, once, on your
own machine:

    python data/fetch_wikipedia_dataset.py

It has no third-party dependencies - just the Python
standard library.

Usage
-----
    python data/fetch_wikipedia_dataset.py
    python data/fetch_wikipedia_dataset.py --date 2026-08-01 --top-n 30
    python data/fetch_wikipedia_dataset.py --project de.wikipedia.org

After running, simulation.py will automatically pick up
data/wikipedia_content_catalog.csv the next time you run the
project - no other code changes needed.
"""

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


PAGEVIEWS_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"
    "/{project}/all-access/{year}/{month}/{day}"
)

ARTICLE_INFO_API = (
    "https://{language}.wikipedia.org/w/api.php"
    "?action=query&prop=info&format=json&titles={title}"
)

# Non-article entries the pageviews API includes that aren't
# real cacheable content (navigation, search, special pages).
EXCLUDED_PREFIXES = (
    "Special:",
    "Main_Page",
    "-",
    "Wikipedia:",
    "File:",
    "Portal:",
    "Talk:",
    "Category:",
    "Help:",
    "User:"
)

USER_AGENT = (
    "cooperative-caching-game-theory-project/1.0 "
    "(student research project; contact via GitHub)"
)


def fetch_json(url):
    """
    Fetches a URL and parses it as JSON. Wikimedia's public
    APIs ask that requests carry a descriptive User-Agent, so
    we set one here.
    """

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_top_articles(project, date, top_n):
    """
    Fetches the most-viewed articles for one day from the
    real Wikimedia Pageviews API, filters out non-article
    entries, and returns the top_n as a list of
    {"article": ..., "views": ...} dicts.
    """

    url = PAGEVIEWS_API.format(
        project=project,
        year=date.strftime("%Y"),
        month=date.strftime("%m"),
        day=date.strftime("%d")
    )

    print(f"Fetching real pageview data from:\n  {url}\n")

    data = fetch_json(url)

    articles = data["items"][0]["articles"]

    filtered = [
        entry
        for entry in articles
        if not entry["article"].startswith(EXCLUDED_PREFIXES)
    ]

    return filtered[:top_n]


def fetch_article_size(language, article_title):
    """
    Fetches the REAL wikitext byte length of one article via
    the MediaWiki Action API. Returns None if the lookup
    fails (e.g. the article was since renamed/deleted).
    """

    url = ARTICLE_INFO_API.format(
        language=language,
        title=urllib.parse.quote(article_title)
    )

    try:
        data = fetch_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError):
        return None

    pages = data.get("query", {}).get("pages", {})

    for page in pages.values():
        if "length" in page:
            return page["length"]

    return None


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Fetch a real Wikimedia pageview dataset for "
            "the cooperative caching simulator."
        )
    )

    parser.add_argument(
        "--project",
        default="en.wikipedia.org",
        help="Wikimedia project, e.g. en.wikipedia.org, "
             "de.wikipedia.org (default: en.wikipedia.org)"
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Date to pull top articles for, YYYY-MM-DD. "
             "Defaults to 3 days ago (pageview stats need a "
             "couple of days to finalize)."
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top articles to include in the "
             "content catalog (default: 20)."
    )

    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(__file__),
            "wikipedia_content_catalog.csv"
        ),
        help="Where to save the resulting CSV."
    )

    args = parser.parse_args()

    if args.date:
        date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        date = datetime.utcnow() - timedelta(days=3)

    language = args.project.split(".")[0]

    top_articles = fetch_top_articles(
        args.project,
        date,
        args.top_n
    )

    if not top_articles:
        print(
            "No articles returned - check the date/project "
            "and try again."
        )
        return

    rows = []

    for rank, entry in enumerate(top_articles, start=1):

        article = entry["article"]
        views = entry["views"]

        print(f"  [{rank:2}/{len(top_articles)}] {article} "
              f"({views:,} views) - fetching real size...")

        size_bytes = fetch_article_size(language, article)

        if size_bytes is None:
            # Fall back to the average of whatever we did
            # manage to fetch, rather than dropping the
            # article entirely.
            known_sizes = [r["size_bytes"] for r in rows if r["size_bytes"]]
            size_bytes = (
                sum(known_sizes) // len(known_sizes)
                if known_sizes else 50000
            )

        rows.append({
            "rank": rank,
            "article": article.replace("_", " "),
            "views": views,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 4)
        })

        # Be polite to the API - no more than a few requests
        # per second.
        time.sleep(0.2)

    with open(args.output, "w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=["rank", "article", "views", "size_bytes", "size_mb"]
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        f"\nSaved {len(rows)} real articles to {args.output}\n"
        f"Date: {date.strftime('%Y-%m-%d')}  Project: {args.project}\n"
        f"Top article: {rows[0]['article']} "
        f"({rows[0]['views']:,} views)\n"
        f"Least-popular of the {len(rows)}: {rows[-1]['article']} "
        f"({rows[-1]['views']:,} views)\n\n"
        f"simulation.py will automatically use this the next "
        f"time you run the project."
    )


if __name__ == "__main__":
    main()
