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
            --chat-sidebar-collapsed-width: 2.75rem;
            --chat-gutter: 1rem;
            --motion-quick: 170ms;
            --motion-smooth: 240ms;
            --motion-curve: cubic-bezier(0.22, 1, 0.36, 1);
            --app-bg:
                radial-gradient(circle at 14% 8%, rgba(34, 90, 170, 0.22) 0%, rgba(34, 90, 170, 0.08) 20%, transparent 42%),
                radial-gradient(circle at 84% 18%, rgba(24, 120, 210, 0.14) 0%, rgba(24, 120, 210, 0.05) 18%, transparent 36%),
                linear-gradient(180deg, #07111c 0%, #050b15 42%, #03070d 100%);
        }}
        @keyframes ui-fade-slide {{
            from {{
                opacity: 0;
                transform: translate3d(0, 10px, 0);
            }}
            to {{
                opacity: 1;
                transform: translate3d(0, 0, 0);
            }}
        }}
        @keyframes ui-soft-fade {{
            from {{
                opacity: 0;
            }}
            to {{
                opacity: 1;
            }}
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
            animation: ui-soft-fade 220ms ease-out both;
        }}
        [data-testid="stMain"] {{
            background: transparent !important;
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #08101b 0%, #070d16 52%, #050a12 100%) !important;
            border-right: 1px solid rgba(103, 168, 255, 0.08) !important;
            box-shadow: 20px 0 38px rgba(0, 0, 0, 0.22) !important;
            backdrop-filter: blur(10px) saturate(122%);
            -webkit-backdrop-filter: blur(10px) saturate(122%);
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                width var(--motion-smooth) var(--motion-curve),
                opacity var(--motion-smooth) ease,
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-smooth) ease,
                background var(--motion-smooth) ease;
            will-change: transform, opacity;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] {{
            min-width: var(--chat-sidebar-collapsed-width) !important;
            max-width: var(--chat-sidebar-collapsed-width) !important;
            width: var(--chat-sidebar-collapsed-width) !important;
            transform: translateX(0) !important;
            margin-left: 0 !important;
            background: transparent !important;
            border-right-color: transparent !important;
            box-shadow: none !important;
            opacity: 1 !important;
            overflow: hidden !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] > div:first-child {{
            min-width: var(--chat-sidebar-collapsed-width) !important;
            max-width: var(--chat-sidebar-collapsed-width) !important;
            width: var(--chat-sidebar-collapsed-width) !important;
            margin-left: 0 !important;
            opacity: 1 !important;
            overflow: hidden !important;
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                opacity var(--motion-smooth) ease,
                width var(--motion-smooth) var(--motion-curve);
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"] > *:not([data-testid="stSidebarHeader"]) {{
            display: none !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] {{
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            padding: 0.35rem 0 !important;
            min-height: 3rem !important;
            background: transparent !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] > *:not([data-testid="stSidebarCollapseButton"]) {{
            display: none !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] {{
            display: flex !important;
            justify-content: center !important;
            width: 100% !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] button {{
            width: 2.25rem !important;
            min-width: 2.25rem !important;
            height: 2.25rem !important;
            min-height: 2.25rem !important;
            padding: 0 !important;
            border-radius: 999px !important;
            background: rgba(8, 16, 27, 0.82) !important;
            border: 1px solid rgba(103, 168, 255, 0.16) !important;
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.22) !important;
            transform: rotate(180deg) !important;
        }}
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] button:hover {{
            background: rgba(14, 24, 38, 0.92) !important;
            border-color: rgba(120, 175, 255, 0.28) !important;
        }}
        section[data-testid="stSidebar"] > div {{
            background: transparent !important;
        }}
        [data-testid="stMainBlockContainer"] {{
            padding-top: 0.6rem !important;
            animation: ui-fade-slide 260ms var(--motion-curve) both;
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
            transition: left var(--motion-smooth) var(--motion-curve) !important;
        }}
        .stApp:has(section[data-testid="stSidebar"][aria-expanded="false"]) [data-testid="stBottomBlockContainer"] {{
            left: calc(var(--chat-sidebar-collapsed-width) + var(--chat-gutter)) !important;
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
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-quick) ease,
                background var(--motion-quick) ease;
            will-change: transform, box-shadow;
        }}
        [data-testid="stChatInput"] form:hover,
        [data-testid="stChatInput"] form:focus-within {{
            transform: translate3d(0, -1px, 0);
            border-color: rgba(120, 175, 255, 0.28) !important;
            box-shadow: 0 18px 34px rgba(0, 0, 0, 0.28), 0 0 0 1px rgba(120, 175, 255, 0.08) !important;
            backdrop-filter: blur(10px) saturate(122%);
            -webkit-backdrop-filter: blur(10px) saturate(122%);
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
        button,
        [data-baseweb="button"],
        [data-testid="stTextInputRootElement"] > div,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            transition:
                transform var(--motion-quick) var(--motion-curve),
                box-shadow var(--motion-quick) ease,
                border-color var(--motion-quick) ease,
                background var(--motion-quick) ease,
                filter var(--motion-quick) ease;
        }}
        [data-testid="stTextInputRootElement"] > div:hover,
        [data-testid="stTextArea"] textarea:hover,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover {{
            transform: translate3d(0, -1px, 0);
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
        @media (prefers-reduced-motion: reduce) {{
            *,
            *::before,
            *::after {{
                animation-duration: 1ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 1ms !important;
                scroll-behavior: auto !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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
