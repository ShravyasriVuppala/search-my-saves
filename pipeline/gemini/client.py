"""Gemini API client + shared retry helper (plan.md §8)."""

import random
import time

from google import genai
from google.genai import errors

from config import Settings

# 429 = quota/rate-limit, 5xx = transient capacity issues. Both are the
# API's fault, not whatever post is being processed -- worker.py relies on
# this distinction to decide whether a failure should burn a post's
# retry_count (plan.md §8.1).
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5
_BASE_DELAY_S = 2.0


def get_client(settings: Settings) -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def call_with_retry(fn, *args, **kwargs):
    """Exponential backoff + jitter on 429/5xx. Any other error, or a
    retryable one that's still failing after _MAX_ATTEMPTS, is re-raised for
    the caller to handle."""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except errors.APIError as exc:
            is_last_attempt = attempt == _MAX_ATTEMPTS - 1
            if exc.code not in RETRYABLE_STATUS_CODES or is_last_attempt:
                raise
            delay = _BASE_DELAY_S * (2**attempt) + random.uniform(0, 1)
            time.sleep(delay)
    raise AssertionError("unreachable: loop above always returns or raises")
