from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from vwait.features.visual_qa.application.ports.report_generator import ReportGenerator
from vwait.features.visual_qa.domain.entities import Report


class NullReportGenerator(ReportGenerator):
    """Offline-safe report generator without LLM calls."""

    def __init__(self, model_name: str = "null-template") -> None:
        self._model_name = model_name

    @staticmethod
    def _j(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def generate_report(self, payload: Dict[str, Any]) -> Report:
        classification = payload.get("classification") or {}
        pixel = payload.get("pixel_result") or {}
        run = payload.get("run") or {}
        historical = payload.get("historical") or {}

        markdown = "\n".join(
            [
                "# Visual QA Report",
                "",
                "## Summary",
                f"- Run ID: `{run.get('run_id', 'n/a')}`",
                f"- Screen Type: `{classification.get('predicted_screen_type', 'unknown')}`",
                f"- Baseline: `{classification.get('selected_baseline_image', 'n/a')}`",
                f"- Pixel Status: `{pixel.get('status', 'n/a')}`",
                "",
                "## Findings",
                f"- Similarity Threshold: `{classification.get('classification_threshold', 'n/a')}`",
                f"- Similarity Winning Score: `{classification.get('winning_score', 'n/a')}`",
                f"- SSIM: `{pixel.get('ssim_score', 'n/a')}`",
                f"- Diff Percent: `{pixel.get('difference_percent', 'n/a')}`",
                f"- Historical Context: `{self._j(historical)}`",
                f"- Top K Matches: `{self._j(classification.get('matches') or [])}`",
            ]
        )

        issues = pixel.get("issues") if isinstance(pixel, dict) else None
        markdown += "\n\n## Issues\n"
        markdown += f"- Items: `{self._j(issues or [])}`\n"

        risk = "low"
        diff_percent = pixel.get("difference_percent") if isinstance(pixel, dict) else None
        try:
            if diff_percent is not None and float(diff_percent) > 5.0:
                risk = "high"
            elif diff_percent is not None and float(diff_percent) > 1.0:
                risk = "medium"
        except (TypeError, ValueError):
            risk = "unknown"
        markdown += "\n## Risk\n"
        markdown += f"- Estimated Risk: `{risk}`\n"

        recommendation = (
            "Investigate UI deltas and rerun validation."
            if risk in {"medium", "high"}
            else "No blocking issues detected; keep monitoring regression history."
        )
        markdown += "\n## Recommendation\n"
        markdown += f"- {recommendation}\n"
        markdown += "- Generated offline by NullReportGenerator from structured JSON only.\n"

        return Report(
            provider="null",
            model=self._model_name,
            markdown=markdown,
            generated_at=datetime.now(timezone.utc),
            prompt_snapshot=None,
        )
