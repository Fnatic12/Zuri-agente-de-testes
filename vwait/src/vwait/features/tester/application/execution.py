from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

from vwait.core.paths import tester_dataset_path


def garantir_dataset_execucao(
    base_dir: str,
    scripts: dict[str, str],
    categoria_exec: str,
    nome_teste_exec: str,
    *,
    on_warning: Callable[[str], None] | None = None,
    on_success: Callable[[str], None] | None = None,
):
    dataset_path = str(tester_dataset_path(categoria_exec, nome_teste_exec))

    if os.path.exists(dataset_path):
        return True, ""

    if callable(on_warning):
        on_warning("Dataset nao encontrado. Gerando automaticamente...")

    proc_dataset = subprocess.run(
        [sys.executable, scripts["Processar Dataset"], categoria_exec, nome_teste_exec],
        cwd=base_dir,
    )

    if proc_dataset.returncode == 0:
        if callable(on_success):
            on_success("Dataset processado com sucesso.")
        return True, ""

    return False, "Falha ao processar dataset."


def iniciar_execucoes_configuradas(
    base_dir: str,
    scripts: dict[str, str],
    execucoes: list[dict],
    session_state,
    *,
    tem_execucao_unica_ativa: Callable[[], bool],
    garantir_dataset_execucao_fn: Callable[[str, str], tuple[bool, str]],
    execucao_log_path_por_serial: Callable[[str], str],
):
    if not execucoes:
        return False, "Nenhuma execucao informada.", []

    if tem_execucao_unica_ativa():
        return False, "Ja existe teste em execucao. Aguarde finalizar antes de iniciar outro.", []

    execucoes_validas = []
    seriais_usados = set()

    for idx, execucao in enumerate(execucoes, start=1):
        categoria_exec = str(execucao.get("categoria", "")).strip()
        nome_teste_exec = str(execucao.get("teste", "")).strip()
        serial = str(execucao.get("serial", "")).strip()
        label = str(execucao.get("label", f"Bancada {idx}")).strip() or f"Bancada {idx}"

        if not categoria_exec or not nome_teste_exec:
            return False, f"Informe categoria e nome do teste para {label}.", []
        if not serial:
            return False, f"Nenhum dispositivo ADB definido para {label}.", []
        if serial in seriais_usados:
            return False, "Selecione bancadas diferentes para executar em paralelo.", []

        seriais_usados.add(serial)

        ok_dataset, msg_dataset = garantir_dataset_execucao_fn(categoria_exec, nome_teste_exec)
        if not ok_dataset:
            return False, f"{label}: {msg_dataset}", []

        execucoes_validas.append(
            {
                "categoria": categoria_exec,
                "teste": nome_teste_exec,
                "serial": serial,
                "label": label,
            }
        )

    processos_iniciados = []

    try:
        for execucao in execucoes_validas:
            categoria_exec = execucao["categoria"]
            nome_teste_exec = execucao["teste"]
            serial = execucao["serial"]
            label = execucao["label"]

            log_path = execucao_log_path_por_serial(serial)
            log_file = open(log_path, "w", encoding="utf-8", errors="ignore", buffering=1)

            proc_exec = subprocess.Popen(
                [sys.executable, scripts["Executar Teste"], categoria_exec, nome_teste_exec, "--serial", serial],
                cwd=base_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

            processos_iniciados.append(
                {
                    "proc": proc_exec,
                    "serial": serial,
                    "categoria": categoria_exec,
                    "teste": nome_teste_exec,
                    "label": label,
                    "status_text": f"{label}: executando {categoria_exec}/{nome_teste_exec} na bancada {serial}...",
                    "log_path": log_path,
                    "log_file": log_file,
                    "log_closed": False,
                }
            )
    except Exception as exc:
        for item in processos_iniciados:
            try:
                if item["proc"].poll() is None:
                    item["proc"].terminate()
            except Exception:
                pass
            try:
                item["log_file"].close()
            except Exception:
                pass
        return False, f"Falha ao iniciar execucao: {exc}", []

    session_state["execucao_unica_processos"] = processos_iniciados
    session_state["proc_execucao_unica"] = processos_iniciados[0]["proc"] if len(processos_iniciados) == 1 else None
    session_state["execucao_unica_status"] = " | ".join(item["status_text"] for item in processos_iniciados)
    session_state["execucao_log_path"] = processos_iniciados[0]["log_path"]
    session_state["teste_em_execucao"] = True
    session_state["teste_pausado"] = False

    return True, "", processos_iniciados


def iniciar_execucoes_teste_unico(
    categoria_exec: str,
    nome_teste_exec: str,
    seriais: list[str],
    *,
    iniciar_execucoes_configuradas_fn: Callable[[list[dict]], tuple[bool, str, list]],
):
    seriais_validos = [str(serial).strip() for serial in seriais if str(serial).strip()]
    return iniciar_execucoes_configuradas_fn(
        [
            {
                "categoria": categoria_exec,
                "teste": nome_teste_exec,
                "serial": serial,
                "label": "Bancada selecionada" if len(seriais_validos) == 1 else f"Bancada {idx}",
            }
            for idx, serial in enumerate(seriais_validos, start=1)
        ]
    )


__all__ = [
    "garantir_dataset_execucao",
    "iniciar_execucoes_configuradas",
    "iniciar_execucoes_teste_unico",
]
