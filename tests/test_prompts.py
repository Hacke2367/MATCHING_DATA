"""Structural tests for engine/prompts.py (Spec 02a — no LLM calls)."""
import json
import pytest

from config.schema import SnippetIdentity, CANONICAL_IDENTIFIER_KEYS
from engine.prompts import EXTRACTION_SYSTEM_PROMPT, PROMPT_VERSION, build_extraction_user_message


def test_prompt_version():
    assert PROMPT_VERSION == "1.0.0"


def test_extraction_system_prompt_is_non_empty():
    assert isinstance(EXTRACTION_SYSTEM_PROMPT, str)
    assert len(EXTRACTION_SYSTEM_PROMPT) > 500


def test_all_snippet_identity_required_fields_in_prompt():
    """Every required SnippetIdentity field name must appear in the prompt text."""
    required_fields = [
        name for name, field in SnippetIdentity.model_fields.items()
        if field.is_required()
    ]
    for field_name in required_fields:
        assert field_name in EXTRACTION_SYSTEM_PROMPT, (
            f"Required SnippetIdentity field '{field_name}' not found in EXTRACTION_SYSTEM_PROMPT"
        )


def test_all_canonical_identifier_keys_in_prompt():
    """All 11 canonical identifier key names must appear in the prompt."""
    for key in CANONICAL_IDENTIFIER_KEYS:
        assert key in EXTRACTION_SYSTEM_PROMPT, (
            f"Canonical identifier key '{key}' not found in EXTRACTION_SYSTEM_PROMPT"
        )


def test_all_snippet_flags_in_prompt():
    """All 4 SnippetFlag literals must appear in the prompt."""
    snippet_flags = [
        "NO_REF_DATE", "AGE_INFERRED", "EVENT_DATE_AMBIGUOUS", "NAME_AMBIGUOUS_IN_TEXT"
    ]
    for flag in snippet_flags:
        assert flag in EXTRACTION_SYSTEM_PROMPT, (
            f"SnippetFlag '{flag}' not found in EXTRACTION_SYSTEM_PROMPT"
        )


def test_prompt_forbids_projected_current_age():
    """Prompt must explicitly forbid computing projected_current_age."""
    assert "projected_current_age" in EXTRACTION_SYSTEM_PROMPT


def test_build_extraction_user_message_round_trip():
    """build_extraction_user_message must produce valid JSON that round-trips correctly."""
    anchor = {"full_name": "priya ramesh nair", "gender": "female"}
    snippet = {"snippet_text": "SEBI matter...", "article_date": "2024-03-15"}

    msg = build_extraction_user_message(anchor, snippet)
    parsed = json.loads(msg)

    assert parsed["anchor"] == anchor
    assert parsed["snippet"] == snippet


def test_build_extraction_user_message_is_string():
    msg = build_extraction_user_message({"a": 1}, {"b": 2})
    assert isinstance(msg, str)
