from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("faiss")

from vwait.features.visual_qa.infrastructure.vector_index.dtos import ScreenMatchCandidate
from vwait.features.visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository


class _FakeEmbeddingProvider:
    def __init__(self, vector_by_name: dict[str, np.ndarray]) -> None:
        self._vector_by_name = vector_by_name

    def embed_image(self, image_path: str) -> np.ndarray:
        key = Path(image_path).name
        return self._vector_by_name[key]


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_search_returns_expected_ordering_with_synthetic_vectors(tmp_path: Path):
    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.7, 0.7, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    metadata = [
        {"image_path": "home.png", "screen_type": "home"},
        {"image_path": "mix.png", "screen_type": "mixed"},
        {"image_path": "login.png", "screen_type": "login"},
    ]

    repo = FaissVectorIndexRepository(index_dir=tmp_path / "idx")
    repo.build(vectors, metadata)
    matches = repo.search(np.array([1.0, 0.0, 0.0], dtype=np.float32), top_k=3)

    assert all(isinstance(m, ScreenMatchCandidate) for m in matches)
    assert [m.screen_type for m in matches] == ["home", "mixed", "login"]
    assert matches[0].score >= matches[1].score >= matches[2].score


def test_save_load_roundtrip_persists_metadata_mapping(tmp_path: Path):
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    metadata = [
        {"image_path": "a.png", "screen_type": "home", "tags": ["main"]},
        {"image_path": "b.png", "screen_type": "login"},
    ]
    index_dir = tmp_path / "idx"

    repo = FaissVectorIndexRepository(index_dir=index_dir)
    repo.build(vectors, metadata)
    repo.save()

    with (index_dir / "metadata.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["0"]["image_path"] == "a.png"
    assert payload["0"]["screen_type"] == "home"
    assert payload["0"]["tags"] == ["main"]

    loaded = FaissVectorIndexRepository(index_dir=index_dir)
    loaded.load()
    matches = loaded.search(np.array([1.0, 0.0], dtype=np.float32), top_k=1)
    assert matches[0].image_path == "a.png"
    assert matches[0].screen_type == "home"


def test_build_from_folder_and_add_item_with_label_map(tmp_path: Path):
    ref_dir = tmp_path / "refs"
    _touch(ref_dir / "home_screen_1.png")
    _touch(ref_dir / "nested" / "login_screen_2.jpg")

    embedder = _FakeEmbeddingProvider(
        {
            "home_screen_1.png": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "login_screen_2.jpg": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        }
    )
    repo = FaissVectorIndexRepository(index_dir=tmp_path / "idx", embedding_provider=embedder)
    repo.build_from_folder(
        reference_dir=str(ref_dir),
        label_map={"login_screen_2.jpg": "login_custom"},
        recursive=True,
    )

    matches = repo.search(np.array([0.0, 1.0, 0.0], dtype=np.float32), top_k=2)
    assert matches[0].screen_type == "login_custom"
    assert matches[1].screen_type == "home_screen"
