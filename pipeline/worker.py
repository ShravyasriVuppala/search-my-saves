"""AI processing worker: PENDING -> COMPLETED/FAILED (plan.md §8).

Never touches an already-COMPLETED post (CLAUDE.md principle 4). Safe to
kill and restart: rows stuck in PROCESSING for >30 minutes are reclaimed as
PENDING at startup, and a 429/503 from Gemini does not count against a
post's retry_count -- that's a quota problem, not the post's fault
(plan.md §8.1).
"""

import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import Settings, load_settings
from db import get_client
from gemini.analyze import analyze_post
from gemini.client import RETRYABLE_STATUS_CODES
from gemini.embed import embed_document
from media import download_bytes, extract_video_frames

# Same non-post-fault reasoning as 429/503 (plan.md §8.1) applies to a
# network error that survived call_with_retry's own backoff -- a timeout or
# dropped connection to Gemini isn't this post's fault either.
_TRANSIENT_NETWORK_ERRORS = (httpx.TimeoutException, httpx.ConnectError)

STUCK_PROCESSING_MINUTES = 30
VIDEO_DOWNLOAD_TIMEOUT_S = 120
CLAIM_BATCH_SIZE = 10


def reclaim_stuck_posts(client) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STUCK_PROCESSING_MINUTES)).isoformat()
    result = (
        client.table("saved_posts")
        .update({"processing_status": "PENDING"})
        .eq("processing_status", "PROCESSING")
        .lt("updated_at", cutoff)
        .execute()
    )
    return len(result.data or [])


def claim_batch(client, settings: Settings, limit: int) -> list[dict]:
    posts = (
        client.table("saved_posts")
        .select("*")
        .eq("processing_status", "PENDING")
        .lt("retry_count", settings.worker_max_retries)
        .order("saved_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    if not posts:
        return []
    ids = [p["id"] for p in posts]
    client.table("saved_posts").update({"processing_status": "PROCESSING"}).in_("id", ids).execute()
    return posts


def resolve_media(client, settings: Settings, post: dict) -> tuple[list[bytes] | None, bytes | None]:
    """Media ladder (plan.md §8.5), always attempted regardless of caption
    length -- a reel's cover frame is often a talking head or title card
    while the real content is on-screen text or narration. Returns
    (frame_jpegs, thumbnail_jpeg); at most one is non-None."""
    if post.get("media_type") == "video" and post.get("video_url"):
        try:
            video_bytes = download_bytes(post["video_url"], timeout=VIDEO_DOWNLOAD_TIMEOUT_S)
            size_mb = len(video_bytes) / (1024 * 1024)
            if size_mb <= settings.video_max_mb:
                frames = extract_video_frames(
                    video_bytes,
                    settings.media_max_frames,
                    settings.media_frame_width,
                    settings.media_frame_height,
                )
                if frames:
                    return frames, None
            else:
                print(
                    f"video for {post['instagram_post_id']} is {size_mb:.1f}MB, "
                    f"over the {settings.video_max_mb}MB cap -- falling back to thumbnail",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001 -- fall through to the next rung
            print(
                f"warning: video fetch/extract failed for {post['instagram_post_id']}: {exc}",
                file=sys.stderr,
            )

    if post.get("media_storage_path"):
        try:
            thumb = client.storage.from_(settings.supabase_storage_bucket).download(
                post["media_storage_path"]
            )
            return None, thumb
        except Exception as exc:  # noqa: BLE001 -- fall through to caption-only
            print(
                f"warning: thumbnail download from storage failed for "
                f"{post['instagram_post_id']}: {exc}",
                file=sys.stderr,
            )

    return None, None


def build_embedding_input(result) -> str:
    parts = [
        result.title,
        result.summary,
        result.search_context,
        ", ".join(result.keywords),
        ", ".join(result.entities),
    ]
    return "\n".join(p for p in parts if p)


def process_post(client, settings: Settings, post: dict) -> None:
    frames, thumbnail = resolve_media(client, settings, post)

    result = analyze_post(
        settings,
        caption=post.get("caption") or "",
        frame_jpegs=frames,
        thumbnail_jpeg=thumbnail,
    )

    result.source_text = " ".join(filter(None, [post.get("caption"), post.get("creator_username")]))
    result.embedding_input = build_embedding_input(result)
    result.embedding = embed_document(settings, result.embedding_input)

    client.table("content_analysis").upsert(
        {
            # post_id is the PK; explicit on_conflict removes any ambiguity
            # about what upsert() targets on the first-ever insert for this
            # post vs. a later reprocess overwriting it.
            "post_id": post["id"],
            "category": result.category,
            "subcategory": result.subcategory,
            "title": result.title,
            "summary": result.summary,
            "search_context": result.search_context,
            "keywords": result.keywords,
            "entities": result.entities,
            "ai_metadata": result.ai_metadata,
            "embedding": result.embedding,
            "embedding_input": result.embedding_input,
            "source_text": result.source_text,
            "ai_model": result.ai_model,
            "prompt_version": result.prompt_version,
            "analysis_input_mode": result.analysis_input_mode,
            "frames_analyzed": result.frames_analyzed,
        },
        on_conflict="post_id",
    ).execute()

    client.table("saved_posts").update(
        {"processing_status": "COMPLETED", "processing_error": None}
    ).eq("id", post["id"]).execute()


def _is_quota_error(exc: Exception) -> bool:
    return getattr(exc, "code", None) in RETRYABLE_STATUS_CODES or isinstance(
        exc, _TRANSIENT_NETWORK_ERRORS
    )


def mark_failed(client, post: dict, error: str, count_against_retry: bool) -> None:
    if count_against_retry:
        update = {
            "processing_status": "FAILED",
            "processing_error": error[:2000],
            "retry_count": post.get("retry_count", 0) + 1,
        }
    else:
        # Quota/capacity error, already retried with backoff inside
        # call_with_retry and still failing -- not this post's fault, so it
        # goes back to PENDING and stays eligible for the very next claim
        # rather than burning a retry (plan.md §8.1).
        update = {"processing_status": "PENDING", "processing_error": error[:2000]}
    client.table("saved_posts").update(update).eq("id", post["id"]).execute()


def run(daily_cap: int | None = None) -> None:
    settings = load_settings()
    client = get_client(settings)

    reclaimed = reclaim_stuck_posts(client)
    if reclaimed:
        print(f"reclaimed {reclaimed} posts stuck in PROCESSING", file=sys.stderr)

    cap = daily_cap if daily_cap is not None else settings.worker_daily_cap
    min_interval_s = 60.0 / settings.worker_rpm

    processed = 0
    completed = 0
    failed = 0
    stopped_early = False

    while processed < cap and not stopped_early:
        batch = claim_batch(client, settings, limit=min(CLAIM_BATCH_SIZE, cap - processed))
        if not batch:
            break

        for post in batch:
            if processed >= cap:
                break
            start = time.monotonic()

            try:
                process_post(client, settings, post)
                completed += 1
            except Exception as exc:  # noqa: BLE001 -- one bad post must not kill the run
                quota_error = _is_quota_error(exc)
                mark_failed(client, post, str(exc), count_against_retry=not quota_error)
                failed += 1
                print(
                    f"{'quota-limited' if quota_error else 'failed'}: "
                    f"{post['instagram_post_id']}: {exc}",
                    file=sys.stderr,
                )
                if quota_error:
                    # 429/5xx surviving call_with_retry's own backoff means
                    # Gemini is globally limited right now, not just for this
                    # post -- every remaining post would fail the same way.
                    # Stop instead of burning through the rest one by one;
                    # they're all still PENDING and pick back up next run.
                    stopped_early = True

            processed += 1
            elapsed_s = time.monotonic() - start
            if elapsed_s < min_interval_s:
                time.sleep(min_interval_s - elapsed_s)

            if stopped_early:
                break

    if stopped_early:
        print(
            "stopping early: Gemini appears quota/capacity limited -- re-run later to pick up the rest",
            file=sys.stderr,
        )
    print(f"processed {processed} ({completed} completed, {failed} failed)", file=sys.stderr)


if __name__ == "__main__":
    run()
