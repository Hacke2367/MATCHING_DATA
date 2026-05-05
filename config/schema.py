"""Symmetric Identity Schema v1.1.0

Canonical Pydantic v2 data contracts for the Pro-Match Identity Engine.
All models are immutable (frozen=True) and reject unknown fields (extra="forbid").

Downstream consumers must assert SCHEMA_VERSION before using these models.
"""
import datetime
from typing import Annotated, Dict, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: str = "1.1.0"

CANONICAL_IDENTIFIER_KEYS = frozenset({
    "PAN", "AADHAR", "SSN", "DIN", "VAT",
    "GST", "LEI", "PASSPORT", "CASE_ID", "OOMERO", "ENTITY_CLIENT",
})

# Strict int for age fields — rejects string coercion (spec §6.1)
AgeBounded = Annotated[int, Field(strict=True, ge=1, le=120)]

# Canonical flag literal sets
SnippetFlag = Literal[
    "NO_REF_DATE", "AGE_INFERRED", "EVENT_DATE_AMBIGUOUS", "NAME_AMBIGUOUS_IN_TEXT",
]
CandidateFlag = Literal[
    "DOB_YEAR_ONLY", "NO_REF_DATE", "GENDER_NULL_BOTH_SIDES",
    "MULTI_COUNTRY_CANDIDATE", "NO_IDENTIFIERS", "AGE_PROJECTED", "CONSENSUS_CONFLICT",
]


def _utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


class GeoLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sub_district: str | None = None  # CRITICAL: required for hierarchical subset-matching
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None  # ISO-2 (e.g. "IN", "GB")
    raw: str | None = None           # original unparsed string for audit trail


class SnippetIdentity(BaseModel):
    """One instance per media[] article. LLM-extracted from Source B snippet text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Origin
    candidate_id: str = Field(..., description="doc.id from Source B")
    snippet_url: str | None = None
    snippet_title: str | None = None
    snippet_text: str

    # Names
    full_name: str = Field(..., min_length=2)
    aliases: List[str] = Field(default_factory=list)

    # Demographics
    gender: Literal["male", "female", "unknown"] = "unknown"

    # Temporal anchoring — store both per Design Decision #2
    article_date: datetime.date | None = None
    event_date: datetime.date | None = None
    age_at_event: AgeBounded | None = None

    # Geography
    locations: List[GeoLocation] = Field(default_factory=list)

    # Identifiers extracted from snippet text
    identifiers_in_text: Dict[str, str] = Field(default_factory=dict)

    # Profession
    profession_raw: str | None = None

    # LLM-generated one-line fact-sheet for this snippet
    identity_summary: str = Field(..., max_length=200)

    # Extraction metadata
    flags: List[SnippetFlag] = Field(default_factory=list)
    extraction_confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("article_date", "event_date", mode="before")
    @classmethod
    def no_future_dates(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            d = datetime.date.fromisoformat(v[:10])
        elif isinstance(v, datetime.datetime):
            d = v.date()
        elif isinstance(v, datetime.date):
            d = v
        else:
            return v  # defer type errors to Pydantic's own validator
        if d > _utc_today():
            raise ValueError(f"Date {d} exceeds UTC today ({_utc_today()})")
        return v


class CandidateIdentity(BaseModel):
    """Aggregated symmetric form used by the scoring engine.

    Both Source A (User KYC) and Source B (Candidate, after snippet aggregation)
    collapse into this shape before entering scoring.py.

    MUST be constructed in a single atomic call: CandidateIdentity(**aggregated_dict)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # === 0. ORIGIN ===
    source: Literal["user", "candidate"]
    record_id: str  # User: oomero_id; Candidate: doc.id

    # === 1. NAMES (20 pts) ===
    full_name: str = Field(..., min_length=2)
    aliases: List[str] = Field(default_factory=list)
    name_tokens: List[str] = Field(default_factory=list)

    # === 2. GENDER (Hard-Reject gate; null/null = neutral per Design Decision #3) ===
    gender: Literal["male", "female", "unknown"] = "unknown"

    # === 3. TEMPORAL (10 pts + Hard-Reject gate) ===
    dob_exact: datetime.date | None = None
    dob_year: int | None = Field(None, ge=1900, le=2030)
    age_at_event: AgeBounded | None = None
    article_date: datetime.date | None = None
    event_date: datetime.date | None = None
    reference_date: datetime.date | None = None  # resolved anchor for age projection
    projected_current_age: AgeBounded | None = None

    # === 4. GEOGRAPHY (10 pts) ===
    locations: List[GeoLocation] = Field(default_factory=list)
    nationality_country: str | None = None
    residency_country: str | None = None

    # === 5. IDENTIFIERS (60 pts — exact boolean match, same type required) ===
    identifiers: Dict[str, str] = Field(default_factory=dict)

    # === 6. PROFESSION ===
    industry: str | None = None
    profession_raw: str | None = None

    # === 7. IDENTITY SUMMARY (required — consumed by Layer-3 LLM Judge) ===
    identity_summary: str = Field(..., max_length=200)

    # === 8. RISK CONTEXT (Source B only) ===
    risk_types: List[str] = Field(default_factory=list)
    source_provenance: List[str] = Field(default_factory=list)

    # === 9. SUPPORTING SNIPPETS (Source B only — LLM Judge audit trail) ===
    supporting_snippets: List[SnippetIdentity] = Field(default_factory=list)

    # === 10. FLAGS & CONFIDENCE ===
    flags: List[CandidateFlag] = Field(default_factory=list)
    extraction_confidence: float | None = Field(None, ge=0.0, le=1.0)

    @field_validator("article_date", "event_date", "dob_exact", "reference_date", mode="before")
    @classmethod
    def no_future_dates(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, str):
            d = datetime.date.fromisoformat(v[:10])
        elif isinstance(v, datetime.datetime):
            d = v.date()
        elif isinstance(v, datetime.date):
            d = v
        else:
            return v
        if d > _utc_today():
            raise ValueError(f"Date {d} exceeds UTC today ({_utc_today()})")
        return v

    @field_validator("identifiers")
    @classmethod
    def validate_identifier_keys(cls, v: Dict[str, str]) -> Dict[str, str]:
        invalid = set(v.keys()) - CANONICAL_IDENTIFIER_KEYS
        if invalid:
            raise ValueError(f"Non-canonical identifier keys: {invalid}")
        return v
