"""Renders the risk intelligence panel: risk type chips, provenance, LLM verdict."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from config.schema import MatchCard

_RISK_CLASS = {
    "sanction":     "risk-chip--sanction",
    "pep":          "risk-chip--pep",
    "adverse-media": "risk-chip--media",
    "fitness":      "risk-chip--fitness",
    "warning":      "risk-chip--warning",
}


def _risk_chip_class(risk: str) -> str:
    for prefix, cls in _RISK_CLASS.items():
        if risk.startswith(prefix) or prefix in risk:
            return cls
    return "risk-chip--other"


def _provenance_tier(src: str) -> tuple[str, str]:
    s = src.lower()
    if any(k in s for k in ("ministry", "government", "corporate-affairs", "mca", "revenue", "court")):
        return "Government Registry", "prov-gov"
    if any(k in s for k in ("complyadvantage", "reuters", "bbc", "times", "guardian", "news")):
        return "Major News / Aggregator", "prov-news"
    return "Other Source", "prov-other"


def render_risk_panel(card: "MatchCard") -> None:
    # Risk type chips
    if card.risk_types:
        st.markdown('<span class="section-label">Risk Classifications</span>', unsafe_allow_html=True)
        chips_html = " ".join(
            f'<span class="risk-chip {_risk_chip_class(r)}">{r}</span>'
            for r in card.risk_types
        )
        st.markdown(chips_html, unsafe_allow_html=True)
    else:
        st.info("No risk classifications in this record.")

    st.divider()

    # Source provenance
    if card.source_provenance:
        st.markdown('<span class="section-label">Source Provenance</span>', unsafe_allow_html=True)
        for src in card.source_provenance:
            tier_label, tier_cls = _provenance_tier(src)
            st.markdown(
                f'<span class="{tier_cls}">● {tier_label}</span>'
                f'<span style="font-size:12px; color:#374151; margin-left:8px;">{src}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No provenance data available.")

    # LLM verdict — only shown when Tier 2 was reached
    if card.tier_reached == "tier_2_llm_judge" and card.llm_verdict:
        st.divider()
        st.markdown('<span class="section-label">LLM Judge Verdict (Tier 2)</span>', unsafe_allow_html=True)
        if card.pre_llm_verdict_label:
            st.caption(f"Pre-LLM verdict: {card.pre_llm_verdict_label}")
        st.markdown(
            f'<div class="llm-verdict-box">{card.llm_verdict}</div>',
            unsafe_allow_html=True,
        )
