"""Page 1 — Run Match: upload files, trigger the engine, view results."""
from __future__ import annotations

import traceback
from datetime import datetime, timezone

import streamlit as st

from dashboard.components.match_card import render_match_card, render_mini_card
from dashboard.utils.file_handler import write_uploads_to_temp


def _fmt_duration(start: str, end: str) -> str:
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end)
        secs = (t1 - t0).total_seconds()
        return f"{secs:.1f}s"
    except Exception:
        return "—"


def _run_engine(anchor_bytes: bytes, anchor_name: str, candidate_files: list) -> None:
    """Write uploads to temp dir, call run_batch(), store result in session_state."""
    from engine.orchestrator import run_batch

    cand_pairs = [(f.read(), f.name) for f in candidate_files]
    anchor_path, candidates_dir, cleanup = write_uploads_to_temp(
        anchor_bytes, anchor_name, cand_pairs
    )
    try:
        result, report_path = run_batch(anchor_path, candidates_dir)
        st.session_state["run_result"] = result
        st.session_state["run_report_path"] = report_path or ""
        st.session_state["run_error"] = None
    except Exception:
        st.session_state["run_result"] = None
        st.session_state["run_report_path"] = ""
        st.session_state["run_error"] = traceback.format_exc()
    finally:
        cleanup()


def render() -> None:
    st.title("Run Match")
    st.caption("Upload a User KYC record (Source A) and one or more candidate files (Source B), then run the engine.")

    st.divider()

    # ── Upload Zone ──────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="upload-header">Source A — User KYC (single JSON)</div>', unsafe_allow_html=True)
        anchor_file = st.file_uploader(
            "User KYC JSON",
            type=["json"],
            key="upload_anchor",
            label_visibility="collapsed",
        )
        if anchor_file:
            st.success(f"Loaded: **{anchor_file.name}** ({anchor_file.size:,} bytes)")

    with col_b:
        st.markdown('<div class="upload-header">Source B — Candidates (one or more JSONs)</div>', unsafe_allow_html=True)
        candidate_files = st.file_uploader(
            "Candidate JSONs",
            type=["json"],
            accept_multiple_files=True,
            key="upload_candidates",
            label_visibility="collapsed",
        )
        if candidate_files:
            st.success(f"Loaded: **{len(candidate_files)}** candidate file(s)")

    st.divider()

    # ── Run Button ───────────────────────────────────────────────────────────
    ready = bool(anchor_file and candidate_files)
    if not ready:
        st.info("Upload both Source A and at least one Source B file to enable the engine.")

    run_clicked = st.button(
        "Run Engine",
        type="primary",
        disabled=not ready,
        use_container_width=False,
    )

    if run_clicked and ready:
        anchor_bytes = anchor_file.getvalue()
        # Reset file pointers so they can be read in _run_engine
        for f in candidate_files:
            f.seek(0)
        with st.spinner("Running extraction → scoring → reasoning…"):
            _run_engine(anchor_bytes, anchor_file.name, candidate_files)
        st.rerun()

    # ── Results ──────────────────────────────────────────────────────────────
    if st.session_state.get("run_error"):
        st.error("Engine run failed.")
        with st.expander("Error detail"):
            st.code(st.session_state["run_error"])
        return

    result = st.session_state.get("run_result")
    if result is None:
        return

    meta = result.run_metadata
    report_path = st.session_state.get("run_report_path", "")
    duration = _fmt_duration(
        meta.get("run_started_utc", ""),
        meta.get("run_finished_utc", ""),
    )

    st.markdown('<div id="results-section"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="run-meta">'
        f'Engine v{meta.get("engine_version", "?")} &nbsp;·&nbsp; '
        f'{meta.get("candidate_count", "?")} candidate(s) scored &nbsp;·&nbsp; '
        f'Runtime: {duration} &nbsp;·&nbsp; '
        f'Report: <code>{report_path or "not saved"}</code>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Best Match ───────────────────────────────────────────────────────────
    if result.best_match is None:
        n_green    = sum(1 for c in result.all_results if c.verdict_color == "GREEN")
        n_amber    = sum(1 for c in result.all_results if c.verdict_color == "AMBER")
        n_rejected = sum(1 for c in result.all_results if c.verdict_color == "RED")
        col1, col2, col3 = st.columns(3)
        col1.metric("Confirmed Match", n_green)
        col2.metric("Review Required", n_amber)
        col3.metric("Hard-Rejected",   n_rejected)
        st.error(
            "No confident match found — all candidates were rejected by the safety gates.  \n"
            "Expand each candidate below to inspect the rejection reason."
        )
    else:
        st.subheader(f"Best Match — {result.best_match.candidate_summary.full_name.title()}")
        render_match_card(result.best_match, key_suffix="best")

    # ── Secondary Candidates ─────────────────────────────────────────────────
    others = [c for c in result.all_results if result.best_match is None or c.candidate_id != result.best_match.candidate_id]
    no_best = result.best_match is None
    if others:
        label = f"All candidates ({len(others)})" if no_best else f"Secondary candidates ({len(others)})"
        with st.expander(label, expanded=no_best):
            for card in others:
                render_mini_card(card)
                with st.expander(f"Detail — {card.candidate_summary.full_name.title()} ({card.candidate_id})", expanded=False):
                    render_match_card(card, key_suffix=card.candidate_id)
