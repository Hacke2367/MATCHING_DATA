
---

# Scoring Logic: Weighted Identity Resolution Engine (v1)

## 1. Scoring Philosophy
The engine calculates a Confidence Score ($S$) between 0.0 and 1.0.
* **Precision**: weighted towards unique identifiers.
* **Safety**: high negative penalties for logical impossibilities (Gender / Age).
* **Consensus**: when multiple `SnippetIdentity` instances exist for one candidate, the engine averages scores per snippet but prioritizes the highest-confidence article and uses cross-snippet consensus to validate identity.
* **Null-tolerant**: missing data on either side is degraded gracefully via flags, never treated as zero.

---

## 2. The Weightage Matrix (Base 100)

| Field | Weight ($w_i$) | Matching Algorithm |
| :--- | :--- | :--- |
| **Unique Identifiers** | 60 Points | Exact Match: Boolean (1 or 0) per shared ID type |
| **Name / Aliases** | 20 Points | Jaro-Winkler: best of (`full_name` OR any alias from either side) |
| **Location History** | 10 Points | Hierarchical Subset Check: User location ⊆ Candidate location |
| **Projected Age** | 10 Points | Variance Check: full points for ±3 years |

Identifier matching requires **same ID type on both sides** (PAN ↔ PAN, DIN ↔ DIN). Cross-type matches are not credited.

---

## 3. Mathematical Formula

$$S = \left( \frac{\sum (Weight_i \cdot Similarity_i)}{\sum Weight_i} \right) - Penalties$$

When a field is unscoreable on either side (missing on both, or no shared identifier type), it is excluded from both numerator and denominator — *not* treated as zero. This preserves the score's meaning when partial data is available.

---

## 4. Hard Rejection & Penalties (Checkpoint 2)

### Gender Safety Gate
| User | Candidate | Action |
| :--- | :--- | :--- |
| Known (M/F) | Known (M/F), match | Pass |
| Known (M/F) | Known (M/F), mismatch | **Hard-Reject (-100 pts)** |
| Known (M/F) | Unknown | Neutral, no penalty |
| Unknown | Known (M/F) | Neutral, no penalty |
| Unknown | Unknown | Neutral, gate skipped; flag `GENDER_NULL_BOTH_SIDES` |

### Temporal Age Conflict
If $|User\_Current\_Age - Projected\_Age| > 5$ years → **Hard-Reject (-100 pts)**.

### Summary Contradiction
If `identity_summary` is logically impossible relative to user (e.g. user was 5 years old at the time of a record event) → **Hard-Reject**.

---

## 5. Temporal Age Projection

When `dob_exact` is absent on the candidate side, current age is projected from the snippet's narrative anchor.

### Formula
$$Projected\_Current\_Age = (Current\_Year - Reference\_Date.year) + Age\_At\_Event$$

### Reference Date Resolution
The `reference_date` field on `CandidateIdentity` is the resolved anchor. It is set in this priority order:

1. **`event_date`** — when the LLM extracts the event's actual date with confidence (e.g. a 2026 article describing a 2005 trial → event_date = 2005). This is preferred because the snippet's age refers to the event, not the article publication.
2. **`article_date`** — fallback when event date is ambiguous. From `media[].date` directly.
3. **None** — if neither is available, set flag `NO_REF_DATE`, skip the temporal score, and reduce the denominator accordingly.

### Worked Example
A 2026 article about Sandeep Golechha says "Arif Chandoo, Amjad Baig, Sandeep Golechha ... stood accused of a fraud" — but the article also mentions the trial collapsed in 2005. LLM extracts:
* `article_date = 2026-02-22`
* `event_date = 2005-06-25` (confident)
* `age_at_event = 38` (LLM-inferred from contextual cues, or null)

Projection uses `reference_date = event_date = 2005`:
$$Projected\_Age = (2026 - 2005) + 38 = 59$$

If we had wrongly used `article_date`, the projected age would be 38, leading to a major false-negative against a 59-year-old user.

### Multi-Snippet Age Reconciliation
When several snippets each give an age, take the **median projection** as the candidate-level value, and flag `CONSENSUS_CONFLICT` if any pair of projections disagree by more than 5 years.

---

## 6. Multi-Article Consensus (Layer-3 LLM Judge)

When a candidate has multiple `supporting_snippets`, identity resolution is not just an arithmetic average — the Judge must verify all snippets describe the **same entity**.

### Consensus Rule
1. **Trust the majority of articles/identifiers**. If 4 of 5 snippets place "Sandeep Golechha" in London + UK fraud context, and 1 snippet describes a different person with the same name, the outlier is discarded.
2. **Compare `identity_summary` across snippets**. The Judge reads each one-line fact-sheet and asks: *Are these describing one entity or two?*
3. **Source provenance weighting**. Government registry > government press release > major news > blog. Conflicting low-credibility snippets cannot override high-credibility consensus.

### Aggregation rules during Snippet → Candidate consolidation
| Field | Aggregation rule |
| :--- | :--- |
| `aliases`, `locations`, `risk_types`, `source_provenance` | Set-union across all snippets |
| `gender`, `dob_exact`, `dob_year` | Consensus = most-frequent non-null; on disagreement, flag `CONSENSUS_CONFLICT` |
| `identifiers` | Union; if same ID type has different values, flag `CONSENSUS_CONFLICT` |
| `projected_current_age` | Median across snippets that have age_at_event |
| `reference_date` | From the snippet whose extraction won the projection (highest confidence + most recent event_date) |
| `identity_summary` | LLM-generated synthesis describing the consensus entity, max 200 chars |

### Tiered Execution
* **Tier 0 (ID Match)**: any 100% identifier match → skip directly to final verdict.
* **Tier 1 (Heuristics)**: pure-Python computation of name, age, location, identifier scores. No LLM call.
* **Tier 2 (Consensus & Reasoner)**: invoked only when Tier 1 score is in the ambiguous band (0.50–0.89) OR when `CONSENSUS_CONFLICT` is flagged. The LLM Judge then reviews `supporting_snippets` and produces a final verdict.

---

## 7. Confidence Thresholds & Verdict Gauge

The Test-Bench dashboard renders a visual signal derived from `final_confidence` and any hard-reject penalties.

| Score Band | Gauge | `verdict_label` | Underlying behaviour |
| :--- | :--- | :--- | :--- |
| ≥ 0.90 **OR** Tier 0 ID match | 🟢 **GREEN** | Confirmed Match | Auto-verified, no human review needed |
| 0.70 – 0.89 | 🟡 **AMBER** | Review Required | LLM Reasoner justification must be shown to reviewer |
| 0.50 – 0.69 | 🟡 **AMBER** | Deferred — Low Confidence | LLM Judge invoked; reviewer must manually accept or reject |
| < 0.50 **OR** Hard-Reject triggered | 🔴 **RED** | No Match / Discard | Engine successfully blocked a False Positive |

**Important**: a 🔴 RED verdict caused by a hard-reject (gender mismatch, age conflict, summary contradiction) is a **success signal**, not a failure — it means the safety gates protected the user from a false positive.

---

## 8. Audit Log Requirement

Every result must produce an explainable record. Minimum fields:

```json
{
  "candidate_id": "9MEHSAOULQNVRR4",
  "user_record_id": "OLPGB17769307040",
  "reference_date_used": "2005-06-25",
  "reference_date_source": "event_date",
  "projected_current_age": 59,
  "user_current_age": 21,
  "age_delta_years": 38,
  "gender_match": "neutral_dual_null",
  "alias_match_found": true,
  "best_alias_pair": ["ankit pankaj dubey", "ankit dubey"],
  "identifier_matches": [],
  "location_subset": false,
  "consensus_status": "single_entity",
  "breakdown": {
    "id": 0,
    "name": 18,
    "age": 0,
    "location": 0
  },
  "denominator_used": 30,
  "penalties_applied": ["TEMPORAL_AGE_CONFLICT"],
  "flags": ["NO_IDENTIFIERS", "GENDER_NULL_BOTH_SIDES", "AGE_PROJECTED"],
  "final_confidence": 0.06,
  "tier_reached": "tier_1_hard_reject",
  "llm_verdict": null
}
```

The `audit_log` must show exactly how the **Reference Date selection**, **Projected Age**, and **Gender Match** influenced the final 0.0–1.0 score.

---

## 9. Batch Scoring & Best-Match Selection

The dashboard always invokes the engine in batch mode: one Source A vs. *N* Source B candidates.

### Engine contract
* Score every candidate independently against the same User.
* Return a single `BatchScoreResult` (see `data_schema.md` §10) containing:
  * `best_match` — highest `final_confidence` candidate (or `None` if all hard-rejected).
  * `all_results` — full list ordered descending by `final_confidence`, including hard-rejects (so the dashboard can show *why* a name-matching candidate was discarded).

### Tie-breaker order
When two candidates tie on `final_confidence`:
1. Higher `extraction_confidence`.
2. More `supporting_snippets`.
3. Higher source-provenance weight (government registry > major news > blog).
4. Most recent `last_updated_utc` on the candidate doc.

### Hard-rejects in the batch
A hard-rejected candidate still appears in `all_results` with its 🔴 RED verdict and `penalties_applied` populated — the dashboard surfaces it so the reviewer can audit what the engine rejected and why.

---

## 10. Dashboard Output Contract

The engine's output is the dashboard's contract. `engine/scoring.py` must populate every field of `MatchCard` so the UI is purely presentational.

Required population per MatchCard:
* `verdict_color` and `verdict_label` derived from §7 gauge logic.
* `comparison_rows` — pre-rendered side-by-side rows for at minimum: Name, DOB / Projected Age, Gender, Location, Profession, and every populated identifier.
* `score_breakdown` and `weights_used` — both sides of the weight ratio so the audit table can show "earned X of Y points" per field.
* `denominator` — the actual sum of weights used (excludes unscoreable fields per §3 — never treat missing as zero).
* `flags` — every operational flag that fired during extraction or scoring.
* `llm_verdict` — populated only when Tier 2 was reached.

No field on `MatchCard` may be left as null when the engine has the data to compute it; the dashboard layer must not perform business logic.
