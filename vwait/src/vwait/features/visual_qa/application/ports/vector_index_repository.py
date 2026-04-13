from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import numpy as np


class VectorIndexRepository(ABC):
    """Stores and queries embedding vectors."""

    @abstractmethod
    def build(self, vectors: np.ndarray, metadata: List[Dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def save(self, index_dir: str) -> None:
        pass

    @abstractmethod
    def load(self, index_dir: str) -> None:
        pass
