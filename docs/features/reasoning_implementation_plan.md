# Implementation Plan: `engine/reasoning.py` — Tier 2 LLM Judge & Storyteller

## Context

`engine/reasoning.py` currently exists as a two-function stub returning `None`. The spec (v1.1.0) defines it as the Tier 2 semantic safety layer of the Pro-Match Identity Engine. It is called by `scoring.py` when `final_confidence` is 0.50–0.89 OR a `CONSENSUS_CONFLICT` flag is present. Its job: use Gemini 1.5 Flash to either upgrade an "Amber" verdict to "Confirmed Match" or lock it at "Review Required", and populate the `llm_verdict` narrative field on `MatchCard`. The implementation must enforce the project's core "Precision over Recall" principle — hard-rejects from Tier 1 are immutable.

---

## Critical Files

| File | Role | Action |
|---|---|---|
| `engine/reasoning.py` | Main implementation target | Full rewrite |
| `engine/prompts.py` | Prompt storage | Add `REASONING_SYSTEM_PROMPT` + `build_reasoning_user_message()` |
| `config/schema.py` | Pydantic models | Add `pre_llm_verdict_label: Optional[str] = None` to `MatchCard` |
| `engine/scoring.py` | Caller | Fix `tier_reached` bug (line ~363) |
| `engine/llm_service.py` | Reuse — Gemini API wrapper | Read-only |

---

## Phase 0 — Schema Patch (`config/schema.py`)

Add one field to `MatchCard` (after `llm_verdict`):

```python
pre_llm_verdict_label: Optional[str] = None
```

This satisfies spec §5 reversibility/audit requirement.

---

## Phase 1 — Scoring.py Bug Fix (`engine/scoring.py`)

Current code (line ~361–365):
```python
updated = reasoning.evaluate(card)
if updated is not None:
    card = updated
card.tier_reached = "tier_2_llm_judge"   # ← BUG: always set
```

Fix — move `tier_reached` inside the success branch (reasoning.py sets it internally, scoring.py removes the assignment):
```python
updated = reasoning.evaluate(card)
if updated is not None:
    card = updated
# tier_reached is now set by reasoning.py only on success
```

Spec rule: "`tier_reached` MUST ONLY be updated to `tier_2_llm_judge` after a successful, validated Pydantic parse."

---

## Phase 2 — Prompt Layer (`engine/prompts.py`)

### 2a. New constant: `REASONING_SYSTEM_PROMPT`

Rules enforced in the system prompt:
- Output MUST be valid JSON only — no markdown fences, no prose
- Language: English only; prohibited phrases: "As an AI", "I think", "Based on the data"
- `reasoning_narrative`: ≥ 50 and ≤ 300 characters
- Upgrade rule: output `"adjudication": "MATCH"` ONLY IF ≥ 2 snippet summaries independently assert the **same profession AND same location within a 5-year window**
- Provenance weighting: treat `source_type = "government_registry"` as higher-confidence than `"blog"` or `"news"`
- If unresolved: output `"adjudication": "UNCERTAIN"`
- Privacy guard: never mention full PAN/Aadhar numbers; call them "matching identifiers"
- For `CONSENSUS_CONFLICT` inputs: `reasoning_narrative` MUST name the conflicting field AND contain the word "resolved" or "prioritized"

### 2b. New function: `build_reasoning_user_message(card: MatchCard) -> str`

Builds the user-turn payload as a JSON string containing:
- `context`: `current_confidence`, `current_verdict`, `active_flags`
- `user_profile`: extracted from `card.comparison_rows` (name, dob, gender, location, profession, identifier_types_present — values masked)
- `candidate_profile`: `name`, `identity_summary`, `source_provenance`
- `snippet_summaries`: `{identity_summary, profession_raw, locations, article_date}` per snippet — truncated to 12 000 chars (drop oldest by `article_date`)

---

## Phase 3 — Response Schema (`config/schema.py`)

```python
class ReasoningOutput(BaseModel):
    adjudication: Literal["MATCH", "UNCERTAIN"]
    reasoning_narrative: str = Field(..., min_length=50)
```

Placed in `config/schema.py` — consistent with project pattern of centralising schemas.

---

## Phase 4 — Full `evaluate()` Implementation (`engine/reasoning.py`)

### Function signature:
```python
def evaluate(card: MatchCard) -> MatchCard
```

### Execution flow:

```
evaluate(card)
  │
  ├─ Gate 1: tier_reached == "tier_1_hard_reject"?
  │    └─ YES → return card unchanged (LLM never called)
  │
  ├─ Gate 2: 0.50 ≤ final_confidence ≤ 0.89 OR "CONSENSUS_CONFLICT" in flags?
  │    └─ NO  → return card unchanged
  │
  ├─ Gate 3: len(supporting_snippets) >= 1?
  │    └─ NO  → append "REASONING_SKIPPED_NO_SNIPPETS" to card.flags; return card
  │
  ├─ Preserve audit state:
  │    card.pre_llm_verdict_label = card.verdict_label
  │
  ├─ Build prompt + call _call_llm()
  │
  ├─ If output is None (exhausted retries):
  │    card.llm_verdict = "System reasoning unavailable."
  │    card.flags += ["LLM_TIMEOUT"]
  │    return card   (tier_reached NOT escalated)
  │
  ├─ Length guard: truncate to 297 + "..." if > 300
  │
  ├─ Update card:
  │    card.llm_verdict = narrative
  │    MATCH  → verdict_label="Confirmed Match", verdict_color="GREEN"
  │    UNCERTAIN → verdict_label="Review Required", verdict_color="AMBER"
  │    card.tier_reached = "tier_2_llm_judge"   ← only on success
  │
  └─ return card
```

---

## Phase 5 — Resiliency / Disaster Handling

| Scenario | Detection | Recovery |
|---|---|---|
| API Timeout / 5xx | Request fails or 5xx | Retry once (2s backoff). On exhaustion: `LLM_TIMEOUT` fallback |
| Malformed JSON / parse failure | `ExtractionError` or `ValidationError` | Retry once. On exhaustion → `LLM_TIMEOUT` fallback |
| Token budget exceeded | User message > 12 000 chars | Drop oldest snippets until fits; `LLM_CONTEXT_TRUNCATED` flag |
| Length breach | `len(narrative) > 300` | Hard truncate at 297 chars + `"..."` |
| Rate limiting (429) | `ExtractionError.code == RATE_LIMIT_EXHAUSTED` | Already handled by `llm_service.py` |

---

## Phase 6 — Acceptance Criteria Mapping

| AC | Implementation |
|---|---|
| AC1: Hard-Reject Preservation | Gate 1 — Gemini never called |
| AC2: Conflict Resolution Structure | System prompt enforces field name + "resolved"/"prioritized" |
| AC3: Length Constraints `50 ≤ len ≤ 300` | `ReasoningOutput.min_length=50` + code truncation at 300 |
| AC4: Audit Trail | `pre_llm_verdict_label` saved before mutation |

---

## Verification Plan

1. **Gate 1 (Hard-Reject):** Call `evaluate()` with `tier_1_hard_reject` card. Assert Gemini never called. Card returned unmodified.
2. **Gate 3 (No Snippets):** Empty `supporting_snippets`. Assert `"REASONING_SKIPPED_NO_SNIPPETS"` in flags.
3. **MATCH upgrade:** Mock Gemini → `{"adjudication": "MATCH", "reasoning_narrative": "50+ chars"}`. Assert GREEN verdict + audit trail.
4. **Length truncation:** Mock 350-char narrative. Assert `len(llm_verdict) == 300` ending with `"..."`.
5. **Timeout fallback:** Mock ExtractionError after retries. Assert sentinel `llm_verdict` + `"LLM_TIMEOUT"` flag.
6. **Integration (test_scenario_2):** Run `batch_score`. Assert `tier_2_llm_judge` + non-null `llm_verdict` on Amber candidate.
