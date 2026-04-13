from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime

from vwait.core.paths import tester_expected_dir, tester_expected_final_path


def subprocess_windowless_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def streamlit_launch_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


def porta_local_ativa(port: int, timeout_s: float = 0.35) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout_s):
            return True
    except OSError:
        return False


def aguardar_porta_local(port: int, timeout_s: float = 12.0) -> bool:
    deadline = time.time() + max(1.0, float(timeout_s))
    while time.time() < deadline:
        if porta_local_ativa(port):
            return True
        time.sleep(0.2)
    return False


def garantir_painel_streamlit(script_path: str, port: int, base_dir: str, timeout_s: float = 12.0) -> bool:
    if porta_local_ativa(port):
        return True

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            script_path,
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--server.fileWatcherType",
            "none",
            "--server.runOnSave",
            "false",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=base_dir,
        env=streamlit_launch_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **subprocess_windowless_kwargs(),
    )
    return aguardar_porta_local(port, timeout_s=timeout_s)


def parse_adb_devices(raw_lines: list[str]) -> list[str]:
    seriais: list[str] = []
    for line in raw_lines[1:]:
        line = line.strip()
        if not line:
            continue
        if line.endswith("\tdevice"):
            seriais.append(line.split("\t")[0])
    return seriais


def listar_bancadas(adb_path: str) -> list[str]:
    try:
        result = subprocess.check_output(
            [adb_path, "devices"],
            text=True,
            **subprocess_windowless_kwargs(),
        ).strip().splitlines()
        return parse_adb_devices(result)
    except Exception:
        return []


def adb_cmd(adb_path: str, serial: str | None = None) -> list[str]:
    if serial:
        return [adb_path, "-s", serial]
    return [adb_path]


def salvar_resultado_parcial(base_dir: str, adb_path: str, categoria: str, nome_teste: str, serial: str | None = None):
    esperados_dir = tester_expected_dir(categoria, nome_teste)
    esperados_dir.mkdir(parents=True, exist_ok=True)
    image_name = "final.png"
    image_path = str(tester_expected_final_path(categoria, nome_teste))

    try:
        cmd = adb_cmd(adb_path, serial) + ["exec-out", "screencap", "-p"]
        with open(image_path, "wb") as handle:
            subprocess.run(cmd, stdout=handle, stderr=subprocess.PIPE)
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            return True, image_name
        return False, "Falha ao salvar resultado esperado."
    except Exception as exc:
        return False, f"Falha ao salvar resultado esperado: {exc}"


def capturar_logs_radio(categoria: str, nome_teste: str, serial: str, motivo: str = "captura_manual_menu_tester"):
    from vwait.entrypoints.cli.run_test import capturar_logs_teste

    return capturar_logs_teste(categoria, nome_teste, serial, motivo=motivo, limpar_antes=False)


def abrir_pasta_local(path: str):
    normalized = os.path.abspath(str(path or "").strip())
    if not normalized or not os.path.exists(normalized):
        return False, "Pasta nao encontrada."
    try:
        if os.name == "nt":
            os.startfile(normalized)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", normalized])
        else:
            subprocess.Popen(["xdg-open", normalized])
        return True, normalized
    except Exception as exc:
        return False, str(exc)


__all__ = [
    "abrir_pasta_local",
    "adb_cmd",
    "aguardar_porta_local",
    "capturar_logs_radio",
    "garantir_painel_streamlit",
    "listar_bancadas",
    "parse_adb_devices",
    "porta_local_ativa",
    "salvar_resultado_parcial",
    "streamlit_launch_env",
    "subprocess_windowless_kwargs",
]
