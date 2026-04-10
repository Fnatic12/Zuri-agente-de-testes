from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request


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


def url_ativa(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5):
            return True
    except Exception:
        return False


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


def streamlit_launch_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


def iniciar_app_streamlit(script_path: str, port: int, *, base_dir: str, silence_output: bool = False) -> None:
    cmd = [
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
    ]
    kwargs = {
        "cwd": base_dir,
        "env": streamlit_launch_env(),
        **subprocess_windowless_kwargs(),
    }
    if silence_output:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        return
    subprocess.Popen(cmd, **kwargs)


def garantir_app_streamlit(
    script_path: str,
    port: int,
    *,
    base_dir: str,
    silence_output: bool = False,
    timeout_s: float = 12.0,
) -> bool:
    if porta_local_ativa(port):
        return True
    iniciar_app_streamlit(script_path, port, base_dir=base_dir, silence_output=silence_output)
    return aguardar_porta_local(port, timeout_s=timeout_s)


__all__ = [
    "aguardar_porta_local",
    "garantir_app_streamlit",
    "iniciar_app_streamlit",
    "porta_local_ativa",
    "streamlit_launch_env",
    "subprocess_windowless_kwargs",
    "url_ativa",
]
