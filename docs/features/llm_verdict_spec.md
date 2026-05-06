# 📑 Feature Spec 04: Reasoning Engine (The Tier 2 Judge & Storyteller)
**Version:** 1.1.0 | **Component:** `engine/reasoning.py` | **Status:** FINAL
**Depends On:** `config/schema.py` (v1.1.0), `engine/scoring.py` (v1.0.0), `engine/extraction.py`
**External Dependency:** Gemini 1.5 Flash API (via `google-genai` SDK)

## 1. Objective & Scope
The Reasoning Engine provides a semantic safety layer over the mathematical score. It resolves ambiguities in "Amber" cases using cross-snippet consensus and generates a structured narrative justification. It strictly enforces the "Precision over Recall" principle by never overriding deterministic Hard-Rejects[cite: 1, 4].

## 2. Strict Execution Gates (The Triggers)
Before calling the Gemini API, `reasoning.py` MUST evaluate these gates. Failure to pass means the LLM is skipped entirely.
*   **Gate 1 (The Hard-Reject Guard):** If `MatchCard.tier_reached` == `"tier_1_hard_reject"`, the engine MUST immediately return the card unchanged. The LLM cannot upgrade a deterministic penalty[cite: 4].
*   **Gate 2 (The Confidence Window):** The LLM is only invoked if `final_confidence` is between 0.50 and 0.89, OR if `CONSENSUS_CONFLICT` is present in `flags`[cite: 4].
*   **Gate 3 (Snippet Floor):** `MatchCard.candidate_summary.supporting_snippets` must contain $\ge 1$ item. If empty, skip LLM, append `"REASONING_SKIPPED_NO_SNIPPETS"` to `flags`, and return the card.

## 3. Disaster Matrix & Resiliency
Network calls fail. The engine must handle these gracefully to protect the `BatchScoreResult` caller contract.

| Scenario | Detection | Recovery Strategy & Fallback |
| :--- | :--- | :--- |
| **API Timeout / Unavailable** | Request takes $> 15000$ ms or returns 5xx error. | Implement Exponential Backoff (max 2 retries). On exhaustion, set `llm_verdict` = `"System reasoning unavailable."`, leave `verdict_label` unchanged, append `"LLM_TIMEOUT"` to flags. |
| **Malformed JSON** | Output contains markdown fences (`` `json ``) or fails Pydantic validation. | Strip markdown fences automatically. If Pydantic parse fails, retry prompt once. On exhaustion, fallback to Timeout strategy above. |
| **Token Budget Exceeded** | Concatenated context exceeds 4000 tokens. | Truncate `supporting_snippets` by dropping the oldest articles (based on `article_date`) until the payload fits. Append `"LLM_CONTEXT_TRUNCATED"` to flags. |
| **Length Breach** | Generated `llm_verdict` $> 300$ characters. | Hard truncate at 297 characters and append `"..."`[cite: 1]. |
| **Rate Limiting (429)** | High batch volume hits API quotas. | Pause execution for $5$ seconds, retry up to 3 times. Fallback to Timeout strategy on exhaustion. |

## 4. Prompt Architecture & Deterministic Logic
The system prompt must enforce strict rules to eliminate non-deterministic "vibes-based" judgments.

*   **Language & Tone:** Output MUST be strictly in English. Prohibited phrases: "As an AI...", "I think...", "Based on the data...".
*   **Character Limits:** `reasoning_narrative` MUST be $\ge 50$ characters and $\le 300$ characters[cite: 1, 2].
*   **Machine-Readable Upgrade Rule:** The LLM may only output `"adjudication": "MATCH"` (upgrading the verdict) IF AND ONLY IF $\ge 2$ snippet summaries independently assert the identical profession AND location within the same 5-year window.
*   **Provenance Weighting:** The prompt must instruct the LLM to weight facts from `"government registry"` higher than `"blog"` or `"news"` when resolving conflicts.
*   **Unresolved Ambiguity:** If the LLM cannot confidently confirm the identity, it must output `"adjudication": "UNCERTAIN"`. The `verdict_label` remains "Review Required"[cite: 4].

## 5. Output Data Contract (Schema Updates)
To ensure reversibility and auditability, `config/schema.py` must be updated to include state preservation.
*   **New Field:** Add `pre_llm_verdict_label: Optional[str] = None` to `MatchCard`.
*   **State Preservation:** Before updating `verdict_label`, `reasoning.py` MUST copy the original value into `pre_llm_verdict_label`.
*   **Tier Flagging:** `tier_reached` MUST ONLY be updated to `"tier_2_llm_judge"` after a successful, validated Pydantic parse of the LLM output[cite: 2].

## 6. Acceptance Criteria (Automated Test Checklist)
1.  **Hard-Reject Preservation:** Pass a `MatchCard` with `tier_1_hard_reject` to the engine. Assert that the Gemini API is never called and the card is returned unmodified.
2.  **Conflict Resolution Structure:** For inputs with `CONSENSUS_CONFLICT`, assert that the resulting `llm_verdict` string contains the name of the conflicting field (e.g., "DOB", "Location") AND the word "resolved" or "prioritized".
3.  **Length Constraints:** Assert `50 <= len(llm_verdict) <= 300`.
4.  **Audit Trail:** Assert `pre_llm_verdict_label` exactly matches the Tier 1 `verdict_label` after the engine completes its run.