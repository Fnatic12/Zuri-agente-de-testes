from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_FRONTEND_DIR = Path(__file__).resolve().parent / "failure_board_frontend" / "dist"
_component = components.declare_component("failure_board", path=str(_FRONTEND_DIR))


def render_failure_board(
    items: list[dict[str, Any]],
    key: str | None = None,
) -> dict[str, Any]:
    value = _component(
        items=items,
        default={"event": "noop", "containers": items, "itemId": "", "eventId": ""},
        key=key,
    )
    return value if isinstance(value, dict) else {"event": "noop", "containers": items, "itemId": "", "eventId": ""}
