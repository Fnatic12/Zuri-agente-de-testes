from __future__ import annotations

from pathlib import Path


_FEATURE_DIR = Path(__file__).resolve().parents[1] / "src" / "vwait" / "features" / "visual_qa"
__path__ = [str(_FEATURE_DIR)]

from .config import VisualQaConfig, load_config

__all__ = ["VisualQaConfig", "load_config"]
