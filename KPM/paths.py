from __future__ import annotations

from pathlib import Path


KPM_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = KPM_DIR.parent
DATA_DIR = PROJECT_ROOT / "Data"
REPORTS_DIR = KPM_DIR / "reports"


def ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def test_dir(category: str, test_name: str) -> Path:
    return DATA_DIR / category / test_name
