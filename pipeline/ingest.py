"""Apify raw items + PostRef data -> normalized saved_posts rows (plan.md §7.3).

Never overwrites an existing row (CLAUDE.md principle 4): upserts with
ignore_duplicates=True keyed on instagram_post_id, so a post already
PENDING/PROCESSING/COMPLETED/FAILED is left completely untouched by
re-running this against the same or overlapping raw data.
"""

import argparse
import json
import sys
from pathlib import Path

from config import load_settings
from db import get_client

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFS = REPO_ROOT / "data" / "post_refs.json"

MEDIA_TYPE_MAP = {"Image": "image", "Video": "video", "Sidecar": "carousel"}


def _media_url(item: dict) -> str | None:
    if item.get("displayUrl"):
        return item["displayUrl"]
    child_posts = item.get("childPosts") or []
    if child_posts:
        return child_posts[0].get("displayUrl")
    return None


def normalize(item: dict, ref: dict | None) -> dict:
    ref = ref or {}
    return {
        "instagram_post_id": item["shortCode"],
        "instagram_url": item.get("url") or ref.get("url"),
        "creator_username": item.get("ownerUsername"),
        # Apify's caption first; the export's caption is the fallback so a
        # post is never left with no text at all if Apify comes back empty.
        "caption": item.get("caption") or ref.get("export_caption"),
        "export_caption": ref.get("export_caption"),
        "alt_text": item.get("alt"),
        "media_type": MEDIA_TYPE_MAP.get(item.get("type"), item.get("type")),
        "product_type": item.get("productType"),
        "media_url": _media_url(item),
        "video_url": item.get("videoUrl"),
        "video_duration": item.get("videoDuration"),
        "posted_at": item.get("timestamp"),
        "saved_at": ref.get("saved_at"),
        "collection_name": ref.get("collection_name"),
        "raw_apify_data": item,
    }


def ingest(raw_items: list[dict], refs_by_shortcode: dict[str, dict]) -> tuple[int, int]:
    settings = load_settings()
    client = get_client(settings)

    rows = []
    for item in raw_items:
        shortcode = item.get("shortCode")
        if not shortcode:
            print(f"warning: skipping item with no shortCode: {item.get('url')}", file=sys.stderr)
            continue
        rows.append(normalize(item, refs_by_shortcode.get(shortcode)))

    if not rows:
        return 0, 0

    # ON CONFLICT DO NOTHING under the hood -- RETURNING only reports rows
    # that were actually inserted, so len(result.data) is the true insert
    # count, not the request size.
    result = (
        client.table("saved_posts")
        .upsert(rows, on_conflict="instagram_post_id", ignore_duplicates=True)
        .execute()
    )
    inserted = len(result.data or [])
    skipped = len(rows) - inserted
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="path to an apify-raw-<ts>.json file from apify_client.py")
    parser.add_argument(
        "--refs",
        default=DEFAULT_REFS,
        type=Path,
        help=f"post_refs.json from export_parser.py, for saved_at/export_caption (default: {DEFAULT_REFS})",
    )
    args = parser.parse_args()

    if not args.raw.exists():
        print(f"error: {args.raw} does not exist", file=sys.stderr)
        raise SystemExit(1)

    raw_items = json.loads(args.raw.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        print(
            f"error: {args.raw} is not a JSON list at the top level -- "
            "Apify's response format may have changed",
            file=sys.stderr,
        )
        raise SystemExit(1)

    refs_by_shortcode: dict[str, dict] = {}
    if args.refs.exists():
        for ref in json.loads(args.refs.read_text(encoding="utf-8")):
            refs_by_shortcode[ref["shortcode"]] = ref
    else:
        print(f"warning: {args.refs} not found -- saved_at/export_caption will be null", file=sys.stderr)

    inserted, skipped = ingest(raw_items, refs_by_shortcode)
    print(f"{inserted} new, {skipped} skipped as duplicates", file=sys.stderr)


if __name__ == "__main__":
    main()
