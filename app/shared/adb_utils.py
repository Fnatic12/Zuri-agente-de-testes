from __future__ import annotations

import os
import sys
import subprocess
from shutil import which

from app.shared.project_paths import project_root, root_path


def candidate_adb_paths() -> list[str]:
    candidates: list[str] = []

    env_path = os.environ.get("ADB_PATH", "").strip()
    if env_path:
        candidates.append(env_path)

    if os.name == "nt" or sys.platform.startswith("win"):
        candidates.extend(
            [
                root_path("tools", "platform-tools", "adb.exe"),
                root_path("platform-tools", "adb.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
                os.path.join(os.environ.get("USERPROFILE", ""), "platform-tools", "adb.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                root_path("tools", "platform-tools", "adb"),
                root_path("platform-tools", "adb"),
                "/usr/local/bin/adb",
                "/usr/bin/adb",
            ]
        )

    discovered = which("adb")
    if discovered:
        candidates.append(discovered)

    candidates.append("adb")

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.normpath(str(candidate)))
        if not candidate or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(candidate)
    return ordered


def resolve_adb_path() -> str:
    for candidate in candidate_adb_paths():
        if candidate == "adb":
            return candidate
        if os.path.exists(candidate):
            return candidate
    return "adb"


def adb_available() -> bool:
    adb_path = resolve_adb_path()
    if adb_path == "adb":
        return which("adb") is not None
    return os.path.exists(adb_path)


def subprocess_windowless_kwargs() -> dict:
    if os.name != "nt" and not sys.platform.startswith("win"):
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def default_platform_tools_dir() -> str:
    if os.name == "nt" or sys.platform.startswith("win"):
        return os.path.join(project_root(), "tools", "platform-tools")
    return os.path.join(project_root(), "tools", "platform-tools")
