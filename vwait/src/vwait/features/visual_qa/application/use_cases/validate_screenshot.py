from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from vwait.features.visual_qa.application.ports.artifact_store import ArtifactStore
from vwait.features.visual_qa.application.ports.report_generator import ReportGenerator
from vwait.features.visual_qa.application.ports.pixel_comparator import PixelComparator
from vwait.features.visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
from vwait.features.visual_qa.domain.entities import PixelDiffResult, Report, ScreenMatch
from vwait.features.visual_qa.domain.entities import ValidationRun
from vwait.features.visual_qa.domain.scaffold_entities import ScreenMatch as Stage1ScreenMatch


def _safe_git_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:
        return None


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _match_to_dict(match: ScreenMatch) -> Dict[str, Any]:
    return {
        "rank": match.rank,
        "screen_type": match.screen_type,
        "image_path": match.image_path,
        "similarity": float(match.similarity),
        "tags": list(match.tags),
        "metadata": dict(match.metadata),
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
        "issues": list(pixel.issues),
        "diff_image_path": pixel.diff_image_path,
        "raw": dict(pixel.raw),
    }


def _ensure_stage1_screen_match(classification: Dict[str, Any]) -> Stage1ScreenMatch:
    candidate = classification.get("screen_match")
    if isinstance(candidate, Stage1ScreenMatch):
        return candidate

    selected = classification.get("selected_baseline_image")
    selected_path = Path(selected) if selected else None
    top_k = []
    for m in classification.get("matches") or []:
        if isinstance(m, ScreenMatch):
            top_k.append(
                {
                    "rank": m.rank,
                    "screen_type": m.screen_type,
                    "image_path": m.image_path,
                    "score": float(m.similarity),
                    "tags": list(m.tags),
                }
            )
    similarity = classification.get("winning_score")
    if similarity is None and classification.get("matches"):
        first = classification["matches"][0]
        if isinstance(first, ScreenMatch):
            similarity = float(first.similarity)
    if similarity is None:
        similarity = 0.0

    return Stage1ScreenMatch(
        screen_type=str(classification.get("predicted_screen_type") or "unknown"),
        similarity_score=float(similarity),
        matched_baseline_path=selected_path,
        top_k=top_k,
    )


def _stringify_baseline_path(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    if path.drive:
        return str(path)
    return path.as_posix()


def _selected_baseline_image(classification: Dict[str, Any], stage1: Stage1ScreenMatch) -> Optional[str]:
    selected = classification.get("selected_baseline_image")
    if isinstance(selected, Path):
        return _stringify_baseline_path(selected)
    if selected:
        return str(selected)
    return _stringify_baseline_path(stage1.matched_baseline_path)


@dataclass
class ValidateScreenshot:
    classifier: ClassifyScreenshot
    pixel_comparator: PixelComparator
    report_generator: Optional[ReportGenerator] = None
    artifact_store: Optional[ArtifactStore] = None
    history_window: int = 30

    def _compute_historical_metrics(self, screen_type: str) -> Dict[str, Any]:
        if self.artifact_store is None:
            return {"count": 0}

        compute_fn = getattr(self.artifact_store, "compute_historical_metrics", None)
        if callable(compute_fn):
            try:
                return dict(compute_fn(screen_type, last_n=max(1, int(self.history_window))))
            except Exception:
                return {"count": 0}

        try:
            rows = self.artifact_store.load_runs_index()
        except Exception:
            return {"count": 0}

        filtered = [r for r in rows if r.get("predicted_screen_type") == screen_type][-max(1, int(self.history_window)) :]
        if not filtered:
            return {"count": 0}

        diffs = [float(r.get("difference_percent")) for r in filtered if r.get("difference_percent") is not None]
        ssims = [float(r.get("ssim_score")) for r in filtered if r.get("ssim_score") is not None]

        return {
            "count": len(filtered),
            "average_difference_percent": (sum(diffs) / len(diffs)) if diffs else None,
            "average_ssim_score": (sum(ssims) / len(ssims)) if ssims else None,
        }

    def _build_reproducibility(self, supplied: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
            "git_sha": _safe_git_sha(),
        }
        if supplied:
            base.update(supplied)
        return base

    def execute(
        self,
        screenshot_path: str,
        index_dir: str,
        top_k: int,
        threshold: float,
        output_dir: Optional[str] = None,
        strategy: str = "best",
        run_id: Optional[str] = None,
        config_snapshot: Optional[Dict] = None,
        reproducibility: Optional[Dict] = None,
    ) -> ValidationRun:
        started = datetime.now(timezone.utc)
        run_id_value = run_id or _new_run_id()
        config_data = dict(config_snapshot or {})
        reproducibility_data = self._build_reproducibility(reproducibility)

        cls = self.classifier.execute(
            screenshot_path=screenshot_path,
            index_dir=index_dir,
            top_k=top_k,
            threshold=threshold,
            strategy=strategy,
        )
        stage1 = _ensure_stage1_screen_match(cls)
        baseline_image = _selected_baseline_image(cls, stage1)

        pixel_result = None
        skip_reason = None
        if baseline_image is not None:
            pixel_result = self.pixel_comparator.compare(
                actual_image_path=screenshot_path,
                expected_image_path=baseline_image,
                output_dir=output_dir,
            )
        else:
            skip_reason = "Pixel comparison skipped because no baseline image was selected by classification."

        predicted_screen_type = str(stage1.screen_type or "unknown")
        historical_metrics = self._compute_historical_metrics(predicted_screen_type)

        report_path = None
        json_path = None
        finished_at = datetime.now(timezone.utc)

        report_payload = {
            "run": {
                "run_id": run_id_value,
                "started_at": started.isoformat(),
                "finished_at": finished_at.isoformat(),
                "screenshot_path": screenshot_path,
            },
            "classification": {
                "predicted_screen_type": predicted_screen_type,
                "classification_threshold": float(threshold),
                "classification_strategy": str(strategy),
                "winning_score": float(stage1.similarity_score),
                "selected_baseline_image": baseline_image,
                "matches": [_match_to_dict(m) for m in (cls.get("matches") or []) if isinstance(m, ScreenMatch)],
                "top_k": list(stage1.top_k),
            },
            "pixel_result": _pixel_to_dict(pixel_result),
            "historical": historical_metrics,
            "pixel_compare_skipped_reason": skip_reason,
            "metadata": {
                "config_snapshot": config_data,
                "reproducibility": reproducibility_data,
            },
        }

        report_obj: Optional[Report] = None
        if self.report_generator is not None:
            generated = self.report_generator.generate_report(report_payload)
            if isinstance(generated, Report):
                report_obj = generated
            else:
                report_obj = Report(
                    provider="custom",
                    model="custom",
                    markdown=str(generated),
                    generated_at=datetime.now(timezone.utc),
                    prompt_snapshot=None,
                )

        if self.artifact_store is not None:
            run_dir = self.artifact_store.create_run_dir(run_id_value)
            markdown = report_obj.markdown if report_obj is not None else "# Validation Report\n\nNo report generated."
            report_path = self.artifact_store.save_markdown(run_dir, "report.md", markdown)

            run_result_payload = {
                "run": report_payload["run"],
                "classification": report_payload["classification"],
                "pixel_result": report_payload["pixel_result"],
                "historical": historical_metrics,
                "metadata": report_payload["metadata"],
                "report": {
                    "provider": report_obj.provider if report_obj else None,
                    "model": report_obj.model if report_obj else None,
                    "generated_at": report_obj.generated_at.isoformat() if report_obj else None,
                    "report_path": str(report_path),
                },
                "pixel_compare_skipped_reason": skip_reason,
            }
            json_path = self.artifact_store.save_json(run_dir, "run_result.json", run_result_payload)

            summary_row = {
                "run_id": run_id_value,
                "timestamp": finished_at.isoformat(),
                "predicted_screen_type": predicted_screen_type,
                "selected_baseline_image": baseline_image,
                "similarity": float(stage1.similarity_score),
                "pixel_status": pixel_result.status if pixel_result else None,
                "ssim_score": pixel_result.ssim_score if pixel_result else None,
                "difference_percent": pixel_result.difference_percent if pixel_result else None,
                "result_json": str(json_path),
                "report_path": str(report_path),
            }
            self.artifact_store.append_runs_index(summary_row)

        return ValidationRun(
            run_id=run_id_value,
            started_at=started,
            finished_at=finished_at,
            screenshot_path=screenshot_path,
            predicted_screen_type=predicted_screen_type,
            classification_threshold=float(threshold),
            selected_baseline_image=baseline_image,
            matches=[m for m in (cls.get("matches") or []) if isinstance(m, ScreenMatch)],
            pixel_result=pixel_result,
            report_path=report_path,
            json_path=json_path,
            config_snapshot=config_data,
            reproducibility=reproducibility_data,
            historical_stats=historical_metrics,
        )
