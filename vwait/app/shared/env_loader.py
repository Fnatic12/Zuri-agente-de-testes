from __future__ import annotations

import os
from pathlib import Path

from app.shared.project_paths import PROJECT_ROOT


DEFAULT_ENV_FILES = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".env.local",
    PROJECT_ROOT / ".env.jira",
    PROJECT_ROOT / ".env.tester",
)


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_file(path: str | Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return env_vars

    for raw_line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_matching_quotes(value.strip())
        if key:
            env_vars[key] = value
    return env_vars


def load_project_env(files: tuple[str | Path, ...] = (), override: bool = False) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for path in (*DEFAULT_ENV_FILES, *files):
        for key, value in read_env_file(path).items():
            loaded[key] = value
            if override or key not in os.environ:
                os.environ[key] = value
    return loaded
