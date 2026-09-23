"""Gemini multimodal analysis call (plan.md §8.2-8.4)."""

import json

from google.genai import types

from config import Settings
from gemini.client import call_with_retry, get_client
from gemini.prompt import (
    ANALYSIS_PROMPT,
    GEMINI_RESPONSE_SCHEMA,
    PROMPT_VERSION,
    RECATEGORIZE_PROMPT,
    RECATEGORIZE_RESPONSE_SCHEMA,
)
from models import AnalysisResult


class EmptyResponseError(RuntimeError):
    """Gemini returned no candidates at all, most often a safety filter
    block. Distinct from other failures because it is frequently caused by
    the attached media rather than the post itself, which makes retrying
    without media (caption-only) a worthwhile recovery -- see worker.py's
    process_post. A dedicated type keeps that caller from having to
    string-match an error message."""


def _parse_ai_metadata(raw_value: str | None) -> dict:
    """ai_metadata comes back as a JSON-encoded string, not a nested object
    (see the comment on GEMINI_RESPONSE_SCHEMA for why). A malformed or
    non-object value degrades to {} rather than failing the whole post --
    it's the least important field here."""
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def analyze_post(
    settings: Settings,
    caption: str,
    frame_jpegs: list[bytes] | None = None,
    thumbnail_jpeg: bytes | None = None,
) -> AnalysisResult:
    """Exactly one of frame_jpegs/thumbnail_jpeg should be set (or neither,
    for caption-only) -- see media.py and worker.py's media ladder
    (plan.md §8.5). Returns a partially-filled AnalysisResult: embedding,
    embedding_input, and source_text are the worker's job to fill in
    afterward, since they depend on the embedding step and on bookkeeping
    the worker itself owns."""
    client = get_client(settings)

    contents: list = []
    if frame_jpegs:
        contents.extend(types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in frame_jpegs)
        input_mode = "frames"
    elif thumbnail_jpeg:
        contents.append(types.Part.from_bytes(data=thumbnail_jpeg, mime_type="image/jpeg"))
        input_mode = "image"
    else:
        input_mode = "caption"

    contents.append(f"{ANALYSIS_PROMPT}\nInstagram caption:\n{caption or '(no caption)'}")

    response = call_with_retry(
        client.models.generate_content,
        model=settings.gemini_analysis_model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GEMINI_RESPONSE_SCHEMA,
            temperature=0.2,
        ),
    )

    if response.text is None:
        # Happens when there are no candidates at all, most commonly a
        # safety filter block -- rare for ordinary food/travel/fashion
        # photos, but not impossible, and json.loads(None) would otherwise
        # surface as an opaque TypeError instead of saying what happened.
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise EmptyResponseError(f"Gemini returned no content (finish_reason={finish_reason})")

    raw = json.loads(response.text)

    return AnalysisResult(
        category=raw["category"],
        title=raw["title"],
        summary=raw["summary"],
        search_context=raw["search_context"],
        keywords=raw.get("keywords") or [],
        subcategory=raw.get("subcategory") or None,
        entities=raw.get("entities") or [],
        ai_metadata=_parse_ai_metadata(raw.get("ai_metadata")),
        ai_model=settings.gemini_analysis_model,
        prompt_version=PROMPT_VERSION,
        analysis_input_mode=input_mode,
        frames_analyzed=len(frame_jpegs) if frame_jpegs else None,
    )


def recategorize_post(
    settings: Settings,
    title: str,
    summary: str,
    search_context: str,
    keywords: list[str],
) -> dict:
    """Text-only re-tagging against a changed category taxonomy -- no media,
    no embedding call. See RECATEGORIZE_PROMPT's docstring in prompt.py for
    why this is safe to do from the existing text alone. Returns a plain
    dict {category, subcategory, ai_metadata}, not an AnalysisResult -- the
    caller (recategorize.py) only ever overwrites those three columns."""
    client = get_client(settings)

    prompt = RECATEGORIZE_PROMPT.format(
        title=title,
        summary=summary,
        search_context=search_context,
        keywords=", ".join(keywords),
    )

    response = call_with_retry(
        client.models.generate_content,
        model=settings.gemini_analysis_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RECATEGORIZE_RESPONSE_SCHEMA,
            temperature=0.2,
        ),
    )

    if response.text is None:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise EmptyResponseError(f"Gemini returned no content (finish_reason={finish_reason})")

    raw = json.loads(response.text)
    return {
        "category": raw["category"],
        "subcategory": raw.get("subcategory") or None,
        "ai_metadata": _parse_ai_metadata(raw.get("ai_metadata")),
    }
