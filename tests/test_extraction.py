"""Acceptance criteria tests for engine/extraction.py (Spec 02c §5 — mock-based)."""
import datetime
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from engine.extraction import extract_user, extract_candidate

DATA_ROOT = Path(__file__).parent.parent / "data"

# ── Shared valid snippet dict (returned by mock call_gemini) ───────────────────
_VALID_SNIPPET = {
    "candidate_id": "SYNTH001PRIYA001",
    "snippet_text": (
        "SEBI issued a notice to Priya Ramesh Nair, 35, "
        "investment banker, Bandra West, Mumbai, Maharashtra."
    ),
    "snippet_url": "https://example.com/article1",
    "snippet_title": "SEBI Notice",
    "full_name": "Priya Ramesh Nair",
    "aliases": [],
    "gender": "female",
    "article_date": "2024-03-15",
    "event_date": None,
    "age_at_event": 35,
    "locations": [
        {
            "sub_district": "Bandra West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "country_code": "IN",
            "raw": "Bandra West, Mumbai, Maharashtra",
        }
    ],
    "identifiers_in_text": {"PAN": "ABCPN1234R"},
    "profession_raw": "investment banker",
    "identity_summary": "SEBI regulatory action; Mumbai investment banker, PAN ABCPN1234R, age 35.",
    "flags": ["EVENT_DATE_AMBIGUOUS"],
    "extraction_confidence": 0.92,
}

_CANDIDATE_PATH = str(DATA_ROOT / "potential_matches" / "boss.json")
_USER_PATH = str(DATA_ROOT / "actual_user" / "boss.json")


# ── §5.1 Surgical Extraction Test ─────────────────────────────────────────────

def test_snippet_indices_filter_llm_input():
    """With snippet_indices=[0, 2] on a 2-item media[], only index 0 is sent to LLM.

    test_scenario_1 has exactly 2 media items (indices 0 and 1).
    Index 2 is out of bounds → bounds check drops it → only index 0 is processed.
    """
    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=_VALID_SNIPPET) as mock_call:
        result = extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0, 2])

    assert mock_call.call_count == 1, (
        f"Expected 1 LLM call (index 0 only), got {mock_call.call_count}"
    )
    assert result is not None


def test_snippet_index_1_not_processed_when_only_0_requested():
    """When snippet_indices=[0], snippet at index 1 must never be sent to LLM."""
    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=_VALID_SNIPPET) as mock_call:
        extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0])

    assert mock_call.call_count == 1
    # Verify the call used the correct snippet text (from index 0)
    call_user_msg = mock_call.call_args[0][1]  # positional arg: user_message
    parsed = json.loads(call_user_msg)
    assert parsed["snippet"]["candidate_id"] == "SYNTH001PRIYA001"


# ── §5.2 Schema Consistency Test ──────────────────────────────────────────────

def test_sub_district_propagates_to_candidate_identity():
    """sub_district from the LLM extraction must appear in CandidateIdentity.locations."""
    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=_VALID_SNIPPET):
        result = extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0])

    assert result is not None
    assert result.locations[0].sub_district == "Bandra West"


def test_identity_summary_within_200_chars():
    """identity_summary in the resulting CandidateIdentity must be ≤200 characters."""
    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=_VALID_SNIPPET):
        result = extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0])

    assert result is not None
    assert len(result.identity_summary) <= 200
    assert result.identity_summary  # non-empty


# ── §5.3 Future-Date Gate ─────────────────────────────────────────────────────

def test_future_article_date_discards_snippet_returns_none():
    """A LLM response with a future article_date must fail Pydantic validation.
    When the only snippet is discarded, extract_candidate must return None.
    """
    future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    future_snippet = {**_VALID_SNIPPET, "article_date": future_date}

    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=future_snippet):
        result = extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0])

    assert result is None


# ── §5.4 extract_user round-trip (Priya Ramesh Nair) ─────────────────────────

def test_extract_user_full_mapping():
    """extract_user must correctly map test_scenario_1 KYC JSON to CandidateIdentity."""
    result = extract_user(_USER_PATH)

    assert result.source == "user"
    assert result.record_id == "OLPIN10100010101"
    assert result.full_name == "priya ramesh nair"
    assert result.gender == "female"
    assert result.dob_exact == datetime.date(1988, 7, 15)
    assert result.identifiers.get("PAN") == "ABCPN1234R"
    assert result.locations[0].city == "Mumbai"
    assert result.locations[0].state == "Maharashtra"
    assert result.locations[0].country_code == "IN"
    assert result.nationality_country == "India"
    assert result.residency_country == "India"
    assert result.profession_raw == "Finance - Investment Banking"
    assert len(result.identity_summary) <= 200


def test_extract_user_name_tokens():
    """extract_user must split full_name into name_tokens."""
    result = extract_user(_USER_PATH)
    assert result.name_tokens == ["priya", "ramesh", "nair"]


def test_extract_user_aliases_include_middle_name():
    """extract_user must include middle_name in aliases."""
    result = extract_user(_USER_PATH)
    assert "ramesh" in result.aliases


# ── Aggregation guard-rails ────────────────────────────────────────────────────

def test_all_snippets_fail_returns_none():
    """If every snippet fails Pydantic validation, extract_candidate must return None."""
    invalid_snippet = {**_VALID_SNIPPET, "full_name": "X"}  # min_length=2 fails on "X"

    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=invalid_snippet):
        result = extract_candidate(user, _CANDIDATE_PATH, snippet_indices=[0, 1])

    assert result is None


def test_extract_candidate_default_n_cap():
    """With no snippet_indices, extract_candidate must process at most 5 snippets."""
    user = extract_user(_USER_PATH)

    with patch("engine.extraction.call_gemini", return_value=_VALID_SNIPPET) as mock_call:
        extract_candidate(user, _CANDIDATE_PATH)  # no snippet_indices → default N=5

    # test_scenario_1 has 2 media items, so N=min(5,2)=2 calls expected
    assert mock_call.call_count <= 5
