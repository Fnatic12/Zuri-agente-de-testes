import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PORTS = (8502, 8503)
APPS = (
    PROJECT_ROOT / "app" / "streamlit" / "menu_chat.py",
    PROJECT_ROOT / "app" / "streamlit" / "menu_tester.py",
)


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


def _listening_pids(port: int) -> list[str]:
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    pids: list[str] = []
    needle = f":{port}"
    for raw_line in result.stdout.splitlines():
        line = " ".join(raw_line.split())
        if needle not in line or "LISTENING" not in line:
            continue
        parts = line.split(" ")
        if parts:
            pid = parts[-1].strip()
            if pid.isdigit():
                pids.append(pid)
    return sorted(set(pids))


def _kill_existing_ports() -> None:
    for port in PORTS:
        for pid in _listening_pids(port):
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def _start_streamlit(script_path: Path, port: int) -> None:
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script_path),
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
    subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        env=_build_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )


def _wait_for_port(port: int, timeout_s: float = 45.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.8):
                return True
        except OSError:
            time.sleep(0.75)
    return False


def main() -> None:
    _kill_existing_ports()
    for script_path, port in zip(APPS, PORTS, strict=True):
        _start_streamlit(script_path, port)

    for port in PORTS:
        if _wait_for_port(port):
            try:
                webbrowser.open_new_tab(f"http://localhost:{port}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
