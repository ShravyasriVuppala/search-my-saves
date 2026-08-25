"""Media handling: thumbnail download to Supabase Storage (plan.md §7.4), and
video frame extraction for reel analysis (plan.md §8.5).

Video is never persisted: downloaded to a temp file, frames extracted, temp
file deleted, always -- even on error. Only the thumbnail JPEG is stored
durably, in Supabase Storage.
"""

import io
import sys
import tempfile
from pathlib import Path

import cv2
import requests
from PIL import Image
from supabase import Client

from config import Settings, load_settings
from db import get_client

# Instagram's CDN blocks the default python-requests User-Agent; a plain
# browser UA is enough to get past it (validated against real CDN links).
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT}
_DOWNLOAD_TIMEOUT_S = 60
_THUMBNAIL_MAX_EDGE = 800
_THUMBNAIL_QUALITY = 80


def download_bytes(url: str, timeout: int = _DOWNLOAD_TIMEOUT_S) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, stream=True)
    resp.raise_for_status()
    return resp.content


def make_thumbnail_jpeg(image_bytes: bytes) -> bytes:
    """Downscale to ~800px longest edge, JPEG q80 (plan.md D4)."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((_THUMBNAIL_MAX_EDGE, _THUMBNAIL_MAX_EDGE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_THUMBNAIL_QUALITY)
    return out.getvalue()


def upload_thumbnail(
    client: Client, settings: Settings, instagram_post_id: str, jpeg_bytes: bytes
) -> str:
    path = f"{instagram_post_id}.jpg"
    client.storage.from_(settings.supabase_storage_bucket).upload(
        path,
        jpeg_bytes,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return path


def fetch_thumbnail_for_post(client: Client, settings: Settings, post: dict) -> str | None:
    """Downloads post['media_url'], stores it durably, returns the storage
    path -- or None (logged, not raised) if the URL has already expired or
    the fetch otherwise fails, so one bad post doesn't stop the batch."""
    media_url = post.get("media_url")
    if not media_url:
        return None
    try:
        raw = download_bytes(media_url)
        jpeg = make_thumbnail_jpeg(raw)
        return upload_thumbnail(client, settings, post["instagram_post_id"], jpeg)
    except Exception as exc:  # noqa: BLE001 -- log and continue, never abort the batch
        print(
            f"warning: thumbnail fetch failed for {post['instagram_post_id']}: {exc}",
            file=sys.stderr,
        )
        return None


def extract_video_frames(
    video_bytes: bytes, max_frames: int, width: int, height: int
) -> list[bytes]:
    """Evenly-spaced JPEG frames from a video, resized to width x height.
    Touches disk only via one temp file, always removed in the finally."""
    if max_frames <= 0:
        return []

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = Path(tmp.name)

    try:
        capture = cv2.VideoCapture(str(tmp_path))
        try:
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            # Some containers report 0/garbage for frame count; fall back to
            # reading every frame rather than dividing by a bad value.
            step = max(1, total_frames // max_frames) if total_frames > 0 else 1

            frames: list[bytes] = []
            frame_idx = 0
            while len(frames) < max_frames:
                success, frame = capture.read()
                if not success:
                    break
                if frame_idx % step == 0:
                    resized = cv2.resize(frame, (width, height))
                    ok, encoded = cv2.imencode(".jpg", resized)
                    if ok:
                        frames.append(encoded.tobytes())
                frame_idx += 1
            return frames
        finally:
            capture.release()
    finally:
        tmp_path.unlink(missing_ok=True)


def fetch_all_pending_thumbnails() -> None:
    """Standalone entry point: fetch a thumbnail for every saved_posts row
    that doesn't have one yet. Safe to re-run -- only touches rows where
    media_storage_path is still null."""
    settings = load_settings()
    client = get_client(settings)

    posts = (
        client.table("saved_posts")
        .select("id, instagram_post_id, media_url")
        .is_("media_storage_path", "null")
        .execute()
        .data
        or []
    )
    print(f"{len(posts)} posts missing a thumbnail", file=sys.stderr)

    fetched = 0
    failed = 0
    for post in posts:
        path = fetch_thumbnail_for_post(client, settings, post)
        if path:
            client.table("saved_posts").update({"media_storage_path": path}).eq(
                "id", post["id"]
            ).execute()
            fetched += 1
        else:
            failed += 1

    print(f"fetched {fetched} thumbnails, {failed} failed (see warnings above)", file=sys.stderr)


if __name__ == "__main__":
    fetch_all_pending_thumbnails()
