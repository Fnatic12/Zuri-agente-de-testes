from datetime import datetime

import streamlit as st
from colorama import Fore, Style


def panel_title(title: str, subtitle: str = ""):
    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
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
        <h1 class="main-title">{title}</h1>
        {subtitle_html}
        """,
        unsafe_allow_html=True,
    )


def chat_greeting(name: str = "Victor") -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return f"Bom dia, {name}"
    if 12 <= hour < 18:
        return f"Boa tarde, {name}"
    return f"Boa noite, {name}"


def render_chat_greeting(name: str = "Victor") -> None:
    greeting = chat_greeting(name)
    st.markdown(
        f"""
        <style>
        .claude-greeting-shell {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 34vh;
            padding: 2.4rem 0 1rem 0;
            text-align: center;
        }}
        .claude-greeting {{
            margin: 0;
            font-size: clamp(10.4rem, 20vw, 16.8rem);
            line-height: 0.96;
            font-weight: 700;
            letter-spacing: -0.04em;
            color: #f3f5f7;
        }}
        </style>
        <div class="claude-greeting-shell">
            <h2 class="claude-greeting">{greeting}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def printc(message, color="white"):
    colors = {
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "red": Fore.RED,
        "white": Style.RESET_ALL,
        "cyan": Fore.CYAN,
        "blue": Fore.BLUE,
    }
    print(f"{colors.get(color, '')}{message}{Style.RESET_ALL}", flush=True)
    return message

