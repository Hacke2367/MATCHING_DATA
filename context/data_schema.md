
---

# Data Schema: Symmetric Identity Model (v1)

## 1. Schema Philosophy
This schema is the **Translation Layer**. Source A (clean User KYC) and Source B (messy multi-snippet candidate records) have asymmetric shapes. To enable mathematical scoring, both must collapse to a single Symmetric Identity Schema with identical keys.

**Precision over Recall**: prefer missing a match over identifying the wrong person.

---

## 2. Two-Layer Model

The schema operates on two layers. Source B passes through both; Source A skips Layer A.

### Layer A — `SnippetIdentity` (Source B only, per-article)
One instance is produced per `media[]` article inside a candidate doc. Each snippet may describe a different point in time (a 2005 article and a 2026 article about the same person).

### Layer B — `CandidateIdentity` (the comparable form)
The aggregated symmetric record used by the Scoring Engine. Source A produces this directly from the KYC object. Source B produces it by aggregating its `SnippetIdentity` instances (consensus across articles, latest-article-wins for time-varying fields, union for set fields like aliases/locations).

Both sides must share identical keys before entering the Scoring Engine.

---

## 3. Core Identity Fields (`CandidateIdentity`)

| Field Name | Data Type | Constraints | Extraction Logic |
| :--- | :--- | :--- | :--- |
| **source** | Literal | `"user"` or `"candidate"` | Origin tag |
| **record_id** | String | Required | User: `oomero_id` / `entity_id`; Candidate: `doc.id` |
| **full_name** | String | Min 2 words; lowercased; titles stripped | Regex stripping + LLM verification |
| **aliases** | List[String] | Includes AKA, middle-name variations, `previous_name`, `trading_as` | LLM extraction; Source A pulls `middle_name`, `previous_name`, `trading_as` |
| **name_tokens** | List[String] | Lowercased first/middle/last tokens | Tokenization for fragmented-name matching |
| **gender** | `male` / `female` / `unknown` | — | Pronouns or direct mention; null-tolerant on both sides |
| **dob_exact** | ISO `YYYY-MM-DD` | Optional | From structured fields |
| **dob_year** | Integer | 1900–2030 | Fallback when only year known (ComplyAdvantage often gives "1960", "1971") |
| **age_at_event** | Integer | 1–120 | Age mentioned in the snippet narrative |
| **article_date** | ISO `YYYY-MM-DD` | Optional | From `media[].date` — always reliable when present |
| **event_date** | ISO `YYYY-MM-DD` | Optional | LLM-inferred date the event actually occurred. May differ from article_date by years |
| **reference_date** | ISO `YYYY-MM-DD` | Optional | **Resolved anchor**: `event_date` if extracted with confidence, else `article_date` |
| **projected_current_age** | Integer | Computed | Per-formula in §6 |
| **locations** | List[`GeoLocation`] | — | See §4 |
| **nationality_country** | String | Optional | User: `country_of_nationality_name`; Candidate: from `fields[]` |
| **residency_country** | String | Optional | User: `country_of_residency_name` |
| **identifiers** | Dict[Type, Value] | Alphanumeric only | Types: PAN, AADHAR, SSN, DIN, VAT, GST, LEI, PASSPORT, CASE_ID, OOMERO, ENTITY_CLIENT |
| **industry** | String | Optional | Semantic classification of profession |
| **profession_raw** | String | Optional | Preserves original text for audit |
| **identity_summary** | String | Max 200 chars | LLM-generated one-line fact-sheet |
| **risk_types** | List[String] | Source B only | adverse-media-v2-*, sanction, pep-class-*, fitness-probity, warning |
| **source_provenance** | List[String] | Source B only | e.g. `["complyadvantage-adverse-media", "india-ministry-of-corporate-affairs-..."]` |
| **supporting_snippets** | List[`SnippetIdentity`] | Source B only | Audit trail for LLM Judge |
| **flags** | List[String] | — | See §7 |
| **extraction_confidence** | Float | 0.0–1.0 | LLM self-reported |

---

## 4. Geographic Hierarchy (`GeoLocation`)

Locations are stored as hierarchical objects, not free strings, so subset checks work mathematically:

```
sub_district → city → state → country (+ country_code ISO-2)
```

| Field | Example (User Ankit) | Example (Sandeep candidate) |
| :--- | :--- | :--- |
| `sub_district` | "Jogeshwari" | "Wheatley Close, Barnet" |
| `city` | "Mumbai" | "London" |
| `state` | "Maharashtra" | — |
| `country` | "India" | "United Kingdom" |
| `country_code` | "IN" | "GB" |
| `raw` | "durganagar Jogeshwari east..." | "Wheatley Close, Barnet, north London" |

**Subset rule**: User location matches Candidate location if all populated levels of User's hierarchy appear in Candidate's hierarchy at the same or higher level.

---

## 5. The Extraction Step (LLM Role)

For every `media[]` snippet, the LLM produces a `SnippetIdentity` with:

* **Cleaning**: strip legal jargon, irrelevant names (judges, lawyers, co-defendants).
* **Temporal capture**:
  * `article_date` ← `media[].date` directly.
  * `event_date` ← LLM extracts when event occurred. If unclear, leave null and add flag `EVENT_DATE_AMBIGUOUS`.
  * `age_at_event` ← extracted from text ("Sandeep Golechha, 55, of...").
* **Identifier extraction**: regex patterns for DIN, PAN, Passport, Case IDs *inside snippet text* — populate `identifiers_in_text`.
* **Summarization**: produce `identity_summary` (max 200 chars) — a logical fact-sheet for the LLM Judge to compare across snippets.
* **Confidence**: report `extraction_confidence` 0.0–1.0.

Aggregation step (Snippet → Candidate):
* `aliases`, `locations`, `risk_types`, `source_provenance` → set-union across snippets.
* `gender`, `dob_exact`, `dob_year` → consensus (most-frequent non-null); flag conflict if disagreement.
* `identifiers` → union, with conflict flag if same type has different values.
* `reference_date` → derived per §6.
* `supporting_snippets` → full list preserved for audit.

---

## 6. Normalization Rules (Checkpoint 1)
* **Names & aliases**: lowercase, remove titles (Mr, Adv, Dr), strip whitespace, collapse internal spaces.
* **Identifiers**: alphanumeric only (remove hyphens, slashes, spaces).
* **Locations**: standardize via geo-hierarchy (e.g. "Jogeshwari" → `{sub_district: Jogeshwari, city: Mumbai, state: Maharashtra, country: India, country_code: IN}`).
* **Country codes**: ISO-2 always.

---

## 7. Failure-Mode Fallbacks (Checkpoint 2)

### Age Projection Logic
When `dob_exact` is missing, the projected current age is calculated as:

$$Projected\_Age = (Current\_Year - Reference\_Date.year) + Age\_At\_Event$$

Where `Reference_Date` is resolved in this order:
1. `event_date` — if extracted with confidence (preferred for accuracy).
2. `article_date` — fallback when event date is ambiguous.
3. If neither exists, set flag `NO_REF_DATE` and skip the temporal score (treat as missing data, not as zero).

### Gender Safety Gate (null-tolerant)
| User Gender | Candidate Gender | Behavior |
| :--- | :--- | :--- |
| Known (M/F) | Known (M/F), match | Pass — full gender weight |
| Known (M/F) | Known (M/F), mismatch | **Hard-Reject (-100 pts)** |
| Known (M/F) | Unknown | Neutral — no bonus, no penalty |
| Unknown | Known (M/F) | Neutral — no bonus, no penalty |
| Unknown | Unknown | Neutral — gate skipped; flag `GENDER_NULL_BOTH_SIDES` |

The dual-null case is the common real-world scenario (User Ankit Dubey example has `sex: null`). Skipping the gate preserves recall without compromising precision.

### Alias Handling
For fragmented-name matching, the system uses **Jaro-Winkler distance** over the union of `full_name` and `aliases` on both sides. Best-of-pairs wins.

Alias sources:
* User side: `middle_name`, `previous_name`, `trading_as`, plus all permutations of first+middle+last and first+last.
* Candidate side: `doc.aka[]` array, plus any name variants extracted from snippet text by the LLM.

### Standard Flag Vocabulary
* `NO_REF_DATE` — neither event_date nor article_date present.
* `DOB_YEAR_ONLY` — only year-precision DOB.
* `GENDER_NULL_BOTH_SIDES` — gender gate skipped.
* `MULTI_COUNTRY_CANDIDATE` — candidate associated with > 2 countries.
* `NO_IDENTIFIERS` — no shared identifier types between sides.
* `AGE_PROJECTED` — current age was projected, not exact.
* `CONSENSUS_CONFLICT` — snippets disagree on a core field (gender, DOB, identifier).
* `EVENT_DATE_AMBIGUOUS` — LLM could not confidently extract event date.

---

## 8. Symmetric Pipeline (Checkpoint 3)
* **Source A (User)**: KYC JSON → directly populate `CandidateIdentity` (skip Layer A).
* **Source B (Candidate)**: raw doc → LLM produces `SnippetIdentity` per `media[]` → aggregator merges into `CandidateIdentity`.
* **Validation**: both objects must share identical keys before entering the Scoring Engine.

---

## 9. Risk Context (Source B only)

`risk_types` and `source_provenance` are carried inside `CandidateIdentity` but are never used in identity comparison — they only flow to the LLM Judge for adjudication weighting (e.g. government registry > blog) and to downstream risk decisioning (PEP, sanction, adverse media each have different handling).

---

## 10. Dashboard Adjudication Outputs

The Test-Bench dashboard consumes two top-level shapes from the engine. These are the **engine's output contract** — `engine/extraction.py` and `engine/scoring.py` must populate every field so the UI is purely presentational (no business logic in the front-end).

### `BatchScoreResult` (engine entry-point output)

```python
class BatchScoreResult(BaseModel):
    user: CandidateIdentity            # the single Source A
    best_match: Optional["MatchCard"]  # highest final_confidence; None only if all candidates hard-rejected
    all_results: List["MatchCard"]     # ordered desc by final_confidence; includes hard-rejects
    run_metadata: Dict[str, str]       # engine_version, run_started_utc, run_finished_utc, candidate_count
```

### `MatchCard` (per-candidate render contract)

```python
class ComparisonRow(BaseModel):
    field_label: str                              # "Name", "Date of Birth", "Projected Age",
                                                  # "Gender", "Location", "Profession", "PAN", "DIN", ...
    user_value: Optional[str]                     # display string for Source A column
    candidate_value: Optional[str]                # display string for Source B column
    match_status: Literal["match", "partial", "mismatch", "missing"]
    contribution_pts: Optional[float]             # how many of this field's weight this row earned

class MatchCard(BaseModel):
    candidate_id: str
    candidate_summary: CandidateIdentity          # full aggregated record for drill-down

    # === Verdict (drives the gauge) ===
    verdict_color: Literal["GREEN", "AMBER", "RED"]
    verdict_label: str                            # "Confirmed Match", "Review Required",
                                                  # "Deferred — Low Confidence", "No Match / Discard"
    final_confidence: float                       # 0.0–1.0
    tier_reached: Literal[
        "tier_0_id_match",
        "tier_1_heuristic",
        "tier_1_hard_reject",
        "tier_2_llm_judge"
    ]

    # === Symmetric Comparison Table (pre-rendered for UI) ===
    comparison_rows: List[ComparisonRow]

    # === Scoring Audit Trail ===
    score_breakdown: Dict[str, float]             # {"id": 60, "name": 18, "age": 10, "location": 10}
    weights_used: Dict[str, int]                  # {"id": 60, "name": 20, "age": 10, "location": 10}
    denominator: int                              # sum of weights for fields that were scoreable
    penalties_applied: List[str]                  # ["GENDER_MISMATCH", "TEMPORAL_AGE_CONFLICT", ...]

    # === Narrative Justification ===
    identity_summary: str                         # aggregated one-line fact-sheet
    llm_verdict: Optional[str]                    # populated only when tier_reached == "tier_2_llm_judge"

    # === Risk Intelligence ===
    risk_types: List[str]                         # PEP, sanction, adverse-media-v2-*, etc.
    source_provenance: List[str]                  # government registry > major news > blog

    # === Operational Flags (transparency) ===
    flags: List[str]                              # AGE_PROJECTED, GENDER_NULL_BOTH_SIDES,
                                                  # DOB_YEAR_ONLY, NO_REF_DATE, MULTI_COUNTRY_CANDIDATE,
                                                  # NO_IDENTIFIERS, CONSENSUS_CONFLICT, EVENT_DATE_AMBIGUOUS
```

### Mandatory `comparison_rows` content
At minimum, every `MatchCard` must include rows for: **Name**, **DOB / Projected Age** (single combined row, prefer `dob_exact` if present, else `projected_current_age` with the `(projected)` suffix), **Gender**, **Location** (rendered as `sub_district → city → state → country`), **Profession**, and one row per identifier present on either side.

### `match_status` semantics
| Status | When |
| :--- | :--- |
| `match` | Both sides populated, full weight earned |
| `partial` | Both sides populated, partial weight earned (e.g. Jaro-Winkler 0.85, location partial subset) |
| `mismatch` | Both sides populated, conflicting values |
| `missing` | One or both sides null — excluded from denominator |
