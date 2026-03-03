import json
import os
from datetime import datetime
from typing import Dict

import cv2


def get_validation_dir(test_dir: str) -> str:
    return os.path.join(test_dir, "hmi_validation")


def save_validation_report(test_dir: str, library_index: Dict, validation_result: Dict) -> str:
    output_dir = get_validation_dir(test_dir)
    overlays_dir = os.path.join(output_dir, "overlays")
    masks_dir = os.path.join(output_dir, "diff_masks")
    heatmaps_dir = os.path.join(output_dir, "heatmaps")
    aligned_dir = os.path.join(output_dir, "aligned")
    os.makedirs(overlays_dir, exist_ok=True)
    os.makedirs(masks_dir, exist_ok=True)
    os.makedirs(heatmaps_dir, exist_ok=True)
    os.makedirs(aligned_dir, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "figma_dir": library_index.get("figma_dir"),
        "library_generated_at": library_index.get("generated_at"),
        "summary": validation_result.get("summary", {}),
        "items": [],
    }

    for item in validation_result.get("items", []):
        serializable = dict(item)
        debug_images = serializable.pop("debug_images", {}) or {}

        base_name = os.path.splitext(os.path.basename(item["screenshot_path"]))[0]
        overlay_path = None
        diff_mask_path = None
        heatmap_path = None
        aligned_path = None

        overlay = debug_images.get("overlay")
        diff_mask = debug_images.get("diff_mask")
        heatmap = debug_images.get("heatmap")
        aligned = debug_images.get("aligned")
        if overlay is not None:
            overlay_path = os.path.join(overlays_dir, f"{base_name}_overlay.png")
            cv2.imwrite(overlay_path, overlay)
        if diff_mask is not None:
            diff_mask_path = os.path.join(masks_dir, f"{base_name}_mask.png")
            cv2.imwrite(diff_mask_path, diff_mask)
        if heatmap is not None:
            heatmap_path = os.path.join(heatmaps_dir, f"{base_name}_heatmap.png")
            cv2.imwrite(heatmap_path, heatmap)
        if aligned is not None:
            aligned_path = os.path.join(aligned_dir, f"{base_name}_aligned.png")
            cv2.imwrite(aligned_path, aligned)

        serializable["artifacts"] = {
            "overlay_path": overlay_path,
            "diff_mask_path": diff_mask_path,
            "heatmap_path": heatmap_path,
            "aligned_path": aligned_path,
        }
        payload["items"].append(serializable)

    report_path = os.path.join(output_dir, "resultado_hmi.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return report_path


def load_validation_report(test_dir: str) -> Dict:
    report_path = os.path.join(get_validation_dir(test_dir), "resultado_hmi.json")
    with open(report_path, "r", encoding="utf-8") as fh:
        return json.load(fh)
