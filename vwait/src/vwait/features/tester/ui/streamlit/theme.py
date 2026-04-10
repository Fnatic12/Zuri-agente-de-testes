from __future__ import annotations

import streamlit as st

from app.shared import ui_theme as _ui_theme


apply_dark_background = _ui_theme.apply_dark_background


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()


def apply_menu_tester_styles() -> None:
    st.markdown(
        """
        <style>
        .exec-row {
            margin-top: 0.35rem;
        }
        .exec-card {
            min-height: 100%;
            padding: 1.1rem 1.15rem 1.2rem 1.15rem;
            border-radius: 22px;
            border: 1px solid rgba(118, 162, 228, 0.14);
            background: linear-gradient(180deg, rgba(15, 23, 36, 0.92) 0%, rgba(9, 16, 27, 0.96) 100%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.04),
                0 18px 34px rgba(0, 0, 0, 0.22);
        }
        .exec-card.secondary {
            background: linear-gradient(180deg, rgba(12, 20, 31, 0.94) 0%, rgba(8, 14, 23, 0.98) 100%);
        }
        .exec-card h4 {
            margin: 0 0 1rem 0;
            font-size: 1.08rem;
            font-weight: 700;
            color: #edf3ff;
            letter-spacing: -0.01em;
        }
        .status-box {
            min-height: 5.3rem;
            padding: 0.9rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(118, 162, 228, 0.12);
            background: linear-gradient(180deg, rgba(23, 31, 45, 0.76) 0%, rgba(13, 20, 31, 0.88) 100%);
            color: rgba(236, 242, 251, 0.94);
            line-height: 1.45;
        }
        div.stButton > button {
            min-height: 4.65rem !important;
            padding: 0.95rem 1.15rem !important;
            border-radius: 18px !important;
        }
        div.stButton > button p {
            font-size: 1rem !important;
            font-weight: 600 !important;
            line-height: 1.24 !important;
        }
        [data-testid="column"] div.stButton > button {
            width: 100% !important;
            max-width: none !important;
        }
        .tester-link-row {
            margin-top: 0.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def titulo_painel(titulo: str, subtitulo: str = ""):
    st.markdown(
        f"""
        <style>
        .main-title {{
            font-size: 2.5rem;
            text-align: center;
            background: linear-gradient(90deg, #12c2e9, #c471ed, #f64f59);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 0.3em;
        }}
        .subtitle {{
            text-align: center;
            color: #AAAAAA;
            font-size: 1rem;
            margin-bottom: 1.8em;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


__all__ = [
    "apply_dark_background",
    "apply_menu_tester_styles",
    "apply_panel_button_theme",
    "titulo_painel",
]
