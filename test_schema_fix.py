"""Isolated sandbox to debug the Gemini API 400 INVALID_ARGUMENT / additionalProperties error.

WHY PYDANTIC SCHEMAS CLASH WITH GEMINI
---------------------------------------
Pydantic v2's model_json_schema() generates JSON Schema draft-07 / OpenAPI 3.1 output.
Gemini's API accepts only a strict subset of OpenAPI 3.0 Schema Objects. The collisions:

  1. additionalProperties: false  →  added by Pydantic for every model with extra="forbid".
                                     Gemini's schema validator rejects this key entirely.
  2. $defs / $ref               →  Pydantic externalises nested models into $defs and uses
                                     $ref pointers. Gemini requires all schemas to be inlined
                                     (no references).
  3. title                       →  Pydantic adds "title" to every property. Gemini ignores it
                                     but older SDK versions raise on it.
  4. $schema                     →  Draft meta-URI at the root. Not in OpenAPI 3.0.
  5. anyOf: [type, null]         →  Pydantic v2 renders Optional[X] as anyOf:[X, null].
                                     Gemini wants {"type": X, "nullable": true} instead.

Passing the Pydantic class directly to response_schema does NOT help: the google-genai SDK
calls model_json_schema() internally and performs the same validation — raising ValueError
before even hitting the network.

The correct approach: clean the dict ourselves, then pass the clean dict.
"""
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

load_dotenv()

# ── Dummy model (simple, no nesting) ──────────────────────────────────────────

class DummyMatch(BaseModel):
    """Minimal model — proves the schema cleaning works end-to-end."""
    model_config = ConfigDict(extra="forbid")  # this is what adds additionalProperties: false

    name: str
    score: float
    verdict: str


# ── Robust schema cleaner ─────────────────────────────────────────────────────

_STRIP_KEYS = frozenset({"additionalProperties", "title", "$schema", "default", "$defs"})


def clean_gemini_schema(schema: dict) -> dict:
    """Recursively clean a Pydantic JSON schema for Gemini API compatibility.

    Transformations applied:
    - Strips: additionalProperties, title, $schema, default, $defs
    - Inlines: $ref pointers replaced with their full definitions
    - Converts: anyOf: [T, null] → {type: T, nullable: true}  (Optional fields)
    """
    defs = schema.get("$defs", {})

    def _clean(node: object) -> object:
        if not isinstance(node, dict):
            if isinstance(node, list):
                return [_clean(i) for i in node]
            return node

        # Resolve $ref first (before any other processing)
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            resolved = defs.get(ref_name, {})
            return _clean(resolved)

        # Convert Optional[X] pattern: anyOf: [{"type": X}, {"type": "null"}]
        # → {"type": X, "nullable": true}
        if "anyOf" in node and len(node["anyOf"]) == 2:
            parts = node["anyOf"]
            null_part = next((p for p in parts if p.get("type") == "null"), None)
            real_part = next((p for p in parts if p.get("type") != "null"), None)
            if null_part is not None and real_part is not None:
                cleaned_real = _clean(real_part)
                if isinstance(cleaned_real, dict):
                    return {**cleaned_real, "nullable": True}

        # Strip unsupported keys and recurse
        result = {}
        for k, v in node.items():
            if k in _STRIP_KEYS:
                continue
            result[k] = _clean(v)

        return result

    return _clean(schema)  # type: ignore[return-value]


# ── Main test ─────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in environment / .env")
        return

    # Step 1: show raw vs cleaned schema
    raw_schema = DummyMatch.model_json_schema()
    clean_schema = clean_gemini_schema(raw_schema)

    print("=== RAW Pydantic schema ===")
    print(json.dumps(raw_schema, indent=2))
    print()
    print("=== CLEAN schema (Gemini-safe) ===")
    print(json.dumps(clean_schema, indent=2))
    print()

    # Step 2: make a real API call with the clean schema
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=clean_schema,
    )

    print("=== Calling Gemini API ===")
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config=config,
            contents="Return a dummy identity match result. Use name='John Doe', score=0.87, verdict='Review Required'.",
        )
        print("SUCCESS — Raw response text:")
        print(response.text)
        parsed = json.loads(response.text)
        print()
        print("SUCCESS — Parsed as DummyMatch:")
        result = DummyMatch(**parsed)
        print(f"  name    = {result.name!r}")
        print(f"  score   = {result.score}")
        print(f"  verdict = {result.verdict!r}")
        print()
        print("✓ Schema fix is working. The clean_gemini_schema() function resolves the 400 error.")

    except ValueError as exc:
        print(f"SCHEMA VALIDATION ERROR (SDK-side, before API call): {exc}")
        print("The schema still has a field the SDK rejects. Inspect CLEAN schema above.")
    except Exception as exc:
        print(f"API ERROR [{type(exc).__name__}]: {exc}")


if __name__ == "__main__":
    main()
