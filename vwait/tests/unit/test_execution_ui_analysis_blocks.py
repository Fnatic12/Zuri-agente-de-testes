from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.ui.streamlit.analysis_blocks import (
    compare_images_cv,
    simple_similarity,
)


def test_simple_similarity_returns_one_for_identical_images():
    img = Image.fromarray(np.zeros((20, 20, 3), dtype=np.uint8))
    assert simple_similarity(img, img) == 1.0


def test_compare_images_cv_returns_expected_keys():
    img_a = np.zeros((40, 40, 3), dtype=np.uint8)
    img_b = img_a.copy()
    result = compare_images_cv(img_a, img_b)
    assert set(result.keys()) == {"diffs", "toggle_changes", "diff_mask", "overlay"}
