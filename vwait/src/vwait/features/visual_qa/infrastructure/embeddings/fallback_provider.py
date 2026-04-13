from __future__ import annotations

import cv2
import numpy as np

from visual_qa.application.ports.embedding_provider import EmbeddingProvider


def _normalize(vec: np.ndarray) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-8:
        return arr
    return arr / norm


class LocalFeatureEmbeddingProvider(EmbeddingProvider):
    """Fully offline embedding fallback using OpenCV descriptors."""

    def embed_image(self, image_path: str) -> np.ndarray:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Cannot read image: {image_path}")

        resized = cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA)
        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        hist = cv2.calcHist([lab], [0, 1, 2], None, [6, 6, 6], [0, 256, 0, 256, 0, 256]).astype(np.float32).flatten()
        hist = hist / max(float(np.linalg.norm(hist)), 1e-8)

        low_res = cv2.resize(gray, (20, 12), interpolation=cv2.INTER_AREA).astype(np.float32).flatten() / 255.0
        edges = cv2.Canny(gray, 60, 180)
        edge_density = np.array([float(np.count_nonzero(edges)) / float(edges.size)], dtype=np.float32)

        return _normalize(np.concatenate([hist, low_res, edge_density], axis=0))
