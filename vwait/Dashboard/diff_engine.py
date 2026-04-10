import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np

BBox = Tuple[int, int, int, int]


@dataclass
class DiffConfig:
    ignore_regions: List[BBox] = field(default_factory=list)
    min_area: int = 200
    max_area: int = 200000
    diff_threshold: int = 25  # for LAB absdiff
    use_alignment: bool = False
    alignment_mode: str = "ecc"  # "ecc" | "orb"
    local_ssim_threshold: Optional[float] = None
    toggle_hsv_blue_lower: Tuple[int, int, int] = (90, 60, 60)
    toggle_hsv_blue_upper: Tuple[int, int, int] = (130, 255, 255)
    toggle_aspect_ratio_range: Tuple[float, float] = (2.0, 4.5)
    knob_detection: str = "contour"  # "contour" | "hough"
    debug_dir: Optional[str] = None

    def __post_init__(self):
        if self.ignore_regions is None:
            self.ignore_regions = []


def _apply_ignore_mask(mask: np.ndarray, ignore_regions: List[BBox]) -> np.ndarray:
    if not ignore_regions:
        return mask
    h, w = mask.shape[:2]
    for (x, y, bw, bh) in ignore_regions:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + bw)
        y2 = min(h, y + bh)
        mask[y1:y2, x1:x2] = 0
    return mask


def _align_ecc(img_a: np.ndarray, img_b: np.ndarray) -> np.ndarray:
    # ECC alignment on grayscale, returns warped B
    a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
    try:
        cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE, criteria)
        aligned = cv2.warpAffine(img_b, warp, (img_b.shape[1], img_b.shape[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
        return aligned
    except Exception:
        return img_b


def _compute_diff_mask(img_a: np.ndarray, img_b: np.ndarray, cfg: DiffConfig) -> np.ndarray:
    lab_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2LAB)
    lab_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2LAB)
    diff = cv2.absdiff(lab_a, lab_b)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    # adaptive threshold (Otsu) with lower bound
    _, otsu = cv2.threshold(diff_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cfg.diff_threshold:
        _, hard = cv2.threshold(diff_gray, cfg.diff_threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_or(otsu, hard)
    else:
        mask = otsu

    # morphology to connect small regions
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def _find_bboxes(mask: np.ndarray, cfg: DiffConfig) -> List[Tuple[BBox, float]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < cfg.min_area or area > cfg.max_area:
            continue
        score = float(area)
        bboxes.append(((x, y, w, h), score))
    return bboxes


def _toggle_state_by_color(img_roi: np.ndarray, cfg: DiffConfig) -> Tuple[str, float]:
    hsv = cv2.cvtColor(img_roi, cv2.COLOR_BGR2HSV)
    lower = np.array(cfg.toggle_hsv_blue_lower, dtype=np.uint8)
    upper = np.array(cfg.toggle_hsv_blue_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    # heur?stica simples
    if ratio >= 0.08:
        return "ON", min(1.0, ratio / 0.2)
    return "OFF", min(1.0, (0.08 - ratio) / 0.08)


def _toggle_state_by_knob(img_roi: np.ndarray) -> Tuple[Optional[str], float]:
    # detect bright/white knob via grayscale threshold
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0
    # pick largest contour
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 30:
        return None, 0.0
    (x, y, w, h) = cv2.boundingRect(c)
    cx = x + w / 2.0
    # left/right
    state = "ON" if cx > (img_roi.shape[1] / 2.0) else "OFF"
    conf = min(1.0, area / (img_roi.shape[0] * img_roi.shape[1] * 0.3))
    return state, conf


def _is_toggle_candidate(bbox: BBox, cfg: DiffConfig) -> bool:
    x, y, w, h = bbox
    if h == 0:
        return False
    ratio = w / float(h)
    return cfg.toggle_aspect_ratio_range[0] <= ratio <= cfg.toggle_aspect_ratio_range[1]


def compare_images(imgA: np.ndarray, imgB: np.ndarray, config: DiffConfig) -> Dict[str, Any]:
    if imgA is None or imgB is None:
        raise ValueError("Images cannot be None")

    if config.use_alignment:
        imgB = _align_ecc(imgA, imgB)

    mask = _compute_diff_mask(imgA, imgB, config)
    mask = _apply_ignore_mask(mask, config.ignore_regions)
    bboxes = _find_bboxes(mask, config)

    diffs = []
    toggle_changes = []

    overlay = imgA.copy()
    for (bbox, score) in bboxes:
        x, y, w, h = bbox
        roi_a = imgA[y:y+h, x:x+w]
        roi_b = imgB[y:y+h, x:x+w]
        dtype = "generic"
        if _is_toggle_candidate(bbox, config):
            state_a_c, conf_a_c = _toggle_state_by_color(roi_a, config)
            state_b_c, conf_b_c = _toggle_state_by_color(roi_b, config)
            state_a_k, conf_a_k = _toggle_state_by_knob(roi_a)
            state_b_k, conf_b_k = _toggle_state_by_knob(roi_b)

            # combine heuristics
            state_a = state_a_k or state_a_c
            state_b = state_b_k or state_b_c
            conf = (conf_a_c + conf_b_c) / 2.0
            if state_a != state_b:
                dtype = "toggle"
                toggle_changes.append({
                    "bbox": bbox,
                    "stateA": state_a,
                    "stateB": state_b,
                    "confidence": round(conf, 3),
                })

        diffs.append({
            "bbox": bbox,
            "score": float(score),
            "type": dtype,
        })

        color = (0, 255, 0) if dtype == "toggle" else (0, 200, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, dtype, (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    result = {
        "diffs": diffs,
        "toggle_changes": toggle_changes,
        "debug_images": {
            "diff_mask": mask,
            "overlay": overlay,
        },
    }

    return result
