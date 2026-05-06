"""Lightweight read-only filesystem scanner for saved_reports/.

No engine imports. No backend mutations. Pure filesystem read.
Intended for use with @st.cache_data to avoid re-scanning on every rerender.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

REPORTS_DIR = Path("saved_reports")


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _read_summary(filepath: Path) -> dict[str, Any] | None:
    """Read only the minimal metadata fields needed for search/filter."""
    try:
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        user = raw.get("user") or {}
        best = raw.get("best_match") or {}
        meta = raw.get("run_metadata") or {}
        return {
            "filepath": str(filepath),
            "filename": filepath.name,
            "record_id": user.get("record_id", ""),
            "full_name": user.get("full_name", ""),
            "aliases": user.get("aliases") or [],
            "verdict_color": best.get("verdict_color", "—") if best else "—",
            "final_confidence": best.get("final_confidence", 0.0) if best else 0.0,
            "run_started_utc": _parse_utc(meta.get("run_started_utc")),
            "candidate_count": meta.get("candidate_count", "0"),
        }
    except Exception:
        return None


def scan_reports(reports_dir_str: str) -> list[dict[str, Any]]:
    """Scan saved_reports/ and return a list of summary dicts, newest first.

    Designed to be wrapped with @st.cache_data(ttl=60) at the call site.
    """
    reports_dir = Path(reports_dir_str)
    if not reports_dir.exists():
        return []
    summaries: list[dict[str, Any]] = []
    for fp in sorted(reports_dir.glob("match_*.json"), reverse=True):
        s = _read_summary(fp)
        if s:
            summaries.append(s)
    return summaries


def search_reports(
    summaries: list[dict[str, Any]],
    query: str = "",
    verdict_filter: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """Filter an in-memory list of report summaries. No filesystem access."""
    q = query.strip().lower()
    results: list[dict[str, Any]] = []
    for s in summaries:
        if q:
            haystack = " ".join([s["full_name"], s["record_id"]] + s["aliases"]).lower()
            if q not in haystack:
                continue
        if verdict_filter:
            if s["verdict_color"] not in verdict_filter:
                continue
        ts: datetime | None = s["run_started_utc"]
        if date_from and ts and ts.date() < date_from:
            continue
        if date_to and ts and ts.date() > date_to:
            continue
        if s["final_confidence"] < min_confidence:
            continue
        results.append(s)
    return results


def load_full_report(filepath: str):
    """Load and parse a complete BatchScoreResult from a saved report file.

    Only called when a user selects a specific report (lazy load).
    """
    from config.schema import BatchScoreResult
    content = Path(filepath).read_text(encoding="utf-8")
    return BatchScoreResult.model_validate_json(content)
