from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paths import REPORTS_DIR, iter_report_roots

from .control import list_failure_records as _list_failure_records


def list_failure_records(reports_root: str | Path | tuple[str | Path, ...] = iter_report_roots()) -> list[dict[str, Any]]:
    return _list_failure_records(reports_root)
