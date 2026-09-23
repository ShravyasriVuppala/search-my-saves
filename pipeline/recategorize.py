"""Lightweight re-tagging after a category taxonomy change (plan.md D9-style,
but text-only -- see gemini/analyze.py's recategorize_post docstring).

Requeues nothing through the worker: reads directly from content_analysis
and writes back only category/subcategory/ai_metadata/prompt_version. Posts
already PENDING don't need this -- they'll get the new taxonomy automatically
next time worker.py processes them.
"""

import sys
import time

from config import load_settings
from db import get_client
from gemini.analyze import recategorize_post
from gemini.prompt import PROMPT_VERSION

FETCH_PAGE_SIZE = 1000


def _fetch_stale(client) -> list[dict]:
    """Every content_analysis row not yet on the current PROMPT_VERSION --
    same staleness definition reprocess.py's --stale-prompt uses, paginated
    for the same reason (plan.md: a library-wide pass can exceed one page)."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            client.table("content_analysis")
            .select("post_id, title, summary, search_context, keywords")
            .neq("prompt_version", PROMPT_VERSION)
            .range(offset, offset + FETCH_PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            break
        offset += FETCH_PAGE_SIZE
    return rows


def run() -> None:
    settings = load_settings()
    client = get_client(settings)
    min_interval_s = 60.0 / settings.worker_rpm

    rows = _fetch_stale(client)
    print(f"{len(rows)} posts on a stale prompt_version", file=sys.stderr)

    done = 0
    failed = 0
    for row in rows:
        start = time.monotonic()
        try:
            result = recategorize_post(
                settings,
                title=row.get("title") or "",
                summary=row.get("summary") or "",
                search_context=row.get("search_context") or "",
                keywords=row.get("keywords") or [],
            )
            client.table("content_analysis").update(
                {
                    "category": result["category"],
                    "subcategory": result["subcategory"],
                    "ai_metadata": result["ai_metadata"],
                    "prompt_version": PROMPT_VERSION,
                }
            ).eq("post_id", row["post_id"]).execute()
            done += 1
        except Exception as exc:  # noqa: BLE001 -- one bad post must not kill the run
            failed += 1
            print(f"failed: {row['post_id']}: {exc}", file=sys.stderr)
            # Left on its old prompt_version -- naturally eligible for the
            # next run of this same script, no separate retry bookkeeping.

        elapsed_s = time.monotonic() - start
        if elapsed_s < min_interval_s:
            time.sleep(min_interval_s - elapsed_s)

    print(f"recategorized {done} ({failed} failed)", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    if argv:
        print("recategorize takes no arguments", file=sys.stderr)
        raise SystemExit(2)
    run()


if __name__ == "__main__":
    main()
