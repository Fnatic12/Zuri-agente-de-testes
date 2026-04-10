from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable


Cleaner = Callable[[Any], str]
Normalizer = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def load_optional_json_file(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        with candidate.open("r", encoding="utf-8", errors="ignore") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_existing_path(base_dir: str | Path, raw_path: Any, expected: str = "file") -> str | None:
    text = str(raw_path or "").strip()
    if not text:
        return None

    base_dir = str(base_dir)
    candidates = [text]
    if not os.path.isabs(text):
        candidates.append(os.path.join(base_dir, text))

    for candidate in candidates:
        resolved = os.path.abspath(candidate)
        if expected == "dir" and os.path.isdir(resolved):
            return resolved
        if expected == "file" and os.path.isfile(resolved):
            return resolved
    return None


def resolve_test_dir(info: dict, data_root: str | Path) -> str | None:
    status_path = str(info.get("_status_path") or "").strip()
    if status_path:
        candidate = os.path.dirname(status_path)
        if os.path.isdir(candidate):
            return candidate

    teste = str(info.get("teste") or "").strip().replace("\\", "/")
    if "/" in teste:
        categoria, nome = teste.split("/", 1)
        candidate = os.path.join(str(data_root), categoria, nome)
        if os.path.isdir(candidate):
            return candidate
    return None


def resolve_logs_root(info: dict, data_root: str | Path) -> str | None:
    test_dir = resolve_test_dir(info, data_root)
    if not test_dir:
        return None
    logs_root = os.path.join(test_dir, "logs")
    return logs_root if os.path.isdir(logs_root) else None


def resolve_log_capture_dir(info: dict, data_root: str | Path) -> str | None:
    test_dir = resolve_test_dir(info, data_root)
    if not test_dir:
        return None

    relative_capture_dir = str(info.get("log_capture_dir") or "").strip()
    if relative_capture_dir:
        candidate = os.path.join(test_dir, relative_capture_dir)
        if os.path.isdir(candidate):
            return candidate

    logs_root = resolve_logs_root(info, data_root)
    if not logs_root:
        return None

    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def resolve_logs_root_from_base_dir(base_dir: str | Path) -> str | None:
    candidate = os.path.join(str(base_dir), "logs")
    return candidate if os.path.isdir(candidate) else None


def resolve_latest_log_capture_from_base_dir(base_dir: str | Path) -> str | None:
    logs_root = resolve_logs_root_from_base_dir(base_dir)
    if not logs_root:
        return None
    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def load_failure_report_bundle(
    base_dir: str | Path,
    status_payload: dict[str, Any] | None = None,
    cleaner: Cleaner | None = None,
) -> dict[str, Any]:
    status_payload = status_payload or {}
    base_dir = str(base_dir)
    clean = cleaner or (lambda value: str(value or "").strip())

    pointer_path = os.path.join(base_dir, "failure_report_latest.json")
    pointer = load_optional_json_file(pointer_path)

    json_path = resolve_existing_path(
        base_dir,
        pointer.get("json_path") or status_payload.get("failure_report_json"),
        expected="file",
    )
    markdown_path = resolve_existing_path(
        base_dir,
        pointer.get("markdown_path") or status_payload.get("failure_report_markdown"),
        expected="file",
    )
    csv_path = resolve_existing_path(
        base_dir,
        pointer.get("csv_path") or status_payload.get("failure_report_csv"),
        expected="file",
    )
    report_dir = resolve_existing_path(
        base_dir,
        pointer.get("report_dir") or status_payload.get("failure_report_dir"),
        expected="dir",
    )

    report = load_optional_json_file(json_path)
    if not report_dir and json_path:
        candidate_dir = os.path.dirname(json_path)
        if os.path.isdir(candidate_dir):
            report_dir = candidate_dir

    status = (
        clean(status_payload.get("failure_report_status"))
        or clean(pointer.get("status"))
        or ("gerado" if report else "nao_gerado")
    ).lower()
    generated_at = (
        clean(status_payload.get("failure_report_generated_at"))
        or clean(pointer.get("generated_at"))
        or clean(report.get("generated_at"))
    )
    short_text = (
        clean(status_payload.get("failure_report_short_text"))
        or clean(pointer.get("short_text"))
        or clean(report.get("short_text"))
    )
    error = clean(status_payload.get("failure_report_error"))

    return {
        "status": status,
        "generated_at": generated_at,
        "short_text": short_text,
        "error": error,
        "pointer_path": pointer_path if os.path.isfile(pointer_path) else "",
        "json_path": json_path or "",
        "markdown_path": markdown_path or "",
        "csv_path": csv_path or "",
        "report_dir": report_dir or "",
        "report": report,
    }


def latest_screenshot_path(info: dict, data_root: str | Path) -> str | None:
    test_dir = resolve_test_dir(info, data_root)
    if not test_dir:
        return None

    hinted = str(info.get("ultimo_screenshot") or "").strip()
    if hinted:
        hinted_path = os.path.join(test_dir, hinted)
        if os.path.exists(hinted_path):
            return hinted_path

    candidates: list[str] = []
    for folder in ("resultados", "frames"):
        img_dir = os.path.join(test_dir, folder)
        if not os.path.isdir(img_dir):
            continue
        for name in os.listdir(img_dir):
            ext = os.path.splitext(name)[1].lower()
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                candidates.append(os.path.join(img_dir, name))

    resultado_final = os.path.join(test_dir, "resultado_final.png")
    if os.path.exists(resultado_final):
        candidates.append(resultado_final)

    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def count_image_files(dir_path: str | None) -> int:
    if not dir_path or not os.path.isdir(dir_path):
        return 0
    return sum(
        1
        for name in os.listdir(dir_path)
        if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    )


def load_execution_entries(
    info: dict,
    data_root: str | Path,
    normalizer: Normalizer | None = None,
) -> list[dict[str, Any]]:
    test_dir = resolve_test_dir(info, data_root)
    if not test_dir:
        return []
    exec_path = os.path.join(test_dir, "execucao_log.json")
    if not os.path.exists(exec_path):
        return []
    try:
        with open(exec_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        return []
    execucao = raw.get("execucao") if isinstance(raw, dict) else raw
    if not isinstance(execucao, list):
        return []
    if callable(normalizer):
        return normalizer(execucao)
    return execucao


__all__ = [
    "count_image_files",
    "latest_screenshot_path",
    "load_execution_entries",
    "load_failure_report_bundle",
    "load_optional_json_file",
    "resolve_existing_path",
    "resolve_latest_log_capture_from_base_dir",
    "resolve_log_capture_dir",
    "resolve_logs_root",
    "resolve_logs_root_from_base_dir",
    "resolve_test_dir",
]
