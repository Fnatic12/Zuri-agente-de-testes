from __future__ import annotations

import os

import streamlit as st


DEFAULT_AUTO_REFRESH_MS = 5000


def _hide_refresh_chrome() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stStatusWidget"],
        [data-testid="stDecoration"],
        [data-testid="stToolbar"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            pointer-events: none !important;
        }

        iframe[title*="streamlit_autorefresh"],
        iframe[src*="streamlit_autorefresh"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            border: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _env_flag_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "nao", "não", "no", "off", "disabled"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1000, value)


def enable_global_auto_refresh(*, key: str, default_interval_ms: int = DEFAULT_AUTO_REFRESH_MS) -> None:
    """Enable a lightweight global Streamlit refresh when the optional package exists."""
    _hide_refresh_chrome()

    if not _env_flag_enabled("VWAIT_AUTO_REFRESH", default=True):
        return
    if bool(st.session_state.get("vwait_auto_refresh_paused")):
        return

    interval_ms = _env_int("VWAIT_AUTO_REFRESH_MS", default_interval_ms)
    try:
        from streamlit_autorefresh import st_autorefresh
    except Exception:
        return

    st_autorefresh(interval=interval_ms, limit=None, key=f"vwait_global_refresh_{key}")


__all__ = ["DEFAULT_AUTO_REFRESH_MS", "enable_global_auto_refresh"]
