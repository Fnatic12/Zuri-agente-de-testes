import os
import signal
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLL_INTERVAL_S = 1.0
DEBOUNCE_S = 1.2
STARTUP_TIMEOUT_S = 60.0
WATCH_EXTENSIONS = {".py", ".toml", ".css"}
WATCH_DIRS = [
    PROJECT_ROOT / ".streamlit",
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "Dashboard",
    PROJECT_ROOT / "HMI",
    PROJECT_ROOT / "Run",
    PROJECT_ROOT / "Pre_process",
    PROJECT_ROOT / "Scripts",
    PROJECT_ROOT / "src",
]


@dataclass
class StreamlitApp:
    name: str
    script_path: Path
    port: int
    open_on_ready: bool = False
    process: subprocess.Popen | None = None


APPS = [
    StreamlitApp("Menu Chat", PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "streamlit" / "menu_chat.py", 8502, open_on_ready=True),
    StreamlitApp("Menu Tester", PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "streamlit" / "menu_tester.py", 8503, open_on_ready=True),
    StreamlitApp(
        "Dashboard",
        PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "streamlit" / "visualizador_execucao.py",
        8504,
    ),
    StreamlitApp(
        "Painel de Logs",
        PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "streamlit" / "painel_logs_radio.py",
        8505,
    ),
    StreamlitApp(
        "Controle de Falhas",
        PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "streamlit" / "controle_falhas.py",
        8506,
    ),
]
LOCK_PATH = PROJECT_ROOT / ".streamlit" / "dev_streamlit_watcher.lock"


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_lock() -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            stale_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            stale_pid = 0
        if _pid_is_running(stale_pid):
            return False
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            return False
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return True


def _release_lock() -> None:
    try:
        if LOCK_PATH.exists():
            current = LOCK_PATH.read_text(encoding="utf-8").strip()
            if current == str(os.getpid()):
                LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _iter_watch_files() -> list[Path]:
    files: list[Path] = []
    for root in WATCH_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in WATCH_EXTENSIONS:
                continue
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def _snapshot() -> dict[str, float]:
    state: dict[str, float] = {}
    for path in _iter_watch_files():
        try:
            state[str(path)] = path.stat().st_mtime
        except OSError:
            continue
    return state


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


def _start_app(app: StreamlitApp) -> None:
    if app.process is not None and app.process.poll() is None:
        return
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app.script_path),
        "--server.port",
        str(app.port),
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--server.runOnSave",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]
    app.process = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        env=_build_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[watcher] started {app.name} on http://localhost:{app.port}", flush=True)


def _stop_app(app: StreamlitApp) -> None:
    if app.process is None:
        return
    if app.process.poll() is None:
        try:
            app.process.terminate()
            app.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            app.process.kill()
    app.process = None


def _restart_apps(reason: str) -> None:
    print(f"[watcher] change detected: {reason}", flush=True)
    for app in APPS:
        _stop_app(app)
    time.sleep(1.0)
    for app in APPS:
        _start_app(app)


def _ensure_running() -> None:
    for app in APPS:
        if app.process is None or app.process.poll() is not None:
            _start_app(app)


def _shutdown(*_args: object) -> None:
    for app in APPS:
        _stop_app(app)
    _release_lock()
    raise SystemExit(0)


def _wait_for_port(port: int, timeout_s: float = STARTUP_TIMEOUT_S) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            import socket

            with socket.create_connection(("127.0.0.1", port), timeout=0.75):
                return True
        except OSError:
            time.sleep(0.8)
    return False


def _open_initial_urls() -> None:
    for app in APPS:
        if not app.open_on_ready:
            continue
        if _wait_for_port(app.port):
            try:
                webbrowser.open_new_tab(f"http://localhost:{app.port}")
            except Exception:
                pass


def main() -> None:
    if not _acquire_lock():
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    last_snapshot = _snapshot()
    last_restart = 0.0
    for app in APPS:
        _start_app(app)
    _open_initial_urls()

    while True:
        time.sleep(POLL_INTERVAL_S)
        _ensure_running()
        current_snapshot = _snapshot()
        if current_snapshot != last_snapshot:
            now = time.time()
            if now - last_restart >= DEBOUNCE_S:
                changed = sorted(
                    path
                    for path, mtime in current_snapshot.items()
                    if last_snapshot.get(path) != mtime
                )
                removed = sorted(path for path in last_snapshot if path not in current_snapshot)
                reason = changed[0] if changed else (removed[0] if removed else "unknown file")
                _restart_apps(str(Path(reason).relative_to(PROJECT_ROOT)) if reason != "unknown file" else reason)
                last_restart = time.time()
                current_snapshot = _snapshot()
            last_snapshot = current_snapshot


if __name__ == "__main__":
    main()
