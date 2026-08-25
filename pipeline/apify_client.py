"""Apify Instagram Scraper wrapper (plan.md §7.2).

Calls Apify's REST API directly via `requests` rather than pulling in the
apify-client SDK -- one HTTP call per batch is all this needs.

Cost control: this actor is billed per-result ($1.50/1,000 posts as of
plan.md §4). Every run prints the estimated cost and requires --confirm.
Already-ingested shortcodes are skipped so re-runs never cost anything.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import load_settings
from db import get_client

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFS = REPO_ROOT / "data" / "post_refs.json"
RAW_DATA_DIR = REPO_ROOT / "data"

# '/' in an actor name is URL-encoded as '~' for Apify's REST API.
ACTOR = "apify~instagram-scraper"
COST_PER_1000_USD = 1.50
BATCH_SIZE = 50
# run-sync-get-dataset-items enforces its own ~300s cap on Apify's side;
# this is kept a little above that so a real Apify timeout surfaces as
# Apify's own error rather than our client giving up first.
REQUEST_TIMEOUT_S = 340


def already_ingested_shortcodes(settings) -> set[str]:
    """Every shortcode already in saved_posts -- scraping these again would
    just spend money on rows ingest.py will silently discard as duplicates."""
    client = get_client(settings)
    shortcodes: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        resp = (
            client.table("saved_posts")
            .select("instagram_post_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        shortcodes.update(row["instagram_post_id"] for row in rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return shortcodes


def scrape_batch(token: str, urls: list[str]) -> list[dict]:
    resp = requests.post(
        f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items",
        # Bearer header, not ?token=, so the token never ends up in a URL --
        # request logs, proxies, and tracebacks routinely capture URLs but
        # not header values.
        headers={"Authorization": f"Bearer {token}"},
        json={
            "directUrls": urls,
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def scrape(urls: list[str], token: str) -> list[dict]:
    all_items: list[dict] = []
    total_batches = (len(urls) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"scraping batch {batch_num}/{total_batches} ({len(batch)} urls)...", file=sys.stderr)
        try:
            items = scrape_batch(token, batch)
        except requests.RequestException as exc:
            # Broad on purpose: a timeout or dropped connection is just as
            # capable of losing already-paid-for batches as an HTTP error
            # status is, if it's allowed to propagate uncaught past this
            # point -- nothing gets written to disk until scrape() returns.
            print(
                f"warning: batch {batch_num} failed ({exc}); keeping the "
                f"{len(all_items)} items already scraped and stopping here -- "
                f"re-run to pick up the rest (already-scraped shortcodes will "
                f"be skipped, so this costs nothing extra)",
                file=sys.stderr,
            )
            break
        all_items.extend(items)

    return all_items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refs",
        default=DEFAULT_REFS,
        type=Path,
        help=f"post_refs.json from export_parser.py (default: {DEFAULT_REFS})",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="required -- actually spend Apify credit and run the scrape",
    )
    args = parser.parse_args()

    if not args.refs.exists():
        print(f"error: {args.refs} does not exist -- run export_parser.py first", file=sys.stderr)
        raise SystemExit(1)

    refs = json.loads(args.refs.read_text(encoding="utf-8"))
    settings = load_settings()

    print("checking for already-ingested posts...", file=sys.stderr)
    existing = already_ingested_shortcodes(settings)
    todo = [r for r in refs if r["shortcode"] not in existing]

    print(
        f"{len(refs)} posts in {args.refs.name}, {len(existing)} already ingested, "
        f"{len(todo)} to scrape",
        file=sys.stderr,
    )
    if not todo:
        print("nothing to do.", file=sys.stderr)
        return

    estimate = len(todo) / 1000 * COST_PER_1000_USD
    print(
        f"estimated cost: {len(todo)} posts x ${COST_PER_1000_USD}/1000 = ${estimate:.2f}",
        file=sys.stderr,
    )

    if not args.confirm:
        print("re-run with --confirm to actually spend Apify credit and scrape.", file=sys.stderr)
        return

    urls = [r["url"] for r in todo]
    items = scrape(urls, settings.apify_token)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DATA_DIR / f"apify-raw-{ts}.json"
    # Written before anything else touches the response -- the
    # disaster-recovery copy (plan.md §7.2). If Supabase is ever lost,
    # re-ingesting from this file costs nothing further.
    raw_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(items)} raw items to {raw_path}", file=sys.stderr)
    print(f"next: python ingest.py {raw_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
