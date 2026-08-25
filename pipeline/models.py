"""Dataclasses mirroring the Supabase schema (supabase/migrations/0001_schema.sql).
Kept here as the shared shape between pipeline modules -- export_parser produces
PostRef, ingest consumes it into SavedPost, the worker produces AnalysisResult.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PostRef:
    """Output of export_parser.py: one saved post, from the Meta export alone."""

    shortcode: str
    url: str
    saved_at: datetime | None
    export_caption: str
    collection_name: str | None = None  # unconfirmed -- see plan.md §7.1


@dataclass
class SavedPost:
    """Mirrors the saved_posts table. id/timestamps are None until the row
    round-trips through Supabase."""

    instagram_post_id: str
    instagram_url: str
    creator_username: str | None
    caption: str | None
    export_caption: str | None
    alt_text: str | None
    media_type: str | None  # image | video | carousel
    product_type: str | None
    media_url: str | None
    video_url: str | None
    video_duration: float | None
    raw_apify_data: dict
    saved_at: datetime | None = None
    collection_name: str | None = None
    media_storage_path: str | None = None
    id: str | None = None
    processing_status: str = "PENDING"
    processing_error: str | None = None
    retry_count: int = 0


@dataclass
class AnalysisResult:
    """Mirrors content_analysis. Matches schema/analysis_schema.json --
    that file is authoritative for the Gemini-facing shape; keep this in sync
    by hand if it changes."""

    category: str
    title: str
    summary: str
    search_context: str
    keywords: list[str] = field(default_factory=list)
    subcategory: str | None = None
    entities: list[str] = field(default_factory=list)
    ai_metadata: dict = field(default_factory=dict)

    # populated by the worker, not by Gemini
    embedding: list[float] | None = None
    embedding_input: str | None = None
    source_text: str | None = None
    ai_model: str | None = None
    prompt_version: str | None = None
    analysis_input_mode: str | None = None  # frames | image | caption
    frames_analyzed: int | None = None
