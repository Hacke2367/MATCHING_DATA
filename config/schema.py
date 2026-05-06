"""Symmetric Identity Schema v1.1.0

Canonical Pydantic v2 data contracts for the Pro-Match Identity Engine.
All models are immutable (frozen=True) and reject unknown fields (extra="forbid").

Downstream consumers must assert SCHEMA_VERSION before using these models.
"""
import datetime
from typing import Annotated, Dict, List, Literal, Optional
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


# ── Dashboard output contract ─────────────────────────────────────────────────

class ComparisonRow(BaseModel):
    """One side-by-side field row for the dashboard comparison table."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_label: str
    user_value: Optional[str] = None
    candidate_value: Optional[str] = None
    match_status: Literal["match", "partial", "mismatch", "missing"]
    contribution_pts: Optional[float] = None


class MatchCard(BaseModel):
    """Per-candidate render contract. scoring.py populates every field;
    the dashboard layer is purely presentational."""
    model_config = ConfigDict(extra="forbid", frozen=False)  # mutable for Tier-2 update

    candidate_id: str
    candidate_summary: CandidateIdentity

    # Verdict
    verdict_color: Literal["GREEN", "AMBER", "RED"]
    verdict_label: str
    final_confidence: float = Field(..., ge=0.0, le=1.0)
    tier_reached: Literal[
        "tier_0_id_match",
        "tier_1_heuristic",
        "tier_1_hard_reject",
        "tier_2_llm_judge",
    ]

    # Symmetric comparison table
    comparison_rows: List[ComparisonRow]

    # Scoring audit trail
    score_breakdown: Dict[str, float]   # {"id": x, "name": x, "age": x, "location": x}
    weights_used: Dict[str, float]      # weights for scoreable fields only
    denominator: float                  # sum of weights_used (excludes missing fields)
    penalties_applied: List[str]

    # Narrative justification
    identity_summary: str
    llm_verdict: Optional[str] = None

    # Risk intelligence
    risk_types: List[str] = Field(default_factory=list)
    source_provenance: List[str] = Field(default_factory=list)

    # Operational flags
    flags: List[str] = Field(default_factory=list)


class BatchScoreResult(BaseModel):
    """Top-level engine output for one Source A vs N Source B run."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    user: CandidateIdentity
    best_match: Optional[MatchCard] = None          # highest final_confidence; None if all hard-rejected
    all_results: List[MatchCard]                    # sorted desc by final_confidence, includes hard-rejects
    run_metadata: Dict[str, str]                    # engine_version, run_started_utc, run_finished_utc, candidate_count
