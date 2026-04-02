from __future__ import annotations

import json

from Scripts.hmi_touch_monitor import (
    _touch_axis_range,
    _store_validation_result,
    is_touch_end_line,
    is_touch_start_line,
    should_stop,
)


def test_touch_start_accepts_tracking_id_without_btn_touch():
    line = "[  123.456789] /dev/input/event2: EV_ABS       ABS_MT_TRACKING_ID   0000002a"
    assert is_touch_start_line(line) is True


def test_touch_end_accepts_tracking_id_release():
    line = "[  123.556789] /dev/input/event2: EV_ABS       ABS_MT_TRACKING_ID   ffffffff"
    assert is_touch_end_line(line) is True


def test_touch_axis_range_falls_back_to_abs_xy_when_mt_range_missing():
    ranges = {
        "ABS_X": {"min": 10, "max": 1010},
        "ABS_Y": {"min": 20, "max": 620},
        "ABS_MT_POSITION_X": {"min": 0, "max": None},
        "ABS_MT_POSITION_Y": {"min": 0, "max": None},
    }

    assert _touch_axis_range(ranges, "x") == (10, 1010)
    assert _touch_axis_range(ranges, "y") == (20, 620)


def test_should_stop_accepts_flag_in_live_lookup_root(tmp_path):
    shots_dir = tmp_path / "screenshots"
    shots_dir.mkdir()
    (tmp_path / "stop.flag").write_text("stop", encoding="utf-8")

    assert should_stop(str(shots_dir)) is True


def test_store_validation_result_persists_serializable_live_history(tmp_path):
    results_path = tmp_path / "results.json"
    result = {
        "screenshot_path": str(tmp_path / "touch_01.png"),
        "screen_name": "Tela Home",
        "feature_context": "home",
        "status": "PASS",
        "scores": {"final": 0.97},
        "diff_summary": {"pixel_match_ratio": 0.992},
        "reference_path": str(tmp_path / "figma" / "home.png"),
        "debug_images": {"overlay": object(), "heatmap": object()},
        "candidate_results": [
            {
                "screen_name": "Tela Home",
                "status": "PASS",
                "debug_images": {"overlay": object()},
            }
        ],
    }

    _store_validation_result(str(results_path), "touch_01.png", result)
    _store_validation_result(str(results_path), "touch_01.png", result)

    saved = json.loads(results_path.read_text(encoding="utf-8"))

    assert saved["processed"] == ["touch_01.png"]
    assert len(saved["history"]) == 1
    assert saved["history"][0]["screen_name"] == "Tela Home"
    assert saved["full_results"][0]["debug_images"] == {}
    assert saved["full_results"][0]["candidate_results"][0]["debug_images"] == {}
