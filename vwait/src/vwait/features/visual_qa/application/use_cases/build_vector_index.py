from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from visual_qa.application.ports.embedding_provider import EmbeddingProvider
from visual_qa.application.ports.vector_index_repository import VectorIndexRepository

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _infer_screen_type(path: Path) -> str:
    stem = path.stem.lower().replace("-", "_").replace(" ", "_")
    parts = [p for p in stem.split("_") if p]
    while parts and parts[-1].isdigit():
        parts.pop()
    return "_".join(parts) if parts else "unknown"


def _read_sidecar(path: Path) -> Dict[str, Any]:
    sidecar = path.with_suffix(".meta.json")
    if not sidecar.exists():
        return {}
    try:
        with sidecar.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass
class BuildVectorIndex:
    embedding_provider: EmbeddingProvider
    vector_repo: VectorIndexRepository

    def execute(self, reference_dir: str, index_dir: str) -> Dict[str, Any]:
        reference_root = Path(reference_dir).resolve()
        if not reference_root.exists() or not reference_root.is_dir():
            raise FileNotFoundError(f"Reference directory not found: {reference_root}")

        vectors: List[np.ndarray] = []
        metadata: List[Dict[str, Any]] = []

        for image_path in sorted(reference_root.rglob("*")):
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            sidecar = _read_sidecar(image_path)
            vector = self.embedding_provider.embed_image(str(image_path))
            vectors.append(vector.astype(np.float32))
            rel_path = str(image_path.relative_to(reference_root)).replace("\\", "/")
            metadata.append(
                {
                    "image_path": str(image_path),
                    "relative_path": rel_path,
                    "screen_type": str(sidecar.get("screen_type") or _infer_screen_type(image_path)),
                    "tags": sidecar.get("tags", []),
                    "extra": sidecar,
                }
            )

        if not vectors:
            raise ValueError(f"No reference images found in {reference_root}")

        matrix = np.vstack(vectors).astype(np.float32)
        self.vector_repo.build(matrix, metadata)
        self.vector_repo.save(index_dir)

        return {
            "reference_dir": str(reference_root),
            "index_dir": str(Path(index_dir).resolve()),
            "images_indexed": len(metadata),
            "embedding_dim": int(matrix.shape[1]),
            "embedding_provider": self.embedding_provider.name,
        }
