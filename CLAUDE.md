# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Pro-Match Identity Engine — a high-precision **Entity Resolution (ER)** system. It matches unstructured "Adverse Media" snippets (from ComplyAdvantage) against structured User KYC profiles. Core design principle: **Precision over Recall** — prefer missing a match over a false positive.

## Development Environment

```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the engine
python main.py
```

## Architecture: 3-Layer Pipeline

Data flows through three sequential stages defined in `engine/`:

```
User KYC JSON  ────────────────────────────────────► CandidateIdentity ─┐
                                                                          ├──► scoring.py ──► reasoning.py ──► final_match.json
Candidate JSON ──► SnippetIdentity (per article) ──► CandidateIdentity ─┘
                       extraction.py                   (aggregated)
                       (Layer 1)                        (Layer 1)            (Layer 2)       (Layer 3)
```

**Layer 1 — `engine/extraction.py`** (Two-sub-layer model)

- **Source B (Candidate)** first produces one `SnippetIdentity` per `media[]` article via LLM extraction, then aggregates them into a single `CandidateIdentity`.
- **Source A (User KYC)** skips the snippet step and maps directly to `CandidateIdentity`.
- LLM extracts per snippet: `full_name`, `aliases`, `gender`, `age_at_event`, `article_date`, `event_date`, `locations`, `identifiers_in_text`, `profession_raw`, `identity_summary`, `flags`, `extraction_confidence`.
- The resolved `reference_date` on `CandidateIdentity` is set to `event_date` if the LLM extracted it with confidence, otherwise falls back to `article_date`.

**Layer 2 — `engine/scoring.py`**
Pure Python heuristic scoring, no LLM. Weighted formula (base 100):
- Unique Identifiers: 60 pts (exact boolean match, same ID type required)
- Name/Aliases: 20 pts (Jaro-Winkler on `full_name` OR best alias from either side)
- Location: 10 pts (hierarchical subset check: user location ⊆ candidate locations)
- Projected Age: 10 pts (±3 year tolerance)

Missing fields are excluded from numerator **and** denominator — never treated as zero.

**Hard Rejection rules** (-100 penalty):
- Gender mismatch when **both** sides are known (null/null = neutral, gate skipped)
- Age divergence > 5 years (`projected_current_age` vs user current age)
- Logically impossible `identity_summary`

**Tiered execution:**
- **Tier 0**: any exact identifier match → skip to final verdict
- **Tier 1**: pure-Python heuristics (name, age, location, identifiers)
- **Tier 2**: LLM Judge invoked when score is 0.50–0.89 OR `CONSENSUS_CONFLICT` is flagged

**Layer 3 — `engine/reasoning.py`**
LLM (Gemini) called **only** for Tier 2 cases. Reviews `identity_summary` across all `supporting_snippets` to confirm all snippets describe the same entity before finalizing the score. Uses source provenance weighting (government registry > blog).

## Data Shapes

**Input A — User KYC** (`data/actual_user/`): Structured JSON from onboarding. Key identity fields: `first_name`, `middle_name`, `last_name`, `date_of_birth`, `sex`, `profession`, `city`, `state`, `country_of_residency_name`, `country_of_nationality_name`, `pan_number`, `aadhar_number`. See `context/data_example/actual_user.json` for full schema.

**Input B — Candidate** (`data/potential_matches/`): Raw ComplyAdvantage result per person. Each candidate has multiple `media[]` snippets (5–10). Key fields: `doc.name`, `doc.aka[]`, `doc.types[]`, `doc.fields[]` (DOB, address, gender from source registries), `score`, `match_types`, `match_status`. See `context/data_example/potentail_matches.json` for full examples.

**Output** (`outputs/final_match.json`): Must include `candidate_id`, `final_confidence` (0.0–1.0), `llm_verdict`, and `audit_log` with `reference_date_used`, `reference_date_source`, `projected_current_age`, `tier_reached`, and full score breakdown.

## Schemas (`config/schema.py`)

Three Pydantic models (to be implemented):
- `GeoLocation` — hierarchical location: `sub_district`, `city`, `state`, `country`, `country_code`, `raw`
- `SnippetIdentity` — per-article extraction result (Source B only)
- `CandidateIdentity` — the symmetric comparable form used by both sides for scoring

See `context/data_schema.md` for full field definitions and `context/final_blueprint_v1.md` for the complete Pydantic code.

## Scoring Thresholds

| Score | Verdict |
|---|---|
| > 0.90 | High Confidence — Auto-Verified |
| 0.70–0.89 | Likely Match — LLM reasoning required |
| 0.50–0.69 | Ambiguous — LLM Judge required, defer if still unclear |
| < 0.50 | Discard |

## Age Projection Formula

When `dob_exact` is missing, the Projected Current Age is:
```
Projected_Age = (Current_Year - reference_date.year) + Age_At_Event
```

`reference_date` resolution priority:
1. `event_date` — LLM-inferred date the event actually occurred (preferred)
2. `article_date` — article publication date from `media[].date` (fallback)
3. Neither present → flag `NO_REF_DATE`, skip temporal scoring

## Key Context Documents

- `context/final_blueprint_v1.md` — **Master design document** (locked v1): full Pydantic schema, field justifications, resolved design decisions, verification plan
- `context/data_schema.md` — Two-layer model details, normalization rules, flag vocabulary, gender gate truth table
- `context/scoring_logic.md` — Weightage matrix, temporal age projection worked example, multi-article consensus rules, audit log format
- `context/Pro-Match_Identity_Engine.md` — High-level architecture overview
