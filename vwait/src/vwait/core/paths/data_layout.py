from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .project_paths import PROJECT_ROOT


DATA_ROOT = PROJECT_ROOT / "Data"
CATALOG_ROOT = DATA_ROOT / "catalog"
RUNS_ROOT = DATA_ROOT / "runs"
CACHE_ROOT = DATA_ROOT / "cache"
TEMPLATES_ROOT = DATA_ROOT / "templates"
SYSTEM_ROOT = DATA_ROOT / "system"

TESTER_CATALOG_ROOT = CATALOG_ROOT / "tester"
TESTER_RUNS_ROOT = RUNS_ROOT / "tester"
HMI_CATALOG_ROOT = CATALOG_ROOT / "hmi"
HMI_CACHE_ROOT = CACHE_ROOT / "hmi"

_RESERVED_DATA_NAMES = {
    "catalog",
    "runs",
    "cache",
    "templates",
    "system",
    "_templates",
    "hmi_cache",
    "HMI_TESTE",
}


def ensure_data_roots() -> None:
    for path in (
        DATA_ROOT,
        CATALOG_ROOT,
        RUNS_ROOT,
        CACHE_ROOT,
        TEMPLATES_ROOT,
        SYSTEM_ROOT,
        TESTER_CATALOG_ROOT,
        TESTER_RUNS_ROOT,
        HMI_CATALOG_ROOT,
        HMI_CACHE_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


def normalize_segment(value: str) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^0-9a-z_.-]+", "_", text)
    return text.strip("_") or "unnamed"


def legacy_tester_test_dir(category: str, test_name: str) -> Path:
    return DATA_ROOT / normalize_segment(category) / normalize_segment(test_name)


def tester_catalog_dir(category: str, test_name: str) -> Path:
    return TESTER_CATALOG_ROOT / normalize_segment(category) / normalize_segment(test_name)


def tester_recorded_dir(category: str, test_name: str) -> Path:
    return tester_catalog_dir(category, test_name) / "recorded"


def tester_recorded_frames_dir(category: str, test_name: str) -> Path:
    return tester_recorded_dir(category, test_name) / "frames"


def tester_actions_path(category: str, test_name: str) -> Path:
    return tester_recorded_dir(category, test_name) / "actions.json"


def tester_dataset_path(category: str, test_name: str) -> Path:
    return tester_catalog_dir(category, test_name) / "dataset.csv"


def tester_expected_dir(category: str, test_name: str) -> Path:
    return tester_catalog_dir(category, test_name) / "expected"


def tester_expected_final_path(category: str, test_name: str) -> Path:
    return tester_expected_dir(category, test_name) / "final.png"


def tester_test_metadata_path(category: str, test_name: str) -> Path:
    return tester_catalog_dir(category, test_name) / "test.json"


def tester_runs_dir(category: str, test_name: str) -> Path:
    return TESTER_RUNS_ROOT / normalize_segment(category) / normalize_segment(test_name)


def build_run_id(moment: datetime | None = None) -> str:
    dt = (moment or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")


def load_tester_test_metadata(category: str, test_name: str) -> dict:
    path = tester_test_metadata_path(category, test_name)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_tester_test_metadata(category: str, test_name: str, payload: dict) -> Path:
    path = tester_test_metadata_path(category, test_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ensure_tester_catalog(category: str, test_name: str) -> Path:
    catalog_dir = tester_catalog_dir(category, test_name)
    tester_recorded_frames_dir(category, test_name).mkdir(parents=True, exist_ok=True)
    tester_expected_dir(category, test_name).mkdir(parents=True, exist_ok=True)
    tester_runs_dir(category, test_name).mkdir(parents=True, exist_ok=True)
    meta = load_tester_test_metadata(category, test_name)
    if not meta:
        save_tester_test_metadata(
            category,
            test_name,
            {
                "feature": "tester",
                "suite": normalize_segment(category),
                "test_id": normalize_segment(test_name),
                "latest_run_id": None,
            },
        )
    return catalog_dir


def iter_tester_categories() -> list[str]:
    categories: set[str] = set()
    if TESTER_CATALOG_ROOT.is_dir():
        for path in TESTER_CATALOG_ROOT.iterdir():
            if path.is_dir():
                categories.add(path.name)
    for path in DATA_ROOT.iterdir() if DATA_ROOT.is_dir() else []:
        if path.is_dir() and path.name not in _RESERVED_DATA_NAMES:
            categories.add(path.name)
    return sorted(categories)


def iter_tester_tests(category: str) -> list[str]:
    category_norm = normalize_segment(category)
    tests: set[str] = set()
    catalog_category = TESTER_CATALOG_ROOT / category_norm
    if catalog_category.is_dir():
        for path in catalog_category.iterdir():
            if path.is_dir():
                tests.add(path.name)
    legacy_category = DATA_ROOT / category_norm
    if legacy_category.is_dir():
        for path in legacy_category.iterdir():
            if path.is_dir():
                tests.add(path.name)
    return sorted(tests)


def latest_tester_run_dir(category: str, test_name: str) -> Path | None:
    meta = load_tester_test_metadata(category, test_name)
    latest_run_id = str(meta.get("latest_run_id") or "").strip()
    if latest_run_id:
        candidate = tester_runs_dir(category, test_name) / latest_run_id
        if candidate.is_dir():
            return candidate

    runs_dir = tester_runs_dir(category, test_name)
    if runs_dir.is_dir():
        candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)

    legacy_dir = legacy_tester_test_dir(category, test_name)
    if legacy_dir.is_dir():
        return legacy_dir
    return None


def create_tester_run_dir(category: str, test_name: str, run_id: str | None = None) -> Path:
    ensure_tester_catalog(category, test_name)
    resolved_run_id = run_id or build_run_id()
    run_dir = tester_runs_dir(category, test_name) / resolved_run_id
    (run_dir / "status").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)

    meta = load_tester_test_metadata(category, test_name)
    meta.update(
        {
            "feature": "tester",
            "suite": normalize_segment(category),
            "test_id": normalize_segment(test_name),
            "latest_run_id": resolved_run_id,
        }
    )
    save_tester_test_metadata(category, test_name, meta)
    return run_dir


def resolve_tester_run_dir(
    category: str,
    test_name: str,
    *,
    run_id: str | None = None,
    create: bool = False,
) -> Path | None:
    if run_id:
        candidate = tester_runs_dir(category, test_name) / run_id
        if candidate.is_dir() or create:
            return create_tester_run_dir(category, test_name, run_id) if create else candidate
    latest = latest_tester_run_dir(category, test_name)
    if latest is not None:
        return latest
    if create:
        return create_tester_run_dir(category, test_name)
    return None


def tester_status_dir(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "status"
    return run_dir / "status"


def tester_status_file_path(
    category: str,
    test_name: str,
    serial: str | None = None,
    *,
    run_id: str | None = None,
    create: bool = False,
) -> Path:
    if serial:
        return tester_status_dir(category, test_name, run_id=run_id, create=create) / f"{serial}.json"
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_status_dir(category, test_name, run_id=run_id, create=create) / "status_bancadas.json"
    return run_dir / "status_bancadas.json"


def tester_execution_log_path(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "execucao_log.json"
    return run_dir / "execucao_log.json"


def tester_logs_root(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "logs"
    return run_dir / "logs"


def tester_artifacts_dir(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "artifacts"
    return run_dir / "artifacts"


def tester_results_dir(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    return tester_artifacts_dir(category, test_name, run_id=run_id, create=create) / "results"


def tester_reports_dir(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "reports"
    return run_dir / "reports"


def tester_failure_report_pointer_path(category: str, test_name: str, *, run_id: str | None = None, create: bool = False) -> Path:
    run_dir = resolve_tester_run_dir(category, test_name, run_id=run_id, create=create)
    if run_dir is None:
        return tester_runs_dir(category, test_name) / (run_id or build_run_id()) / "failure_report_latest.json"
    return run_dir / "failure_report_latest.json"


def tester_system_exec_log_path(serial: str | None = None) -> Path:
    ensure_data_roots()
    if serial:
        return SYSTEM_ROOT / f"execucao_live_{normalize_segment(serial)}.log"
    return SYSTEM_ROOT / "execucao_live.log"


def tester_system_collection_log_path() -> Path:
    ensure_data_roots()
    return SYSTEM_ROOT / "coleta_live.log"


def global_log_sequence_paths() -> tuple[Path, Path, Path]:
    ensure_data_roots()
    base = SYSTEM_ROOT / "failure_log_sequence"
    return (
        base.with_suffix(".csv"),
        base.with_suffix(".raw.json"),
        base.with_suffix(".meta.json"),
    )


def log_sequence_template_path() -> Path:
    return TEMPLATES_ROOT / "log_capture_sequence_template.csv"


def hmi_capture_archive_dir() -> Path:
    return HMI_CATALOG_ROOT / "captures" / "HMI_TESTE"


def hmi_cache_dir() -> Path:
    return HMI_CACHE_ROOT


def legacy_tester_categories() -> Iterable[Path]:
    if not DATA_ROOT.is_dir():
        return ()
    return tuple(
        path
        for path in DATA_ROOT.iterdir()
        if path.is_dir() and path.name not in _RESERVED_DATA_NAMES
    )


__all__ = [
    "CACHE_ROOT",
    "CATALOG_ROOT",
    "DATA_ROOT",
    "HMI_CACHE_ROOT",
    "HMI_CATALOG_ROOT",
    "RUNS_ROOT",
    "SYSTEM_ROOT",
    "TEMPLATES_ROOT",
    "TESTER_CATALOG_ROOT",
    "TESTER_RUNS_ROOT",
    "build_run_id",
    "create_tester_run_dir",
    "ensure_data_roots",
    "ensure_tester_catalog",
    "global_log_sequence_paths",
    "hmi_cache_dir",
    "hmi_capture_archive_dir",
    "iter_tester_categories",
    "iter_tester_tests",
    "legacy_tester_categories",
    "legacy_tester_test_dir",
    "log_sequence_template_path",
    "latest_tester_run_dir",
    "normalize_segment",
    "resolve_tester_run_dir",
    "save_tester_test_metadata",
    "load_tester_test_metadata",
    "tester_actions_path",
    "tester_artifacts_dir",
    "tester_catalog_dir",
    "tester_dataset_path",
    "tester_execution_log_path",
    "tester_expected_dir",
    "tester_expected_final_path",
    "tester_failure_report_pointer_path",
    "tester_logs_root",
    "tester_recorded_dir",
    "tester_recorded_frames_dir",
    "tester_reports_dir",
    "tester_results_dir",
    "tester_runs_dir",
    "tester_status_dir",
    "tester_status_file_path",
    "tester_system_collection_log_path",
    "tester_system_exec_log_path",
    "tester_test_metadata_path",
]
