"""Pro-Match Identity Engine — Streamlit Test-Bench.

Launch from the project root:
    streamlit run dashboard/app.py

The project root must be the working directory so engine module imports
and saved_reports/ paths resolve correctly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Ensure project root is CWD and on sys.path ──────────────────────────────
_project_root = Path(__file__).parent.parent.resolve()
os.chdir(_project_root)
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Load .env (same as main.py does for CLI runs) ────────────────────────────
from dotenv import load_dotenv
load_dotenv(_project_root / ".env")

import streamlit as st

st.set_page_config(
    page_title="Pro-Match Identity Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject CSS ───────────────────────────────────────────────────────────────
_css_path = Path(__file__).parent / "styles" / "main.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)

# ── Sidebar Navigation ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "## 🔍 Pro-Match\n"
        "**Identity Engine** v1\n"
    )
    st.divider()
    page = st.radio(
        "Navigation",
        options=["Run Match", "History"],
        index=0,
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        "**Precision over Recall.**  \n"
        "A 🔴 RED verdict on a hard-reject is a *success* — the safety gates protected the user."
    )

# ── Page Dispatch ─────────────────────────────────────────────────────────────
if page == "Run Match":
    from dashboard.pages.run_match import render
    render()
else:
    from dashboard.pages.history import render
    render()
