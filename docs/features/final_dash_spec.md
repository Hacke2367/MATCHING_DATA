# 📑 Feature Spec 05: Batch Orchestrator (The Master Pipeline & Persistence Layer)
**Version:** 1.2.0 | **Component:** `engine/orchestrator.py` | **Status:** FINAL
**Depends On:** `engine/extraction.py`, `engine/scoring.py`, `config/schema.py`, `engine/errors.py` (New)
**External Dependency:** `pathlib`, `uuid`, `json`

## 1. Objective & Scope
The Batch Orchestrator coordinates the pipeline. **Crucial Architecture Fix:** The Orchestrator ONLY calls `extraction.extract_candidate()` and `scoring.score()`. It does **NOT** call `reasoning.evaluate()` directly, as `scoring.py` owns the Tier-2 handoff. The engine ensures fault isolation and atomic disk persistence.

## 2. Versioning & Dependencies
*   **Version Source:** This module defines `ORCHESTRATOR_VERSION = "1.2.0"` locally. It does not import scoring's version.
*   **Error Module:** A new file `engine/errors.py` MUST be created containing:
    ```python
    class FatalOrchestrationError(Exception):
        def __init__(self, message: str, user_file_path: str, cause: Exception = None):
            self.user_file_path = user_file_path
            self.cause = cause
            super().__init__(message)
    ```

## 3. Strict Execution Gates (Ordered Precedence)
1.  **Gate 1 (File Discovery):** Scan `candidates_dir` using `pathlib.Path.glob("*.json")` (strictly ignoring hidden or non-JSON files). If empty $\rightarrow$ Return `(BatchScoreResult(...), None)` without writing to disk.
2.  **Gate 2 (Storage Readiness):** Create `saved_reports/` (relative to CWD). If `OSError` or `PermissionError` occurs, raise `FatalOrchestrationError`.
3.  **Gate 3 (Anchor Validation):** Execute `extract_user(anchor_filepath)`. If it raises an exception or returns `None`, raise `FatalOrchestrationError` including the path and cause.

## 4. Disaster Matrix & Resiliency

| Scenario | Detection | Recovery Strategy & Sentinel Values |
| :--- | :--- | :--- |
| **Candidate Parse/Score Crash** | `ValueError`, `ValidationError`, `JSONDecodeError` during processing. | **Isolate:** Do not crash. Create a Dummy MatchCard with strict sentinels: `candidate_id="ERROR"`, `candidate_summary=CandidateIdentity(source="candidate", record_id="err", full_name="Parse Error", identity_summary="Failed")`, `verdict_color="RED"`, `verdict_label="Processing Failed"`, `final_confidence=0.0`, `tier_reached="tier_1_hard_reject"`, `flags=["ORCHESTRATOR_PARSE_ERROR", f"error_detail: {str(exc)[:50]}"]`. |
| **Atomic Disk Write Failure** | `OSError` (including ENOSPC/DiskFull) during `.model_dump_json()`. | **Graceful Degradation:** Log error. Return the tuple `(result_object, None)` so the caller knows the result is purely in-memory. |
| **Batch Timeout** | A single candidate hangs indefinitely. | **Accepted Risk:** For MVP, sequential execution has NO enforced timeout per candidate. |
| **All Candidates Rejected** | All MatchCards are RED. | `best_match` MUST explicitly be set to `None`. |

## 5. Execution Pipeline & Sorting Cascade
*   **Step 1:** For each `.json` file in `candidates_dir`, run extraction and `scoring.score(anchor, candidate)`.
*   **Step 2:** Append all outputs (including Dummy error cards) to `all_results`.
*   **Step 3:** Sort `all_results` descending:
    1.  `final_confidence`
    2.  `candidate_summary.extraction_confidence` (fallback to 0.0 if None)
    3.  `len(candidate_summary.supporting_snippets)`
*   **Step 4:** Set `best_match` to index `[0]` ONLY IF its `verdict_color` is `"GREEN"` or `"AMBER"`. Otherwise, `None`.
*   **Step 5:** Populate `run_metadata` with `run_started_utc`, `run_finished_utc`, `candidate_count` (int string), and `engine_version` (ORCHESTRATOR_VERSION).

## 6. Output Data Contract (Atomic Persistence)
*   **Return Signature:** `def run_batch(...) -> tuple[BatchScoreResult, Optional[str]]:` (Returns the object AND the saved file path, or `None` if saving failed).
*   **Timestamp & Collision Prevention:** Filename MUST use format: `match_{anchor_id}_{YYYYMMDDTHHMMSS_ffffff}_{uuid4().hex[:6]}.json`.
*   **Atomic Write:**
    1. Write JSON data to a temporary file: `temp_path = final_path + ".tmp"`.
    2. Execute `os.rename(temp_path, final_path)` to ensure the file is never left half-written on disk.

## 7. Acceptance Criteria (Automated Tests)
1.  **Architecture Verification:** Assert that `orchestrator.py` never imports or calls `reasoning.evaluate()` directly.
2.  **Sentinel Integrity:** Pass a completely corrupted JSON. Assert the output `all_results` contains a MatchCard matching the exact sentinel values defined in the Disaster Matrix (e.g., `full_name="Parse Error"`).
3.  **Atomic Save Contract:** Assert that successful runs return `(BatchScoreResult, "saved_reports/match_...json")`. Assert that if `os.rename` is mocked to raise `OSError`, it returns `(BatchScoreResult, None)`.
4.  **JSON Schema Validation:** Assert the saved file reads back into a dictionary containing exactly the keys: `["user", "best_match", "all_results", "run_metadata"]`.
