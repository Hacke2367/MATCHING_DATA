# Implementation Plan: Scoring Engine (`engine/scoring.py`)
**Status:** IMPLEMENTED | **Date:** 2026-05-06 | **Author:** Claude Code

## Context

Layer 2 of the Pro-Match Identity Engine was a stub (`calculate_score(extracted_data): pass`).
This plan documents the implementation of the full Scoring Engine, which transforms two
`CandidateIdentity` objects into a fully-populated `MatchCard` using a weighted heuristic formula.

Implements: `docs/features/scoring_system_spec.md` (v1.0.0), aligned to `context/scoring_logic.md`.

---

## Files Modified

| File | Change |
|---|---|
| `engine/scoring.py` | Full implementation (replaced stub) |
| `config/schema.py` | Added `ComparisonRow`, `MatchCard`, `BatchScoreResult` models |
| `engine/reasoning.py` | Added `evaluate(card: MatchCard) -> MatchCard | None` stub |

---

## Architecture

```
score(anchor, candidate) -> MatchCard
    │
    ├── Tier 0: _norm_id() exact match on {PAN, AADHAR, PASSPORT, SSN}
    │           → final_confidence = 1.0, tier_reached = "tier_0_id_match"
    │
    ├── Tier 1: Heuristic scoring
    │   ├── Gender gate: both known + mismatch → hard_reject
    │   ├── _score_name():     JW > 0.95 → 0.20 | token match → 0.15 | JW > 0.88 → 0.10
    │   ├── _score_location(): sub_district 0.06 | city 0.03 | state 0.01
    │   ├── Age score:         gap ≤ 2 → 0.10 | ≤ 5 → 0.05 | > 5 → hard_reject
    │   ├── Identifier score:  DIN/VAT/GST/etc exact match → 0.60
    │   ├── Penalties:         CONSENSUS_CONFLICT -0.15, NAME_AMBIGUOUS_IN_TEXT -0.10
    │   └── Floor:             max(0.0, raw_score)
    │
    └── Tier 2: reasoning.evaluate(card) if 0.50 ≤ score ≤ 0.89 OR CONSENSUS_CONFLICT
                → tier_reached = "tier_2_llm_judge"

batch_score(anchor, candidates) -> BatchScoreResult
    → Scores all candidates, sorts desc by final_confidence, selects best_match
```

---

## Weight Matrix (aligned with `scoring_logic.md §2`)

| Field | Weight | Algorithm |
|---|---|---|
| Identifiers (Tier-0) | 1.0 total | Exact match on PAN/AADHAR/PASSPORT/SSN → instant match |
| Identifiers (Tier-1) | 0.60 | Exact match on DIN/VAT/GST/LEI/CASE_ID/etc |
| Name / Aliases | 0.20 | Jaro-Winkler (jellyfish) — first-match-wins rules |
| Location | 0.10 | Hierarchical subset: sub_district→city→state |
| Projected Age | 0.10 | Calendar-accurate age from dob_exact or projection formula |

**Null-tolerant denominator:** Missing fields are excluded from both numerator and denominator — never treated as zero.

---

## Normalization Contract

- **Identifiers:** `uppercase().strip_spaces().strip_hyphens()`
- **Names:** `NFKD → ASCII → lowercase → strip_titles(Mr/Ms/Dr/Shri/Smt) → strip_spaces()`
- **Normalization runs in `scoring.py`** — does not depend on extraction having pre-normalized.

---

## Verdict Gauge

| final_confidence | verdict_color | verdict_label |
|---|---|---|
| 1.0 (Tier 0) | GREEN | Confirmed Match |
| ≥ 0.90 | GREEN | Confirmed Match |
| 0.50 – 0.89 | AMBER | Review Required |
| < 0.50 | RED | No Match |
| hard_reject | RED | No Match |

---

## Acceptance Criteria (all pass)

| Test | Input | Result |
|---|---|---|
| Case-insensitive ID | anchor PAN="pan123" vs cand PAN="PAN123" | tier_0_id_match, 1.0 |
| CONSENSUS_CONFLICT + name match | name JW=1.0, flag CONSENSUS_CONFLICT | 0.85 AMBER, tier_2_llm_judge |
| Gender hard reject | both known, mismatch | tier_1_hard_reject, 0.0 |
| Temporal hard reject | age gap > 5 yrs | tier_1_hard_reject, 0.0 |
| Negative guard | score after penalties < 0 | floor at 0.0 |
| Null tolerance | no location data | location excluded from denominator |

---

## Dependencies

- `jellyfish >= 1.0` (already in `requirements.txt`) — Jaro-Winkler implementation
- `engine/reasoning.py` — must expose `evaluate(card: MatchCard) -> MatchCard | None`
- `config/schema.py` v1.1.0 — `ComparisonRow`, `MatchCard`, `BatchScoreResult`
