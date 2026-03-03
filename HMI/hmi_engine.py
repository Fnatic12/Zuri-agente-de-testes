import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from Dashboard.diff_engine import DiffConfig, compare_images

try:
    from skimage.metrics import structural_similarity as ssim
except Exception:  # pragma: no cover
    ssim = None


@dataclass
class ValidationConfig:
    top_k: int = 8
    pass_threshold: float = 0.93
    warning_threshold: float = 0.82
    max_diff_area_ratio: float = 0.010
    hash_distance_limit: int = 48
    point_tolerance: float = 18.0
    exact_match_ratio: float = 0.985
    min_cell_score: float = 0.92
    grid_rows: int = 6
    grid_cols: int = 8
    allow_alignment: bool = True
    global_weight: float = 0.22
    pixel_weight: float = 0.28
    edge_weight: float = 0.18
    grid_weight: float = 0.14
    structure_weight: float = 0.10
    component_weight: float = 0.08


def _hash_distance(hash_a: str, hash_b: str) -> int:
    return sum(ch1 != ch2 for ch1, ch2 in zip(hash_a, hash_b))


def _color_score(hist_a: List[float], hist_b: List[float]) -> float:
    arr_a = np.array(hist_a, dtype=np.float32)
    arr_b = np.array(hist_b, dtype=np.float32)
    dist = cv2.compareHist(arr_a, arr_b, cv2.HISTCMP_CORREL)
    return float(max(0.0, min(1.0, (dist + 1.0) / 2.0)))


def _load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Nao foi possivel ler imagem: {path}")
    return img


def _resize_to_reference(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    if candidate.shape[:2] == reference.shape[:2]:
        return candidate
    return cv2.resize(candidate, (reference.shape[1], reference.shape[0]), interpolation=cv2.INTER_AREA)


def _global_similarity(img_a: np.ndarray, img_b: np.ndarray) -> float:
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
    if ssim is not None:
        try:
            score = ssim(gray_a, gray_b)
            return float(max(0.0, min(1.0, score)))
        except Exception:
            pass
    diff = np.abs(gray_a.astype(np.float32) - gray_b.astype(np.float32))
    score = 1.0 - (float(np.mean(diff)) / 255.0)
    return float(max(0.0, min(1.0, score)))


def _align_ecc(reference: np.ndarray, candidate: np.ndarray) -> Tuple[np.ndarray, float]:
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    cand_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
    cc, warp = cv2.findTransformECC(ref_gray, cand_gray, warp, cv2.MOTION_AFFINE, criteria)
    aligned = cv2.warpAffine(
        candidate,
        warp,
        (candidate.shape[1], candidate.shape[0]),
        flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return aligned, float(max(0.0, min(1.0, cc)))


def _align_orb(reference: np.ndarray, candidate: np.ndarray) -> Tuple[np.ndarray, float]:
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    cand_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(1000)
    kp1, des1 = orb.detectAndCompute(ref_gray, None)
    kp2, des2 = orb.detectAndCompute(cand_gray, None)
    if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
        return candidate, 0.0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(matcher.match(des1, des2), key=lambda m: m.distance)
    if len(matches) < 8:
        return candidate, 0.0
    matches = matches[:80]
    src = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC)
    if matrix is None:
        return candidate, 0.0
    aligned = cv2.warpAffine(
        candidate,
        matrix,
        (candidate.shape[1], candidate.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    inlier_ratio = float(np.count_nonzero(inliers)) / float(len(inliers)) if inliers is not None and len(inliers) else 0.0
    return aligned, float(max(0.0, min(1.0, inlier_ratio)))


def _align_image(reference: np.ndarray, candidate: np.ndarray, allow_alignment: bool) -> Tuple[np.ndarray, float]:
    candidate = _resize_to_reference(reference, candidate)
    if not allow_alignment:
        return candidate, 0.0
    try:
        return _align_ecc(reference, candidate)
    except Exception:
        try:
            return _align_orb(reference, candidate)
        except Exception:
            return candidate, 0.0


def _apply_ignore_mask(mask: np.ndarray, ignore_regions: List[List[int]]) -> np.ndarray:
    if not ignore_regions:
        return mask
    masked = mask.copy()
    height, width = masked.shape[:2]
    for region in ignore_regions:
        if len(region) != 4:
            continue
        x, y, w, h = [int(v) for v in region]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + w)
        y2 = min(height, y + h)
        masked[y1:y2, x1:x2] = 0
    return masked


def _delta_map(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    ref_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB).astype(np.float32)
    cand_lab = cv2.cvtColor(candidate, cv2.COLOR_BGR2LAB).astype(np.float32)
    return np.linalg.norm(ref_lab - cand_lab, axis=2)


def _pixel_metrics(delta_map: np.ndarray, tolerance: float) -> Dict[str, float]:
    matched = delta_map <= tolerance
    pixel_match_ratio = float(np.count_nonzero(matched)) / float(matched.size)
    p95_delta = float(np.percentile(delta_map, 95))
    mean_delta = float(np.mean(delta_map))
    return {
        "pixel_match_ratio": pixel_match_ratio,
        "mean_delta": mean_delta,
        "p95_delta": p95_delta,
    }


def _exact_diff_mask(delta_map: np.ndarray, tolerance: float, ignore_regions: List[List[int]]) -> np.ndarray:
    mask = np.where(delta_map > tolerance, 255, 0).astype(np.uint8)
    return _apply_ignore_mask(mask, ignore_regions)


def _edge_score(reference: np.ndarray, candidate: np.ndarray, ignore_regions: List[List[int]]) -> float:
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    cand_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    ref_edges = cv2.Canny(ref_gray, 80, 180)
    cand_edges = cv2.Canny(cand_gray, 80, 180)
    ref_edges = _apply_ignore_mask(ref_edges, ignore_regions)
    cand_edges = _apply_ignore_mask(cand_edges, ignore_regions)
    ref_bin = ref_edges > 0
    cand_bin = cand_edges > 0
    denom = np.count_nonzero(ref_bin) + np.count_nonzero(cand_bin)
    if denom == 0:
        return 1.0
    intersection = np.count_nonzero(ref_bin & cand_bin)
    return float((2.0 * intersection) / float(denom))


def _grid_metrics(
    delta_map: np.ndarray,
    tolerance: float,
    rows: int,
    cols: int,
    ignore_regions: List[List[int]],
) -> Dict[str, Any]:
    mask = _exact_diff_mask(delta_map, tolerance, ignore_regions)
    match_map = mask == 0
    height, width = match_map.shape
    row_edges = np.linspace(0, height, rows + 1, dtype=int)
    col_edges = np.linspace(0, width, cols + 1, dtype=int)
    scores = []
    worst = 1.0
    worst_cell = None
    for row in range(rows):
        for col in range(cols):
            y1, y2 = row_edges[row], row_edges[row + 1]
            x1, x2 = col_edges[col], col_edges[col + 1]
            cell = match_map[y1:y2, x1:x2]
            if cell.size == 0:
                continue
            score = float(np.count_nonzero(cell)) / float(cell.size)
            scores.append(score)
            if score < worst:
                worst = score
                worst_cell = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))
    avg = float(sum(scores) / max(len(scores), 1))
    return {"avg_score": avg, "min_score": worst, "worst_cell": worst_cell}


def _diff_area_ratio(diffs: List[Dict], total_area: int) -> float:
    if total_area <= 0:
        return 1.0
    area = 0
    for item in diffs:
        x, y, w, h = item["bbox"]
        area += int(w) * int(h)
    return float(area) / float(total_area)


def _component_score(toggle_changes: List[Dict], diff_area_ratio: float) -> float:
    toggle_penalty = min(1.0, len(toggle_changes) * 0.4)
    area_penalty = min(1.0, diff_area_ratio * 12.0)
    score = 1.0 - max(toggle_penalty, area_penalty)
    return float(max(0.0, min(1.0, score)))


def _structure_score(diff_area_ratio: float) -> float:
    score = 1.0 - min(1.0, diff_area_ratio * 15.0)
    return float(max(0.0, min(1.0, score)))


def _critical_region_metrics(
    delta_map: np.ndarray,
    regions: List[Dict[str, Any]],
    tolerance: float,
) -> List[Dict[str, Any]]:
    failures = []
    for region in regions or []:
        try:
            x = int(region.get("x", 0))
            y = int(region.get("y", 0))
            w = int(region.get("w", 0))
            h = int(region.get("h", 0))
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        roi = delta_map[y:y + h, x:x + w]
        if roi.size == 0:
            continue
        match_ratio = float(np.count_nonzero(roi <= tolerance)) / float(roi.size)
        min_match = float(region.get("min_match", 0.985))
        if match_ratio < min_match:
            failures.append(
                {
                    "name": region.get("name") or "critical_region",
                    "bbox": (x, y, w, h),
                    "match_ratio": round(match_ratio, 4),
                    "min_match": round(min_match, 4),
                }
            )
    return failures


def _classify_result(
    final_score: float,
    toggle_changes: List[Dict],
    diff_area_ratio: float,
    pixel_match_ratio: float,
    worst_cell_score: float,
    critical_failures: List[Dict[str, Any]],
    cfg: ValidationConfig,
) -> str:
    if toggle_changes:
        return "FAIL_COMPONENT_STATE"
    if critical_failures:
        return "FAIL_CRITICAL_REGION"
    if (
        final_score >= cfg.pass_threshold
        and diff_area_ratio <= cfg.max_diff_area_ratio
        and pixel_match_ratio >= cfg.exact_match_ratio
        and worst_cell_score >= cfg.min_cell_score
    ):
        return "PASS"
    if (
        final_score >= cfg.warning_threshold
        and pixel_match_ratio >= max(0.92, cfg.exact_match_ratio - 0.05)
        and worst_cell_score >= max(0.82, cfg.min_cell_score - 0.08)
    ):
        return "PASS_WITH_WARNINGS"
    return "FAIL_SCREEN_MISMATCH"


def _build_reason(
    status: str,
    match_name: str,
    diff_area_ratio: float,
    toggle_count: int,
    pixel_match_ratio: float,
    worst_cell_score: float,
    critical_failures: List[Dict[str, Any]],
) -> str:
    if status == "PASS":
        return (
            f"Tela validada com sucesso contra {match_name}. "
            f"Match pixel a pixel {pixel_match_ratio:.2%}, pior celula {worst_cell_score:.2%}."
        )
    if status == "PASS_WITH_WARNINGS":
        return (
            f"Melhor match encontrado em {match_name}, mas com diferencas cosmeticas "
            f"(area divergente {diff_area_ratio:.2%}, pixel match {pixel_match_ratio:.2%})."
        )
    if status == "FAIL_COMPONENT_STATE":
        return f"Divergencia critica de componente detectada ({toggle_count} toggle(s) divergente(s))."
    if status == "FAIL_CRITICAL_REGION":
        return (
            f"Regiao critica divergente em {match_name}: "
            f"{', '.join(region['name'] for region in critical_failures[:3])}."
        )
    return (
        f"Nenhuma tela do Figma atingiu confianca suficiente. "
        f"Area divergente observada: {diff_area_ratio:.2%}, "
        f"pixel match {pixel_match_ratio:.2%}, pior celula {worst_cell_score:.2%}."
    )


def _status_priority(status: str) -> int:
    order = {
        "PASS": 4,
        "PASS_WITH_WARNINGS": 3,
        "FAIL_CRITICAL_REGION": 2,
        "FAIL_COMPONENT_STATE": 1,
        "FAIL_SCREEN_MISMATCH": 0,
    }
    return order.get(status, 0)


def _compose_overlay(
    reference: np.ndarray,
    diff_result: Dict[str, Any],
    exact_mask: np.ndarray,
    worst_cell: Optional[Tuple[int, int, int, int]],
    critical_failures: List[Dict[str, Any]],
) -> np.ndarray:
    heat = cv2.applyColorMap(exact_mask, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(reference, 0.68, heat, 0.32, 0.0)
    for diff in diff_result.get("diffs", []):
        x, y, w, h = diff["bbox"]
        color = (0, 255, 0) if diff["type"] == "toggle" else (0, 200, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
    if worst_cell:
        x, y, w, h = worst_cell
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(overlay, "worst", (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    for region in critical_failures:
        x, y, w, h = region["bbox"]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(
            overlay,
            region["name"],
            (x, max(12, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return overlay


def _heatmap_from_delta(delta_map: np.ndarray) -> np.ndarray:
    normalized = cv2.normalize(delta_map, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.applyColorMap(normalized.astype(np.uint8), cv2.COLORMAP_TURBO)


def _average_hash_local(img_bgr: np.ndarray, hash_size: int = 8) -> str:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = float(resized.mean())
    bits = (resized >= avg).astype(np.uint8).flatten()
    return "".join(str(int(bit)) for bit in bits)


def _difference_hash_local(img_bgr: np.ndarray, hash_size: int = 8) -> str:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    bits = (resized[:, 1:] >= resized[:, :-1]).astype(np.uint8).flatten()
    return "".join(str(int(bit)) for bit in bits)


def _color_histogram_local(img_bgr: np.ndarray, bins: int = 8) -> List[float]:
    hist = cv2.calcHist([img_bgr], [0, 1, 2], None, [bins, bins, bins], [0, 256] * 3)
    hist = cv2.normalize(hist, hist).flatten()
    return hist.astype(float).tolist()


def _edge_density_from_image(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return float(np.count_nonzero(edges)) / float(edges.size)


def _candidate_rank(
    entry: Dict,
    screenshot_hash: str,
    screenshot_diff_hash: str,
    screenshot_hist: List[float],
    screenshot_shape,
    screenshot_edge_density: float,
) -> float:
    screen_h, screen_w = screenshot_shape[:2]
    screenshot_ratio = screen_w / float(max(screen_h, 1))
    hash_dist = _hash_distance(entry["average_hash"], screenshot_hash)
    diff_hash_dist = _hash_distance(entry.get("difference_hash", entry["average_hash"]), screenshot_diff_hash)
    aspect_penalty = abs(float(entry["aspect_ratio"]) - screenshot_ratio)
    color_score = _color_score(entry["color_histogram"], screenshot_hist)
    edge_penalty = abs(float(entry.get("edge_density", 0.0)) - screenshot_edge_density) * 35.0
    return (hash_dist * 1.2) + (diff_hash_dist * 0.9) + (aspect_penalty * 24.0) + edge_penalty - (color_score * 10.0)


def evaluate_single_screenshot(
    screenshot_path: str,
    library_index: Dict,
    cfg: Optional[ValidationConfig] = None,
) -> Dict:
    cfg = cfg or ValidationConfig()
    screenshot = _load_image(screenshot_path)
    screenshot_hash = _average_hash_local(screenshot)
    screenshot_diff_hash = _difference_hash_local(screenshot)
    screenshot_hist = _color_histogram_local(screenshot)
    screenshot_edge_density = _edge_density_from_image(screenshot)

    ranked = sorted(
        library_index.get("screens", []),
        key=lambda entry: _candidate_rank(
            entry,
            screenshot_hash,
            screenshot_diff_hash,
            screenshot_hist,
            screenshot.shape,
            screenshot_edge_density,
        ),
    )
    ranked = ranked[: max(1, cfg.top_k)]

    best_result = None
    for entry in ranked:
        hash_distance = _hash_distance(entry["average_hash"], screenshot_hash)
        if hash_distance > cfg.hash_distance_limit:
            continue

        reference = _load_image(entry["path"])
        aligned_shot, alignment_score = _align_image(reference, screenshot, cfg.allow_alignment)
        ignore_regions = entry.get("ignore_regions", [])
        diff_cfg = DiffConfig(
            ignore_regions=ignore_regions,
            min_area=40,
            max_area=300000,
            diff_threshold=max(10, int(cfg.point_tolerance)),
            use_alignment=False,
        )
        diff_result = compare_images(reference, aligned_shot, diff_cfg)
        delta_map = _delta_map(reference, aligned_shot)
        exact_mask = _exact_diff_mask(delta_map, cfg.point_tolerance, ignore_regions)
        total_area = int(reference.shape[0]) * int(reference.shape[1])
        changed_pixels = int(np.count_nonzero(exact_mask))
        diff_area_ratio = float(changed_pixels) / float(max(total_area, 1))
        pixel_metrics = _pixel_metrics(delta_map, cfg.point_tolerance)
        edge_score = _edge_score(reference, aligned_shot, ignore_regions)
        grid_metrics = _grid_metrics(delta_map, cfg.point_tolerance, cfg.grid_rows, cfg.grid_cols, ignore_regions)
        global_score = _global_similarity(reference, aligned_shot)
        structure_score = _structure_score(_diff_area_ratio(diff_result["diffs"], total_area))
        component_score = _component_score(diff_result["toggle_changes"], diff_area_ratio)
        critical_failures = _critical_region_metrics(delta_map, entry.get("critical_regions", []), cfg.point_tolerance)
        final_score = (
            global_score * cfg.global_weight
            + pixel_metrics["pixel_match_ratio"] * cfg.pixel_weight
            + edge_score * cfg.edge_weight
            + grid_metrics["avg_score"] * cfg.grid_weight
            + structure_score * cfg.structure_weight
            + component_score * cfg.component_weight
        )
        status = _classify_result(
            final_score,
            diff_result["toggle_changes"],
            diff_area_ratio,
            pixel_metrics["pixel_match_ratio"],
            grid_metrics["min_score"],
            critical_failures,
            cfg,
        )

        candidate_result = {
            "screen_id": entry["screen_id"],
            "screen_name": entry["name"],
            "reference_path": entry["path"],
            "relative_reference_path": entry["relative_path"],
            "hash_distance": hash_distance,
            "difference_hash_distance": _hash_distance(
                entry.get("difference_hash", entry["average_hash"]),
                screenshot_diff_hash,
            ),
            "scores": {
                "global": round(global_score, 4),
                "pixel": round(pixel_metrics["pixel_match_ratio"], 4),
                "edge": round(edge_score, 4),
                "grid_avg": round(grid_metrics["avg_score"], 4),
                "grid_min": round(grid_metrics["min_score"], 4),
                "structure": round(structure_score, 4),
                "component": round(component_score, 4),
                "alignment": round(alignment_score, 4),
                "final": round(final_score, 4),
            },
            "diff_summary": {
                "diff_count": len(diff_result["diffs"]),
                "toggle_count": len(diff_result["toggle_changes"]),
                "diff_area_ratio": round(diff_area_ratio, 6),
                "pixel_match_ratio": round(pixel_metrics["pixel_match_ratio"], 6),
                "changed_pixels": changed_pixels,
                "mean_delta": round(pixel_metrics["mean_delta"], 4),
                "p95_delta": round(pixel_metrics["p95_delta"], 4),
                "worst_cell_score": round(grid_metrics["min_score"], 4),
            },
            "toggle_changes": diff_result["toggle_changes"],
            "critical_region_failures": critical_failures,
            "status": status,
            "reason": _build_reason(
                status,
                entry["name"],
                diff_area_ratio,
                len(diff_result["toggle_changes"]),
                pixel_metrics["pixel_match_ratio"],
                grid_metrics["min_score"],
                critical_failures,
            ),
            "debug_images": {
                "overlay": _compose_overlay(reference, diff_result, exact_mask, grid_metrics["worst_cell"], critical_failures),
                "diff_mask": exact_mask,
                "heatmap": _heatmap_from_delta(delta_map),
                "aligned": aligned_shot,
            },
        }
        if best_result is None:
            best_result = candidate_result
            continue
        current_key = (_status_priority(candidate_result["status"]), candidate_result["scores"]["final"])
        best_key = (_status_priority(best_result["status"]), best_result["scores"]["final"])
        if current_key > best_key:
            best_result = candidate_result

    if best_result is None:
        return {
            "screenshot_path": screenshot_path,
            "status": "FAIL_SCREEN_MISMATCH",
            "reason": "Nenhuma referencia valida encontrada na biblioteca.",
            "scores": {
                "global": 0.0,
                "pixel": 0.0,
                "edge": 0.0,
                "grid_avg": 0.0,
                "grid_min": 0.0,
                "structure": 0.0,
                "component": 0.0,
                "alignment": 0.0,
                "final": 0.0,
            },
            "diff_summary": {
                "diff_count": 0,
                "toggle_count": 0,
                "diff_area_ratio": 1.0,
                "pixel_match_ratio": 0.0,
                "changed_pixels": 0,
                "mean_delta": 0.0,
                "p95_delta": 0.0,
                "worst_cell_score": 0.0,
            },
            "toggle_changes": [],
            "critical_region_failures": [],
            "reference_path": None,
            "relative_reference_path": None,
            "screen_id": None,
            "screen_name": None,
            "debug_images": {},
        }

    best_result["screenshot_path"] = screenshot_path
    return best_result


def validate_execution_images(
    screenshot_paths: List[str],
    library_index: Dict,
    cfg: Optional[ValidationConfig] = None,
) -> Dict:
    cfg = cfg or ValidationConfig()
    items = [evaluate_single_screenshot(path, library_index, cfg) for path in screenshot_paths]
    total = len(items)
    passed = sum(1 for item in items if item["status"] == "PASS")
    warnings = sum(1 for item in items if item["status"] == "PASS_WITH_WARNINGS")
    failed = total - passed - warnings
    avg_score = sum(item["scores"]["final"] for item in items) / max(total, 1)
    avg_pixel_match = sum(item["diff_summary"]["pixel_match_ratio"] for item in items) / max(total, 1)
    critical_failures = sum(len(item.get("critical_region_failures", [])) for item in items)
    component_failures = sum(1 for item in items if item["status"] == "FAIL_COMPONENT_STATE")

    return {
        "summary": {
            "total_screens": total,
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "average_score": round(avg_score, 4),
            "average_pixel_match": round(avg_pixel_match, 4),
            "critical_failures": critical_failures,
            "component_failures": component_failures,
            "result": "PASS" if failed == 0 else "FAIL",
        },
        "items": items,
    }


def collect_result_screens(test_dir: str) -> List[str]:
    results_dir = os.path.join(test_dir, "resultados")
    if not os.path.isdir(results_dir):
        return []
    files = []
    for name in sorted(os.listdir(results_dir)):
        if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            files.append(os.path.join(results_dir, name))
    return files
