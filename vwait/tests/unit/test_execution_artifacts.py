from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.application import (
    count_image_files,
    latest_screenshot_path,
    load_execution_entries,
    load_failure_report_bundle,
    resolve_existing_path,
    resolve_latest_log_capture_from_base_dir,
    resolve_log_capture_dir,
    resolve_logs_root,
    resolve_logs_root_from_base_dir,
    resolve_test_dir,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_resolve_test_and_logs_dirs(tmp_path: Path):
    test_dir = tmp_path / "radio" / "teste_a"
    (test_dir / "logs" / "capture_001").mkdir(parents=True)
    info = {"teste": "radio/teste_a"}

    assert resolve_test_dir(info, tmp_path) == str(test_dir)
    assert resolve_logs_root(info, tmp_path) == str(test_dir / "logs")


def test_resolve_log_capture_dir_prefers_status_hint(tmp_path: Path):
    test_dir = tmp_path / "radio" / "teste_a"
    hinted = test_dir / "logs" / "capture_002"
    hinted.mkdir(parents=True)
    info = {"teste": "radio/teste_a", "log_capture_dir": "logs/capture_002"}

    assert resolve_log_capture_dir(info, tmp_path) == str(hinted)


def test_resolve_latest_log_capture_from_base_dir(tmp_path: Path):
    logs_root = tmp_path / "logs"
    cap1 = logs_root / "c1"
    cap2 = logs_root / "c2"
    cap1.mkdir(parents=True)
    cap2.mkdir(parents=True)

    assert resolve_logs_root_from_base_dir(tmp_path) == str(logs_root)
    latest = resolve_latest_log_capture_from_base_dir(tmp_path)
    assert latest in {str(cap1), str(cap2), str(logs_root)}


def test_load_failure_report_bundle_reads_pointer_and_report(tmp_path: Path):
    report_dir = tmp_path / "workspace" / "reports" / "failures" / "radio" / "teste_a" / "2026-04-10T10-00-00"
    report_dir.mkdir(parents=True)
    report_path = report_dir / "failure_report.json"
    _write_json(report_path, {"generated_at": "2026-04-10T10:00:00", "short_text": "Falha X"})
    pointer_path = tmp_path / "failure_report_latest.json"
    _write_json(
        pointer_path,
        {
            "status": "gerado",
            "generated_at": "2026-04-10T10:00:00",
            "short_text": "Falha X",
            "json_path": str(report_path),
            "report_dir": str(report_dir),
        },
    )

    bundle = load_failure_report_bundle(tmp_path, cleaner=lambda value: str(value or "").strip())
    assert bundle["status"] == "gerado"
    assert bundle["short_text"] == "Falha X"
    assert bundle["json_path"] == str(report_path)


def test_latest_screenshot_and_count_images(tmp_path: Path):
    test_dir = tmp_path / "radio" / "teste_a"
    resultados = test_dir / "resultados"
    resultados.mkdir(parents=True)
    img = resultados / "resultado_01.png"
    img.write_bytes(b"fake")
    info = {"teste": "radio/teste_a"}

    assert latest_screenshot_path(info, tmp_path) == str(img)
    assert count_image_files(str(resultados)) == 1


def test_load_execution_entries_uses_normalizer(tmp_path: Path):
    test_dir = tmp_path / "radio" / "teste_a"
    _write_json(test_dir / "execucao_log.json", {"execucao": [{"acao": "tap", "status": "ok"}]})
    info = {"teste": "radio/teste_a"}

    entries = load_execution_entries(info, tmp_path, normalizer=lambda rows: [{"count": len(rows)}])
    assert entries == [{"count": 1}]


def test_resolve_existing_path_accepts_relative_file(tmp_path: Path):
    path = tmp_path / "artifact.json"
    path.write_text("{}", encoding="utf-8")
    assert resolve_existing_path(tmp_path, "artifact.json", expected="file") == str(path.resolve())
