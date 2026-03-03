import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import cv2
import numpy as np


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _normalize_path(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def iter_image_files(root_dir: str) -> List[str]:
    files: List[str] = []
    for current_root, _, current_files in os.walk(root_dir):
        for name in current_files:
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                files.append(os.path.join(current_root, name))
    return sorted(files)


def _average_hash(img_bgr: np.ndarray, hash_size: int = 8) -> str:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = float(resized.mean())
    bits = (resized >= avg).astype(np.uint8).flatten()
    return "".join(str(int(bit)) for bit in bits)


def _difference_hash(img_bgr: np.ndarray, hash_size: int = 8) -> str:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    bits = (resized[:, 1:] >= resized[:, :-1]).astype(np.uint8).flatten()
    return "".join(str(int(bit)) for bit in bits)


def _color_histogram(img_bgr: np.ndarray, bins: int = 8) -> List[float]:
    hist = cv2.calcHist([img_bgr], [0, 1, 2], None, [bins, bins, bins], [0, 256] * 3)
    hist = cv2.normalize(hist, hist).flatten()
    return hist.astype(float).tolist()


def _edge_density(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return round(float(np.count_nonzero(edges)) / float(edges.size), 6)


def _load_sidecar_meta(image_path: str) -> Dict:
    meta_path = os.path.splitext(image_path)[0] + ".meta.json"
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_library_index(figma_dir: str, output_path: Optional[str] = None) -> Dict:
    figma_dir = _normalize_path(figma_dir)
    if not os.path.isdir(figma_dir):
        raise FileNotFoundError(f"Pasta Figma nao encontrada: {figma_dir}")

    screens = []
    for image_path in iter_image_files(figma_dir):
        img = cv2.imread(image_path)
        if img is None:
            continue

        rel_path = os.path.relpath(image_path, figma_dir)
        height, width = img.shape[:2]
        meta = _load_sidecar_meta(image_path)
        screen_id = meta.get("screen_id") or os.path.splitext(rel_path)[0].replace("\\", "/")

        screens.append(
            {
                "screen_id": screen_id,
                "name": meta.get("name") or os.path.basename(image_path),
                "path": _normalize_path(image_path),
                "relative_path": rel_path.replace("\\", "/"),
                "width": int(width),
                "height": int(height),
                "aspect_ratio": round(width / float(max(height, 1)), 6),
                "average_hash": _average_hash(img),
                "difference_hash": _difference_hash(img),
                "color_histogram": _color_histogram(img),
                "edge_density": _edge_density(img),
                "ignore_regions": meta.get("ignore_regions", []),
                "critical_regions": meta.get("critical_regions", []),
                "tags": meta.get("tags", []),
            }
        )

    index = {
        "figma_dir": figma_dir,
        "generated_at": datetime.now().isoformat(),
        "screen_count": len(screens),
        "screens": screens,
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)

    return index


def load_library_index(index_path: str) -> Dict:
    with open(index_path, "r", encoding="utf-8") as fh:
        return json.load(fh)
