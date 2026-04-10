from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_root() -> str:
    return str(PROJECT_ROOT)


def root_path(*parts: str) -> str:
    return str(PROJECT_ROOT.joinpath(*parts))
