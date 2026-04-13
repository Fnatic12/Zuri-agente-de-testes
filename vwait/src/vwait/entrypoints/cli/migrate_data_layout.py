from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.core.paths import (
    DATA_ROOT,
    SYSTEM_ROOT,
    TEMPLATES_ROOT,
    build_run_id,
    ensure_data_roots,
    hmi_cache_dir,
    hmi_capture_archive_dir,
    legacy_tester_categories,
    legacy_tester_test_dir,
    tester_actions_path,
    tester_catalog_dir,
    tester_dataset_path,
    tester_expected_final_path,
    tester_reports_dir,
    tester_results_dir,
    tester_runs_dir,
    tester_status_dir,
)


def _move_file(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    shutil.move(str(src), str(dst))


def _move_tree_contents(src_dir: Path, dst_dir: Path) -> None:
    if not src_dir.is_dir():
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(src_dir.iterdir()):
        target = dst_dir / path.name
        if path.is_dir():
            _move_tree_contents(path, target)
            try:
                path.rmdir()
            except OSError:
                pass
        else:
            _move_file(path, target)


def _guess_legacy_run_id(test_dir: Path) -> str:
    candidates = [
        test_dir / "execucao_log.json",
        test_dir / "resultado_final.png",
        test_dir,
    ]
    for candidate in candidates:
        if candidate.exists():
            dt = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
            return f"legacy_{build_run_id(dt)}"
    return f"legacy_{build_run_id()}"


def migrate_templates_and_system() -> None:
    ensure_data_roots()
    legacy_templates = DATA_ROOT / "_templates"
    if legacy_templates.is_dir():
        _move_tree_contents(legacy_templates, TEMPLATES_ROOT)
        try:
            legacy_templates.rmdir()
        except OSError:
            pass

    for legacy_log in DATA_ROOT.glob("*.log"):
        _move_file(legacy_log, SYSTEM_ROOT / legacy_log.name)


def migrate_hmi_data() -> None:
    ensure_data_roots()
    legacy_hmi_cache = DATA_ROOT / "hmi_cache"
    if legacy_hmi_cache.is_dir():
        _move_tree_contents(legacy_hmi_cache, hmi_cache_dir())
        try:
            legacy_hmi_cache.rmdir()
        except OSError:
            pass

    legacy_hmi_teste = DATA_ROOT / "HMI_TESTE"
    if legacy_hmi_teste.is_dir():
        _move_tree_contents(legacy_hmi_teste, hmi_capture_archive_dir())
        try:
            legacy_hmi_teste.rmdir()
        except OSError:
            pass


def migrate_legacy_tester_tests() -> None:
    ensure_data_roots()
    for category_dir in legacy_tester_categories():
        category = category_dir.name
        for test_dir in sorted(path for path in category_dir.iterdir() if path.is_dir()):
            test_name = test_dir.name
            catalog_dir = tester_catalog_dir(category, test_name)
            catalog_dir.mkdir(parents=True, exist_ok=True)

            _move_file(test_dir / "dataset.csv", tester_dataset_path(category, test_name))
            _move_file(test_dir / "resultado_final.png", tester_expected_final_path(category, test_name))
            _move_file(test_dir / "json" / "acoes.json", tester_actions_path(category, test_name))
            _move_tree_contents(test_dir / "frames", catalog_dir / "recorded" / "frames")

            run_id = _guess_legacy_run_id(test_dir)
            run_dir = tester_runs_dir(category, test_name) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            _move_file(test_dir / "execucao_log.json", run_dir / "execucao_log.json")
            _move_tree_contents(test_dir / "logs", run_dir / "logs")
            _move_tree_contents(test_dir / "resultados", tester_results_dir(category, test_name, run_id=run_id, create=True))
            _move_tree_contents(test_dir / "hmi_validation", tester_results_dir(category, test_name, run_id=run_id, create=True) / "hmi_validation")
            _move_tree_contents(test_dir / "esperados", catalog_dir / "expected")
            _move_tree_contents(test_dir / "json", catalog_dir / "recorded")

            for status_file in sorted(test_dir.glob("status_*.json")):
                serial = status_file.stem.replace("status_", "", 1)
                _move_file(status_file, tester_status_dir(category, test_name, run_id=run_id, create=True) / f"{serial}.json")

            for extra_name in ("execution_context.json", "test_meta.json", "failure_report_latest.json"):
                extra_path = test_dir / extra_name
                if extra_name == "failure_report_latest.json":
                    _move_file(extra_path, run_dir / extra_name)
                else:
                    _move_file(extra_path, run_dir / extra_name)

            metadata_path = catalog_dir / "test.json"
            metadata_path.write_text(
                (
                    "{\n"
                    f'  "feature": "tester",\n'
                    f'  "suite": "{category}",\n'
                    f'  "test_id": "{test_name}",\n'
                    f'  "latest_run_id": "{run_id}"\n'
                    "}\n"
                ),
                encoding="utf-8",
            )

            try:
                shutil.rmtree(test_dir)
            except OSError:
                pass

        try:
            category_dir.rmdir()
        except OSError:
            pass


def main() -> None:
    migrate_templates_and_system()
    migrate_hmi_data()
    migrate_legacy_tester_tests()
    print(f"[ok] Layout de Data migrado para {DATA_ROOT}")


if __name__ == "__main__":
    main()
