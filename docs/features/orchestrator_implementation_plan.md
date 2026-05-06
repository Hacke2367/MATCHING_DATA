# Implementation Plan: `engine/orchestrator.py` — Batch Orchestrator (Master Pipeline & Persistence Layer)

## Context

`engine/orchestrator.py` does not exist. Neither does `engine/errors.py`. The spec (v1.2.0) defines orchestrator.py as the single public entry point for the entire Pro-Match pipeline: it calls extraction → scoring (which internally handles Tier-2 reasoning), sorts results deterministically, and persists the `BatchScoreResult` to disk atomically. Fault isolation is a first-class requirement — a single corrupt candidate file must not crash the batch.

A practical ordering note: the spec's Gate 1 (file discovery) fires before Gate 3 (anchor extraction), but `BatchScoreResult.user: CandidateIdentity` is a required non-optional field. To satisfy the return type contract on an empty-dir early return, anchor extraction must happen before the early return — anchor extraction is cheap (no LLM, pure JSON mapping). The implementation therefore: discovers files → extracts anchor → early-returns if empty → continues with Gate 2 (storage).

---

## Critical Files

| File | Action |
|---|---|
| `engine/errors.py` | **Created** — FatalOrchestrationError definition |
| `engine/orchestrator.py` | **Created** — Main implementation |

---

## Phase 0 — `engine/errors.py`

```python
class FatalOrchestrationError(Exception):
    def __init__(self, message: str, user_file_path: str, cause: Exception | None = None):
        self.user_file_path = user_file_path
        self.cause = cause
        super().__init__(message)
```

---

## Phase 1 — `engine/orchestrator.py`

### Public API

```python
ORCHESTRATOR_VERSION = "1.2.0"
REPORTS_DIR = Path("saved_reports")   # relative to CWD

def run_batch(anchor_filepath: str, candidates_dir: str) -> tuple[BatchScoreResult, Optional[str]]
```

### Execution Flow

```
run_batch(anchor_filepath, candidates_dir)
  │
  ├─ 1. Record run_started_utc
  │
  ├─ 2. File Discovery (Gate 1):
  │       candidate_files = sorted(Path(candidates_dir).glob("*.json"))
  │
  ├─ 3. Anchor Extraction:
  │       anchor = extraction.extract_user(anchor_filepath)
  │       on failure → raise FatalOrchestrationError(msg, path, exc)
  │
  ├─ 4. Gate 1 early-return:
  │       if not candidate_files → return (empty BatchScoreResult, None)
  │
  ├─ 5. Gate 2 — Storage Readiness:
  │       REPORTS_DIR.mkdir(parents=True, exist_ok=True)
  │       on OSError → raise FatalOrchestrationError
  │
  ├─ 6. Processing Loop:
  │       for file_path in candidate_files:
  │         try:
  │           candidate = extraction.extract_candidate(anchor, str(file_path))
  │           if candidate is None: raise ValueError(...)
  │           card = scoring.score(anchor, candidate)
  │         except Exception as exc:
  │           card = _build_dummy_card(file_path.stem, exc)
  │         all_results.append(card)
  │
  ├─ 7. Sort descending:
  │       key = (-final_confidence, -extraction_confidence, -len(snippets))
  │
  ├─ 8. Select best_match:
  │       all_results[0] if verdict_color in ("GREEN", "AMBER") else None
  │
  ├─ 9. Build BatchScoreResult
  │
  └─ 10. Atomic Write:
          temp = REPORTS_DIR / (filename + ".tmp")
          temp.write_text(result.model_dump_json())
          os.rename(temp, final_path)
          on OSError → log CRITICAL, cleanup temp, return (result, None)
```

### Timestamp + Filename Format

```python
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")  # microsecond resolution
filename = f"match_{anchor.record_id}_{timestamp}_{uuid4().hex[:6]}.json"
```

### Dummy MatchCard Sentinel Values

```python
MatchCard(
    candidate_id=record_id,
    candidate_summary=CandidateIdentity(
        source="candidate", record_id=record_id,
        full_name="Parse Error",       # min_length=2 satisfied
        identity_summary="Failed",
    ),
    verdict_color="RED", verdict_label="Processing Failed",
    final_confidence=0.0, tier_reached="tier_1_hard_reject",
    comparison_rows=[], score_breakdown={}, weights_used={},
    denominator=0.0, penalties_applied=[], identity_summary="Processing error",
    flags=["ORCHESTRATOR_PARSE_ERROR", f"error_detail: {str(exc)[:50]}"],
)
```

---

## Acceptance Criteria Mapping

| AC | Implementation |
|---|---|
| AC1: No direct reasoning import | Only `scoring.score()` called; scoring owns Tier-2 |
| AC2: Sentinel integrity | `_build_dummy_card()` uses exact spec values |
| AC3: Atomic save contract | `write_text()` + `os.rename()` → `(result, None)` on OSError |
| AC4: JSON schema keys | `model_dump_json()` always produces `user`, `best_match`, `all_results`, `run_metadata` |

---

## Verification Plan

1. Import check: assert `"reasoning"` not in `open("engine/orchestrator.py").read()`
2. Sentinel: pass corrupted JSON → assert `all_results[0].candidate_summary.full_name == "Parse Error"`
3. Atomic write: mock `os.rename` → OSError → assert return is `(BatchScoreResult, None)`
4. JSON schema: run against test_scenario_1, read saved file, assert top-level keys
5. Nullification: test_scenario_5 (hard-reject) → `best_match is None`, `len(all_results) > 0`
6. Empty dir: empty candidates_dir → `(result, None)`, `best_match=None`, `all_results=[]`
