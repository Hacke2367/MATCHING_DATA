"""Full MatchCard renderer — tabbed layout with colored left-border card styling."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from dashboard.components.comparison_table import render_comparison_table
from dashboard.components.risk_panel import render_risk_panel
from dashboard.components.score_audit import render_score_audit

if TYPE_CHECKING:
    from config.schema import MatchCard

_BORDER_COLOR = {
    "GREEN": "#22c55e",
    "AMBER": "#f59e0b",
    "RED":   "#ef4444",
}
_VERDICT_ICONS = {
    "GREEN": "🟢",
    "AMBER": "🟡",
    "RED":   "🔴",
}


def _render_verdict_tab(card: "MatchCard") -> None:
    border = _BORDER_COLOR.get(card.verdict_color, "#e5e7eb")
    icon = _VERDICT_ICONS.get(card.verdict_color, "")

    # Colored verdict banner
    st.markdown(
        f"""
        <div style="border-left: 4px solid {border}; padding-left: 14px; margin-bottom: 12px;">
          <span class="verdict-badge verdict-badge--{card.verdict_color}">
            {icon} {card.verdict_label}
          </span>
          <span class="confidence-pct" style="margin-left:16px;">
            {card.final_confidence:.1%}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.progress(card.final_confidence, text=f"Confidence: {card.final_confidence:.1%}")

    col_tier, col_cand = st.columns([1, 2])
    with col_tier:
        tier_display = card.tier_reached.replace("_", " ").title()
        st.markdown(
            f'<span class="tier-badge">{tier_display}</span>',
            unsafe_allow_html=True,
        )
    with col_cand:
        st.caption(f"Candidate ID: `{card.candidate_id}`")

    st.markdown(
        f'<div class="identity-summary">{card.identity_summary}</div>',
        unsafe_allow_html=True,
    )

    # Operational flags
    if card.flags:
        flag_html = "".join(
            f'<span class="flag-chip">{f}</span>' for f in card.flags
        )
        st.markdown(
            f'<div class="flag-chips"><span class="section-label">Flags</span><br>{flag_html}</div>',
            unsafe_allow_html=True,
        )


def _render_snippets_tab(card: "MatchCard") -> None:
    snippets = card.candidate_summary.supporting_snippets
    if not snippets:
        st.info("No supporting snippets available for this candidate.")
        return

    st.caption(f"{len(snippets)} snippet(s) extracted from media articles.")
    for i, s in enumerate(snippets, 1):
        date_str = str(s.article_date) if s.article_date else "Unknown date"
        with st.expander(f"Snippet {i} — {s.snippet_title or 'Untitled'} ({date_str})"):
            st.markdown(
                f'<span class="snippet-title">{s.snippet_title or "(no title)"}</span>'
                f'<span class="snippet-date">{date_str}</span>',
                unsafe_allow_html=True,
            )
            if s.event_date and s.event_date != s.article_date:
                st.caption(f"Event date (LLM-inferred): {s.event_date}")

            # Extracted text
            text_preview = s.snippet_text[:400] + ("…" if len(s.snippet_text) > 400 else "")
            st.markdown(
                f'<div class="snippet-text">{text_preview}</div>',
                unsafe_allow_html=True,
            )

            # Key extracted fields
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Gender", s.gender.title())
                if s.age_at_event:
                    st.metric("Age at event", s.age_at_event)
            with col2:
                if s.profession_raw:
                    st.metric("Profession", s.profession_raw[:30])
                if s.locations:
                    loc = s.locations[0]
                    location_str = ", ".join(filter(None, [loc.city, loc.country]))
                    st.metric("Location", location_str or loc.raw or "—")
            with col3:
                st.metric("Confidence", f"{s.extraction_confidence:.0%}")
                if s.identifiers_in_text:
                    st.write("**Identifiers:**", s.identifiers_in_text)

            if s.flags:
                flag_html = "".join(f'<span class="flag-chip">{f}</span>' for f in s.flags)
                st.markdown(flag_html, unsafe_allow_html=True)


def render_match_card(card: "MatchCard", key_suffix: str = "") -> None:
    """Render a complete MatchCard with a 5-tab layout.

    key_suffix disambiguates multiple cards on the same page (e.g., candidate ID).
    """
    tab_verdict, tab_cmp, tab_audit, tab_risk, tab_snippets = st.tabs([
        "Verdict",
        "Comparison",
        "Score Audit",
        "Risk Intelligence",
        "Snippets",
    ])

    with tab_verdict:
        _render_verdict_tab(card)

    with tab_cmp:
        render_comparison_table(card.comparison_rows)

    with tab_audit:
        render_score_audit(card)

    with tab_risk:
        render_risk_panel(card)

    with tab_snippets:
        _render_snippets_tab(card)


def render_mini_card(card: "MatchCard") -> None:
    """Compact one-liner card for use in the secondary candidates list."""
    border = _BORDER_COLOR.get(card.verdict_color, "#e5e7eb")
    icon = _VERDICT_ICONS.get(card.verdict_color, "")
    st.markdown(
        f"""
        <div style="border-left: 3px solid {border}; padding: 8px 12px;
                    background: #fafafa; border-radius: 0 6px 6px 0; margin-bottom: 4px;">
          <strong style="font-size:13px;">{card.candidate_summary.full_name.title()}</strong>
          &nbsp;
          <span class="verdict-badge verdict-badge--{card.verdict_color}"
                style="font-size:11px; padding: 2px 10px;">
            {icon} {card.verdict_label}
          </span>
          <span style="float:right; font-weight:700; font-size:14px; color:#374151;">
            {card.final_confidence:.1%}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
