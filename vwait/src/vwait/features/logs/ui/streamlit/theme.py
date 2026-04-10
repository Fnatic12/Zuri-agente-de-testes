from __future__ import annotations

import streamlit as st


def apply_panel_button_theme() -> None:
    st.markdown(
        """
        <style>
        div.stButton {
            width: 100%;
        }
        div.stButton > button {
            width: min(100%, 18rem);
            min-height: 4.2rem;
            padding: 0.9rem 1.15rem;
            border-radius: 18px;
            border: 1px solid rgba(121, 148, 188, 0.28);
            background: linear-gradient(180deg, rgba(27, 34, 48, 0.94) 0%, rgba(18, 24, 36, 0.98) 100%);
            color: #f5f7fb;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            white-space: normal;
            line-height: 1.32;
            letter-spacing: 0.01em;
            box-shadow: 0 12px 26px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            transition: transform 0.18s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.16s ease, box-shadow 0.18s ease, background 0.16s ease, filter 0.16s ease;
            will-change: transform, box-shadow;
        }
        div.stButton > button p {
            margin: 0;
            font-size: 1rem;
            font-weight: 600;
            line-height: 1.32;
        }
        [data-testid="column"] div.stButton > button {
            width: 100%;
            max-width: none;
        }
        div.stButton > button:hover:not(:disabled) {
            transform: translate3d(0, -1px, 0);
            border-color: rgba(106, 176, 255, 0.56);
            background: linear-gradient(180deg, rgba(31, 41, 58, 0.98) 0%, rgba(20, 28, 40, 1) 100%);
            box-shadow: 0 16px 30px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(106, 176, 255, 0.12);
            filter: saturate(1.06);
        }
        div.stButton > button:focus:not(:active) {
            border-color: rgba(106, 176, 255, 0.72);
            box-shadow: 0 0 0 0.2rem rgba(72, 140, 220, 0.22), 0 16px 30px rgba(0, 0, 0, 0.28);
        }
        div.stButton > button:active:not(:disabled) {
            transform: translate3d(0, 0, 0);
            box-shadow: 0 10px 18px rgba(0, 0, 0, 0.24);
        }
        div.stButton > button:disabled {
            opacity: 0.58;
            cursor: not-allowed;
            box-shadow: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def titulo_painel(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            background: #0B0C10 !important;
            color: #E0E0E0 !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
        }}
        [data-testid="stHeader"], [data-testid="stToolbar"] {{
            display: none !important;
            height: 0 !important;
        }}
        .block-container {{
            padding-top: 1.15rem;
            max-width: 1240px;
        }}
        .main-title {{
            font-size: 2.0rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #60a5fa 40%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.1em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #9ca3af;
            font-size: 0.94rem;
            margin-bottom: 1.0em;
        }}
        .panel-card {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.45);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


__all__ = ["apply_panel_button_theme", "titulo_painel"]
