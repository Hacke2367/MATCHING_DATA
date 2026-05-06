"""Renders the scoring audit trail from a MatchCard."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from config.schema import MatchCard

_FIELD_LABELS = {
    "id":       "Unique Identifiers",
    "name":     "Name / Aliases",
    "location": "Geography",
    "age":      "Projected Age",
}


def render_score_audit(card: "MatchCard") -> None:
    breakdown = card.score_breakdown
    weights = card.weights_used

    if not breakdown and not weights:
        st.info("No scoring breakdown available (hard-reject before heuristics).")
        if card.penalties_applied:
            st.markdown("**Penalties applied:**")
            for p in card.penalties_applied:
                st.markdown(f"- `{p}`")
        return

    # Score bars
    all_fields = list(dict.fromkeys(list(weights.keys()) + list(breakdown.keys())))
    for field in all_fields:
        max_pts = weights.get(field, 0.0)
        earned = breakdown.get(field, 0.0)
        label = _FIELD_LABELS.get(field, field.upper())
        pct = (earned / max_pts) if max_pts > 0 else 0.0

        col_label, col_pts, col_bar = st.columns([2, 1, 5])
        with col_label:
            st.markdown(f'<span class="score-field-label">{label}</span>', unsafe_allow_html=True)
        with col_pts:
            st.markdown(
                f'<span class="score-pts">{earned:.0f} / {max_pts:.0f}</span>',
                unsafe_allow_html=True,
            )
        with col_bar:
            st.progress(min(pct, 1.0))

    st.divider()

    # Denominator + tier
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"**Denominator used:** `{card.denominator:.0f}` pts  \n"
            f"*(fields with no data excluded from scoring)*"
        )
    with col_b:
        tier_display = card.tier_reached.replace("_", " ").title()
        st.markdown(f"**Tier reached:** `{tier_display}`")

    # Penalties
    if card.penalties_applied:
        st.markdown("**Hard-reject penalties:**")
        for p in card.penalties_applied:
            st.markdown(
                f'<span style="color:#b91c1c; font-family:monospace; font-size:13px;">⊘ {p}</span>',
                unsafe_allow_html=True,
            )
