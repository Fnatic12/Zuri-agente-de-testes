from __future__ import annotations

import shutil
import tempfile
import inspect
from pathlib import Path
from typing import Any, Optional

from visual_qa.application.ports.pixel_comparator import PixelComparator
from visual_qa.domain.entities import PixelDiffResult


def _load_legacy_pixel_api():
    """Load existing pixel validator API lazily to keep adapter import-safe."""
    from vwait.features.hmi.application import ValidationConfig, build_library_index, validate_execution_images

    return ValidationConfig, validate_execution_images, build_library_index


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_issues(item: dict[str, Any], status: str) -> list[str]:
    issues: list[str] = []
    for toggle in item.get("toggle_changes") or []:
        issues.append(f"toggle_change:{toggle.get('stateA')}->{toggle.get('stateB')}")
    for critical in item.get("critical_region_failures") or []:
        issues.append(f"critical_region:{critical.get('name')}")
    if not issues and status.upper() != "PASS":
        issues.append(status)
    return issues


def _write_debug_image(image: Any, output_path: Path) -> bool:
    """Best-effort writer for debug images produced by legacy validator."""
    try:
        import cv2  # type: ignore
    except Exception:
        return False

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(output_path), image))
    except Exception:
        return False


def _capture_debug_artifacts(item: dict[str, Any], output_dir: Optional[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    debug_images = item.get("debug_images") or {}
    if not isinstance(debug_images, dict):
        debug_images = {}

    # Preserve already-materialized path strings from legacy output.
    for key in ("overlay", "diff_mask", "heatmap", "aligned"):
        value = debug_images.get(key)
        if isinstance(value, (str, Path)):
            paths[key] = str(value)

    # Persist in-memory debug images when an output directory is provided.
    if output_dir:
        out = Path(output_dir).resolve()
        filename_map = {
            "overlay": "pixel_overlay.png",
            "diff_mask": "pixel_diff_mask.png",
            "heatmap": "pixel_heatmap.png",
            "aligned": "pixel_aligned.png",
        }
        for key, filename in filename_map.items():
            value = debug_images.get(key)
            if value is None or isinstance(value, (str, Path)):
                continue
            target = out / filename
            if _write_debug_image(value, target):
                paths[key] = str(target)

    return paths


def _sanitize_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is not None and dtype is not None:
        return {"type": type(value).__name__, "shape": list(shape), "dtype": str(dtype)}
    return str(value)


class ExistingPixelAdapter(PixelComparator):
    """Adapter over the current legacy pixel validator (unchanged code path)."""

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
            raise FileNotFoundError(f"Expected baseline image not found: {expected}")

        ValidationConfig, validate_execution_images, build_library_index = _load_legacy_pixel_api()

        cfg_kwargs = {"top_k": 1}
        try:
            params = inspect.signature(ValidationConfig).parameters
            if "stage1_enabled" in params:
                cfg_kwargs["stage1_enabled"] = False
        except Exception:
            fields = getattr(ValidationConfig, "__dataclass_fields__", {}) or {}
            if "stage1_enabled" in fields:
                cfg_kwargs["stage1_enabled"] = False

        with tempfile.TemporaryDirectory(prefix="visual_qa_pixel_adapter_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            staged_baseline = tmp_root / expected.name
            shutil.copy2(expected, staged_baseline)

            library_index = build_library_index(str(tmp_root))
            cfg = ValidationConfig(**cfg_kwargs)
            legacy_result = validate_execution_images([str(actual)], library_index, cfg) or {}
            if not isinstance(legacy_result, dict):
                legacy_result = {"value": legacy_result}

        item = ((legacy_result.get("items") or [{}])[0]) if isinstance(legacy_result, dict) else {}
        if not isinstance(item, dict):
            item = {}

        status = str(item.get("status") or "UNKNOWN")
        scores = item.get("scores") or {}
        if not isinstance(scores, dict):
            scores = {}
        diff_summary = item.get("diff_summary") or {}
        if not isinstance(diff_summary, dict):
            diff_summary = {}

        ssim = _to_float(scores.get("global"))
        if ssim is None:
            ssim = _to_float(scores.get("ssim"))
        if ssim is None:
            ssim = _to_float(item.get("ssim"))

        diff_percent = _to_float(item.get("difference_percent"))
        if diff_percent is None and diff_summary.get("diff_area_ratio") is not None:
            ratio = _to_float(diff_summary.get("diff_area_ratio"))
            diff_percent = None if ratio is None else ratio * 100.0

        artifact_paths = _capture_debug_artifacts(item, output_dir)
        diff_image_path = (
            artifact_paths.get("overlay")
            or artifact_paths.get("diff_mask")
            or artifact_paths.get("heatmap")
            or artifact_paths.get("aligned")
        )

        return PixelDiffResult(
            status=status,
            baseline_image=str(expected),
            actual_image=str(actual),
            ssim_score=ssim,
            difference_percent=diff_percent,
            issues=_extract_issues(item, status),
            diff_image_path=diff_image_path,
            raw={
                "legacy_result": _sanitize_for_json(legacy_result),
                "item": _sanitize_for_json(item),
                "artifact_paths": artifact_paths,
                "scores": _sanitize_for_json(scores),
                "diff_summary": _sanitize_for_json(diff_summary),
            },
        )
