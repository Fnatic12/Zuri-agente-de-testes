from __future__ import annotations

from pathlib import Path
from typing import Iterable


FEATURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DIR.parents[3]
DATA_DIR = PROJECT_ROOT / "Data"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
REPORTS_DIR = WORKSPACE_DIR / "reports" / "failures"
LEGACY_REPORTS_DIR = PROJECT_ROOT / "KPM" / "reports"


def ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def test_dir(category: str, test_name: str) -> Path:
    return DATA_DIR / category / test_name


def iter_report_roots() -> tuple[Path, ...]:
    roots: list[Path] = [REPORTS_DIR]
    if LEGACY_REPORTS_DIR != REPORTS_DIR:
        roots.append(LEGACY_REPORTS_DIR)
    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = str(root)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(root)
    return tuple(unique_roots)


__all__ = [
    "DATA_DIR",
    "FEATURE_DIR",
    "LEGACY_REPORTS_DIR",
    "PROJECT_ROOT",
    "REPORTS_DIR",
    "WORKSPACE_DIR",
    "ensure_reports_dir",
    "iter_report_roots",
    "test_dir",
]
