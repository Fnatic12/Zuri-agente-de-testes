import json
import os

import cv2
import numpy as np

from HMI.hmi_engine import ValidationConfig, collect_result_screens, validate_execution_images
from HMI.hmi_indexer import build_library_index


def _make_screen(color, toggle_on=False):
    img = np.zeros((120, 220, 3), dtype=np.uint8)
    img[:] = color
    cv2.rectangle(img, (20, 20), (200, 45), (255, 255, 255), -1)
    cv2.rectangle(img, (20, 70), (110, 98), (60, 60, 60), -1)
    if toggle_on:
        cv2.rectangle(img, (20, 70), (110, 98), (255, 120, 0), -1)
        knob_x = 92
    else:
        knob_x = 38
    cv2.circle(img, (knob_x, 84), 11, (245, 245, 245), -1)
    return img


def test_hmi_validation_matches_best_reference(tmp_path):
    figma_dir = tmp_path / "figma"
    results_dir = tmp_path / "exec" / "resultados"
    figma_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True)

    ref_home = _make_screen((20, 80, 140), toggle_on=False)
    ref_audio = _make_screen((110, 30, 30), toggle_on=True)
    shot = _make_screen((110, 30, 30), toggle_on=True)

    cv2.imwrite(str(figma_dir / "home.png"), ref_home)
    cv2.imwrite(str(figma_dir / "audio.png"), ref_audio)
    cv2.imwrite(str(results_dir / "resultado_01.png"), shot)

    with open(figma_dir / "audio.meta.json", "w", encoding="utf-8") as fh:
        json.dump({"screen_id": "audio_screen", "name": "Audio"}, fh)

    index = build_library_index(str(figma_dir))
    result = validate_execution_images(
        [str(results_dir / "resultado_01.png")],
        index,
        ValidationConfig(top_k=2, pass_threshold=0.70, warning_threshold=0.60),
    )

    assert result["summary"]["total_screens"] == 1
    assert result["items"][0]["screen_id"] == "audio_screen"
    assert result["items"][0]["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert result["items"][0]["stage1"]["predicted_screen_type"] is not None
    assert len(result["items"][0]["stage1"]["top_matches"]) >= 1


def test_hmi_validation_handles_small_shift_with_alignment(tmp_path):
    figma_dir = tmp_path / "figma"
    results_dir = tmp_path / "exec" / "resultados"
    figma_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True)

    ref = _make_screen((30, 70, 150), toggle_on=False)
    shifted = np.roll(ref, 2, axis=1)
    shifted[:, :2] = shifted[:, 2:3]

    cv2.imwrite(str(figma_dir / "home.png"), ref)
    cv2.imwrite(str(results_dir / "resultado_01.png"), shifted)

    index = build_library_index(str(figma_dir))
    result = validate_execution_images(
        [str(results_dir / "resultado_01.png")],
        index,
        ValidationConfig(top_k=1, pass_threshold=0.80, warning_threshold=0.70),
    )

    assert result["items"][0]["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert result["items"][0]["scores"]["alignment"] >= 0.0


def test_hmi_validation_fails_toggle_component_change(tmp_path):
    figma_dir = tmp_path / "figma"
    results_dir = tmp_path / "exec" / "resultados"
    figma_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True)

    ref = _make_screen((50, 50, 120), toggle_on=False)
    changed = _make_screen((50, 50, 120), toggle_on=True)

    cv2.imwrite(str(figma_dir / "home.png"), ref)
    cv2.imwrite(str(results_dir / "resultado_01.png"), changed)

    index = build_library_index(str(figma_dir))
    result = validate_execution_images(
        [str(results_dir / "resultado_01.png")],
        index,
        ValidationConfig(top_k=1, pass_threshold=0.80, warning_threshold=0.70),
    )

    assert result["items"][0]["status"] == "FAIL_COMPONENT_STATE"


def test_hmi_context_stage_routes_by_feature_folder(tmp_path):
    figma_dir = tmp_path / "figma"
    results_dir = tmp_path / "exec" / "resultados"
    (figma_dir / "BT").mkdir(parents=True)
    (figma_dir / "Carplay").mkdir(parents=True)
    results_dir.mkdir(parents=True)

    bt_ref = _make_screen((25, 120, 35), toggle_on=True)
    cp_ref = _make_screen((130, 40, 140), toggle_on=False)
    shot = _make_screen((25, 120, 35), toggle_on=True)

    cv2.imwrite(str(figma_dir / "BT" / "bt_menu.png"), bt_ref)
    cv2.imwrite(str(figma_dir / "Carplay" / "cp_menu.png"), cp_ref)
    cv2.imwrite(str(results_dir / "resultado_01.png"), shot)

    index = build_library_index(str(figma_dir))
    result = validate_execution_images(
        [str(results_dir / "resultado_01.png")],
        index,
        ValidationConfig(top_k=1, context_top_k=4, enable_context_routing=True, pass_threshold=0.70, warning_threshold=0.60),
    )

    item = result["items"][0]
    assert item["stage1"]["predicted_screen_type"] == "BT"
    assert item["feature_context"] == "BT"
    assert "BT" in item["reference_path"]


def test_collect_result_screens_auto_falls_back_to_frames(tmp_path):
    test_dir = tmp_path / "exec"
    frames_dir = test_dir / "frames"
    frames_dir.mkdir(parents=True)
    frame = _make_screen((90, 30, 20), toggle_on=False)
    cv2.imwrite(str(frames_dir / "frame_01.png"), frame)

    auto_files = collect_result_screens(str(test_dir), source="auto")
    frame_files = collect_result_screens(str(test_dir), source="frames")

    assert len(auto_files) == 1
    assert auto_files == frame_files
