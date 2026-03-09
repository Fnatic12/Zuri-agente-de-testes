import streamlit as st


def apply_dark_background(hide_header: bool = True) -> None:
    header_css = (
        "[data-testid=\"stHeader\"] { display: none !important; height: 0 !important; min-height: 0 !important; }\n"
        "[data-testid=\"stToolbar\"] { display: none !important; }\n"
        "[data-testid=\"stDecoration\"] { display: none !important; }\n"
        "[data-testid=\"stStatusWidget\"] { display: none !important; }\n"
    ) if hide_header else (
        "[data-testid=\"stHeader\"] { background: #070b12 !important; }\n"
    )

    st.markdown(
        f"""
        <style>
        :root {{
            --chat-sidebar-offset: 260px;
            --chat-gutter: 1rem;
            --app-bg:
                radial-gradient(circle at 14% 8%, rgba(34, 90, 170, 0.22) 0%, rgba(34, 90, 170, 0.08) 20%, transparent 42%),
                radial-gradient(circle at 84% 18%, rgba(24, 120, 210, 0.14) 0%, rgba(24, 120, 210, 0.05) 18%, transparent 36%),
                linear-gradient(180deg, #07111c 0%, #050b15 42%, #03070d 100%);
        }}
        html, body, [class*="css"] {{
            background: var(--app-bg) !important;
            color: #E0E0E0 !important;
        }}
        html, body {{
            margin: 0 !important;
            padding: 0 !important;
            min-height: 100vh !important;
        }}
        .stApp {{
            background: var(--app-bg) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: var(--app-bg) !important;
            padding-top: 0 !important;
            margin-top: 0 !important;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            background: transparent !important;
            padding-top: 0 !important;
            margin-top: 0 !important;
        }}
        [data-testid="stMain"] {{
            background: transparent !important;
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #08101b 0%, #070d16 52%, #050a12 100%) !important;
            border-right: 1px solid rgba(103, 168, 255, 0.08) !important;
        }}
        section[data-testid="stSidebar"] > div {{
            background: transparent !important;
        }}
        [data-testid="stMainBlockContainer"] {{
            padding-top: 0.6rem !important;
        }}
        [data-testid="stBottomBlockContainer"],
        [data-testid="stBottom"],
        [data-testid="stChatInputContainer"],
        [data-testid="stChatInput"] {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            backdrop-filter: none !important;
        }}
        [data-testid="stBottomBlockContainer"] > div,
        [data-testid="stBottom"] > div,
        [data-testid="stChatInputContainer"] > div,
        [data-testid="stChatInput"] > div {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            backdrop-filter: none !important;
        }}
        .stChatFloatingInputContainer,
        .stChatFloatingInputContainer::before,
        .stChatFloatingInputContainer::after {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            backdrop-filter: none !important;
        }}
        .stChatFloatingInputContainer {{
            position: fixed !important;
            left: var(--chat-gutter) !important;
            right: var(--chat-gutter) !important;
            bottom: 0 !important;
            z-index: 100 !important;
            padding: 0 0 0.8rem 0 !important;
        }}
        [data-testid="stBottomBlockContainer"] * {{
            backdrop-filter: none !important;
        }}
        [data-testid="stBottomBlockContainer"] {{
            position: fixed !important;
            left: calc(var(--chat-sidebar-offset) + var(--chat-gutter)) !important;
            right: var(--chat-gutter) !important;
            bottom: 0 !important;
            z-index: 100 !important;
            padding-bottom: 0.75rem !important;
        }}
        [data-testid="stMainBlockContainer"] {{
            padding-bottom: 8rem !important;
        }}
        [data-testid="stChatInput"] {{
            padding: 0.4rem 0 0.8rem !important;
            border-radius: 999px !important;
            width: 100% !important;
            max-width: 980px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}
        [data-testid="stChatInput"] > div {{
            overflow: visible !important;
            border-radius: 999px !important;
        }}
        [data-testid="stChatInput"] form {{
            background: rgba(36, 40, 54, 0.92) !important;
            border: 1px solid rgba(110, 150, 220, 0.18) !important;
            border-radius: 999px !important;
            overflow: hidden !important;
            clip-path: inset(0 round 999px) !important;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.24) !important;
            width: 100% !important;
            max-width: 980px !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}
        [data-testid="stChatInput"] form > div,
        [data-testid="stChatInput"] form > div > div,
        [data-testid="stChatInput"] form [data-testid="stChatInputTextArea"],
        [data-testid="stChatInput"] form [data-testid="stChatInputTextArea"] > div,
        [data-testid="stChatInput"] [data-baseweb="base-input"],
        [data-testid="stChatInput"] [data-baseweb="input"],
        [data-testid="stChatInput"] [data-baseweb="textarea"] {{
            background: rgba(36, 40, 54, 0.92) !important;
            border-radius: 999px !important;
            overflow: hidden !important;
            clip-path: inset(0 round 999px) !important;
        }}
        [data-testid="stChatInput"] textarea {{
            background: transparent !important;
            border: 0 !important;
            color: #e5e7eb !important;
            padding-left: 0.85rem !important;
            border-radius: 999px !important;
        }}
        [data-testid="stChatInput"] button {{
            border-radius: 999px !important;
            margin-right: 0.15rem !important;
        }}
        [data-testid="stChatInput"] button > div,
        [data-testid="stChatInput"] button svg {{
            border-radius: 999px !important;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: var(--app-bg) !important;
            pointer-events: none;
            z-index: -1;
        }}
        /* TODO: keep menu_chat on the same global background contract as the other dashboards. */
        {header_css}
        .main .block-container, .block-container {{
            background: transparent !important;
            padding-top: 0.6rem !important;
        }}
        @media (max-width: 900px) {{
            .stChatFloatingInputContainer,
            [data-testid="stBottomBlockContainer"] {{
                left: var(--chat-gutter) !important;
                right: var(--chat-gutter) !important;
            }}
            [data-testid="stChatInput"],
            [data-testid="stChatInput"] form {{
                max-width: none !important;
            }}
            [data-testid="stMainBlockContainer"] {{
                padding-bottom: 8.5rem !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
