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

## Architecture: 3-Layer Engine + Dashboard Test-Bench

The engine runs in **batch mode**: 1 Source A vs. *N* Source B candidates. The dashboard (Phase 5) is the human-facing surface.

```
User KYC JSON ──────────────────────────────────────► CandidateIdentity ─┐
                                                                           ├──► scoring.py ──► reasoning.py ──► BatchScoreResult ──► dashboard
Candidate JSON[] ──► SnippetIdentity (per article) ──► CandidateIdentity ─┘                                       (MatchCard per candidate,
                          extraction.py                  (aggregated)                                              best_match selected)
                          (Layer 1)                       (Layer 1)              (Layer 2)       (Layer 3)
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

**Engine Output** (`BatchScoreResult`): Top-level entry point output — contains `user`, `best_match` (top-ranked `MatchCard` or null if all hard-rejected), `all_results` (full list ordered desc by `final_confidence`, includes hard-rejects), and `run_metadata`. Persisted to `outputs/final_match.json`.

**Test data** (`data/`): 5 synthetic Source A + Source B pairs in `data/actual_user/test_scenario_{1..5}.json` and `data/potential_matches/test_scenario_{1..5}.json` covering Tier 0 ID match, fuzzy aliases + DOB year fallback, temporal projection (2005 article → 2026 user), geo-hierarchy subset, and dual hard-reject (gender + age).

## Schemas (`config/schema.py`)

Six Pydantic models (to be implemented; full definitions in `context/data_schema.md` §3, §4, §10 and `context/final_blueprint_v1.md`):

**Identity layer:**
- `GeoLocation` — hierarchical location: `sub_district`, `city`, `state`, `country`, `country_code`, `raw`
- `SnippetIdentity` — per-article extraction result (Source B only); carries both `article_date` and `event_date`
- `CandidateIdentity` — symmetric comparable form used by both sides for scoring

**Dashboard contract layer:**
- `ComparisonRow` — one side-by-side table row: `field_label`, `user_value`, `candidate_value`, `match_status` (`match`/`partial`/`mismatch`/`missing`), `contribution_pts`
- `MatchCard` — per-candidate render contract: verdict (color/label/confidence/tier), `comparison_rows`, `score_breakdown` + `weights_used` + `denominator`, `penalties_applied`, `identity_summary`, `llm_verdict`, `risk_types`, `source_provenance`, `flags`
- `BatchScoreResult` — engine entry-point output: `user`, `best_match`, `all_results`, `run_metadata`

**Important**: `MatchCard` is the engine's output contract. `engine/scoring.py` must populate every field — the dashboard layer is purely presentational, no business logic in the front-end.

## Verdict Gauge (Dashboard / Test-Bench)

Visual signal derived from `final_confidence` and any hard-reject penalties:

| Score Band | Gauge | `verdict_label` |
|---|---|---|
| ≥ 0.90 **OR** Tier 0 ID match | 🟢 **GREEN** | Confirmed Match |
| 0.70 – 0.89 | 🟡 **AMBER** | Review Required (LLM Reasoner shown) |
| 0.50 – 0.69 | 🟡 **AMBER** | Deferred — Low Confidence (manual override) |
| < 0.50 **OR** Hard-Reject | 🔴 **RED** | No Match / Discard |

A 🔴 RED on a hard-reject case is a **success signal** — the safety gates protected the user from a false positive.

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

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
