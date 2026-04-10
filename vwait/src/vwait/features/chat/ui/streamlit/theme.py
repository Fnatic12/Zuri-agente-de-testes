from __future__ import annotations

import unicodedata

from app.shared import ui_theme as _ui_theme


apply_dark_background = _ui_theme.apply_dark_background


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()


def sanitize_text(value: str):
    if not isinstance(value, str):
        return value
    try:
        if any(ch in value for ch in ["Ã", "â", "�"]):
            value = value.encode("latin1", "ignore").decode("utf-8", "ignore")
    except Exception:
        pass
    value = unicodedata.normalize("NFKD", value)
    return value.encode("ascii", "ignore").decode("ascii")


__all__ = ["apply_dark_background", "apply_panel_button_theme", "sanitize_text"]
