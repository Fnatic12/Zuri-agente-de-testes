import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLL_INTERVAL_S = 1.0
DEBOUNCE_S = 1.2
WATCH_EXTENSIONS = {".py", ".toml", ".css"}
WATCH_DIRS = [
    PROJECT_ROOT / ".streamlit",
    PROJECT_ROOT / "app",
    PROJECT_ROOT / "Dashboard",
    PROJECT_ROOT / "HMI",
    PROJECT_ROOT / "KPM",
    PROJECT_ROOT / "Run",
    PROJECT_ROOT / "Pre_process",
    PROJECT_ROOT / "Scripts",
]


@dataclass
class StreamlitApp:
    name: str
    script_path: Path
    port: int
    process: subprocess.Popen | None = None


APPS = [
    StreamlitApp("Menu Chat", PROJECT_ROOT / "app" / "streamlit" / "menu_chat.py", 8502),
    StreamlitApp("Menu Tester", PROJECT_ROOT / "app" / "streamlit" / "menu_tester.py", 8503),
]


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
    app.process = subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=_build_env())
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
    raise SystemExit(0)


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    last_snapshot = _snapshot()
    last_restart = 0.0
    for app in APPS:
        _start_app(app)

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
