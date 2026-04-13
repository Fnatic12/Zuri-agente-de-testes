from __future__ import annotations

import json
import os
import re

from vwait.core.paths import (
    DATA_ROOT,
    tester_logs_root,
    tester_status_file_path,
    tester_system_collection_log_path,
    tester_system_exec_log_path,
)


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def clean_display_text(value: str) -> str:
    text = value if isinstance(value, str) else str(value)
    text = ANSI_ESCAPE_RE.sub("", text)
    for _ in range(2):
        try:
            if any(mark in text for mark in ("Ã", "Â", "â", "�")):
                text = text.encode("latin1", "ignore").decode("utf-8", "ignore")
        except Exception:
            break
    text = text.replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def execucao_log_path_por_serial(base_dir: str, serial: str) -> str:
    return str(tester_system_exec_log_path(serial))


def status_file_path(base_dir: str, categoria: str, teste: str, serial: str) -> str:
    return str(tester_status_file_path(categoria, teste, serial))


def carregar_status_execucao(base_dir: str, categoria: str, teste: str, serial: str) -> dict:
    path = status_file_path(base_dir, categoria, teste, serial)
    if not os.path.exists(path):
        legacy_path = os.path.join(base_dir, "Data", categoria, teste, f"status_{serial}.json")
        if os.path.exists(legacy_path):
            path = legacy_path
        else:
            return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    if isinstance(data, dict):
        nested = data.get(str(serial))
        if isinstance(nested, dict):
            return nested
        return data
    return {}


def resolver_teste_por_serial(base_dir: str, serial: str):
    latest = None
    latest_ts = None
    if not serial:
        return None, None
    search_root = os.path.join(base_dir, "Data") if base_dir else str(DATA_ROOT)
    for root, _dirs, files in os.walk(search_root):
        for name in files:
            if name != f"status_{serial}.json":
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            ts = data.get("atualizado_em") or data.get("inicio") or os.path.getmtime(path)
            if latest_ts is None or str(ts) > str(latest_ts):
                latest_ts = ts
                latest = data

    if not isinstance(latest, dict):
        return None, None
    teste_ref = str(latest.get("teste", "") or "").strip()
    if "/" not in teste_ref:
        return None, None
    categoria, nome_teste = teste_ref.split("/", 1)
    return categoria, nome_teste


def resolver_pasta_logs_teste(base_dir: str, categoria: str, nome_teste: str, serial: str | None = None):
    logs_root = str(tester_logs_root(categoria, nome_teste))
    status_payload = carregar_status_execucao(base_dir, categoria, nome_teste, serial) if serial else {}
    relative_capture_dir = str((status_payload or {}).get("log_capture_dir", "") or "").strip()

    if relative_capture_dir:
        capture_dir = os.path.join(logs_root, relative_capture_dir.replace("logs/", "", 1))
        if os.path.isdir(capture_dir):
            return capture_dir
        legacy_dir = os.path.join(base_dir, "Data", str(categoria or "").strip(), str(nome_teste or "").strip(), relative_capture_dir)
        if os.path.isdir(legacy_dir):
            return legacy_dir

    if not os.path.isdir(logs_root):
        legacy_logs_root = os.path.join(base_dir, "Data", str(categoria or "").strip(), str(nome_teste or "").strip(), "logs")
        if not os.path.isdir(legacy_logs_root):
            return None
        logs_root = legacy_logs_root

    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def formatar_resumo_execucao(payload: dict, fallback_returncode=None) -> str:
    status = str(payload.get("status", "")).strip().lower()
    resultado_final = str(payload.get("resultado_final", "")).strip().lower()
    log_capture_status = str(payload.get("log_capture_status", "")).strip().lower()
    log_capture_dir = str(payload.get("log_capture_dir", "") or "").strip()

    if status == "executando":
        return "Executando"
    if status == "coletando_logs":
        return "Coletando logs da peca"
    if status == "erro":
        detalhe = str(payload.get("erro_motivo", "") or "").strip()
        return f"Erro tecnico ({detalhe})" if detalhe else "Erro tecnico"
    if resultado_final == "aprovado":
        return "Finalizado aprovado"
    if resultado_final == "reprovado":
        if log_capture_status == "capturado":
            return f"Finalizado reprovado | logs capturados em {log_capture_dir}"
        if log_capture_status == "executando":
            return "Finalizado reprovado | capturando logs"
        if log_capture_status == "sem_artefatos":
            return "Finalizado reprovado | nenhum log novo encontrado"
        if log_capture_status == "sem_roteiro":
            return "Finalizado reprovado | sem roteiro de logs"
        if log_capture_status == "falha":
            return "Finalizado reprovado | falha ao capturar logs"
        return "Finalizado reprovado"
    if fallback_returncode is not None:
        return "Finalizado com sucesso" if fallback_returncode == 0 else f"Erro ({fallback_returncode})"
    return "Sem status"


def tem_execucao_unica_ativa(processos: list[dict]) -> bool:
    for item in processos:
        proc = item.get("proc")
        if proc is not None and proc.poll() is None:
            return True
    return False


__all__ = [
    "carregar_status_execucao",
    "clean_display_text",
    "execucao_log_path_por_serial",
    "formatar_resumo_execucao",
    "resolver_pasta_logs_teste",
    "resolver_teste_por_serial",
    "status_file_path",
    "tester_system_collection_log_path",
    "tem_execucao_unica_ativa",
]
