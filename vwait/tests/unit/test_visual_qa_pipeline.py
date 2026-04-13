from dataclasses import dataclass
from datetime import datetime, timezone

from vwait.features.visual_qa.application.use_cases.generate_report import GenerateReport
from vwait.features.visual_qa.application.use_cases.visual_qa_pipeline import VisualQaPipeline
from vwait.features.visual_qa.domain.entities import PixelDiffResult, Report, ScreenMatch, ValidationRun
from vwait.features.visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore


@dataclass
class FakeValidator:
    def execute(self, **kwargs):
        return ValidationRun(
            run_id="",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            screenshot_path=kwargs["screenshot_path"],
            predicted_screen_type="home_screen",
            classification_threshold=float(kwargs["threshold"]),
            selected_baseline_image="/tmp/home_screen_1.png",
            matches=[
                ScreenMatch(
                    rank=1,
                    screen_type="home_screen",
                    image_path="/tmp/home_screen_1.png",
                    similarity=0.91,
                )
            ],
            pixel_result=PixelDiffResult(
                status="PASS",
                baseline_image="/tmp/home_screen_1.png",
                actual_image=kwargs["screenshot_path"],
                ssim_score=0.98,
                difference_percent=0.5,
                issues=[],
                diff_image_path=None,
                raw={"status": "PASS"},
            ),
            report_path=None,
            json_path=None,
            config_snapshot=kwargs.get("config_snapshot", {}),
            reproducibility=kwargs.get("reproducibility", {}),
        )


@dataclass
class FakeReportGenerator:
    def generate_report(self, payload):
        return Report(
            provider="fake",
            model="fake-model",
            markdown="# Fake report\n\nAll good.",
            generated_at=datetime.now(timezone.utc),
            prompt_snapshot="fake",
        )


def test_pipeline_orchestration_with_fakes(tmp_path):
    validator = FakeValidator()
    report_uc = GenerateReport(report_generator=FakeReportGenerator())
    store = LocalArtifactStore(runs_dir=str(tmp_path / "runs"))

    pipeline = VisualQaPipeline(
        validator=validator,
        report_use_case=report_uc,
        artifact_store=store,
    )

    run = pipeline.run(
        screenshot_path="/tmp/actual.png",
        index_dir="/tmp/index",
        top_k=5,
        threshold=0.4,
        config_snapshot={"test": True},
    )

    assert run.run_id
    assert run.predicted_screen_type == "home_screen"
    assert run.pixel_result is not None
    assert run.report_path is not None and run.report_path.exists()
    assert run.json_path is not None and run.json_path.exists()

    idx_rows = store.load_runs_index()
    assert len(idx_rows) == 1
    assert idx_rows[0]["predicted_screen_type"] == "home_screen"
