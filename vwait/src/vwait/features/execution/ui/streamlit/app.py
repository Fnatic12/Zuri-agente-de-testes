from __future__ import annotations

import streamlit as st

from vwait.core.config.auto_refresh import enable_global_auto_refresh
from .page import render_dashboard_page
from .theme import apply_panel_button_theme


def main() -> None:
    st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")
    enable_global_auto_refresh(key="execution")
    apply_panel_button_theme()
    render_dashboard_page()


__all__ = ["main"]
