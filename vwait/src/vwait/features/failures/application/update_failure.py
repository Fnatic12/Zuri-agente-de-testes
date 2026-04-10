from __future__ import annotations

from pathlib import Path
from typing import Any

from .control import update_failure_control as _update_failure_control


def update_failure_control(
    report_dir: str | Path,
    report: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    return _update_failure_control(report_dir, report, updates)
