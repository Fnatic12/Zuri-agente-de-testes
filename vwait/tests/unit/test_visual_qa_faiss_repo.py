import pytest
import numpy as np

from visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository


def test_faiss_repository_save_load_search(tmp_path):
    pytest.importorskip("faiss")
    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    metadata = [
        {"image_path": "a.png", "screen_type": "home"},
        {"image_path": "b.png", "screen_type": "login"},
        {"image_path": "c.png", "screen_type": "settings"},
    ]

    repo = FaissVectorIndexRepository(use_faiss=True)
    repo.build(vectors, metadata)
    repo.save(str(tmp_path / "idx"))

    repo2 = FaissVectorIndexRepository(use_faiss=True)
    repo2.load(str(tmp_path / "idx"))

    result = repo2.search(np.array([1.0, 0.0, 0.0], dtype=np.float32), top_k=2)
    assert len(result) == 2
    assert result[0]["metadata"]["screen_type"] == "home"
    assert result[0]["score"] >= result[1]["score"]
