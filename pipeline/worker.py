"""AI processing worker: PENDING -> COMPLETED/FAILED (plan.md §8).

Never touches an already-COMPLETED post (CLAUDE.md principle 4). Safe to
kill and restart: rows stuck in PROCESSING for >30 minutes are reclaimed as
PENDING at startup, and a 429/503 from Gemini does not count against a
post's retry_count -- that's a quota problem, not the post's fault
(plan.md §8.1).
"""

import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import Settings, load_settings
from db import get_client
from gemini.analyze import EmptyResponseError, analyze_post
from gemini.client import RETRYABLE_STATUS_CODES
from gemini.embed import embed_document
from media import download_bytes, extract_video_frames

# Same non-post-fault reasoning as 429/503 (plan.md §8.1) applies to a
# network error that survived call_with_retry's own backoff -- a timeout or
# dropped connection to Gemini isn't this post's fault either.
_TRANSIENT_NETWORK_ERRORS = (httpx.TimeoutException, httpx.ConnectError)

STUCK_PROCESSING_MINUTES = 30
VIDEO_DOWNLOAD_TIMEOUT_S = 120
CONSECUTIVE_QUOTA_ERROR_LIMIT = 3
# Claim race handling: pull a few candidates so N threads racing for work
# usually each win a different row on the first pass instead of serializing.
CLAIM_CANDIDATE_POOL = 10
CLAIM_RACE_ATTEMPTS = 3
CLAIM_ERROR_PAUSE_S = 5


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


def claim_one(client, settings: Settings) -> dict | None:
    """Claims a single post, not a batch -- so a post is never marked
    PROCESSING without being processed next by the same caller. Removes the
    "claimed but never attempted" state entirely instead of needing to
    recover from it (previously handled by releasing unprocessed batch
    members on a quota stop, and before that by the 30-minute
    stuck-PROCESSING reclaim).

    The claim is a compare-and-swap, not a plain update: the PENDING filter
    is repeated on the UPDATE so that when several worker threads race for
    the same row, exactly one of them gets a non-empty result back and the
    losers retry against the next candidate. A plain
    `.update().eq("id", ...)` would let every racing thread believe it had
    claimed the same post and process it N times."""
    for _ in range(CLAIM_RACE_ATTEMPTS):
        candidates = (
            client.table("saved_posts")
            .select("id")
            .eq("processing_status", "PENDING")
            .lt("retry_count", settings.worker_max_retries)
            .order("saved_at", desc=True)
            .limit(CLAIM_CANDIDATE_POOL)
            .execute()
            .data
            or []
        )
        if not candidates:
            return None

        for candidate in candidates:
            claimed = (
                client.table("saved_posts")
                .update({"processing_status": "PROCESSING"})
                .eq("id", candidate["id"])
                .eq("processing_status", "PENDING")
                .execute()
                .data
                or []
            )
            if claimed:
                return claimed[0]
    return None


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
    caption = post.get("caption") or ""

    try:
        result = analyze_post(
            settings,
            caption=caption,
            frame_jpegs=frames,
            thumbnail_jpeg=thumbnail,
        )
    except EmptyResponseError:
        # An empty response is usually a safety filter, and the media is the
        # likelier trigger -- so drop it and try the caption alone rather
        # than losing the post outright. resolve_media's ladder only falls
        # back when media can't be *fetched*; this covers media that was
        # fetched fine but made the analysis itself come back empty.
        # Degraded but recoverable: analysis_input_mode records "caption",
        # so these rows stay identifiable for a later reprocess.
        if frames is None and thumbnail is None:
            raise  # already caption-only, nothing left to drop
        print(
            f"empty response with media for {post['instagram_post_id']} -- "
            "retrying caption-only",
            file=sys.stderr,
        )
        result = analyze_post(settings, caption=caption)

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


class _Pacer:
    """Shared across worker threads so combined dispatch rate still honours
    WORKER_RPM. Without this, N threads would each pace themselves and the
    real rate would be N x the configured limit.

    Paces *posts*, not raw API calls: each post makes one analysis call plus
    one embedding call, and those hit two different models with separate
    quotas, so WORKER_RPM should be read as posts-per-minute rather than
    Gemini-requests-per-minute."""

    def __init__(self, min_interval_s: float) -> None:
        self._min_interval_s = min_interval_s
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait_for_slot(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval_s
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def run(daily_cap: int | None = None) -> None:
    settings = load_settings()

    reclaimed = reclaim_stuck_posts(get_client(settings))
    if reclaimed:
        print(f"reclaimed {reclaimed} posts stuck in PROCESSING", file=sys.stderr)

    cap = daily_cap if daily_cap is not None else settings.worker_daily_cap
    concurrency = max(1, settings.worker_concurrency)
    pacer = _Pacer(60.0 / settings.worker_rpm)

    state_lock = threading.Lock()
    state = {"processed": 0, "completed": 0, "failed": 0, "consecutive_quota_errors": 0}
    stop = threading.Event()

    def worker_loop() -> None:
        # Each thread gets its own Supabase client -- supabase-py wraps an
        # httpx session that isn't documented as thread-safe, and sharing
        # one across threads is the kind of bug that shows up as rare,
        # unreproducible request corruption rather than a clean failure.
        client = get_client(settings)

        while not stop.is_set():
            # Reserve the cap slot *before* claiming. Checking and then
            # incrementing after the work would let all N threads pass the
            # check before any of them increments, overshooting the cap by
            # up to N-1 posts -- and the cap exists to bound daily API
            # spend, so it needs to hold exactly.
            with state_lock:
                if state["processed"] >= cap:
                    return
                state["processed"] += 1

            post = None
            claim_failed = False
            try:
                post = claim_one(client, settings)
            except Exception as exc:  # noqa: BLE001 -- see below
                # A transient Supabase error while claiming must not kill
                # this thread for the rest of the run: with several threads
                # that would silently shrink the pool one blip at a time
                # until the run ends early looking like "no work left".
                claim_failed = True
                print(f"claim failed: {exc}", file=sys.stderr)

            if post is None:
                with state_lock:
                    state["processed"] -= 1  # slot went unused
                if claim_failed and not stop.is_set():
                    time.sleep(CLAIM_ERROR_PAUSE_S)
                    continue
                return  # genuinely nothing left to claim

            pacer.wait_for_slot()

            try:
                process_post(client, settings, post)
                with state_lock:
                    state["completed"] += 1
                    state["consecutive_quota_errors"] = 0
            except Exception as exc:  # noqa: BLE001 -- one bad post must not kill the run
                quota_error = _is_quota_error(exc)
                mark_failed(client, post, str(exc), count_against_retry=not quota_error)
                print(
                    f"{'quota-limited' if quota_error else 'failed'}: "
                    f"{post['instagram_post_id']}: {exc}",
                    file=sys.stderr,
                )
                with state_lock:
                    state["failed"] += 1
                    if quota_error:
                        # A single 429/5xx surviving call_with_retry's own
                        # backoff doesn't mean Gemini is down for every post
                        # -- observed in practice, capacity is spotty
                        # (several succeed, then one fails) rather than out.
                        # Only bail after several in a row, which is a much
                        # stronger signal of a real, sustained outage.
                        state["consecutive_quota_errors"] += 1
                        if state["consecutive_quota_errors"] >= CONSECUTIVE_QUOTA_ERROR_LIMIT:
                            stop.set()
                    else:
                        state["consecutive_quota_errors"] = 0

    threads = [threading.Thread(target=worker_loop, daemon=True) for _ in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if stop.is_set():
        print(
            f"stopping early: {CONSECUTIVE_QUOTA_ERROR_LIMIT} consecutive quota/capacity "
            "errors -- re-run later to pick up the rest",
            file=sys.stderr,
        )
    print(
        f"processed {state['processed']} "
        f"({state['completed']} completed, {state['failed']} failed)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    run()
