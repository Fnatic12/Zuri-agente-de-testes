from __future__ import annotations

from pathlib import Path

from vwait.core.paths import (
    DATA_ROOT,
    legacy_tester_test_dir,
    resolve_tester_run_dir,
    tester_failure_report_pointer_path,
    tester_status_file_path,
)

FEATURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DIR.parents[3]
STATUS_FILE = DATA_ROOT / "status_bancadas.json"


def status_dir(category: str, test_name: str) -> Path:
    resolved = resolve_tester_run_dir(category, test_name)
    if resolved is not None:
        return resolved
    legacy = legacy_tester_test_dir(category, test_name)
    if legacy.exists():
        return legacy
    return DATA_ROOT / "runs" / "tester" / category / test_name


def test_ref(category: str, test_name: str) -> str:
    return f"{category}/{test_name}"


def status_file_path(category: str, test_name: str, serial: str | None = None) -> Path:
    return tester_status_file_path(category, test_name, serial)


def failure_report_pointer_path(category: str, test_name: str) -> Path:
    return tester_failure_report_pointer_path(category, test_name)


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
