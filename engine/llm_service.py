"""LLM Connectivity Bridge — Gemini 1.5 Flash (google-genai SDK).

Handles connectivity, retry logic, and raw JSON de-serialization.
Upstream callers (extraction.py, reasoning.py) never interact with the SDK directly.

Public interface:
    call_gemini(system_prompt, user_message, response_schema) -> dict
    ExtractionError — raised on all LLM-layer failures

API version note:
    responseMimeType and responseSchema live in v1beta's generation_config.
    They do NOT exist in the stable v1 API — always use v1beta for structured output.
"""
import json
import logging
import os
import re
import time
from typing import Type

import google.api_core.exceptions
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_STRIP_KEYS = frozenset({"additionalProperties", "title", "$schema", "default", "$defs"})


def _clean_schema(schema: dict) -> dict:
    """Convert a Pydantic JSON schema dict into a Gemini-compatible schema.

    Gemini accepts a restricted OpenAPI 3.0 subset. Pydantic v2 emits several
    keys that the v1beta API rejects. This function:
      - Strips:   additionalProperties, title, $schema, default, $defs
      - Inlines:  $ref pointers using the $defs definitions
      - Converts: anyOf:[T, null]  →  {type: T, nullable: true}  (Optional fields)
    """
    defs = schema.get("$defs", {})

    def _walk(node: object) -> object:
        if not isinstance(node, dict):
            return [_walk(i) for i in node] if isinstance(node, list) else node

        # Resolve $ref inline
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            return _walk(defs.get(ref_name, {}))

        # Convert Optional[X] pattern: anyOf:[{type:X}, {type:null}] → nullable
        if "anyOf" in node and len(node["anyOf"]) == 2:
            null_part = next((p for p in node["anyOf"] if p.get("type") == "null"), None)
            real_part = next((p for p in node["anyOf"] if p.get("type") != "null"), None)
            if null_part is not None and real_part is not None:
                cleaned = _walk(real_part)
                if isinstance(cleaned, dict):
                    return {**cleaned, "nullable": True}

        return {k: _walk(v) for k, v in node.items() if k not in _STRIP_KEYS}

    return _walk(schema)  # type: ignore[return-value]


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
    response_schema: Type[BaseModel],
) -> dict:
    """Call Gemini 1.5 Flash (v1beta) with temperature=0 and JSON output enforcement.

    Args:
        system_prompt:   The system instruction (from engine/prompts.py).
        user_message:    The per-call user turn as a JSON string.
        response_schema: A Pydantic BaseModel *class*. Its schema is cleaned
                         internally before being sent to the API.

    Returns:
        Parsed dict from Gemini's response.

    Raises:
        ExtractionError(code="AUTH_FAILURE"):                GEMINI_API_KEY not set.
        ExtractionError(code="RATE_LIMIT_EXHAUSTED"):        429 after 3 retries.
        ExtractionError(code="PRE_VALIDATION_PARSE_FAILURE"): JSON parse failed.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ExtractionError(
            "GEMINI_API_KEY environment variable is not set", code="AUTH_FAILURE"
        )

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=_clean_schema(response_schema.model_json_schema()),
    )

    last_exc: Exception | None = None
    raw_text: str = ""

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
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
