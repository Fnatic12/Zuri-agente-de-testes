from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

from HMI.hmi_engine import ValidationConfig, validate_execution_images
from HMI.hmi_indexer import build_library_index
from visual_qa.application.ports.pixel_comparator import PixelComparator
from visual_qa.domain.entities import PixelDiffResult


class ExistingPixelComparatorAdapter(PixelComparator):
    """Adapter that calls the existing pixel validator exactly as-is."""

    def compare(
        self,
        actual_image_path: str,
        expected_image_path: str,
        output_dir: Optional[str] = None,
    ) -> PixelDiffResult:
        actual = Path(actual_image_path).resolve()
        expected = Path(expected_image_path).resolve()
        if not actual.exists():
            raise FileNotFoundError(f"Actual image not found: {actual}")
        if not expected.exists():
            raise FileNotFoundError(f"Expected image not found: {expected}")

        with tempfile.TemporaryDirectory(prefix="visual_qa_pixel_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            staged_baseline = tmp_root / expected.name
            shutil.copy2(expected, staged_baseline)

            library_index = build_library_index(str(tmp_root))
            cfg = ValidationConfig(top_k=1, stage1_enabled=False)
            result = validate_execution_images([str(actual)], library_index, cfg)

            item = ((result or {}).get("items") or [{}])[0]
            status = str(item.get("status") or "FAIL_SCREEN_MISMATCH")
            scores = item.get("scores") or {}
            diff_summary = item.get("diff_summary") or {}

            issues: List[str] = []
            for toggle in item.get("toggle_changes") or []:
                issues.append(f"toggle_change:{toggle.get('stateA')}->{toggle.get('stateB')}")
            for critical in item.get("critical_region_failures") or []:
                issues.append(f"critical_region:{critical.get('name')}")
            if not issues and status != "PASS":
                issues.append(status)

            diff_image_path = None
            debug_images = item.get("debug_images") or {}
            if output_dir:
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                overlay = debug_images.get("overlay")
                if overlay is not None:
                    overlay_path = out / "pixel_overlay.png"
                    cv2.imwrite(str(overlay_path), overlay)
                    diff_image_path = str(overlay_path)
                diff_mask = debug_images.get("diff_mask")
                if diff_mask is not None:
                    cv2.imwrite(str(out / "pixel_diff_mask.png"), diff_mask)
                heatmap = debug_images.get("heatmap")
                if heatmap is not None:
                    cv2.imwrite(str(out / "pixel_heatmap.png"), heatmap)

            raw_payload: Dict[str, Any] = {
                "status": status,
                "screen_id": item.get("screen_id"),
                "screen_name": item.get("screen_name"),
                "scores": scores,
                "diff_summary": diff_summary,
                "toggle_changes": item.get("toggle_changes") or [],
                "critical_region_failures": item.get("critical_region_failures") or [],
                "reason": item.get("reason"),
            }

            return PixelDiffResult(
                status=status,
                baseline_image=str(expected),
                actual_image=str(actual),
                ssim_score=float(scores.get("global")) if scores.get("global") is not None else None,
                difference_percent=(
                    float(diff_summary.get("diff_area_ratio", 0.0)) * 100.0
                    if diff_summary.get("diff_area_ratio") is not None
                    else None
                ),
                issues=issues,
                diff_image_path=diff_image_path,
                raw=raw_payload,
            )
