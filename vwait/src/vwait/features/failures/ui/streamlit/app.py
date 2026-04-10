from __future__ import annotations

import streamlit as st

from .page import render_failure_control_page
from .presenters import apply_panel_button_theme


def main() -> None:
    st.set_page_config(page_title="Controle de Falhas - VWAIT", page_icon="", layout="wide")
    apply_panel_button_theme()
    render_failure_control_page()


__all__ = ["main"]

