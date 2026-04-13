from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np

from vwait.features.visual_qa.application.ports.vector_index_repository import VectorIndexRepository
from vwait.features.visual_qa.infrastructure.vector_index.dtos import ScreenMatchCandidate

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _l2_normalize_vector(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize near-zero vector.")
    return (arr / norm).astype(np.float32, copy=False)


def _l2_normalize_rows(matrix: np.ndarray) -> np.ndarray:
    arr = np.asarray(matrix, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D matrix, got shape {arr.shape}.")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms <= 1e-12, 1.0, norms).astype(np.float32)
    return (arr / norms).astype(np.float32, copy=False)


def _infer_screen_type(image_path: Path) -> str:
    stem = image_path.stem.strip().lower()
    if not stem:
        return "unknown"
    normalized = re.sub(r"[_-]?\d+$", "", stem)
    return normalized or "unknown"


class FaissVectorIndexRepository(VectorIndexRepository):
    """FAISS IndexFlatIP repository with persisted metadata mapping."""

    def __init__(
        self,
        index_dir: str | Path | None = None,
        embedding_provider: Any | None = None,
        use_faiss: bool = True,
    ) -> None:
        if not use_faiss:
            raise ValueError("FaissVectorIndexRepository requires use_faiss=True.")
        try:
            import faiss  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("faiss is required. Install dependency: faiss-cpu.") from exc

        self._faiss = faiss
        self._index_dir = Path(index_dir).resolve() if index_dir else None
        self._embedding_provider = embedding_provider
        self._index = None
        self._dimension: int | None = None
        self._metadata_by_id: dict[str, dict[str, Any]] = {}

    @property
    def backend(self) -> str:
        return "faiss"

    def build(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        if len(metadata) != int(vectors.shape[0]):
            raise ValueError("metadata length must match vectors rows.")
        normalized = _l2_normalize_rows(vectors)
        self._reset_index(normalized.shape[1])
        self._index.add(normalized)
        self._metadata_by_id = {}
        for idx, item in enumerate(metadata):
            self._metadata_by_id[str(idx)] = {
                "image_path": str(item.get("image_path", "")),
                "screen_type": str(item.get("screen_type", "unknown")),
                "tags": list(item.get("tags", [])) if item.get("tags") else [],
            }

    def build_from_folder(
        self,
        reference_dir: str,
        label_map: dict[str, str] | None = None,
        recursive: bool = False,
    ) -> None:
        if self._embedding_provider is None:
            raise ValueError("embedding_provider is required for build_from_folder.")

        root = Path(reference_dir).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Reference directory not found: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Reference path is not a directory: {root}")

        self._index = None
        self._dimension = None
        self._metadata_by_id = {}

        label_map = label_map or {}
        pattern = "**/*" if recursive else "*"
        files = sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS)

        for image_path in files:
            screen_type = (
                label_map.get(str(image_path))
                or label_map.get(image_path.name)
                or label_map.get(image_path.stem)
                or _infer_screen_type(image_path)
            )
            self.add_item(image_path=str(image_path), screen_type=screen_type, tags=None)

    def add_item(
        self,
        image_path: str,
        screen_type: str,
        tags: list[str] | None = None,
    ) -> None:
        if self._embedding_provider is None:
            raise ValueError("embedding_provider is required for add_item.")
        embed_fn: Callable[[str], np.ndarray] | None = getattr(self._embedding_provider, "embed_image", None)
        if embed_fn is None:
            raise TypeError("embedding_provider must expose embed_image(path: str) -> np.ndarray.")

        vector = _l2_normalize_vector(embed_fn(str(image_path)))
        if self._index is None:
            self._reset_index(vector.shape[0])
        if vector.shape[0] != int(self._dimension):
            raise ValueError(
                f"Vector dimension mismatch: expected {self._dimension}, got {vector.shape[0]} for '{image_path}'."
            )
        self._index.add(vector.reshape(1, -1))
        vector_id = int(self._index.ntotal) - 1
        self._metadata_by_id[str(vector_id)] = {
            "image_path": str(image_path),
            "screen_type": str(screen_type or "unknown"),
            "tags": list(tags or []),
        }

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> list[ScreenMatchCandidate]:
        if self._index is None or self._index.ntotal == 0:
            raise RuntimeError("Index is empty. Build or load an index before searching.")
        query = _l2_normalize_vector(query_vec).reshape(1, -1)
        if query.shape[1] != int(self._dimension):
            raise ValueError(f"Query vector dimension mismatch: expected {self._dimension}, got {query.shape[1]}.")

        k = max(1, min(int(top_k), int(self._index.ntotal)))
        scores, indices = self._index.search(query.astype(np.float32), k)

        results: list[ScreenMatchCandidate] = []
        for score, idx in zip(scores[0], indices[0]):
            if int(idx) < 0:
                continue
            meta = self._metadata_by_id.get(str(int(idx)), {})
            results.append(
                ScreenMatchCandidate(
                    image_path=str(meta.get("image_path", "")),
                    screen_type=str(meta.get("screen_type", "unknown")),
                    score=float(score),
                    vector_id=int(idx),
                    tags=list(meta.get("tags", [])),
                )
            )
        return results

    def save(self, index_dir: str | Path | None = None) -> None:
        if self._index is None or self._index.ntotal == 0:
            raise RuntimeError("Nothing to save: index is empty.")
        target_dir = self._resolve_index_dir(index_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        self._faiss.write_index(self._index, str(target_dir / "index.faiss"))
        with (target_dir / "metadata.json").open("w", encoding="utf-8") as fh:
            json.dump(self._metadata_by_id, fh, ensure_ascii=False, indent=2)

    def load(self, index_dir: str | Path | None = None) -> None:
        source_dir = self._resolve_index_dir(index_dir)
        index_path = source_dir / "index.faiss"
        metadata_path = source_dir / "metadata.json"
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        self._index = self._faiss.read_index(str(index_path))
        self._dimension = int(self._index.d)

        with metadata_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, list):
            self._metadata_by_id = {
                str(i): {
                    "image_path": str(item.get("image_path", "")),
                    "screen_type": str(item.get("screen_type", "unknown")),
                    "tags": list(item.get("tags", [])) if item.get("tags") else [],
                }
                for i, item in enumerate(loaded)
            }
        elif isinstance(loaded, dict):
            self._metadata_by_id = {
                str(key): {
                    "image_path": str((value or {}).get("image_path", "")),
                    "screen_type": str((value or {}).get("screen_type", "unknown")),
                    "tags": list((value or {}).get("tags", [])) if (value or {}).get("tags") else [],
                }
                for key, value in loaded.items()
            }
        else:
            raise ValueError("metadata.json must be a dict mapping vector_id -> metadata.")

    def _resolve_index_dir(self, index_dir: str | Path | None) -> Path:
        if index_dir is not None:
            self._index_dir = Path(index_dir).resolve()
        if self._index_dir is None:
            raise ValueError("index_dir is required. Provide it in constructor or method call.")
        return self._index_dir

    def _reset_index(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("Index dimension must be positive.")
        self._dimension = int(dimension)
        self._index = self._faiss.IndexFlatIP(self._dimension)
