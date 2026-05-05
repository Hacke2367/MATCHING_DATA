# Implementation Plan: Symmetric Identity Schema (Feature Spec 01 v1.1.0)

**Status:** APPROVED & EXECUTED  
**Schema Version:** 1.1.0  
**Target File:** `config/schema.py`  
**Test File:** `tests/test_schema.py`

---

## Context

`config/schema.py` previously contained only three placeholder `@dataclass` stubs (`User`, `Candidate`, `MatchResult`) with no Pydantic. The entire engine — `extraction.py`, `scoring.py`, `reasoning.py` — is BLOCKED on this schema. This plan covers the complete replacement with Pydantic v2 models per Feature Spec 01 v1.1.0.

---

## Files Modified / Created

| File | Action |
|---|---|
| `config/schema.py` | **Full rewrite** — Pydantic v2 models |
| `config/__init__.py` | **Created** — empty package marker |
| `tests/test_schema.py` | **Created** — 11 tests covering spec §6 acceptance criteria |
| `tests/__init__.py` | **Created** — empty package marker |
| `requirements.txt` | **Updated** — added `pytest>=7.0` |

---

## Models Implemented

### `SCHEMA_VERSION = "1.1.0"`
Module-level constant for downstream consumer assertions.

### `GeoLocation`
- 6 optional fields: `sub_district` (CRITICAL), `city`, `state`, `country`, `country_code` (ISO-2), `raw`
- `ConfigDict(extra="forbid", frozen=True)`

### `SnippetIdentity` (Layer A — Source B only, per-article)
- 13 fields verbatim from `final_blueprint_v1.md`
- Mandatory: `candidate_id`, `snippet_text`, `full_name`, `identity_summary`, `extraction_confidence`
- Strict int type (`AgeBounded`) for `age_at_event` — rejects string coercion
- Future-date validator (UTC) on `article_date` and `event_date`
- `flags` typed as `List[SnippetFlag]` (Literal — 4 canonical values)

### `CandidateIdentity` (Layer B — aggregated, both sources)
- 21 fields verbatim from `final_blueprint_v1.md`
- Mandatory: `source`, `record_id`, `full_name`, `identity_summary`
- `identifiers: Dict[str, str] = Field(default_factory=dict)` — NOT Optional; extractor passes `{}` when empty
- Identifier key validator against 11-type canonical list (PAN, AADHAR, SSN, DIN, VAT, GST, LEI, PASSPORT, CASE_ID, OOMERO, ENTITY_CLIENT)
- Future-date validator (UTC) on `dob_exact`, `article_date`, `event_date`, `reference_date`
- `flags` typed as `List[CandidateFlag]` (Literal — 7 canonical values)
- `projected_current_age: AgeBounded | None` — strict int

---

## Key Design Decisions Implemented

| Decision | Implementation |
|---|---|
| `frozen=True` | All 3 models — enforces atomic `CandidateIdentity(**aggregated_dict)` construction |
| `extra="forbid"` | All 3 models — ComplyAdvantage fields must be stripped by extraction layer before instantiation |
| UTC future-date check | `datetime.datetime.now(datetime.timezone.utc).date()` — resolves timezone ambiguity from spec review |
| Strict ints | `AgeBounded = Annotated[int, Field(strict=True, ge=1, le=120)]` — field-level, not model-level, to preserve string→date coercion on date fields |
| Canonical identifier keys | `CANONICAL_IDENTIFIER_KEYS = frozenset({...})` validated in `CandidateIdentity.validate_identifier_keys` |

---

## Deferred to Feature Spec 02

- `ComparisonRow`
- `MatchCard`
- `BatchScoreResult`

---

## Verification

```bash
# Activate virtual environment
.venv\Scripts\activate

# Run all schema tests
python -m pytest tests/test_schema.py -v

# Smoke-test import
python -c "from config.schema import GeoLocation, SnippetIdentity, CandidateIdentity, SCHEMA_VERSION; print('OK', SCHEMA_VERSION)"
```

---

## What This Unblocks

- `engine/extraction.py` — can now import and instantiate `SnippetIdentity` and `CandidateIdentity`
- `engine/scoring.py` — can now type-hint and consume `CandidateIdentity` objects
- `engine/reasoning.py` — can now access `supporting_snippets: List[SnippetIdentity]` on `CandidateIdentity`
