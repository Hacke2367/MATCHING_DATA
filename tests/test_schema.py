"""Acceptance criteria tests for config/schema.py (Feature Spec 01 v1.1.0).

Tests map directly to spec §6:
  §6.1 — Strict Type Test
  §6.2 — sub_district Structural Check
  §6.3 — Data Path Round-Trip (Priya Ramesh Nair, test_scenario_1)
  §6.4 — Atomic Construction / Immutability Test
"""
import json
import datetime
import pytest
from pathlib import Path
from pydantic import ValidationError

from config.schema import (
    GeoLocation,
    SnippetIdentity,
    CandidateIdentity,
    SCHEMA_VERSION,
)

DATA_ROOT = Path(__file__).parent.parent / "data"


# ── Version sanity ─────────────────────────────────────────────────────────────

def test_schema_version():
    assert SCHEMA_VERSION == "1.1.0"


# ── §6.1 Strict Type Test ──────────────────────────────────────────────────────

def test_strict_int_rejects_string_age():
    """A string passed to an AgeBounded (strict int) field must raise ValidationError."""
    with pytest.raises(ValidationError):
        SnippetIdentity(
            candidate_id="TEST001",
            snippet_text="Priya Nair, 35, appeared before SEBI.",
            full_name="Priya Ramesh Nair",
            identity_summary="SEBI regulatory matter, Mumbai.",
            extraction_confidence=0.95,
            age_at_event="150",  # string — must be rejected in strict mode
        )


def test_strict_int_rejects_string_projected_age():
    """projected_current_age is also AgeBounded — must reject string input."""
    with pytest.raises(ValidationError):
        CandidateIdentity(
            source="user",
            record_id="TEST",
            full_name="Test User",
            identity_summary="Test.",
            projected_current_age="35",  # string — must be rejected
        )


# ── §6.2 sub_district Structural Check ────────────────────────────────────────

def test_geolocation_has_sub_district():
    """sub_district must be a defined field in GeoLocation (CRITICAL for subset-matching)."""
    assert "sub_district" in GeoLocation.model_fields


def test_geolocation_accepts_full_hierarchy():
    """GeoLocation must accept a fully-populated hierarchical instance."""
    loc = GeoLocation(
        sub_district="Bandra West",
        city="Mumbai",
        state="Maharashtra",
        country="India",
        country_code="IN",
        raw="12 Palm Grove, Bandra West, Mumbai 400051",
    )
    assert loc.sub_district == "Bandra West"
    assert loc.country_code == "IN"


def test_geolocation_rejects_extra_fields():
    """extra='forbid' must reject unknown fields."""
    with pytest.raises(ValidationError):
        GeoLocation(city="Mumbai", unknown_field="value")


# ── §6.3 Data Path Round-Trip (Priya Ramesh Nair — test_scenario_1) ──────────

def test_parse_user_kyc_to_candidate_identity():
    """CandidateIdentity must parse successfully from test_scenario_1 KYC data."""
    with open(DATA_ROOT / "actual_user" / "boss.json") as f:
        d = json.load(f)

    user = CandidateIdentity(
        source="user",
        record_id=d["oomero_id"],
        full_name=f"{d['first_name']} {d['middle_name']} {d['last_name']}".lower(),
        gender=d.get("sex") or "unknown",
        dob_exact=datetime.date.fromisoformat(d["date_of_birth"]),
        identifiers={"PAN": d["pan_number"]} if d.get("pan_number") else {},
        nationality_country=d.get("country_of_nationality_name"),
        residency_country=d.get("country_of_residency_name"),
        profession_raw=d.get("profession"),
        identity_summary="Priya Ramesh Nair, Finance – Investment Banking, Mumbai, DOB 1988-07-15.",
        locations=[
            GeoLocation(
                sub_district="Bandra West",
                city=d.get("city"),
                state=d.get("state"),
                country=d.get("country_of_residency_name"),
                country_code="IN",
                raw=d.get("address"),
            )
        ],
    )

    assert user.source == "user"
    assert user.record_id == "OLPIN10100010101"
    assert user.full_name == "priya ramesh nair"
    assert user.gender == "female"
    assert user.dob_exact == datetime.date(1988, 7, 15)
    assert user.identifiers["PAN"] == "ABCPN1234R"
    assert user.locations[0].sub_district == "Bandra West"
    assert user.locations[0].city == "Mumbai"


def test_parse_candidate_media_to_snippet_identity():
    """SnippetIdentity must parse successfully from test_scenario_1 media article."""
    with open(DATA_ROOT / "potential_matches" / "test_scenario_1.json") as f:
        d = json.load(f)

    media = d["doc"]["media"][0]
    snippet = SnippetIdentity(
        candidate_id=d["doc"]["id"],
        snippet_text=media["snippet"],
        snippet_url=media["url"],
        snippet_title=media["title"],
        article_date=datetime.date.fromisoformat(media["date"][:10]),
        full_name=d["doc"]["name"],
        age_at_event=35,
        identifiers_in_text={"PAN": "ABCPN1234R"},
        locations=[
            GeoLocation(city="Mumbai", state="Maharashtra", country="India", country_code="IN")
        ],
        identity_summary="SEBI front-running matter; Mumbai investment banker, PAN ABCPN1234R.",
        extraction_confidence=0.92,
    )

    assert snippet.candidate_id == "SYNTH001PRIYA001"
    assert snippet.full_name == "Priya Ramesh Nair"
    assert snippet.article_date == datetime.date(2024, 3, 15)
    assert snippet.age_at_event == 35
    assert snippet.identifiers_in_text["PAN"] == "ABCPN1234R"


# ── §6.4 Atomic Construction / Immutability Test ──────────────────────────────

def test_frozen_prevents_field_mutation():
    """Mutating any field on a frozen CandidateIdentity must raise ValidationError."""
    user = CandidateIdentity(
        source="user",
        record_id="OLPIN10100010101",
        full_name="priya ramesh nair",
        identity_summary="Priya Ramesh Nair, Finance, Mumbai.",
    )
    with pytest.raises(ValidationError):
        user.full_name = "mutated name"


def test_frozen_prevents_alias_append():
    """Even mutable containers on a frozen model must not be directly replaced."""
    candidate = CandidateIdentity(
        source="candidate",
        record_id="SYNTH001PRIYA001",
        full_name="priya ramesh nair",
        identity_summary="SEBI matter.",
        aliases=["Priya Nair"],
    )
    with pytest.raises(ValidationError):
        candidate.aliases = ["Priya Nair", "P. R. Nair"]


# ── Additional guard-rail tests ────────────────────────────────────────────────

def test_non_canonical_identifier_key_rejected():
    """identifiers dict must reject keys not in CANONICAL_IDENTIFIER_KEYS."""
    with pytest.raises(ValidationError):
        CandidateIdentity(
            source="user",
            record_id="X",
            full_name="Test User",
            identity_summary="Test.",
            identifiers={"DRIVER_LICENSE": "DL12345"},
        )


def test_future_date_rejected_on_snippet():
    """article_date in the future must raise ValidationError (UTC-aware)."""
    future = datetime.date.today() + datetime.timedelta(days=30)
    with pytest.raises(ValidationError):
        SnippetIdentity(
            candidate_id="X",
            snippet_text="Test snippet.",
            full_name="Test User",
            identity_summary="Test.",
            extraction_confidence=0.8,
            article_date=future,
        )


def test_extra_fields_forbidden_on_candidate_identity():
    """extra='forbid' must reject undefined fields on CandidateIdentity."""
    with pytest.raises(ValidationError):
        CandidateIdentity(
            source="user",
            record_id="X",
            full_name="Test User",
            identity_summary="Test.",
            metadata_v2="should_fail",
        )
