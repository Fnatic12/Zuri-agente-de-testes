from __future__ import annotations

from pathlib import Path

from vwait.core.paths import DATA_ROOT, TESTER_RUNS_ROOT
FEATURE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FEATURE_DIR.parents[3]

__all__ = ["DATA_ROOT", "FEATURE_DIR", "PROJECT_ROOT", "TESTER_RUNS_ROOT"]
