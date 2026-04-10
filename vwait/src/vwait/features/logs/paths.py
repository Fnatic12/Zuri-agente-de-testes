from __future__ import annotations

from pathlib import Path


FEATURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DIR.parents[3]
DATA_ROOT = PROJECT_ROOT / "Data"


__all__ = ["DATA_ROOT", "FEATURE_DIR", "PROJECT_ROOT"]
