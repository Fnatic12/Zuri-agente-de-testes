from __future__ import annotations

import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from visual_qa.application.ports.artifact_store import ArtifactStore
from visual_qa.application.use_cases.generate_report import GenerateReport
from visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
from visual_qa.domain.entities import PixelDiffResult, ScreenMatch, ValidationRun
from visual_qa.infrastructure.observability.json_logger import JsonRunLogger


def _safe_git_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True)
        return out.strip() or None
    except Exception:
        return None


def _run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _match_to_dict(match: ScreenMatch) -> Dict[str, Any]:
    return {
        "rank": match.rank,
        "screen_type": match.screen_type,
        "image_path": match.image_path,
        "similarity": round(float(match.similarity), 6),
        "tags": match.tags,
        "metadata": match.metadata,
    }


def _pixel_to_dict(pixel: Optional[PixelDiffResult]) -> Optional[Dict[str, Any]]:
    if pixel is None:
        return None
    return {
        "status": pixel.status,
        "baseline_image": pixel.baseline_image,
        "actual_image": pixel.actual_image,
        "ssim_score": pixel.ssim_score,
        "difference_percent": pixel.difference_percent,
        "issues": pixel.issues,
        "diff_image_path": pixel.diff_image_path,
        "raw": pixel.raw,
    }


class VisualQaPipeline:
    """Orchestrates Stage 1 -> Stage 2 -> Stage 3 for one screenshot."""

    def __init__(
        self,
        validator: ValidateScreenshot,
        report_use_case: GenerateReport,
        artifact_store: ArtifactStore,
    ) -> None:
        self._validator = validator
        self._report_use_case = report_use_case
        self._artifact_store = artifact_store

    def _historical_stats(self, predicted_screen_type: str) -> Dict[str, Any]:
        rows = self._artifact_store.load_runs_index()
        if not rows:
            return {"count": 0}

        filtered = [r for r in rows if r.get("predicted_screen_type") == predicted_screen_type][-30:]
        if not filtered:
            return {"count": 0}

        diffs = [float(r.get("difference_percent", 0.0)) for r in filtered if r.get("difference_percent") is not None]
        avg_diff = sum(diffs) / len(diffs) if diffs else None
        pass_count = sum(1 for r in filtered if str(r.get("pixel_status", "")).upper() == "PASS")

        return {
            "count": len(filtered),
            "average_difference_percent": avg_diff,
            "pass_rate": (pass_count / len(filtered)) if filtered else None,
        }

    def run(
        self,
        screenshot_path: str,
        index_dir: str,
        top_k: int,
        threshold: float,
        config_snapshot: Dict[str, Any],
    ) -> ValidationRun:
        run_id = _run_id()
        logger = JsonRunLogger(run_id)
        run_dir = self._artifact_store.create_run_dir(run_id)
        logger.log("run_started", screenshot_path=screenshot_path, index_dir=index_dir)

        reproducibility = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
            "git_sha": _safe_git_sha(),
        }

        pixel_artifacts_dir = str((run_dir / "pixel_artifacts").resolve())
        validation = self._validator.execute(
            screenshot_path=screenshot_path,
            index_dir=index_dir,
            top_k=top_k,
            threshold=threshold,
            output_dir=pixel_artifacts_dir,
            config_snapshot=config_snapshot,
            reproducibility=reproducibility,
        )
        validation.run_id = run_id
        validation.reproducibility = reproducibility

        historical = self._historical_stats(validation.predicted_screen_type)
        validation.historical_stats = historical

        classification_payload = {
            "predicted_screen_type": validation.predicted_screen_type,
            "classification_threshold": validation.classification_threshold,
            "selected_baseline_image": validation.selected_baseline_image,
            "matches": [_match_to_dict(m) for m in validation.matches],
        }

        run_payload = {
            "run_id": run_id,
            "started_at": validation.started_at.isoformat(),
            "screenshot_path": validation.screenshot_path,
            "reproducibility": reproducibility,
            "config_snapshot": config_snapshot,
        }

        structured_for_report = {
            "run": run_payload,
            "classification": classification_payload,
            "pixel_result": _pixel_to_dict(validation.pixel_result),
            "historical_stats": historical,
        }

        report = self._report_use_case.execute(structured_for_report)
        report_path = self._artifact_store.save_markdown(run_dir, "report.md", report.markdown)
        logger.log("report_generated", provider=report.provider, model=report.model, report_path=str(report_path))

        result_payload: Dict[str, Any] = {
            "run": run_payload,
            "classification": classification_payload,
            "pixel_result": _pixel_to_dict(validation.pixel_result),
            "historical_stats": historical,
            "report": {
                "provider": report.provider,
                "model": report.model,
                "generated_at": report.generated_at.isoformat(),
                "report_path": str(report_path),
            },
        }

        json_path = self._artifact_store.save_json(run_dir, "result.json", result_payload)
        logger.log("run_finished", result_json=str(json_path), logs=str(run_dir / "logs.jsonl"))
        logs_path = self._artifact_store.save_json_lines(run_dir, "logs.jsonl", logger.events)

        index_row = {
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "predicted_screen_type": validation.predicted_screen_type,
            "selected_baseline_image": validation.selected_baseline_image,
            "pixel_status": validation.pixel_result.status if validation.pixel_result else None,
            "difference_percent": validation.pixel_result.difference_percent if validation.pixel_result else None,
            "result_json": str(json_path),
            "report_path": str(report_path),
        }
        self._artifact_store.append_runs_index(index_row)

        validation.finished_at = datetime.now(timezone.utc)
        validation.report_path = report_path
        validation.json_path = json_path
        return validation
