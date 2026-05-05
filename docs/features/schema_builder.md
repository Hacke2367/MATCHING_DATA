# Feature Spec 01: Symmetric Identity Schema (Pydantic Models)
**Version:** 1.1.0 | **Component:** Backend Models (`config/schema.py`) | **Status:** FINAL / APPROVED
**Blocks:** `engine/extraction.py`, `engine/scoring.py`, `engine/reasoning.py`

---

## 1. The Core Problem (Objective)
Source A (Clean KYC) and Source B (Messy News Snippets) have asymmetric structures. This spec defines the **Symmetric Identity Schema**—the canonical bridge that allows both sources to be compared mathematically. Any deviation from this schema breaks the scoring engine's subset-matching and temporal projection algorithms.

## 2. Reference Documents (Sources of Truth)
The developer **MUST** adhere to the fields defined in:
*   **`Final Blueprint v1`**: Primary source for model field lists and aggregation logic.
*   **`data_schema.md`**: Canonical source for flag strings and geography hierarchy.
*   **`scoring_logic.md`**: Defines how fields like `sub_district` and `reference_date` are consumed.

## 3. Architectural Constraints & Guardrails
*   **Target File:** `config/schema.py` (As per `CLAUDE.md` and `Final Blueprint v1`).
*   **Dependencies:** Requires `pydantic>=2.0` and `Python >=3.10` (for `X | None` union syntax).
*   **Constraint 1 (No Logic):** This module must strictly contain data definitions only.
*   **Constraint 2 (Garbage Policy):** Use `ConfigDict(extra="forbid")`. If external APIs (ComplyAdvantage) add fields, the extraction layer must strip them before instantiation.
*   **Constraint 3 (Immutability):** **MUST** use `frozen=True`. Objects must be created in a single atomic call (e.g., `CandidateIdentity(**aggregated_dict)`).
*   **Constraint 4 (Versioning):** Export a module-level constant `SCHEMA_VERSION = "1.1.0"` for downstream consumer assertions.

## 4. Data Contracts (The Models)

### A. GeoLocation (Hierarchy Support)
| Field | Type | Required? | Justification |
| :--- | :--- | :--- | :--- |
| `city` | `str \| None` | No | Scoring (10 pts) |
| `sub_district`| `str \| None` | No | **CRITICAL** for Mumbai subset matching |
| `state` | `str \| None` | No | Scoring (10 pts) |
| `country` | `str \| None` | No | Geo-gate |
| `country_code`| `str \| None` | No | ISO-2 Standard |
| `raw` | `str \| None` | No | Auditability |

### B. SnippetIdentity (Layer A - Per Snippet)
Implement **verbatim** from `Final Blueprint v1` §SnippetIdentity.
*   **Mandatory Fields:** `candidate_id`, `snippet_text`, `full_name`, `identity_summary`, `extraction_confidence`.
*   **Strict Flags:** Must use `Literal` of: `["NO_REF_DATE", "AGE_INFERRED", "EVENT_DATE_AMBIGUOUS", "NAME_AMBIGUOUS_IN_TEXT"]`.

### C. CandidateIdentity (Layer B - Aggregated)
Implement **verbatim** from `Final Blueprint v1` §CandidateIdentity.
*   **Mandatory Fields:** `source`, `record_id`, `full_name`, `identity_summary`.
*   **Nullability:** `identifiers` MUST be `Dict[str, str] = Field(default_factory=dict)`. Extractor must pass `{}` if no IDs are found; `None` is invalid.
*   **Flags:** Must use `Literal` of: `["DOB_YEAR_ONLY", "NO_REF_DATE", "GENDER_NULL_BOTH_SIDES", "MULTI_COUNTRY_CANDIDATE", "NO_IDENTIFIERS", "AGE_PROJECTED", "CONSENSUS_CONFLICT"]`.

### D. Out of Scope Models
The following are deferred to **Feature Spec 02**: `ComparisonRow`, `MatchCard`, `BatchScoreResult`.

## 5. Logic & Validation Matrix
*   **Timezone Standard:** All `date` objects must be normalized to **UTC** before validation.
*   **Future Date Validator:** Use `@field_validator` to reject any date > `date.today()` (UTC).
*   **Identifier Keys:** Use a validator to ensure keys in `identifiers` dict match the canonical list in `Final Blueprint v1` (PAN, DIN, etc.).

## 6. Acceptance Criteria (Testing)
1.  **Strict Type Test:** Passing `"150"` (string) to an `int` field must trigger a `ValidationError` (Strict mode).
2.  **Missing Field Test:** Omission of `sub_district` from `GeoLocation` must be flagged during code review.
3.  **Data Path Test:** Successfully parse `data/actual_user/test_scenario_1.json` and `data/potential_matches/test_scenario_1.json`.
4.  **Atomic Construction Test:** Verify that `CandidateIdentity` cannot be mutated after `**aggregated_dict` instantiation.

---
