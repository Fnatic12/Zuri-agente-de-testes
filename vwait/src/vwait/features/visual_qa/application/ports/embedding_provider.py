from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EmbeddingProvider(ABC):
    """Converts an image path into a normalized embedding vector."""

    @abstractmethod
    def embed_image(self, image_path: str) -> np.ndarray:
        """Return a L2-normalized float32 vector with shape (D,)."""

    @property
    def name(self) -> str:
        return self.__class__.__name__
