from __future__ import annotations

import streamlit as st

from .page import render_dashboard_page
from .theme import apply_panel_button_theme


def main() -> None:
    st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")
    apply_panel_button_theme()
    render_dashboard_page()


__all__ = ["main"]
