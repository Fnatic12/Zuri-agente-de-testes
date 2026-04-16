from __future__ import annotations

import streamlit as st

from vwait.core.config import ui_theme as _ui_theme


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
        .tester-button-marker {
            display: none;
        }
        [class*="st-key-tester-btn-start"] div.stButton > button,
        [class*="st-key-tester-btn-start"] div[data-testid="stButton"] button,
        .tester-btn-start + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-start) + div[data-testid="stButton"] button {
            border-color: rgba(74, 222, 128, 0.52) !important;
            background: linear-gradient(135deg, rgba(22, 101, 52, 0.96), rgba(34, 197, 94, 0.78)) !important;
            color: #f0fff7 !important;
            box-shadow: 0 16px 32px rgba(34, 197, 94, 0.16) !important;
        }
        [class*="st-key-tester-btn-stop"] div.stButton > button,
        [class*="st-key-tester-btn-danger"] div.stButton > button,
        [class*="st-key-tester-btn-stop"] div[data-testid="stButton"] button,
        [class*="st-key-tester-btn-danger"] div[data-testid="stButton"] button,
        .tester-btn-stop + div[data-testid="stButton"] button,
        .tester-btn-danger + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-stop) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-danger) + div[data-testid="stButton"] button {
            border-color: rgba(248, 113, 113, 0.58) !important;
            background: linear-gradient(135deg, rgba(127, 29, 29, 0.96), rgba(239, 68, 68, 0.78)) !important;
            color: #fff5f5 !important;
            box-shadow: 0 16px 32px rgba(239, 68, 68, 0.16) !important;
        }
        [class*="st-key-tester-btn-save"] div.stButton > button,
        [class*="st-key-tester-btn-export"] div.stButton > button,
        [class*="st-key-tester-btn-save"] div[data-testid="stButton"] button,
        [class*="st-key-tester-btn-export"] div[data-testid="stButton"] button,
        .tester-btn-save + div[data-testid="stButton"] button,
        .tester-btn-export + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-save) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-export) + div[data-testid="stButton"] button {
            border-color: rgba(56, 189, 248, 0.55) !important;
            background: linear-gradient(135deg, rgba(14, 116, 144, 0.96), rgba(56, 189, 248, 0.74)) !important;
            color: #f0fbff !important;
            box-shadow: 0 16px 32px rgba(56, 189, 248, 0.14) !important;
        }
        [class*="st-key-tester-btn-log"] div.stButton > button,
        [class*="st-key-tester-btn-log"] div[data-testid="stButton"] button,
        .tester-btn-log + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-log) + div[data-testid="stButton"] button {
            border-color: rgba(250, 204, 21, 0.52) !important;
            background: linear-gradient(135deg, rgba(133, 77, 14, 0.96), rgba(234, 179, 8, 0.72)) !important;
            color: #fffbea !important;
            box-shadow: 0 16px 32px rgba(234, 179, 8, 0.14) !important;
        }
        [class*="st-key-tester-btn-open"] div.stButton > button,
        [class*="st-key-tester-btn-help"] div.stButton > button,
        [class*="st-key-tester-btn-open"] div[data-testid="stButton"] button,
        [class*="st-key-tester-btn-help"] div[data-testid="stButton"] button,
        .tester-btn-open + div[data-testid="stButton"] button,
        .tester-btn-help + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-open) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-help) + div[data-testid="stButton"] button {
            border-color: rgba(129, 140, 248, 0.55) !important;
            background: linear-gradient(135deg, rgba(49, 46, 129, 0.96), rgba(99, 102, 241, 0.72)) !important;
            color: #f5f6ff !important;
            box-shadow: 0 16px 32px rgba(99, 102, 241, 0.14) !important;
        }
        [class*="st-key-tester-btn-run"] div.stButton > button,
        [class*="st-key-tester-btn-run"] div[data-testid="stButton"] button,
        .tester-btn-run + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-run) + div[data-testid="stButton"] button {
            border-color: rgba(45, 212, 191, 0.54) !important;
            background: linear-gradient(135deg, rgba(17, 94, 89, 0.96), rgba(20, 184, 166, 0.76)) !important;
            color: #effffd !important;
            box-shadow: 0 16px 32px rgba(20, 184, 166, 0.14) !important;
        }
        [class*="st-key-tester-btn-pause"] div.stButton > button,
        [class*="st-key-tester-btn-pause"] div[data-testid="stButton"] button,
        .tester-btn-pause + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-pause) + div[data-testid="stButton"] button {
            border-color: rgba(251, 146, 60, 0.56) !important;
            background: linear-gradient(135deg, rgba(154, 52, 18, 0.96), rgba(249, 115, 22, 0.76)) !important;
            color: #fff7ed !important;
        }
        [class*="st-key-tester-btn-resume"] div.stButton > button,
        [class*="st-key-tester-btn-resume"] div[data-testid="stButton"] button,
        .tester-btn-resume + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-resume) + div[data-testid="stButton"] button {
            border-color: rgba(132, 204, 22, 0.56) !important;
            background: linear-gradient(135deg, rgba(63, 98, 18, 0.96), rgba(132, 204, 22, 0.72)) !important;
            color: #fbffe8 !important;
        }
        [class*="st-key-tester-btn-report"] div.stButton > button,
        [class*="st-key-tester-btn-report"] div[data-testid="stButton"] button,
        .tester-btn-report + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .tester-btn-report) + div[data-testid="stButton"] button {
            border-color: rgba(244, 114, 182, 0.52) !important;
            background: linear-gradient(135deg, rgba(131, 24, 67, 0.96), rgba(236, 72, 153, 0.72)) !important;
            color: #fff1f7 !important;
        }
        [class*="st-key-tester-btn-"] div.stButton > button:hover,
        [class*="st-key-tester-btn-"] div[data-testid="stButton"] button:hover,
        .tester-btn-start + div[data-testid="stButton"] button:hover,
        .tester-btn-stop + div[data-testid="stButton"] button:hover,
        .tester-btn-danger + div[data-testid="stButton"] button:hover,
        .tester-btn-save + div[data-testid="stButton"] button:hover,
        .tester-btn-export + div[data-testid="stButton"] button:hover,
        .tester-btn-log + div[data-testid="stButton"] button:hover,
        .tester-btn-open + div[data-testid="stButton"] button:hover,
        .tester-btn-help + div[data-testid="stButton"] button:hover,
        .tester-btn-run + div[data-testid="stButton"] button:hover,
        .tester-btn-pause + div[data-testid="stButton"] button:hover,
        .tester-btn-resume + div[data-testid="stButton"] button:hover,
        .tester-btn-report + div[data-testid="stButton"] button:hover {
            transform: translateY(-1px);
            filter: brightness(1.08);
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
