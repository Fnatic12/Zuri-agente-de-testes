from __future__ import annotations

from pathlib import Path


FEATURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DIR.parents[3]
DATA_ROOT = PROJECT_ROOT / "Data"
STATUS_FILE = DATA_ROOT / "status_bancadas.json"


def status_dir(category: str, test_name: str) -> Path:
    return DATA_ROOT / category / test_name


def test_ref(category: str, test_name: str) -> str:
    return f"{category}/{test_name}"


def status_file_path(category: str, test_name: str, serial: str | None = None) -> Path:
    filename = f"status_{serial}.json" if serial else "status_bancadas.json"
    return status_dir(category, test_name) / filename


def failure_report_pointer_path(category: str, test_name: str) -> Path:
    return status_dir(category, test_name) / "failure_report_latest.json"


__all__ = [
    "DATA_ROOT",
    "FEATURE_DIR",
    "PROJECT_ROOT",
    "STATUS_FILE",
    "failure_report_pointer_path",
    "status_dir",
    "status_file_path",
    "test_ref",
]
