"""LLM Connectivity Bridge — Gemini 1.5 Flash (google-genai SDK).

Handles connectivity, retry logic, and raw JSON de-serialization.
Upstream callers (extraction.py) never interact with the Gemini SDK directly.

Public interface:
    call_gemini(system_prompt, user_message, response_schema) -> dict
    ExtractionError — raised on all LLM-layer failures
"""
import json
import logging
import os
import re
import time

import google.api_core.exceptions
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class ExtractionError(Exception):
    """Raised by the LLM service layer on connectivity or de-serialization failures.

    Attributes:
        code: Machine-readable error code string.
    """

    def __init__(self, message: str, code: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.code = code


def call_gemini(
    system_prompt: str,
    user_message: str,
    response_schema: dict,
) -> dict:
    """Call Gemini 1.5 Flash with temperature=0 and JSON output enforcement.

    Args:
        system_prompt: The system instruction (from engine/prompts.py).
        user_message: The per-call user turn (JSON string from build_extraction_user_message).
        response_schema: JSON schema dict for Gemini's response_schema parameter.

    Returns:
        Parsed dict from Gemini's response.

    Raises:
        ExtractionError(code="AUTH_FAILURE"):               GEMINI_API_KEY not set.
        ExtractionError(code="RATE_LIMIT_EXHAUSTED"):       429 after 3 retries.
        ExtractionError(code="PRE_VALIDATION_PARSE_FAILURE"): JSON parse failed.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ExtractionError(
            "GEMINI_API_KEY environment variable is not set", code="AUTH_FAILURE"
        )

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=response_schema,
    )

    last_exc: Exception | None = None
    raw_text: str = ""

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                config=config,
                contents=user_message,
            )
            raw_text = response.text
            break
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                last_exc = exc
                sleep_secs = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning(
                    "Gemini rate-limited (attempt %d/%d). Retrying in %ds.",
                    attempt + 1, _MAX_RETRIES, sleep_secs,
                )
                time.sleep(sleep_secs)
            else:
                raise  # non-rate-limit client errors propagate immediately
        except google.api_core.exceptions.ResourceExhausted as exc:
            # Fallback for underlying transport-layer 429
            last_exc = exc
            sleep_secs = 2 ** (attempt + 1)
            logger.warning(
                "Gemini rate-limited via api_core (attempt %d/%d). Retrying in %ds.",
                attempt + 1, _MAX_RETRIES, sleep_secs,
            )
            time.sleep(sleep_secs)
    else:
        raise ExtractionError(
            f"Gemini rate limit exhausted after {_MAX_RETRIES} retries",
            code="RATE_LIMIT_EXHAUSTED",
        ) from last_exc

    # De-serialization guard: strip markdown code fences Gemini sometimes adds
    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"JSON parse failed after markdown-fence strip: {exc}",
            code="PRE_VALIDATION_PARSE_FAILURE",
        ) from exc
