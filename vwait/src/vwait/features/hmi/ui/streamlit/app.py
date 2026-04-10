from __future__ import annotations

import streamlit as st

from .page import render_hmi_validation_page
from app.shared.ui_theme import apply_dark_background
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[6]
DATA_ROOT = PROJECT_ROOT / "Data"


def main() -> None:
    st.set_page_config(page_title="Validacao HMI", page_icon="", layout="wide")
    apply_dark_background(hide_header=True)
    render_hmi_validation_page(str(PROJECT_ROOT), str(DATA_ROOT))


__all__ = ["main"]
