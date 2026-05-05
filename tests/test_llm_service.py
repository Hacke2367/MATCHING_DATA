"""Tests for engine/llm_service.py (Spec 02b — mock-based, no live API calls)."""
import pytest
from unittest.mock import patch, MagicMock

import google.api_core.exceptions
from google.genai import errors as genai_errors

from engine.llm_service import call_gemini, ExtractionError


# ── Auth failure ───────────────────────────────────────────────────────────────

def test_raises_auth_failure_when_no_api_key(monkeypatch):
    """call_gemini must raise ExtractionError(code='AUTH_FAILURE') when GEMINI_API_KEY is absent."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ExtractionError) as exc_info:
        call_gemini("system", "user", {})

    assert exc_info.value.code == "AUTH_FAILURE"


# ── Markdown fence stripping ───────────────────────────────────────────────────

def test_strips_json_markdown_fences(monkeypatch):
    """call_gemini must strip ```json ... ``` fences before JSON parsing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fenced = '```json\n{"name": "Priya", "age": 35}\n```'

    with patch("engine.llm_service.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = fenced
        MockClient.return_value.models.generate_content.return_value = mock_response

        result = call_gemini("sys", "usr", {})

    assert result == {"name": "Priya", "age": 35}


def test_strips_plain_markdown_fences(monkeypatch):
    """Handles ``` without 'json' language specifier."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fenced = '```\n{"key": "value"}\n```'

    with patch("engine.llm_service.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = fenced
        MockClient.return_value.models.generate_content.return_value = mock_response

        result = call_gemini("sys", "usr", {})

    assert result == {"key": "value"}


# ── Rate-limit retry and exhaustion ───────────────────────────────────────────

def test_rate_limit_exhausted_after_3_retries(monkeypatch):
    """call_gemini must retry exactly 3 times and then raise RATE_LIMIT_EXHAUSTED."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    rate_limit_exc = genai_errors.ClientError(code=429, response_json={"error": "rate limited"})

    with patch("engine.llm_service.genai.Client") as MockClient:
        with patch("time.sleep"):  # suppress actual sleep in tests
            MockClient.return_value.models.generate_content.side_effect = rate_limit_exc

            with pytest.raises(ExtractionError) as exc_info:
                call_gemini("sys", "usr", {})

    assert exc_info.value.code == "RATE_LIMIT_EXHAUSTED"
    assert MockClient.return_value.models.generate_content.call_count == 3


def test_non_rate_limit_client_error_propagates(monkeypatch):
    """Non-429 ClientErrors (e.g. 400 bad request) must propagate immediately without retry."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    bad_request_exc = genai_errors.ClientError(code=400, response_json={"error": "bad request"})

    with patch("engine.llm_service.genai.Client") as MockClient:
        MockClient.return_value.models.generate_content.side_effect = bad_request_exc

        with pytest.raises(genai_errors.ClientError):
            call_gemini("sys", "usr", {})

    # Must not retry — only 1 call
    assert MockClient.return_value.models.generate_content.call_count == 1


# ── JSON parse failure ─────────────────────────────────────────────────────────

def test_json_parse_failure_raises_pre_validation_error(monkeypatch):
    """call_gemini must raise ExtractionError(code='PRE_VALIDATION_PARSE_FAILURE') on invalid JSON."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with patch("engine.llm_service.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = "This is narrative text, not JSON."
        MockClient.return_value.models.generate_content.return_value = mock_response

        with pytest.raises(ExtractionError) as exc_info:
            call_gemini("sys", "usr", {})

    assert exc_info.value.code == "PRE_VALIDATION_PARSE_FAILURE"


# ── Happy path ─────────────────────────────────────────────────────────────────

def test_returns_parsed_dict_on_valid_json(monkeypatch):
    """call_gemini must return a dict when Gemini returns clean JSON."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    payload = {"candidate_id": "X001", "full_name": "Priya Nair", "extraction_confidence": 0.9}

    with patch("engine.llm_service.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = '{"candidate_id": "X001", "full_name": "Priya Nair", "extraction_confidence": 0.9}'
        MockClient.return_value.models.generate_content.return_value = mock_response

        result = call_gemini("sys", "usr", {})

    assert result == payload
