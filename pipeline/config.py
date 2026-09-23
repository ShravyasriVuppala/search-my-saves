"""Environment loading for the pipeline. Every other pipeline module calls
load_settings() once at the top of main(), rather than touching os.environ
directly, so a missing/misnamed var fails immediately with a clear message
instead of surfacing as a confusing error deep in a Gemini or Supabase call."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def _optional(name: str, default: str) -> str:
    # os.environ.get(name, default) only falls back when the key is absent --
    # a present-but-blank .env line (e.g. `SUPABASE_STORAGE_BUCKET=`) would
    # silently win as "", which is never what's intended for a default.
    return os.environ.get(name) or default


def _optional_int(name: str, default: str) -> int:
    raw = os.environ.get(name) or default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a valid integer.") from None


@dataclass(frozen=True)
class Settings:
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_storage_bucket: str

    # Gemini
    gemini_api_key: str
    gemini_analysis_model: str
    gemini_analysis_fallback_model: str
    gemini_embedding_model: str
    gemini_embedding_dim: int

    # Apify
    apify_token: str

    # Worker / media
    worker_rpm: int
    worker_concurrency: int
    worker_daily_cap: int
    worker_max_retries: int
    media_max_frames: int
    media_frame_width: int
    media_frame_height: int
    video_max_mb: int


def load_settings() -> Settings:
    return Settings(
        supabase_url=_require("SUPABASE_URL"),
        supabase_service_role_key=_require("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_storage_bucket=_optional("SUPABASE_STORAGE_BUCKET", "thumbnails"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        gemini_analysis_model=_optional("GEMINI_ANALYSIS_MODEL", "gemini-3.1-flash-lite"),
        gemini_analysis_fallback_model=_optional(
            "GEMINI_ANALYSIS_FALLBACK_MODEL", "gemini-2.5-flash"
        ),
        gemini_embedding_model=_optional("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        gemini_embedding_dim=_optional_int("GEMINI_EMBEDDING_DIM", "768"),
        apify_token=_require("APIFY_TOKEN"),
        worker_rpm=_optional_int("WORKER_RPM", "10"),
        worker_concurrency=_optional_int("WORKER_CONCURRENCY", "5"),
        worker_daily_cap=_optional_int("WORKER_DAILY_CAP", "400"),
        worker_max_retries=_optional_int("WORKER_MAX_RETRIES", "3"),
        media_max_frames=_optional_int("MEDIA_MAX_FRAMES", "12"),
        media_frame_width=_optional_int("MEDIA_FRAME_WIDTH", "480"),
        media_frame_height=_optional_int("MEDIA_FRAME_HEIGHT", "854"),
        video_max_mb=_optional_int("VIDEO_MAX_MB", "25"),
    )
