from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..paths import (
    DATA_ROOT,
    failure_report_pointer_path,
    status_dir,
    status_file_path,
    test_ref,
)


STATUS_FIELDS = (
    "serial",
    "status",
    "teste",
    "acoes_totais",
    "acoes_executadas",
    "progresso",
    "tempo_decorrido_s",
    "inicio",
    "fim",
    "atualizado_em",
    "categoria",
    "ultima_acao",
    "ultima_acao_idx",
    "ultima_acao_status",
    "resultados_ok",
    "resultados_divergentes",
    "similaridade_media",
    "ultima_similaridade",
    "ultimo_screenshot",
    "velocidade_acoes_min",
    "resultado_final",
    "log_capture_status",
    "log_capture_dir",
    "log_capture_error",
    "log_capture_sequence",
    "failure_report_status",
    "failure_report_dir",
    "failure_report_json",
    "failure_report_markdown",
    "failure_report_csv",
    "failure_report_short_text",
    "failure_report_generated_at",
    "failure_report_error",
    "erro_motivo",
)

_status_lock = threading.Lock()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=path.parent) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _parse_datetime(value: Any) -> datetime | None:
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


def bancada_key_from_serial(serial: str | None) -> str:
    if not serial or str(serial).strip() == "":
        return "2801761952320038"
    return str(serial)


def carregar_status(category: str, test_name: str, serial: str | None = None) -> dict:
    path = status_file_path(category, test_name, serial)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def carregar_payload_bancada(category: str, test_name: str, bancada_key: str) -> dict:
    raw = carregar_status(category, test_name, serial=bancada_key)
    if not isinstance(raw, dict):
        return {}
    nested = raw.get(bancada_key)
    if isinstance(nested, dict):
        return dict(nested)
    if str(raw.get("serial", "")).strip() == str(bancada_key):
        return dict(raw)
    return {}


def salvar_status(status: dict, category: str, test_name: str, serial: str | None = None) -> None:
    try:
        with _status_lock:
            path = status_file_path(category, test_name, serial)
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, status)
    except Exception as exc:
        print(f"ERRO: falha ao salvar status: {exc}")


def limpar_relatorio_falha_automatico(category: str, test_name: str) -> None:
    pointer_path = failure_report_pointer_path(category, test_name)
    if pointer_path.exists():
        try:
            pointer_path.unlink()
        except Exception:
            pass


def extract_status_payload(serial: str, raw: dict) -> dict:
    payload = {}
    nested = raw.get(serial)
    if isinstance(nested, dict):
        payload.update(nested)
    for key in STATUS_FIELDS:
        if key in raw and raw.get(key) is not None:
            payload[key] = raw.get(key)
    payload["serial"] = serial
    return payload


def carregar_status_bancadas(data_root: str | Path = DATA_ROOT) -> dict:
    latest = {}
    data_root = Path(data_root)
    if not data_root.is_dir():
        return latest

    for path in data_root.rglob("*.json"):
        if path.name == "status_bancadas.json":
            continue
        if path.parent.name != "status" and not path.name.startswith("status_"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
        except Exception:
            continue

        serial = str(raw.get("serial") or path.stem.replace("status_", "", 1)).strip()
        if not serial:
            continue

        payload = extract_status_payload(serial, raw)
        ts = (
            _parse_datetime(payload.get("atualizado_em"))
            or _parse_datetime(payload.get("inicio"))
            or _parse_datetime(payload.get("fim"))
            or datetime.fromtimestamp(path.stat().st_mtime)
        )

        prev = latest.get(serial)
        if prev is None or ts > prev.get("_timestamp_dt", datetime.min):
            payload["_timestamp_dt"] = ts
            payload["_status_path"] = str(path)
            latest[serial] = payload
    return latest


def carregar_status_teste(base_dir: str | Path) -> dict[str, Any]:
    base_dir = Path(base_dir)
    if not base_dir.is_dir():
        return {}

    candidates = sorted(base_dir.glob("status_*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return {}

    status_path = candidates[-1]
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    serial = str(raw.get("serial") or status_path.stem[len("status_") :]).strip()
    payload = extract_status_payload(serial, raw)
    payload["_status_path"] = str(status_path)
    return payload


__all__ = [
    "bancada_key_from_serial",
    "carregar_payload_bancada",
    "carregar_status",
    "carregar_status_bancadas",
    "carregar_status_teste",
    "extract_status_payload",
    "failure_report_pointer_path",
    "limpar_relatorio_falha_automatico",
    "salvar_status",
    "status_dir",
    "test_ref",
]
