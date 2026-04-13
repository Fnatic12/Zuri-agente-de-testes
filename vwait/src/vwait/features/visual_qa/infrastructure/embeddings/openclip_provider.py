from __future__ import annotations

import importlib

import numpy as np

from visual_qa.application.ports.embedding_provider import EmbeddingProvider
from visual_qa.infrastructure.embeddings.mobileclip_provider import _as_numpy_1d, _l2_normalize, _load_rgb_image


class OpenCLIPEmbeddingProvider(EmbeddingProvider):
    """Fallback embedding provider using OpenCLIP ViT-B-32."""

    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
    ) -> None:
        try:
            open_clip = importlib.import_module("open_clip")
            torch = importlib.import_module("torch")
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependencies for OpenCLIPEmbeddingProvider. "
                "Install: open-clip-torch, torch, torchvision, pillow."
            ) from exc

        self._torch = torch
        self._model_name = model_name
        self._pretrained = pretrained

        try:
            model, _train_preprocess, val_preprocess = open_clip.create_model_and_transforms(
                model_name,
                pretrained=pretrained,
            )
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Could not initialize OpenCLIP model '{model_name}' with pretrained '{pretrained}'."
            ) from exc

        self._model = model
        self._preprocess = val_preprocess  # deterministic preprocessing
        self._model.eval()

    @property
    def name(self) -> str:
        return f"OpenCLIPEmbeddingProvider[{self._model_name}:{self._pretrained}]"

    def embed_image(self, image_path: str) -> np.ndarray:
        rgb_image = _load_rgb_image(image_path)
        image_tensor = self._preprocess(rgb_image).unsqueeze(0)
        with self._torch.no_grad():
            features = self._model.encode_image(image_tensor)
        vector = _as_numpy_1d(features)
        return _l2_normalize(vector)
