from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np

from visual_qa.application.ports.embedding_provider import EmbeddingProvider

_SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _as_numpy_1d(value: Any) -> np.ndarray:
    arr: np.ndarray
    if hasattr(value, "detach") and hasattr(value, "cpu") and hasattr(value, "numpy"):
        arr = np.asarray(value.detach().cpu().numpy(), dtype=np.float32)
    else:
        arr = np.asarray(value, dtype=np.float32)
    if arr.ndim == 0:
        raise ValueError("Embedding model returned a scalar; expected a vector.")
    if arr.ndim > 1:
        arr = arr[0]
    return arr.reshape(-1).astype(np.float32, copy=False)


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("Embedding model returned a near-zero vector; cannot normalize.")
    return (vector / norm).astype(np.float32, copy=False)


def _load_rgb_image(image_path: str):
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    if path.suffix.lower() not in _SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension '{path.suffix}'. "
            f"Supported formats: {sorted(_SUPPORTED_IMAGE_EXTENSIONS)}"
        )
    try:
        pil_image_module = importlib.import_module("PIL.Image")
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency 'pillow'. Install pillow to read PNG/JPG images.") from exc
    with pil_image_module.open(path) as image:
        return image.convert("RGB")


class MobileCLIPEmbeddingProvider(EmbeddingProvider):
    """Primary lightweight embedding provider using MobileCLIP via open_clip."""

    def __init__(
        self,
        model_name: str = "MobileCLIP-S1",
        pretrained: str | None = None,
    ) -> None:
        try:
            open_clip = importlib.import_module("open_clip")
            torch = importlib.import_module("torch")
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependencies for MobileCLIPEmbeddingProvider. "
                "Install: open-clip-torch, torch, torchvision, pillow."
            ) from exc

        self._torch = torch
        self._model_name = model_name
        self._pretrained = pretrained

        init_attempts = [
            (model_name, pretrained),
            ("MobileCLIP-S1", pretrained),
            ("ViT-B-32", "laion2b_s34b_b79k"),
        ]
        last_error: Exception | None = None
        self._model = None
        self._preprocess = None

        for candidate_model, candidate_pretrained in init_attempts:
            try:
                model, _train_preprocess, val_preprocess = open_clip.create_model_and_transforms(
                    candidate_model,
                    pretrained=candidate_pretrained,
                )
                self._model = model
                self._preprocess = val_preprocess  # deterministic preprocessing
                self._model_name = candidate_model
                self._pretrained = candidate_pretrained
                break
            except Exception as exc:  # pragma: no cover
                last_error = exc

        if self._model is None or self._preprocess is None:
            raise RuntimeError(
                "Could not initialize MobileCLIP model via open_clip. "
                f"Tried: {init_attempts}. Last error: {last_error}"
            ) from last_error

        self._model.eval()

    @property
    def name(self) -> str:
        return f"MobileCLIPEmbeddingProvider[{self._model_name}:{self._pretrained}]"

    def embed_image(self, image_path: str) -> np.ndarray:
        rgb_image = _load_rgb_image(image_path)
        image_tensor = self._preprocess(rgb_image).unsqueeze(0)
        with self._torch.no_grad():
            features = self._model.encode_image(image_tensor)
        vector = _as_numpy_1d(features)
        return _l2_normalize(vector)
