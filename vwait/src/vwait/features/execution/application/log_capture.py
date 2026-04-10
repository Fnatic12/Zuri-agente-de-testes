from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..domain import DEFAULT_FAILURE_LOG_PATTERNS, LOG_CAPTURE_SEQUENCE_FILENAMES


RunSubprocess = Callable[..., Any]
AtomicWriteJson = Callable[[str | Path, Any], None]
AdbCmdBuilder = Callable[[str | None], list[str]]
PullFile = Callable[[str, str, str | None], str | None]
CaptureScreenshot = Callable[[str, str, str | None], str | None]
ExecuteStep = Callable[[dict[str, Any], str | None, str, int], dict[str, Any]]


def default_log_label(pattern: str) -> str:
    base = str(pattern or "").rstrip("*").rstrip("/")
    label = os.path.basename(base) or "logs"
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", label) or "logs"


def list_matches_device_glob(
    pattern: str,
    *,
    serial: str | None,
    adb_cmd_builder: AdbCmdBuilder,
    run_subprocess: RunSubprocess,
    adb_timeout: int,
) -> list[str]:
    script = f'for p in {pattern}; do if [ -e "$p" ]; then echo "$p"; fi; done'
    result = run_subprocess(
        adb_cmd_builder(serial) + ["shell", "sh", "-c", script],
        timeout=max(adb_timeout, 45),
        quiet=True,
    )
    if result is None or getattr(result, "returncode", 1) != 0:
        return []
    matches = []
    for line in (getattr(result, "stdout", "") or "").splitlines():
        text = str(line).strip()
        if text:
            matches.append(text)
    return sorted(set(matches))


def prepare_logs_post_failure(
    *,
    serial: str | None,
    adb_cmd_builder: AdbCmdBuilder,
    run_subprocess: RunSubprocess,
    adb_timeout: int,
    patterns: tuple[str, ...] = DEFAULT_FAILURE_LOG_PATTERNS,
) -> list[dict[str, Any]]:
    cleaned = []
    for pattern in patterns:
        script = f'for p in {pattern}; do if [ -e "$p" ]; then rm -rf "$p"; fi; done'
        result = run_subprocess(
            adb_cmd_builder(serial) + ["shell", "sh", "-c", script],
            timeout=max(adb_timeout, 60),
            quiet=True,
        )
        cleaned.append(
            {
                "pattern": pattern,
                "status": "ok" if result is not None and getattr(result, "returncode", 1) == 0 else "erro",
                "error": None if result is not None and getattr(result, "returncode", 1) == 0 else "falha ao limpar origem remota",
            }
        )
    return cleaned


def log_capture_dir(base_dir: str | Path, started_at: datetime) -> str:
    return os.path.join(str(base_dir), "logs", started_at.strftime("%Y%m%d_%H%M%S"))


def failure_log_sequence_candidates(
    category: str,
    test_name: str,
    *,
    data_root: str | Path,
    test_dir: str | Path,
    sequence_filenames: tuple[str, ...] = LOG_CAPTURE_SEQUENCE_FILENAMES,
) -> list[str]:
    category_dir = os.path.join(str(data_root), category)
    candidates = []
    for root in (str(test_dir), category_dir, str(data_root)):
        for filename in sequence_filenames:
            candidates.append(os.path.join(root, filename))
    return candidates


def resolve_failure_log_sequence(
    category: str,
    test_name: str,
    *,
    data_root: str | Path,
    test_dir: str | Path,
    sequence_filenames: tuple[str, ...] = LOG_CAPTURE_SEQUENCE_FILENAMES,
) -> str | None:
    for candidate in failure_log_sequence_candidates(
        category,
        test_name,
        data_root=data_root,
        test_dir=test_dir,
        sequence_filenames=sequence_filenames,
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def load_failure_log_steps(sequence_path: str | Path | None) -> list[dict[str, Any]]:
    if not sequence_path or not os.path.exists(sequence_path):
        return []

    sequence_path = str(sequence_path)
    ext = os.path.splitext(sequence_path)[1].lower()
    if ext == ".csv":
        with open(sequence_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    if ext == ".json":
        with open(sequence_path, "r", encoding="utf-8", errors="ignore") as handle:
            raw = json.load(handle)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            for key in ("acoes", "steps", "actions"):
                values = raw.get(key)
                if isinstance(values, list):
                    return [item for item in values if isinstance(item, dict)]
    return []


def execute_default_log_capture(
    category: str,
    test_name: str,
    serial: str | None,
    motivo: str,
    *,
    base_dir: str | Path,
    adb_cmd_builder: AdbCmdBuilder,
    run_subprocess: RunSubprocess,
    adb_timeout: int,
    pull_file: PullFile,
    capture_screenshot: CaptureScreenshot,
    atomic_write_json: AtomicWriteJson,
    patterns: tuple[str, ...] = DEFAULT_FAILURE_LOG_PATTERNS,
) -> dict[str, Any]:
    started_at = datetime.now()
    base_dir = str(base_dir)
    capture_dir = log_capture_dir(base_dir, started_at)
    logs_root = os.path.join(capture_dir, "radio_logs")
    os.makedirs(logs_root, exist_ok=True)

    metadata_path = os.path.join(capture_dir, "capture_metadata.json")
    metadata = {
        "categoria": category,
        "teste": test_name,
        "serial": serial,
        "motivo": motivo,
        "mode": "default_auto_capture",
        "status": "executando",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "patterns": [],
    }
    atomic_write_json(metadata_path, metadata)

    total_artifacts = 0
    for idx, pattern in enumerate(patterns, start=1):
        label = default_log_label(pattern)
        matches = list_matches_device_glob(
            pattern,
            serial=serial,
            adb_cmd_builder=adb_cmd_builder,
            run_subprocess=run_subprocess,
            adb_timeout=adb_timeout,
        )
        pattern_payload = {
            "pattern": pattern,
            "label": label,
            "match_count": len(matches),
            "status": "vazio",
            "artifacts": [],
            "error": None,
        }

        for match in matches:
            output_name = os.path.basename(match.rstrip("/")) or label
            target_root = os.path.join(logs_root, f"{idx:02d}_{label}")
            local_target = os.path.join(target_root, output_name)
            saved = pull_file(match, local_target, serial)
            if saved:
                pattern_payload["artifacts"].append(os.path.relpath(saved, capture_dir))
                total_artifacts += 1
            else:
                pattern_payload["status"] = "falha"
                pattern_payload["error"] = f"falha ao puxar {match}"
                break

        if pattern_payload["status"] != "falha":
            pattern_payload["status"] = "capturado" if pattern_payload["artifacts"] else "vazio"

        metadata["patterns"].append(pattern_payload)
        atomic_write_json(metadata_path, metadata)

    final_shot = capture_screenshot(capture_dir, "estado_final.png", serial)
    metadata["status"] = "capturado" if total_artifacts > 0 else "sem_artefatos"
    metadata["finished_at"] = datetime.now().isoformat()
    metadata["total_artifacts"] = total_artifacts
    metadata["final_screenshot"] = (
        os.path.relpath(final_shot, capture_dir) if final_shot and os.path.exists(final_shot) else None
    )
    atomic_write_json(metadata_path, metadata)
    return {
        "status": "capturado" if total_artifacts > 0 else "sem_artefatos",
        "artifact_dir": os.path.relpath(capture_dir, base_dir),
        "error": None if total_artifacts > 0 else "Nenhum log novo encontrado nos caminhos padrao.",
        "sequence_path": "default_auto_capture",
    }


def execute_post_failure_log_capture(
    category: str,
    test_name: str,
    serial: str | None,
    motivo: str,
    *,
    base_dir: str | Path,
    data_root: str | Path,
    execute_step: ExecuteStep,
    capture_screenshot: CaptureScreenshot,
    atomic_write_json: AtomicWriteJson,
    sequence_filenames: tuple[str, ...] = LOG_CAPTURE_SEQUENCE_FILENAMES,
) -> dict[str, Any]:
    base_dir = str(base_dir)
    sequence_path = resolve_failure_log_sequence(
        category,
        test_name,
        data_root=data_root,
        test_dir=base_dir,
        sequence_filenames=sequence_filenames,
    )
    if not sequence_path:
        return {
            "status": "sem_roteiro",
            "artifact_dir": None,
            "error": "Nenhum roteiro de captura encontrado.",
            "sequence_path": None,
        }

    steps = load_failure_log_steps(sequence_path)
    if not steps:
        return {
            "status": "sem_roteiro",
            "artifact_dir": None,
            "error": f"Roteiro encontrado em {sequence_path}, mas sem passos validos.",
            "sequence_path": sequence_path,
        }

    started_at = datetime.now()
    capture_dir = log_capture_dir(base_dir, started_at)
    os.makedirs(capture_dir, exist_ok=True)
    metadata_path = os.path.join(capture_dir, "capture_metadata.json")
    metadata = {
        "categoria": category,
        "teste": test_name,
        "serial": serial,
        "motivo": motivo,
        "sequence_path": os.path.relpath(sequence_path, base_dir),
        "status": "executando",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "steps": [],
    }
    atomic_write_json(metadata_path, metadata)

    for step_index, step in enumerate(steps, start=1):
        result = execute_step(step, serial, capture_dir, step_index)
        metadata["steps"].append(result)
        if result["status"] != "ok":
            metadata["status"] = "falha"
            metadata["finished_at"] = datetime.now().isoformat()
            metadata["error"] = result.get("error")
            atomic_write_json(metadata_path, metadata)
            return {
                "status": "falha",
                "artifact_dir": os.path.relpath(capture_dir, base_dir),
                "error": result.get("error"),
                "sequence_path": sequence_path,
            }
        atomic_write_json(metadata_path, metadata)

    final_shot = capture_screenshot(capture_dir, "estado_final.png", serial)
    metadata["status"] = "capturado"
    metadata["finished_at"] = datetime.now().isoformat()
    metadata["final_screenshot"] = (
        os.path.relpath(final_shot, capture_dir) if final_shot and os.path.exists(final_shot) else None
    )
    atomic_write_json(metadata_path, metadata)
    return {
        "status": "capturado",
        "artifact_dir": os.path.relpath(capture_dir, base_dir),
        "error": None,
        "sequence_path": sequence_path,
    }


__all__ = [
    "default_log_label",
    "execute_default_log_capture",
    "execute_post_failure_log_capture",
    "failure_log_sequence_candidates",
    "list_matches_device_glob",
    "load_failure_log_steps",
    "log_capture_dir",
    "prepare_logs_post_failure",
    "resolve_failure_log_sequence",
]
