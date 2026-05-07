"""Renders the symmetric comparison table from MatchCard.comparison_rows."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    from config.schema import ComparisonRow

_STATUS_BG = {
    "match":    "#d1fae5",
    "partial":  "#fef9c3",
    "mismatch": "#fee2e2",
    "missing":  "#f3f4f6",
}
_STATUS_LABEL = {
    "match":    "✓ Match",
    "partial":  "~ Partial",
    "mismatch": "✗ Mismatch",
    "missing":  "– Missing",
}


def render_comparison_table(rows: list["ComparisonRow"]) -> None:
    if not rows:
        st.info("No comparison data available for this candidate.")
        return

    records = []
    for r in rows:
        records.append({
            "Field": r.field_label,
            "User (Source A)": r.user_value or "—",
            "Candidate (Source B)": r.candidate_value or "—",
            "Status": _STATUS_LABEL.get(r.match_status, r.match_status),
            "Pts": f"{r.contribution_pts:.0f}" if r.contribution_pts is not None else "—",
            "_status": r.match_status,
        })

    df = pd.DataFrame(records)

    # Capture statuses before dropping the helper column so the closure can
    # reference them by row index position — _status is gone from df_display.
    statuses = df["_status"].reset_index(drop=True)
    df_display = df.drop(columns=["_status"])

    def _row_color(row: pd.Series) -> list[str]:
        bg = _STATUS_BG.get(statuses.iloc[row.name], "#ffffff")
        return [f"background-color: {bg}"] * len(row)

    styled = (
        df_display
        .style
        .apply(_row_color, axis=1)
        .set_properties(**{"font-size": "13px"})
        .set_table_styles([
            {"selector": "th", "props": [
                ("font-size", "11px"),
                ("font-weight", "700"),
                ("text-transform", "uppercase"),
                ("letter-spacing", "0.06em"),
                ("color", "#1f2937"),
                ("border-bottom", "2px solid #e5e7eb"),
            ]},
            {"selector": "td", "props": [
                ("border-bottom", "1px solid #f3f4f6"),
                ("color", "#1f2937"),
            ]},
        ])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
