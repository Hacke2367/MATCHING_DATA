"""Batch Orchestrator — Master Pipeline & Persistence Layer.

Single public entry point for the Pro-Match engine. Coordinates:
    extraction.extract_user  →  extraction.extract_candidate  →  scoring.score
                                                               (scoring owns Tier-2 handoff)

Candidate files are processed concurrently via ThreadPoolExecutor.
The concurrency cap and rate-limit guard live in llm_service.py.

Public interface:
    run_batch(anchor_filepath, candidates_dir) -> tuple[BatchScoreResult, Optional[str]]
"""
from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.schema import BatchScoreResult, CandidateIdentity, MatchCard
from engine import extraction, scoring
from engine.errors import FatalOrchestrationError

logger = logging.getLogger(__name__)

ORCHESTRATOR_VERSION = "1.2.0"
REPORTS_DIR = Path("saved_reports")   # relative to CWD per spec §6
_MAX_WORKERS: int = int(os.getenv("GEMINI_MAX_CONCURRENCY", "8"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_dummy_card(record_id: str, exc: Exception) -> MatchCard:
    """Construct an error-state MatchCard when a candidate fails to process."""
    return MatchCard(
        candidate_id=record_id,
        candidate_summary=CandidateIdentity(
            source="candidate",
            record_id=record_id,
            full_name="Parse Error",       # min_length=2 ✓
            identity_summary="Failed",     # max_length=200 ✓
        ),
        verdict_color="RED",
        verdict_label="Processing Failed",
        final_confidence=0.0,
        tier_reached="tier_1_hard_reject",
        comparison_rows=[],
        score_breakdown={},
        weights_used={},
        denominator=0.0,
        penalties_applied=[],
        identity_summary="Processing error",
        flags=["ORCHESTRATOR_PARSE_ERROR", f"error_detail: {str(exc)[:200]}"],
    )


def _sort_key(card: MatchCard) -> tuple[float, float, int]:
    return (
        -card.final_confidence,
        -(card.candidate_summary.extraction_confidence or 0.0),
        -len(card.candidate_summary.supporting_snippets),
    )


def _process_one(anchor: CandidateIdentity, file_path: Path) -> MatchCard:
    """Process a single candidate file end-to-end. Fault-isolated per candidate."""
    try:
        candidate = extraction.extract_candidate(anchor, str(file_path))
        if candidate is None:
            raise ValueError("extract_candidate returned None — all snippets failed validation")
        return scoring.score(anchor, candidate)
    except Exception as exc:
        logger.warning(
            "Candidate processing failed for %s [%s]: %s",
            file_path.name, type(exc).__name__, exc,
        )
        logger.debug("Full traceback for %s:", file_path.name, exc_info=True)
        return _build_dummy_card(file_path.stem, exc)


# ── Public API ─────────────────────────────────────────────────────────────────

def run_batch(
    anchor_filepath: str,
    candidates_dir: str,
) -> tuple[BatchScoreResult, Optional[str]]:
    """Run the full Pro-Match pipeline for one anchor against N candidates.

    Args:
        anchor_filepath: Path to the User KYC JSON file (Source A).
        candidates_dir:  Directory containing candidate JSON files (Source B).

    Returns:
        A tuple of (BatchScoreResult, saved_file_path).
        saved_file_path is None if the directory was empty or disk write failed.

    Raises:
        FatalOrchestrationError: If anchor extraction fails or saved_reports/ cannot
                                 be created.
    """
    run_started_utc = datetime.now(timezone.utc).isoformat()

    # Gate 1 — File Discovery (non-JSON and hidden files are excluded by glob)
    candidate_files = sorted(Path(candidates_dir).glob("*.json"))

    # Anchor extraction — required by BatchScoreResult.user in all return paths
    try:
        anchor = extraction.extract_user(anchor_filepath)
        if anchor is None:
            raise ValueError("extract_user returned None")
    except Exception as exc:
        raise FatalOrchestrationError(
            f"Anchor extraction failed: {exc}",
            user_file_path=anchor_filepath,
            cause=exc,
        ) from exc

    # Gate 1 early-return: empty candidates directory — no disk write
    if not candidate_files:
        logger.info("No candidate files found in %s. Returning empty result.", candidates_dir)
        result = BatchScoreResult(
            user=anchor,
            best_match=None,
            all_results=[],
            run_metadata={
                "engine_version": ORCHESTRATOR_VERSION,
                "run_started_utc": run_started_utc,
                "run_finished_utc": datetime.now(timezone.utc).isoformat(),
                "candidate_count": "0",
            },
        )
        return (result, None)

    # Gate 2 — Storage Readiness
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as exc:
        raise FatalOrchestrationError(
            f"Cannot create saved_reports/ directory: {exc}",
            user_file_path=anchor_filepath,
            cause=exc,
        ) from exc

    # Parallel candidate processing (fault-isolated per candidate)
    all_results: list[MatchCard] = []
    n_workers = min(len(candidate_files), _MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(_process_one, anchor, fp): fp
            for fp in candidate_files
        }
        for future in as_completed(futures):
            all_results.append(future.result())

    # Deterministic sort cascade (descending)
    all_results.sort(key=_sort_key)

    # Best match: index[0] only if GREEN or AMBER
    best_match: Optional[MatchCard] = None
    if all_results and all_results[0].verdict_color in ("GREEN", "AMBER"):
        best_match = all_results[0]

    run_finished_utc = datetime.now(timezone.utc).isoformat()

    result = BatchScoreResult(
        user=anchor,
        best_match=best_match,
        all_results=all_results,
        run_metadata={
            "engine_version": ORCHESTRATOR_VERSION,
            "run_started_utc": run_started_utc,
            "run_finished_utc": run_finished_utc,
            "candidate_count": str(len(candidate_files)),
        },
    )

    # Atomic Write — temp-then-rename prevents partial-write corruption
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    collision_suffix = uuid.uuid4().hex[:6]
    filename = f"match_{anchor.record_id}_{timestamp}_{collision_suffix}.json"
    final_path = REPORTS_DIR / filename
    temp_path = REPORTS_DIR / (filename + ".tmp")

    try:
        temp_path.write_text(result.model_dump_json(), encoding="utf-8")
        os.rename(str(temp_path), str(final_path))
        logger.info("Batch result saved to %s", final_path)
        return (result, str(final_path))
    except OSError as exc:
        logger.critical("Disk write failed — result is in-memory only: %s", exc)
        # Best-effort cleanup of orphaned temp file
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return (result, None)
