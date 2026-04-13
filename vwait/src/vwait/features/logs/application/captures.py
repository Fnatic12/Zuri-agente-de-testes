from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from vwait.core.paths import DATA_ROOT, TESTER_RUNS_ROOT

from ..domain import IMAGE_EXTS, MAX_AI_FILE_CHARS, MAX_VIEW_CHARS, TEXT_EXTS


def open_folder(path: str | Path) -> tuple[bool, str]:
    resolved = os.path.abspath(str(path or "").strip())
    if not resolved or not os.path.exists(resolved):
        return False, "Pasta nao encontrada."
    try:
        if os.name == "nt":
            os.startfile(resolved)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", resolved])
        else:
            subprocess.Popen(["xdg-open", resolved])
        return True, resolved
    except Exception as exc:
        return False, str(exc)


def safe_datetime(path: str | Path) -> datetime:
    return datetime.fromtimestamp(os.path.getmtime(path))


def try_load_json(path: str | Path) -> dict | list | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def clean_display_text(value: str) -> str:
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def read_file_for_view(path: str | Path, max_chars: int = MAX_VIEW_CHARS) -> tuple[str, bool]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except Exception as exc:
        return f"Falha ao ler arquivo: {exc}", False

    text = clean_display_text(decode_bytes(raw))
    truncated = False
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        text = f"{head}\n\n... [conteudo truncado] ...\n\n{tail}"
        truncated = True
    return text, truncated


def read_file_for_ai(path: str | Path, max_chars: int = MAX_AI_FILE_CHARS) -> str:
    ext = Path(path).suffix.lower()
    raw_json = try_load_json(path) if ext == ".json" else None
    if raw_json is not None:
        text = json.dumps(raw_json, ensure_ascii=False, indent=2)
    else:
        text, _ = read_file_for_view(path, max_chars=max_chars)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars // 2]}\n\n... [truncado para analise] ...\n\n{text[-max_chars // 2 :]}"


def is_text_like(path: str | Path) -> bool:
    ext = Path(path).suffix.lower()
    if ext in TEXT_EXTS:
        return True
    try:
        with open(path, "rb") as handle:
            sample = handle.read(2048)
        if not sample:
            return True
        return b"\x00" not in sample
    except Exception:
        return False


def list_capture_files(capture_dir: str | Path) -> list[dict]:
    files = []
    capture_dir = str(capture_dir)
    for root, _, names in os.walk(capture_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            relpath = os.path.relpath(path, capture_dir)
            ext = os.path.splitext(name)[1].lower()
            files.append(
                {
                    "name": name,
                    "path": path,
                    "relpath": relpath,
                    "size": os.path.getsize(path) if os.path.exists(path) else 0,
                    "ext": ext,
                    "image": ext in IMAGE_EXTS,
                    "text_like": is_text_like(path),
                }
            )
    files.sort(key=lambda item: item["relpath"].lower())
    return files


def parse_capture_datetime(value) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def human_size(size: int) -> str:
    size_f = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if size_f < 1024.0 or unit == "GB":
            return f"{size_f:.1f}{unit}"
        size_f /= 1024.0
    return f"{size_f:.1f}GB"


def load_log_captures(data_root: str | Path) -> list[dict]:
    captures = []
    provided_root = Path(data_root)
    runs_root = provided_root if provided_root != Path(DATA_ROOT) else Path(TESTER_RUNS_ROOT)
    if not runs_root.is_dir():
        return captures

    for categoria in os.listdir(runs_root):
        categoria_dir = os.path.join(runs_root, categoria)
        if not os.path.isdir(categoria_dir):
            continue
        for teste in os.listdir(categoria_dir):
            teste_dir = os.path.join(categoria_dir, teste)
            if not os.path.isdir(teste_dir):
                continue
            legacy_logs_dir = os.path.join(teste_dir, "logs")
            if os.path.isdir(legacy_logs_dir):
                _append_capture_entries(
                    captures,
                    categoria=categoria,
                    teste=teste,
                    run_id="legacy",
                    logs_dir=legacy_logs_dir,
                )
                continue
            for run_id in os.listdir(teste_dir):
                run_dir = os.path.join(teste_dir, run_id)
                if not os.path.isdir(run_dir):
                    continue
                logs_dir = os.path.join(run_dir, "logs")
                if not os.path.isdir(logs_dir):
                    continue
                _append_capture_entries(
                    captures,
                    categoria=categoria,
                    teste=teste,
                    run_id=run_id,
                    logs_dir=logs_dir,
                )
    captures.sort(key=lambda item: item["timestamp"], reverse=True)
    return captures


def _append_capture_entries(
    captures: list[dict],
    *,
    categoria: str,
    teste: str,
    run_id: str,
    logs_dir: str,
) -> None:
    for capture_name in os.listdir(logs_dir):
        capture_dir = os.path.join(logs_dir, capture_name)
        if not os.path.isdir(capture_dir):
            continue
        metadata_path = os.path.join(capture_dir, "capture_metadata.json")
        metadata = try_load_json(metadata_path)
        if not isinstance(metadata, dict):
            metadata = {}
        files = list_capture_files(capture_dir)
        capture_dt = parse_capture_datetime(metadata.get("started_at")) or safe_datetime(capture_dir)
        captures.append(
            {
                "label": f"{categoria}/{teste} | {run_id} | {capture_name}",
                "categoria": categoria,
                "teste": teste,
                "run_id": run_id,
                "capture_name": capture_name,
                "capture_dir": capture_dir,
                "logs_dir": logs_dir,
                "metadata": metadata,
                "metadata_path": metadata_path if os.path.exists(metadata_path) else None,
                "timestamp": capture_dt,
                "files": files,
            }
        )
