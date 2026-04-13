import os
import threading
from shutil import which


def init_colorama_safely(*, colorama_module, os_name: str) -> None:
    try:
        if os_name == "nt" and hasattr(colorama_module, "just_fix_windows_console"):
            colorama_module.just_fix_windows_console()
            return
        colorama_module.init(autoreset=True)
    except Exception:
        pass


def resolve_ollama_cli(cli_name: str) -> str:
    path = which(cli_name)
    if path:
        return path
    local_app = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "Programs", "Ollama", "ollama.exe")
    if candidate and os.path.exists(candidate):
        return candidate
    return cli_name


def warmup_ollama_once(*, session_state, warmup_key: str, warmup_fn) -> None:
    if warmup_key in session_state:
        return
    session_state[warmup_key] = True

    def _run():
        try:
            warmup_fn()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
