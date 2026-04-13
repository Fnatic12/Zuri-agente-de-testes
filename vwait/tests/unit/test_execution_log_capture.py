from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.application import (
    default_log_label,
    execute_default_log_capture,
    execute_post_failure_log_capture,
    load_failure_log_steps,
    log_capture_dir,
    resolve_failure_log_sequence,
)


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_default_log_label_sanitizes_pattern():
    assert default_log_label("/data/vendor/broadcastradio/log*") == "log"


def test_log_capture_dir_uses_timestamp():
    from datetime import datetime

    path = log_capture_dir("/tmp/base", datetime(2026, 4, 10, 10, 30, 0))
    assert path.endswith("logs/20260410_103000")


def test_resolve_failure_log_sequence_prefers_test_dir(tmp_path: Path):
    test_dir = tmp_path / "radio" / "teste_a"
    seq = test_dir / "failure_log_sequence.json"
    seq.parent.mkdir(parents=True, exist_ok=True)
    seq.write_text("[]", encoding="utf-8")

    resolved = resolve_failure_log_sequence("radio", "teste_a", data_root=tmp_path, test_dir=test_dir)
    assert resolved == str(seq)


def test_load_failure_log_steps_supports_json(tmp_path: Path):
    seq = tmp_path / "steps.json"
    seq.write_text(json.dumps({"steps": [{"tipo": "wait"}]}), encoding="utf-8")
    steps = load_failure_log_steps(seq)
    assert steps == [{"tipo": "wait"}]


def test_execute_default_log_capture_writes_metadata_and_returns_artifact_dir(tmp_path: Path):
    writes = []

    def atomic_write_json(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        writes.append(path)

    def run_subprocess(_cmd, **_kwargs):
        return _Result(0, "/data/tombstones/tomb1\n")

    def adb_cmd_builder(serial):
        return ["adb", "-s", serial] if serial else ["adb"]

    def pull_file(device_path, destino_local, _serial):
        target = Path(destino_local)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(device_path, encoding="utf-8")
        return str(target)

    def capture_screenshot(capture_dir, name, _serial):
        shot = Path(capture_dir) / name
        shot.write_bytes(b"fake")
        return str(shot)

    result = execute_default_log_capture(
        "radio",
        "teste_a",
        "SERIAL1",
        "falha",
        base_dir=tmp_path / "radio" / "teste_a",
        adb_cmd_builder=adb_cmd_builder,
        run_subprocess=run_subprocess,
        adb_timeout=25,
        pull_file=pull_file,
        capture_screenshot=capture_screenshot,
        atomic_write_json=atomic_write_json,
        patterns=("/data/tombstones/*",),
    )

    assert result["status"] == "capturado"
    assert result["artifact_dir"]
    assert any(path.name == "capture_metadata.json" for path in writes)


def test_execute_post_failure_log_capture_runs_steps_and_records_metadata(tmp_path: Path):
    seq = tmp_path / "radio" / "teste_a" / "failure_log_sequence.json"
    seq.parent.mkdir(parents=True, exist_ok=True)
    seq.write_text(json.dumps([{"tipo": "wait"}]), encoding="utf-8")

    def atomic_write_json(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def execute_step(_step, _serial, artifacts_dir, step_index):
        artifact = Path(artifacts_dir) / f"step_{step_index:02d}.txt"
        artifact.write_text("ok", encoding="utf-8")
        return {
            "step": step_index,
            "label": "passo",
            "type": "wait",
            "started_at": "2026-04-10T10:00:00",
            "finished_at": "2026-04-10T10:00:01",
            "status": "ok",
            "artifact": artifact.name,
            "error": None,
        }

    def capture_screenshot(capture_dir, name, _serial):
        shot = Path(capture_dir) / name
        shot.write_bytes(b"fake")
        return str(shot)

    result = execute_post_failure_log_capture(
        "radio",
        "teste_a",
        "SERIAL1",
        "falha",
        base_dir=tmp_path / "radio" / "teste_a",
        data_root=tmp_path,
        execute_step=execute_step,
        capture_screenshot=capture_screenshot,
        atomic_write_json=atomic_write_json,
    )

    assert result["status"] == "capturado"
    assert result["sequence_path"] == str(seq)
