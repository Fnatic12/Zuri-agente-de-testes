from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vwait.features.visual_qa.domain.entities import PixelDiffResult, ScreenMatch, ValidationRun
from vwait.features.visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore


def _build_validation_run() -> ValidationRun:
    return ValidationRun(
        run_id="run-123",
        started_at=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 3, 5, 10, 1, tzinfo=timezone.utc),
        screenshot_path="/tmp/actual.png",
        predicted_screen_type="home_screen",
        classification_threshold=0.5,
        selected_baseline_image="/tmp/baseline.png",
        matches=[
            ScreenMatch(
                rank=1,
                screen_type="home_screen",
                image_path="/tmp/baseline.png",
                similarity=0.91,
            )
        ],
        pixel_result=PixelDiffResult(
            status="PASS",
            baseline_image="/tmp/baseline.png",
            actual_image="/tmp/actual.png",
            ssim_score=0.98,
            difference_percent=0.5,
            issues=[],
            diff_image_path=None,
            raw={},
        ),
        report_path=None,
        json_path=None,
        config_snapshot={"mode": "test"},
        reproducibility={"git_sha": "abc123"},
    )


def test_local_artifact_store_save_json_and_markdown_with_run_id(tmp_path: Path):
    store = LocalArtifactStore(runs_dir=str(tmp_path / "runs"))
    run = _build_validation_run()

    json_path = store.save_json("run-123", run, filename="run_result.json")
    md_path = store.save_markdown("run-123", "# Report", filename="report.md")

    assert json_path.exists()
    assert md_path.exists()
    assert json_path.parent.name == "run-123"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-123"
    assert payload["predicted_screen_type"] == "home_screen"
    assert payload["pixel_result"]["ssim_score"] == 0.98
    assert md_path.read_text(encoding="utf-8") == "# Report"


def test_local_artifact_store_append_history_and_compute_metrics(tmp_path: Path):
    store = LocalArtifactStore(runs_dir=str(tmp_path / "runs"))
    store.append_history(
        {
            "run_id": "a",
            "screen_type": "home_screen",
            "similarity": 0.9,
            "diff_percent": 1.0,
            "ssim": 0.98,
            "timestamp": "2026-03-05T10:00:00Z",
        }
    )
    store.append_history(
        {
            "run_id": "b",
            "screen_type": "home_screen",
            "similarity": 0.7,
            "diff_percent": 3.0,
            "ssim": 0.92,
            "timestamp": "2026-03-05T10:10:00Z",
        }
    )
    store.append_history(
        {
            "run_id": "c",
            "screen_type": "login_screen",
            "similarity": 0.8,
            "diff_percent": 2.0,
            "ssim": 0.95,
            "timestamp": "2026-03-05T10:20:00Z",
        }
    )

    metrics = store.compute_historical_metrics("home_screen", last_n=10)
    assert metrics["screen_type"] == "home_screen"
    assert metrics["runs_considered"] == 2
    assert metrics["average_similarity"] == 0.8
    assert metrics["average_diff_percent"] == 2.0
    assert metrics["average_ssim"] == 0.95


def test_local_artifact_store_copies_diff_images_when_present(tmp_path: Path):
    store = LocalArtifactStore(runs_dir=str(tmp_path / "runs"))
    source_diff = tmp_path / "external" / "overlay.png"
    source_diff.parent.mkdir(parents=True, exist_ok=True)
    source_diff.write_bytes(b"img")

    payload = {
        "run_id": "run-456",
        "pixel_result": {
            "diff_image_path": str(source_diff),
            "raw": {
                "artifact_paths": {
                    "overlay": str(source_diff),
                }
            },
        },
    }
    json_path = store.save_json("run-456", payload, filename="run_result.json")
    data = json.loads(json_path.read_text(encoding="utf-8"))

    copied = data.get("diff_image_artifacts") or []
    assert len(copied) >= 1
    assert any(Path(path).exists() for path in copied)
    assert (tmp_path / "runs" / "run-456" / "diff_images" / "overlay.png").exists()
