from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import cv2
import numpy as np

from .ai import embedding_to_list, extract_ocr_text, extract_semantic_embedding, get_backend_status


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


def _infer_feature_context(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    if not normalized:
        return "geral"
    head = normalized.split("/", 1)[0].strip()
    return head or "geral"


def _infer_screen_type(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    stem = os.path.splitext(os.path.basename(normalized))[0].strip().lower()
    if not stem:
        return "unknown"
    screen_type = re.sub(r"[_-]?\d+$", "", stem)
    return screen_type or "unknown"


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


def _normalize_vector(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-8:
        return arr
    return (arr / norm).astype(np.float32, copy=False)


def _local_feature_embedding(img_bgr: np.ndarray) -> List[float]:
    """Cheap offline embedding kept for stage-1 compatibility and tests."""
    resized = cv2.resize(img_bgr, (224, 224), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    hist = cv2.calcHist(
        [lab],
        [0, 1, 2],
        None,
        [6, 6, 6],
        [0, 256, 0, 256, 0, 256],
    ).astype(np.float32).flatten()
    low_res = cv2.resize(gray, (20, 12), interpolation=cv2.INTER_AREA).astype(np.float32).flatten() / 255.0
    edges = cv2.Canny(gray, 60, 180)
    edge_density = np.array([float(np.count_nonzero(edges)) / float(max(edges.size, 1))], dtype=np.float32)

    embedding = _normalize_vector(np.concatenate([hist, low_res, edge_density], axis=0))
    return embedding.astype(float).tolist()


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


def build_library_index(
    figma_dir: str,
    output_path: Optional[str] = None,
    enable_semantic: bool = False,
    enable_ocr: bool = False,
) -> Dict:
    figma_dir = _normalize_path(figma_dir)
    if not os.path.isdir(figma_dir):
        raise FileNotFoundError(f"Pasta Figma nao encontrada: {figma_dir}")

    backends = get_backend_status()
    screens = []
    for image_path in iter_image_files(figma_dir):
        img = cv2.imread(image_path)
        if img is None:
            continue

        rel_path = os.path.relpath(image_path, figma_dir)
        height, width = img.shape[:2]
        meta = _load_sidecar_meta(image_path)
        feature_context = str(meta.get("feature_context") or _infer_feature_context(rel_path))
        screen_type = str(meta.get("screen_type") or _infer_screen_type(rel_path))
        screen_id = meta.get("screen_id") or os.path.splitext(rel_path)[0].replace("\\", "/")
        semantic_embedding = embedding_to_list(extract_semantic_embedding(img)) if enable_semantic and backends.semantic_available else None
        embedding = _local_feature_embedding(img)
        ocr_text = extract_ocr_text(img) if enable_ocr and backends.ocr_available else ""
        tags = list(meta.get("tags", []))
        if feature_context and feature_context not in tags:
            tags.append(feature_context)

        screens.append(
            {
                "screen_id": screen_id,
                "name": meta.get("name") or os.path.basename(image_path),
                "path": _normalize_path(image_path),
                "relative_path": rel_path.replace("\\", "/"),
                "screen_type": screen_type,
                "width": int(width),
                "height": int(height),
                "aspect_ratio": round(width / float(max(height, 1)), 6),
                "average_hash": _average_hash(img),
                "difference_hash": _difference_hash(img),
                "color_histogram": _color_histogram(img),
                "edge_density": _edge_density(img),
                "embedding": embedding,
                "semantic_embedding": semantic_embedding,
                "ocr_text": ocr_text,
                "feature_context": feature_context,
                "ignore_regions": meta.get("ignore_regions", []),
                "critical_regions": meta.get("critical_regions", []),
                "tags": tags,
            }
        )

    index = {
        "figma_dir": figma_dir,
        "generated_at": datetime.now().isoformat(),
        "screen_count": len(screens),
        "backends": {
            "semantic_enabled": bool(enable_semantic and backends.semantic_available),
            "semantic_engine": backends.semantic_engine,
            "ocr_enabled": bool(enable_ocr and backends.ocr_available),
            "ocr_engine": backends.ocr_engine,
            "details": backends.details,
        },
        "screens": screens,
    }

    if output_path:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)

    return index


def load_library_index(index_path: str) -> Dict:
    with open(index_path, "r", encoding="utf-8") as fh:
        return json.load(fh)
