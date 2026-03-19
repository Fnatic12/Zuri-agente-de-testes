from __future__ import annotations

from typing import Any, Dict, Iterable, List

import cv2
import numpy as np

from HMI.hmi_indexer import _local_feature_embedding


def _as_image(image_or_path: Any) -> np.ndarray:
    if isinstance(image_or_path, np.ndarray):
        return image_or_path
    if isinstance(image_or_path, str):
        image = cv2.imread(image_or_path)
        if image is None:
            raise ValueError(f"Nao foi possivel ler imagem: {image_or_path}")
        return image
    raise TypeError(f"image_or_path deve ser ndarray ou caminho str, recebido: {type(image_or_path)!r}")


def _embedding_from_entry(entry: Dict[str, Any]) -> np.ndarray | None:
    raw = entry.get("embedding") or entry.get("semantic_embedding")
    if raw:
        arr = np.asarray(raw, dtype=np.float32).reshape(-1)
        if arr.size > 0:
            return arr
    image_path = entry.get("path")
    if image_path:
        image = cv2.imread(str(image_path))
        if image is not None:
            return np.asarray(_local_feature_embedding(image), dtype=np.float32)
    return None


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / denom)


def build_runtime_index(
    screens: Iterable[Dict[str, Any]],
    backend: str = "local",
    use_faiss: bool = False,
) -> Dict[str, Any]:
    if str(backend or "local").strip().lower() not in {"local", "auto"}:
        raise ValueError("Somente backend local e suportado neste runtime.")

    runtime_screens: List[Dict[str, Any]] = []
    for entry in screens:
        normalized = dict(entry)
        embedding = _embedding_from_entry(normalized)
        if embedding is None:
            continue
        normalized["embedding"] = embedding.astype(float).tolist()
        normalized["screen_type"] = str(
            normalized.get("screen_type")
            or normalized.get("feature_context")
            or normalized.get("screen_id")
            or "unknown"
        )
        runtime_screens.append(normalized)

    return {
        "backend": "local",
        "use_faiss": bool(use_faiss),
        "screen_count": len(runtime_screens),
        "screens": runtime_screens,
    }


def classify_with_runtime(
    image_or_path: Any,
    runtime_index: Dict[str, Any],
    top_k: int = 5,
    backend: str = "local",
) -> Dict[str, Any]:
    if str(backend or "local").strip().lower() not in {"local", "auto"}:
        raise ValueError("Somente backend local e suportado neste runtime.")

    screenshot = _as_image(image_or_path)
    query_embedding = np.asarray(_local_feature_embedding(screenshot), dtype=np.float32)

    matches: List[Dict[str, Any]] = []
    for entry in runtime_index.get("screens", []):
        candidate_embedding = _embedding_from_entry(entry)
        if candidate_embedding is None or candidate_embedding.shape != query_embedding.shape:
            continue
        score = _cosine_similarity(query_embedding, candidate_embedding)
        matches.append(
            {
                "screen_type": str(entry.get("screen_type") or "unknown"),
                "screen_id": entry.get("screen_id"),
                "image_path": entry.get("path"),
                "relative_path": entry.get("relative_path"),
                "score": score,
            }
        )

    matches.sort(key=lambda item: (float(item["score"]), str(item["screen_type"])), reverse=True)
    matches = matches[: max(1, int(top_k))]
    best = matches[0] if matches else None

    return {
        "predicted_screen_type": str(best["screen_type"]) if best else "unknown",
        "winning_score": float(best["score"]) if best else 0.0,
        "selected_baseline_image": best.get("image_path") if best else None,
        "matches": matches,
        "backend": "local",
    }
