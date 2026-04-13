from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vwait.features.visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
from vwait.features.visual_qa.domain.entities import PixelDiffResult, Report, ScreenMatch
from vwait.features.visual_qa.domain.scaffold_entities import ScreenMatch as Stage1ScreenMatch


@dataclass
class FakeClassifier:
    result: dict
    calls: list

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


@dataclass
class FakePixelComparator:
    response: PixelDiffResult
    calls: list

    def compare(self, actual_image_path: str, expected_image_path: str, output_dir: str | None = None):
        self.calls.append(
            {
                "actual_image_path": actual_image_path,
                "expected_image_path": expected_image_path,
                "output_dir": output_dir,
            }
        )
        return self.response


@dataclass
class FakeReportGenerator:
    calls: list

    def generate_report(self, payload):
        self.calls.append(payload)
        return Report(
            provider="fake",
            model="fake-model",
            markdown="# Summary\n\nok",
            generated_at=datetime.now(timezone.utc),
            prompt_snapshot=None,
        )


class FakeArtifactStore:
    def __init__(self, root: Path, historical: dict | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.created_dirs: list[Path] = []
        self.saved_json: list[tuple[Path, str, dict]] = []
        self.saved_md: list[tuple[Path, str, str]] = []
        self.index_rows: list[dict] = []
        self.historical = historical or {"count": 0}

    def create_run_dir(self, run_id: str) -> Path:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.created_dirs.append(run_dir)
        return run_dir

    def save_json(self, run_dir: Path, filename: str, payload: dict):
        out = run_dir / filename
        out.write_text(json.dumps(payload), encoding="utf-8")
        self.saved_json.append((run_dir, filename, payload))
        return out

    def save_markdown(self, run_dir: Path, filename: str, markdown: str):
        out = run_dir / filename
        out.write_text(markdown, encoding="utf-8")
        self.saved_md.append((run_dir, filename, markdown))
        return out

    def save_json_lines(self, run_dir: Path, filename: str, rows):
        out = run_dir / filename
        with out.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        return out

    def append_runs_index(self, row: dict):
        self.index_rows.append(row)
        return self.root / "index.jsonl"

    def load_runs_index(self):
        return []

    def compute_historical_metrics(self, screen_type: str, last_n: int = 30):
        row = dict(self.historical)
        row["screen_type"] = screen_type
        row["window"] = last_n
        return row


def _base_match() -> ScreenMatch:
    return ScreenMatch(
        rank=1,
        screen_type="home_screen",
        image_path="/tmp/home_screen_1.png",
        similarity=0.93,
    )


def test_validate_screenshot_orchestrates_all_stages_with_injected_ports(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "vwait.features.visual_qa.application.use_cases.validate_screenshot._safe_git_sha",
        lambda: "abc123",
    )

    classifier = FakeClassifier(
        result={
            "predicted_screen_type": "home_screen",
            "selected_baseline_image": "/tmp/home_screen_1.png",
            "winning_score": 0.93,
            "matches": [_base_match()],
            "screen_match": Stage1ScreenMatch(
                screen_type="home_screen",
                similarity_score=0.93,
                matched_baseline_path=Path("/tmp/home_screen_1.png"),
                top_k=[{"rank": 1, "screen_type": "home_screen", "score": 0.93}],
            ),
        },
        calls=[],
    )
    pixel = FakePixelComparator(
        response=PixelDiffResult(
            status="PASS",
            baseline_image="/tmp/home_screen_1.png",
            actual_image="/tmp/actual.png",
            ssim_score=0.99,
            difference_percent=0.4,
            issues=[],
            diff_image_path=None,
            raw={},
        ),
        calls=[],
    )
    report = FakeReportGenerator(calls=[])
    store = FakeArtifactStore(tmp_path / "runs", historical={"count": 7, "average_difference_percent": 0.8})

    use_case = ValidateScreenshot(
        classifier=classifier,
        pixel_comparator=pixel,
        report_generator=report,
        artifact_store=store,
    )
    run = use_case.execute(
        screenshot_path="/tmp/actual.png",
        index_dir="/tmp/index",
        top_k=3,
        threshold=0.5,
        strategy="vote",
        run_id="run-fixed",
        config_snapshot={"env": "test"},
        reproducibility={"session": "xyz"},
    )

    assert classifier.calls[0]["strategy"] == "vote"
    assert pixel.calls and pixel.calls[0]["expected_image_path"] == "/tmp/home_screen_1.png"
    assert report.calls and report.calls[0]["classification"]["predicted_screen_type"] == "home_screen"
    assert run.run_id == "run-fixed"
    assert run.predicted_screen_type == "home_screen"
    assert run.pixel_result is not None
    assert run.report_path is not None and run.report_path.exists()
    assert run.json_path is not None and run.json_path.exists()
    assert run.config_snapshot["env"] == "test"
    assert run.reproducibility["git_sha"] == "abc123"
    assert run.reproducibility["session"] == "xyz"
    assert run.historical_stats["count"] == 7
    assert store.index_rows and store.index_rows[0]["run_id"] == "run-fixed"


def test_validate_screenshot_handles_unknown_without_baseline(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "vwait.features.visual_qa.application.use_cases.validate_screenshot._safe_git_sha",
        lambda: None,
    )

    classifier = FakeClassifier(
        result={
            "predicted_screen_type": "unknown",
            "selected_baseline_image": None,
            "winning_score": 0.12,
            "matches": [],
            "screen_match": Stage1ScreenMatch(
                screen_type="unknown",
                similarity_score=0.12,
                matched_baseline_path=None,
                top_k=[],
            ),
        },
        calls=[],
    )
    pixel = FakePixelComparator(
        response=PixelDiffResult(
            status="PASS",
            baseline_image="",
            actual_image="",
            ssim_score=None,
            difference_percent=None,
            issues=[],
            diff_image_path=None,
            raw={},
        ),
        calls=[],
    )
    report = FakeReportGenerator(calls=[])
    store = FakeArtifactStore(tmp_path / "runs")

    use_case = ValidateScreenshot(
        classifier=classifier,
        pixel_comparator=pixel,
        report_generator=report,
        artifact_store=store,
    )
    run = use_case.execute(
        screenshot_path="/tmp/actual.png",
        index_dir="/tmp/index",
        top_k=5,
        threshold=0.9,
        run_id="run-unknown",
    )

    assert run.predicted_screen_type == "unknown"
    assert run.selected_baseline_image is None
    assert run.pixel_result is None
    assert pixel.calls == []
    payload = report.calls[0]
    assert payload["pixel_compare_skipped_reason"] is not None
    assert "no baseline image" in payload["pixel_compare_skipped_reason"].lower()
    assert run.report_path is not None and run.report_path.exists()
    assert run.json_path is not None and run.json_path.exists()
