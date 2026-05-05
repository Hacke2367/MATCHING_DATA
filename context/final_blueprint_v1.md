# Final Blueprint v1 — Pro-Match Identity Engine

**Status**: Locked design (post-clarification). All four ambiguities resolved by the project owner.
**Companion docs**: `data_schema.md` (schema specifics), `scoring_logic.md` (scoring math).

---

## Context

We are building Pro-Match Identity Engine — a precision-first Entity Resolution system that matches Source A (a clean User KYC profile, e.g. `actual_user.json`) against Source B (raw, multi-snippet ComplyAdvantage candidate records like the 5 cases in `potentail_matches.json`).

The two sources have **asymmetric shapes**: Source A is a flat ~130-field KYC object; Source B is a nested doc with `aka[]`, `media[]` (5–10 messy news snippets per candidate), and `fields[]` (heterogeneous metadata from various registries). To enable mathematical scoring, both must collapse to a **Symmetric Identity Schema** with identical keys.

This blueprint is the deliverable: the final field list, justifications, and Pydantic-style definitions, with all four design ambiguities resolved.

---

## Resolved Design Decisions

| # | Decision Point | Resolution |
|---|---|---|
| 1 | Granularity | **Per-snippet + aggregation layer.** Source B produces one `SnippetIdentity` per `media[]` article, then an aggregator emits a single `CandidateIdentity`. Source A produces one `CandidateIdentity` directly. |
| 2 | Reference-date semantics | **Store both `article_date` and `event_date` separately.** Projection prefers `event_date` when LLM extracts it confidently; falls back to `article_date` otherwise. |
| 3 | Gender null/null case | **Neutral — skip the gate.** When both sides are unknown, no bonus and no penalty. No separate manual-review flag. |
| 4 | Risk types in schema | **Yes — included as Source-B-only fields** in the symmetric schema (`risk_types`, `source_provenance`). Downstream risk decisioning consumes them without a separate plumbing layer. |

---

## Phase 1 Findings: What Each Source Actually Contains

### Source A — `actual_user.json` (Ankit Pankaj Dubey, age ~21)
Populated high-signal fields:
- **Names**: `first_name`, `middle_name`, `last_name`, `title`, `previous_name`, `trading_as`
- **DOB**: `date_of_birth` (ISO date, exact)
- **Gender**: `sex` — **null in this example** (real-world common case)
- **National identifiers**: `pan_number`, `aadhar_number`, `ssn_no`, `vat_no`, `gst_no`, `legal_entity_number` — all null in this example
- **Geography**: `address`, `city`, `state`, `zip`, `country_of_residency_name`, `country_of_nationality_name` (+ `previous_*` mirror set)
- **Profession**: `profession` (e.g. "Computer - Software Engineer")
- **Date ranges**: `date_from` / `date_to` (residency window)

The schema must degrade gracefully when most identifiers are null.

### Source B — Candidate (e.g. Sandeep Golechha, ID `O03P3W86VROFSPK`)
- `doc.id`, `doc.name`, `doc.aka[]`
- `doc.types[]` — risk taxonomy (adverse-media-v2-fraud-linked, fitness-probity, sanction, pep-class-*)
- `doc.fields[]` — heterogeneous `{name, value, source, tag?}` triples mixing DOB, gender, address, enforcement type, identifiers
- `doc.sources[]`, `doc.source_notes{}` — provenance
- `doc.media[]` — articles, each `{url, date, title, snippet}`
- `score`, `match_types`, `match_status`

Per-snippet LLM-extractable: name confirmation, `age_at_event`, location at event, role/profession, identifiers mentioned in text (DIN, Case ID), event date, event description.

### Cross-source identifier asymmetry (critical)
- User side: PAN, Aadhar, SSN, VAT, GST, LEI (jurisdictional, structured, mostly private)
- Candidate side: DIN (India MCA), enforcement IDs, sex offender registry IDs, related URLs, alphanumeric values inside `fields[]`

These rarely overlap. Only same-type matches (DIN ↔ DIN, Passport ↔ Passport) earn the 60-point identifier score. Therefore the system is fundamentally **name + age + geo + profession** driven for the majority of cases.

---

## Final Symmetric Schema (Pydantic-style)

Two-layer model: `SnippetIdentity` is emitted per-article during extraction; `CandidateIdentity` is the aggregated form used by the scoring engine. Source A skips Snippet and produces `CandidateIdentity` directly.

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from datetime import date

# ---------- Reusable sub-models ----------

class GeoLocation(BaseModel):
    sub_district: Optional[str] = None     # "Jogeshwari", "Wendell"
    city: Optional[str] = None             # "Mumbai", "Wendell"
    state: Optional[str] = None            # "Maharashtra", "Idaho"
    country: Optional[str] = None          # standardized country name
    country_code: Optional[str] = None     # ISO-2: "IN", "US"
    raw: Optional[str] = None              # original unparsed string

# ---------- Layer A: per-snippet (Source B only) ----------

class SnippetIdentity(BaseModel):
    """One instance per `media[]` article. LLM-extracted from snippet text."""

    # Origin
    candidate_id: str = Field(..., description="doc.id from Source B")
    snippet_url: Optional[str] = None
    snippet_title: Optional[str] = None
    snippet_text: str

    # Names mentioned
    full_name: str = Field(..., min_length=2)
    aliases: List[str] = Field(default_factory=list)

    # Demographics extractable from this snippet
    gender: Literal["male", "female", "unknown"] = "unknown"

    # Temporal anchoring (Decision #2: store both)
    article_date: Optional[date] = Field(None,
        description="From media[].date — always reliable when present")
    event_date: Optional[date] = Field(None,
        description="LLM-inferred date the event/incident actually occurred. "
                    "May differ from article_date by years.")
    age_at_event: Optional[int] = Field(None, ge=1, le=120,
        description="Age mentioned in this snippet's narrative")

    # Geography mentioned in snippet
    locations: List[GeoLocation] = Field(default_factory=list)

    # Identifiers mentioned in snippet text
    identifiers_in_text: Dict[str, str] = Field(default_factory=dict)

    # Profession/role mentioned
    profession_raw: Optional[str] = None

    # One-line LLM fact-sheet of what THIS snippet says
    identity_summary: str = Field(..., max_length=200)

    # Extraction quality
    flags: List[str] = Field(default_factory=list,
        description="NO_REF_DATE, AGE_INFERRED, EVENT_DATE_AMBIGUOUS, "
                    "NAME_AMBIGUOUS_IN_TEXT")
    extraction_confidence: float = Field(..., ge=0, le=1)

# ---------- Layer B: per-candidate / per-user (the comparable form) ----------

class CandidateIdentity(BaseModel):
    """Aggregated symmetric form. Both User (Source A) and Candidate (Source B,
    after snippet aggregation) collapse into this shape for scoring."""

    # === 0. ORIGIN ===
    source: Literal["user", "candidate"]
    record_id: str  # User: oomero_id / entity_id; Candidate: doc.id

    # === 1. NAMES (20 pts in scoring) ===
    full_name: str = Field(..., min_length=2)
    aliases: List[str] = Field(default_factory=list)
    name_tokens: List[str] = Field(default_factory=list,
        description="Lowercased first/middle/last/previous/trading_as tokens")

    # === 2. GENDER (Hard-Reject gate; null/null = neutral per Decision #3) ===
    gender: Literal["male", "female", "unknown"] = "unknown"

    # === 3. TEMPORAL (10 pts + Hard-Reject gate) ===
    dob_exact: Optional[date] = None
    dob_year: Optional[int] = Field(None, ge=1900, le=2030)
    age_at_event: Optional[int] = Field(None, ge=1, le=120)
    article_date: Optional[date] = None       # latest article date if Source B
    event_date: Optional[date] = None         # preferred for projection
    reference_date: Optional[date] = Field(None,
        description="Resolved anchor: event_date if present and confident, "
                    "else article_date. Used by projection formula.")
    projected_current_age: Optional[int] = Field(None,
        description="(current_year - reference_date.year) + age_at_event")

    # === 4. GEOGRAPHY (10 pts) ===
    locations: List[GeoLocation] = Field(default_factory=list)
    nationality_country: Optional[str] = None
    residency_country: Optional[str] = None

    # === 5. IDENTIFIERS (60 pts — exact match) ===
    identifiers: Dict[str, str] = Field(default_factory=dict,
        description="Normalized {ID_TYPE: alphanumeric_value}. "
                    "Types: PAN, AADHAR, SSN, DIN, VAT, GST, LEI, "
                    "PASSPORT, CASE_ID, OOMERO, ENTITY_CLIENT")

    # === 6. PROFESSION ===
    industry: Optional[str] = Field(None,
        description="Semantic class: 'Technology', 'Finance', 'Construction'")
    profession_raw: Optional[str] = None

    # === 7. IDENTITY SUMMARY ===
    identity_summary: str = Field(..., max_length=200,
        description="Aggregated one-line fact-sheet used by Layer-3 LLM Judge")

    # === 8. RISK CONTEXT (Decision #4: kept in schema, Source B only) ===
    risk_types: List[str] = Field(default_factory=list,
        description="adverse-media-v2-*, sanction, pep-class-*, "
                    "fitness-probity, warning")
    source_provenance: List[str] = Field(default_factory=list,
        description="e.g. ['complyadvantage-adverse-media', "
                    "'india-ministry-of-corporate-affairs-...']")

    # === 9. SUPPORTING SNIPPETS (Source B only — for LLM Judge audit) ===
    supporting_snippets: List[SnippetIdentity] = Field(default_factory=list)

    # === 10. EXTRACTION FLAGS ===
    flags: List[str] = Field(default_factory=list,
        description="DOB_YEAR_ONLY, NO_REF_DATE, GENDER_NULL_BOTH_SIDES, "
                    "MULTI_COUNTRY_CANDIDATE, NO_IDENTIFIERS, "
                    "AGE_PROJECTED, CONSENSUS_CONFLICT")
    extraction_confidence: Optional[float] = Field(None, ge=0, le=1)
```

---

## Field-by-Field Justification

| # | Field | Why selected | False-positive defense |
|---|---|---|---|
| 1 | `full_name` | Primary join key; every comparison starts here | Title-strip + lowercase prevents "Mr Ankit Dubey" ≠ "ankit dubey" mismatch |
| 1 | `aliases` | Vance Jay record carries "Vance Edward Jay"; Sandeep Golechha snippets vary spelling. Without aliases these are missed | Jaro-Winkler best-of name-or-alias catches partial-name records |
| 1 | `name_tokens` | "David James" appears in 3 of 5 example records — name alone is useless. Tokens enable token-overlap heuristics | Blocks the "popular name in same article as our user" trap |
| 2 | `gender` | Hard-reject gate (-100 pts) — most powerful single defense. Per Decision #3, null/null is neutral, not penalized | Eliminates cross-gender false positives; preserves recall on dual-null case |
| 3 | `dob_exact` | Strongest non-ID signal when present; Vance Jay example carries `1957-11-08` | Day-precision eliminates same-name same-city collisions |
| 3 | `dob_year` | ComplyAdvantage often gives only year ("1960", "1971"); without fallback, ~40% of records have no DOB at all | Year-level still rejects 30-year age gaps |
| 3 | `age_at_event` | Sandeep Golechha snippets say "55", "53" — extractable from text | Cross-validates `dob_year` against article narrative |
| 3 | `article_date` | Always reliable; from `media[].date` | Anchor when LLM cannot infer event date |
| 3 | `event_date` | A 2026 article describing a 2005 trial mentions "age 38 at the time" — without event_date, projection inflates by 21 years | Per Decision #2, this is the preferred projection anchor when extracted with confidence |
| 3 | `reference_date` | The resolved anchor used by the projection formula. Promoted from `event_date` if available, else `article_date` | Single explicit field eliminates per-formula ambiguity |
| 3 | `projected_current_age` | Final scalar comparable against User's current age | ±3 yr tolerance for full points; >5 yr triggers Hard-Reject |
| 4 | `locations` (hierarchy) | User: Jogeshwari → Mumbai → Maharashtra → IN. Candidate: Wheatley Close → Barnet → London → GB. Subset checks need hierarchy | Stops "Mumbai" from matching "Mumbai, Texas" |
| 4 | `nationality_country` / `residency_country` | User has UK residency + UK nationality but Mumbai address — these legitimately disagree | Allows match on nationality OR residency without forcing both |
| 5 | `identifiers` (Dict) | DIN exact match alone earns 60/100 — most valuable signal. Generic dict keeps schema cross-jurisdictional | Boolean-only matching (no fuzziness) so identifier never produces a false positive |
| 6 | `industry` | "Software Engineer" vs "Technology Lead" vs "Waste-management criminal" — semantic class drives consensus | Disambiguates same-name people across sectors |
| 6 | `profession_raw` | Preserves original text for LLM Judge audit | Prevents lossy industry-bucketing from dropping signal |
| 7 | `identity_summary` | Layer-3 LLM Judge compares summaries across snippets to verify all describe one entity | Final consensus gate before score is reported |
| 8 | `risk_types` | Per Decision #4, kept in schema. PEP, sanction, adverse-media each have different downstream handling | Source-B-only — never used in identity comparison; only in adjudication |
| 8 | `source_provenance` | Government registry > blog. LLM Judge weights accordingly | Prevents low-credibility sources from anchoring a match |
| 9 | `supporting_snippets` | Required for LLM Judge to re-read original text when summary is ambiguous | Audit trail satisfies the "Logical Auditability" requirement |
| 10 | `flags` | `NO_REF_DATE`, `DOB_YEAR_ONLY`, `AGE_PROJECTED` etc. surface degraded cases to scoring | Lets scoring downweight rather than crash on missing data |

---

## Verification Plan (post-implementation)

1. **Round-trip the 5 candidate examples + the user object.** All 6 must produce a valid `CandidateIdentity`.
2. **Spot-check Sandeep Golechha** (`O03P3W86VROFSPK`): `aliases` includes "Sandeep Golechha"; `identifiers` includes `{"DIN": "3208006"}`; `dob_year=1971`; `risk_types` contains `"fitness-probity"`; `locations` resolves to UK; `supporting_snippets` length = 10 (matches `media[]`).
3. **Spot-check Vance Jay**: `gender="male"`, `dob_exact=date(1957,11,8)`, `aliases=["Vance Edward Jay"]`, `risk_types` contains `"warning"` and `"adverse-media-v2-violence-aml-cft"`.
4. **Spot-check User Ankit Dubey**: `full_name="ankit pankaj dubey"`, `aliases` includes `"pankaj"` (from middle_name), `dob_exact=date(2005,3,1)`, `gender="unknown"`, `locations[0]` resolves Jogeshwari → Mumbai → Maharashtra → IN, `nationality_country="United Kingdom"`.
5. **Edge case: David James (3 separate records).** Confirm each produces a distinct `CandidateIdentity` with different `record_id`, that aggregation does NOT merge them, and that `flags` includes `MULTI_COUNTRY_CANDIDATE` where applicable.
6. **Projection check**: Take a snippet whose `event_date` ≠ `article_date` (e.g. 2005 customs trial mentioned in a 2026 article). Verify `reference_date == event_date` and that `projected_current_age` uses event_date.
7. **Null-gender symmetry check**: Match User Ankit (sex=null) against a Candidate with no gender field. Confirm `flags` carries `GENDER_NULL_BOTH_SIDES` and the gate produces a neutral (zero-impact) outcome.

---

## Phase 5 — Manual Adjudication Dashboard (Test-Bench)

The dashboard is the human-facing surface that exercises the engine end-to-end against real Source A + Source B inputs. It is the primary tool for validating extraction, scoring, and the safety gates before the engine is wired into production KYC flows.

### Workflow Contract
1. **Input 1 — Source A**: a single User KYC JSON (the 130-field shape from `actual_user.json`).
2. **Input 2 — Source B**: a list of one or more raw ComplyAdvantage candidate objects.
3. **On Submit**: the engine iterates through every candidate in Source B, scores each against Source A independently, sorts by `final_confidence` descending, and returns a `BatchScoreResult` (see `data_schema.md` §10).
4. **Best-Match Identification**: the candidate at index 0 of `all_results` is the dashboard's primary focus and renders as a `MatchCard`. Lower-ranked candidates are accessible via a collapsible secondary list. Hard-rejected candidates remain in `all_results` so the reviewer can audit *why* a name-matching candidate was discarded.

### Verdict Gauge

| Score Band | Gauge | `verdict_label` | Meaning |
| :--- | :--- | :--- | :--- |
| ≥ 0.90 **OR** Tier 0 ID match | 🟢 **GREEN** | Confirmed Match | Auto-verified |
| 0.70 – 0.89 | 🟡 **AMBER** | Review Required | LLM Reasoner justification must be displayed |
| 0.50 – 0.69 | 🟡 **AMBER** | Deferred — Low Confidence | LLM Judge invoked; reviewer must manually accept or reject |
| < 0.50 **OR** Hard-Reject | 🔴 **RED** | No Match / Discard | Engine successfully blocked a False Positive |

A 🔴 RED verdict on a hard-reject case is a **success signal**, not a failure: it means the safety gates protected the user.

### Match Card Sections (UI rendering order)

1. **Verdict Banner** — large color-coded gauge + `final_confidence` + `tier_reached` + `verdict_label`.
2. **Symmetric Comparison Table** — two-column side-by-side view driven by `MatchCard.comparison_rows`. Mandatory rows: Name, DOB / Projected Age, Gender, Location (hierarchical render), Profession, and one row per populated identifier on either side. Each row is tagged `match` / `partial` / `mismatch` / `missing`.
3. **Scoring Audit Trail** — transparent table of the 60/20/10/10 weightage distribution showing points actually earned per field, the `denominator` used (which excludes unscoreable fields — never treat missing as zero), and any `penalties_applied`.
4. **Narrative Justification** — `identity_summary` always shown. `llm_verdict` displayed only when `tier_reached == "tier_2_llm_judge"`.
5. **Risk Intelligence** — `risk_types` chips (PEP, Sanctions, Adverse Media variants, fitness-probity) and `source_provenance` (rendered with credibility tier: government registry > major news > blog).
6. **Operational Flags** — surface every flag (`AGE_PROJECTED`, `GENDER_NULL_BOTH_SIDES`, `DOB_YEAR_ONLY`, `NO_REF_DATE`, `MULTI_COUNTRY_CANDIDATE`, `NO_IDENTIFIERS`, `CONSENSUS_CONFLICT`, `EVENT_DATE_AMBIGUOUS`) so the reviewer sees exactly which graceful-degradation paths the engine took.

### Implementation Note
The `MatchCard` shape **is** the engine's output contract. `engine/extraction.py` and `engine/scoring.py` must populate every MatchCard field so the dashboard layer is purely presentational — no business logic in the front-end. This keeps the engine independently testable (the Test-Bench is one consumer; production KYC pipelines will be another).

---

## Files to Implement (next phase — not in scope of this document)

- `config/schema.py` — replace placeholder dataclasses with the full Pydantic models (`GeoLocation`, `SnippetIdentity`, `CandidateIdentity`, `ComparisonRow`, `MatchCard`, `BatchScoreResult`).
- `engine/extraction.py` — implement `extract_user(raw_user_json) -> CandidateIdentity` and `extract_candidate(raw_candidate_json) -> CandidateIdentity` (the latter internally produces `SnippetIdentity` per article, then aggregates).
- `engine/scoring.py` — implement weighted scoring per `scoring_logic.md` §2–§5, batch-mode best-match selection per §9, and `MatchCard` population per §10.
- `engine/reasoning.py` — implement Layer-3 LLM Judge per `scoring_logic.md` §6; populate `llm_verdict` on the MatchCard.
- `dashboard/` — Test-Bench UI (separate package). Consumes `BatchScoreResult` only — no engine logic.
- Add `pydantic` to `requirements.txt`.
