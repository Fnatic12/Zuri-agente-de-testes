from __future__ import annotations

from pathlib import Path

from visual_qa.infrastructure.pixel_compare.existing_pixel_adapter import ExistingPixelAdapter


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stub")


def test_existing_pixel_adapter_maps_legacy_dict_result(monkeypatch, tmp_path: Path):
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _touch(actual)
    _touch(baseline)

    calls = {"build": None, "validate": None}

    class FakeValidationConfig:
        def __init__(self, top_k: int, stage1_enabled: bool):
            self.top_k = top_k
            self.stage1_enabled = stage1_enabled

    def fake_build_library_index(reference_dir: str):
        calls["build"] = reference_dir
        return {"screens": [{"image_path": "baseline.png"}]}

    def fake_validate_execution_images(screenshot_paths, library_index, cfg):
        calls["validate"] = (screenshot_paths, library_index, cfg)
        return {
            "items": [
                {
                    "status": "PASS",
                    "scores": {"global": 0.97},
                    "diff_summary": {"diff_area_ratio": 0.0125},
                    "toggle_changes": [],
                    "critical_region_failures": [],
                    "debug_images": {"overlay": "/tmp/overlay.png"},
                }
            ]
        }

    monkeypatch.setattr(
        "visual_qa.infrastructure.pixel_compare.existing_pixel_adapter._load_legacy_pixel_api",
        lambda: (FakeValidationConfig, fake_validate_execution_images, fake_build_library_index),
    )

    adapter = ExistingPixelAdapter()
    result = adapter.compare(str(actual), str(baseline))

    assert result.status == "PASS"
    assert result.ssim_score == 0.97
    assert result.difference_percent == 1.25
    assert result.diff_image_path == "/tmp/overlay.png"
    assert result.issues == []
    assert result.raw["legacy_result"]["items"][0]["status"] == "PASS"
    assert calls["build"] is not None
    screenshot_paths, _library_index, cfg = calls["validate"]
    assert screenshot_paths == [str(actual.resolve())]
    assert cfg.top_k == 1
    assert cfg.stage1_enabled is False


def test_existing_pixel_adapter_handles_missing_fields(monkeypatch, tmp_path: Path):
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _touch(actual)
    _touch(baseline)

    class FakeValidationConfig:
        def __init__(self, top_k: int, stage1_enabled: bool):
            self.top_k = top_k
            self.stage1_enabled = stage1_enabled

    def fake_build_library_index(_reference_dir: str):
        return {}

    def fake_validate_execution_images(_screenshot_paths, _library_index, _cfg):
        return {"items": [{}]}

    monkeypatch.setattr(
        "visual_qa.infrastructure.pixel_compare.existing_pixel_adapter._load_legacy_pixel_api",
        lambda: (FakeValidationConfig, fake_validate_execution_images, fake_build_library_index),
    )

    adapter = ExistingPixelAdapter()
    result = adapter.compare(str(actual), str(baseline))

    assert result.status == "UNKNOWN"
    assert result.ssim_score is None
    assert result.difference_percent is None
    assert result.diff_image_path is None
    assert result.raw["legacy_result"]["items"] == [{}]
    assert result.raw["artifact_paths"] == {}
    assert result.issues == ["UNKNOWN"]


def test_existing_pixel_adapter_captures_saved_debug_image_paths(monkeypatch, tmp_path: Path):
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    out_dir = tmp_path / "out"
    _touch(actual)
    _touch(baseline)

    class FakeValidationConfig:
        def __init__(self, top_k: int, stage1_enabled: bool):
            self.top_k = top_k
            self.stage1_enabled = stage1_enabled

    def fake_build_library_index(_reference_dir: str):
        return {}

    def fake_validate_execution_images(_screenshot_paths, _library_index, _cfg):
        return {
            "items": [
                {
                    "status": "FAIL_SCREEN_MISMATCH",
                    "debug_images": {"overlay": object()},
                }
            ]
        }

    monkeypatch.setattr(
        "visual_qa.infrastructure.pixel_compare.existing_pixel_adapter._load_legacy_pixel_api",
        lambda: (FakeValidationConfig, fake_validate_execution_images, fake_build_library_index),
    )
    monkeypatch.setattr(
        "visual_qa.infrastructure.pixel_compare.existing_pixel_adapter._write_debug_image",
        lambda _image, path: (_touch(path), True)[1],
    )

    adapter = ExistingPixelAdapter()
    result = adapter.compare(str(actual), str(baseline), output_dir=str(out_dir))

    assert result.diff_image_path is not None
    assert result.diff_image_path.endswith("pixel_overlay.png")
    assert Path(result.diff_image_path).exists()
    assert result.raw["artifact_paths"]["overlay"].endswith("pixel_overlay.png")
