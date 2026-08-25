"""Selective reprocessing (plan.md §9.2, D9).

Resets matching posts to PENDING with retry_count=0 and clears
processing_error -- worker.py picks them back up on the next run. Never
touches content_analysis directly; the worker's upsert (on_conflict="post_id")
overwrites the old row when it reprocesses.
"""

import argparse
import sys

from config import load_settings
from db import get_client

FETCH_PAGE_SIZE = 1000
REQUEUE_BATCH_SIZE = 200

# Mirrors the category enum in schema/analysis_schema.json / CLAUDE.md.
VALID_CATEGORIES = {
    "Food",
    "Travel",
    "Fashion",
    "Home",
    "Products",
    "Learning",
    "Entertainment",
    "Ideas",
    "Other",
}


def _fetch_all(query_builder_factory) -> list[dict]:
    """Paginates through .range() -- PostgREST caps rows per request, and a
    library-wide reprocess (e.g. every post on a stale prompt_version) can
    plausibly exceed one page as the library grows past a few thousand posts."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            query_builder_factory().range(offset, offset + FETCH_PAGE_SIZE - 1).execute().data
            or []
        )
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            break
        offset += FETCH_PAGE_SIZE
    return rows


def _requeue(client, post_ids: list[str]) -> int:
    """Chunked so a large reprocess doesn't build one .in_() filter long
    enough to risk a URL-length limit on the underlying REST call."""
    total = 0
    for i in range(0, len(post_ids), REQUEUE_BATCH_SIZE):
        batch = post_ids[i : i + REQUEUE_BATCH_SIZE]
        result = (
            client.table("saved_posts")
            .update({"processing_status": "PENDING", "retry_count": 0, "processing_error": None})
            .in_("id", batch)
            .execute()
        )
        total += len(result.data or [])
    return total


def reprocess_failed(client) -> int:
    rows = _fetch_all(
        lambda: client.table("saved_posts").select("id").eq("processing_status", "FAILED")
    )
    return _requeue(client, [r["id"] for r in rows])


def reprocess_by_category(client, category: str) -> int:
    # category lives on content_analysis, not saved_posts -- this can
    # requeue COMPLETED posts too, for a deliberate full recategorization
    # pass, not just fixing failures.
    rows = _fetch_all(
        lambda: client.table("content_analysis").select("post_id").eq("category", category)
    )
    return _requeue(client, [r["post_id"] for r in rows])


def reprocess_stale_prompt(client, current_version: str) -> int:
    # The actual D9 use case: bump PROMPT_VERSION in gemini/prompt.py, then
    # requeue everything analyzed under an older one.
    rows = _fetch_all(
        lambda: client.table("content_analysis")
        .select("post_id")
        .neq("prompt_version", current_version)
    )
    return _requeue(client, [r["post_id"] for r in rows])


def reprocess_one(client, shortcode: str) -> int:
    rows = (
        client.table("saved_posts").select("id").eq("instagram_post_id", shortcode).execute().data
        or []
    )
    return _requeue(client, [r["id"] for r in rows])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli.py reprocess", description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--failed", action="store_true", help="requeue every FAILED post")
    group.add_argument(
        "--category", metavar="CATEGORY", help="requeue every post currently in this category"
    )
    group.add_argument(
        "--stale-prompt",
        metavar="CURRENT_VERSION",
        help="requeue every analyzed post NOT on this prompt_version",
    )
    group.add_argument(
        "--post-id", metavar="SHORTCODE", help="requeue one post by its Instagram shortcode"
    )
    args = parser.parse_args(argv)

    if args.category and args.category not in VALID_CATEGORIES:
        # A typo'd category (e.g. "food" instead of "Food") would otherwise
        # silently match zero rows with no indication why.
        print(
            f"error: {args.category!r} is not a known category. "
            f"Valid: {', '.join(sorted(VALID_CATEGORIES))}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    settings = load_settings()
    client = get_client(settings)

    if args.failed:
        count = reprocess_failed(client)
    elif args.category:
        count = reprocess_by_category(client, args.category)
    elif args.stale_prompt:
        count = reprocess_stale_prompt(client, args.stale_prompt)
    else:
        count = reprocess_one(client, args.post_id)

    print(f"requeued {count} post(s) as PENDING", file=sys.stderr)


if __name__ == "__main__":
    main()
