My bad. I got ahead of myself. You're right—our protocol is: **I provide the Spec (What/Why), and you use Claude for the Implementation Plan.** I broke that by jumping into the "How."

The Reviewer was brutal but correct. I've analyzed the report and split the requirements into three distinct, surgical specs to avoid "Scope Violation" and fix the architectural drift.

### 📝 Mistakes Noted (The "Hall of Shame")
1.  **Scope Violation:** Mixing Orchestration, Routing, and Prompting in one document.
2.  **Path Drift:** Using `backend/src/` instead of the canonical root paths.
3.  **Missing Anchor:** Defining an "anchored" extraction but forgetting to pass the `user_identity` into the function signature.
4.  **Vague Metrics:** Using terms like "High-Signal" and "N" without defining them.
5.  **Silent Failures:** Ignoring what happens when Gemini returns prose or when *all* snippets fail validation.

---

### 📑 Feature Spec 02a: Prompt Engineering (The Instruction Vault)
**Component:** `engine/prompts.py` | **Status:** FINAL

#### 1. The "What" (Objective)
Establish a centralized, versioned repository for LLM instructions. This module must provide the `EXTRACTION_SYSTEM_PROMPT` and a helper to package the "Anchor + Snippet" payload.

#### 2. The "Why" (Strategic Value)
Centralizing prompts prevents "prompt drift" across the engine. By forcing a version constant (`PROMPT_VERSION`), we ensure that every extraction is audit-trailed, which is a mandatory requirement for KYC/Identity systems.

#### 3. Constraints
*   **Prompt Provenance:** Must export `PROMPT_VERSION = "1.0.0"`.
*   **Input Shape:** The prompt must expect a JSON-structured user message containing an `anchor` (User KYC) and a `snippet` (Media article).
*   **Anti-Hallucination:** Instructions must strictly forbid computing `projected_current_age`. It must only extract `age_at_event` and `event_date`.

---

### 📑 Feature Spec 02b: LLM Routing (LLM Service)
**Component:** `engine/llm_service.py` | **Status:** FINAL

#### 1. The "What" (Objective)
Provide a hardened interface for Gemini 1.5 Flash. This layer handles connectivity, retry logic, and raw JSON parsing.

#### 2. The "Why" (Strategic Value)
Gemini can sometimes return markdown code fences (```json ... ```) even in JSON mode. This layer acts as a "De-serialization Guard" that cleans the raw string before passing it to Pydantic, preventing the orchestrator from crashing on string-to-dict errors.

#### 3. Interface Contract
*   **Function:** `call_gemini(system_prompt: str, user_message: str, response_schema: dict) -> dict`
*   **Enforcement:** Use Gemini's `response_mime_type="application/json"` and the `response_schema` parameter.
*   **Error Handling:**
    *   **Rate Limits:** Raise `ExtractionError` after 3 failed retries.
    *   **Parse Failures:** If JSON parsing fails (invalid string), raise `ExtractionError` with a "PRE_VALIDATION_PARSE_FAILURE" code.

---

### 📑 Feature Spec 02c: Orchestration (Extraction Engine)
**Component:** `engine/extraction.py` | **Status:** FINAL
**Depends On:** `02a`, `02b`, `config/schema.py`

#### 1. The "What" (Objective)
Orchestrate the extraction of identity data from multiple snippets and aggregate them into a single, symmetric `CandidateIdentity` object.

#### 2. The "Why" (Strategic Value)
Individual news snippets are often incomplete. This module performs "Consensus Aggregation"—if three snippets say a person is "Male" and one is "Unknown," it concludes "Male." This reduces noise and builds a high-confidence identity profile from messy data.

#### 3. Functional Contract
*   **Interface:** `extract_candidate(user: CandidateIdentity, file_path: str, snippet_indices: list[int] = None) -> CandidateIdentity | None`
*   **Snippet Selection ($N$):** Default $N=5$. If `snippet_indices` is `None`, take the first 5 snippets from `media[]`.
*   **Aggregation Rules (via `scoring_logic.md §6`):**
    *   **Consensus Fields (Gender/DOB):** Most-frequent non-null value.
    *   **Conflict Logic:** If snippets provide conflicting non-null values, set the `CONSENSUS_CONFLICT` flag.
    *   **List Fields (Aliases/Locations):** Perform a Unique Set Union.
*   **Temporal Calculation:** Strictly compute `projected_current_age` in Python using the `(Current_Year - Event_Year) + Age_at_Event` formula.

#### 4. Guardrails & Disaster Matrix
*   **Total Failure:** If *zero* snippets pass Pydantic validation, the function must return `None`.
*   **Version Check:** At the module level, assert `config.schema.SCHEMA_VERSION == "1.1.0"`. Fail-fast on mismatch.
*   **Bounds Check:** Truncate `snippet_indices` to the actual length of the `media[]` array to prevent `IndexError`.

---
