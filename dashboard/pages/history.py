"""Page 2 — History: search and filter all past run reports."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.components.match_card import render_match_card
from dashboard.utils.report_index import REPORTS_DIR, load_full_report, scan_reports, search_reports

_VERDICT_COLORS = ["GREEN", "AMBER", "RED"]
_VERDICT_ICONS = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "—": "⚪"}


@st.cache_data(ttl=60, show_spinner=False)
def _cached_scan(reports_dir_str: str) -> list[dict]:
    """Filesystem scan cached for 60 s to avoid re-reading on every rerender."""
    return scan_reports(reports_dir_str)


def render() -> None:
    st.title("History")
    st.caption("Search all past batch runs saved in `saved_reports/`. Results are lazy-loaded — only the selected report is fully read.")

    st.divider()

    summaries = _cached_scan(str(REPORTS_DIR))

    if not summaries:
        st.markdown(
            '<div class="hist-empty">No saved reports found in <code>saved_reports/</code>.'
            "<br>Run a match first to populate this view.</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Search & Filter Controls ──────────────────────────────────────────────
    col_q, col_v, col_c = st.columns([3, 2, 2])
    with col_q:
        query = st.text_input(
            "Search by name or record ID",
            placeholder="e.g. ankit dubey or OLPGB17769307040",
        )
    with col_v:
        verdict_filter = st.multiselect(
            "Verdict",
            options=_VERDICT_COLORS,
            default=[],
            format_func=lambda v: f"{_VERDICT_ICONS.get(v, '')} {v}",
        )
    with col_c:
        min_conf = st.slider("Min confidence", min_value=0.0, max_value=1.0, value=0.0, step=0.05)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        date_from = st.date_input("From date", value=None, key="hist_date_from")
    with col_d2:
        date_to = st.date_input("To date", value=None, key="hist_date_to")

    filtered = search_reports(
        summaries,
        query=query,
        verdict_filter=verdict_filter or None,
        date_from=date_from if isinstance(date_from, date) else None,
        date_to=date_to if isinstance(date_to, date) else None,
        min_confidence=min_conf,
    )

    st.caption(f"{len(filtered)} of {len(summaries)} report(s) shown")

    if not filtered:
        st.info("No reports match the current filters.")
        return

    st.divider()

    # ── Results Table ─────────────────────────────────────────────────────────
    rows = []
    for s in filtered:
        ts: datetime | None = s["run_started_utc"]
        verdict_display = f"{_VERDICT_ICONS.get(s['verdict_color'], '')} {s['verdict_color']}"
        rows.append({
            "Date (UTC)": ts.strftime("%Y-%m-%d %H:%M") if ts else "—",
            "User Name": s["full_name"].title() if s["full_name"] else "—",
            "Record ID": s["record_id"],
            "Best Verdict": verdict_display,
            "Confidence": f"{s['final_confidence']:.1%}" if s["verdict_color"] != "—" else "—",
            "Candidates": s["candidate_count"],
        })

    df = pd.DataFrame(rows)

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="history_table",
    )

    # ── Selected Report Detail ────────────────────────────────────────────────
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if not selected_rows:
        st.caption("Select a row above to view the full match report.")
        return

    selected_idx = selected_rows[0]
    if selected_idx >= len(filtered):
        return

    selected_summary = filtered[selected_idx]
    filepath = selected_summary["filepath"]

    # Cache loaded result in session state to avoid re-reading on re-render
    cache_key = f"hist_loaded_{filepath}"
    if cache_key not in st.session_state:
        with st.spinner("Loading report…"):
            try:
                st.session_state[cache_key] = load_full_report(filepath)
            except Exception as e:
                st.error(f"Failed to load report: {e}")
                return

    loaded: object = st.session_state[cache_key]

    st.divider()
    st.subheader(
        f"Report — {selected_summary['full_name'].title() or selected_summary['record_id']}"
    )

    meta = loaded.run_metadata
    st.markdown(
        f'<div class="run-meta">'
        f'Engine v{meta.get("engine_version", "?")} &nbsp;·&nbsp; '
        f'{meta.get("candidate_count", "?")} candidate(s) &nbsp;·&nbsp; '
        f'Run: <code>{meta.get("run_started_utc", "?")}</code><br>'
        f'File: <code>{Path(filepath).name}</code>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if loaded.best_match:
        st.markdown(f"**Best Match:** {loaded.best_match.candidate_summary.full_name.title()}")
        render_match_card(loaded.best_match, key_suffix=f"hist_{filepath}")
    else:
        st.warning("All candidates were hard-rejected in this run.")

    others = [
        c for c in loaded.all_results
        if loaded.best_match is None or c.candidate_id != loaded.best_match.candidate_id
    ]
    if others:
        with st.expander(f"Other candidates ({len(others)})", expanded=False):
            for card in others:
                with st.expander(
                    f"{card.candidate_summary.full_name.title()} — {card.verdict_label}",
                    expanded=False,
                ):
                    render_match_card(card, key_suffix=f"hist_{filepath}_{card.candidate_id}")
