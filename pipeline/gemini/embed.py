"""Gemini embeddings: gemini-embedding-001, L2-normalized (plan.md D1-D3).

Asymmetric task_type -- RETRIEVAL_DOCUMENT when embedding a post,
RETRIEVAL_QUERY when embedding a search query. Both sides MUST use the same
model and output_dimensionality or the vectors aren't comparable; that
invariant is enforced simply by both paths reading settings.gemini_embedding_*
rather than hardcoding anything.
"""

import math

from google.genai import types

from config import Settings
from gemini.client import call_with_retry, get_client


def _normalize(vector: list[float]) -> list[float]:
    """MRL-truncated embeddings from gemini-embedding-001 aren't guaranteed
    unit-length (plan.md D3) -- pgvector's cosine distance assumes they are."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def _embed(settings: Settings, text: str, task_type: str) -> list[float]:
    client = get_client(settings)
    response = call_with_retry(
        client.models.embed_content,
        model=settings.gemini_embedding_model,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.gemini_embedding_dim,
        ),
    )
    return _normalize(response.embeddings[0].values)


def embed_document(settings: Settings, text: str) -> list[float]:
    return _embed(settings, text, "RETRIEVAL_DOCUMENT")


def embed_query(settings: Settings, text: str) -> list[float]:
    return _embed(settings, text, "RETRIEVAL_QUERY")
