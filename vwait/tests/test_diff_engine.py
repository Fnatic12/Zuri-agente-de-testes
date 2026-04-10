import sys
from pathlib import Path

import numpy as np
import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.hmi.application import DiffConfig, compare_images


def _make_toggle(on: bool):
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)
    # track
    cv2.rectangle(img, (40, 40), (160, 70), (80, 80, 80), -1)
    # knob
    if on:
        cx = 140
        track_color = (255, 120, 0)  # orange-ish in BGR
    else:
        cx = 60
        track_color = (80, 80, 80)
    cv2.rectangle(img, (40, 40), (160, 70), track_color, -1)
    cv2.circle(img, (cx, 55), 12, (240, 240, 240), -1)
    return img


def test_toggle_color_change():
    a = _make_toggle(False)
    b = _make_toggle(True)
    cfg = DiffConfig(min_area=50, max_area=10000)
    result = compare_images(a, b, cfg)
    assert len(result['diffs']) > 0


def test_toggle_position_change():
    a = _make_toggle(False)
    b = _make_toggle(True)
    cfg = DiffConfig(min_area=50, max_area=10000)
    result = compare_images(a, b, cfg)
    assert any(d['type'] == 'toggle' for d in result['diffs'])
