from __future__ import annotations

import numpy as np
import pytest

from vwait.features.visual_qa.application.ports.embedding_provider import EmbeddingProvider
from vwait.features.visual_qa.application.ports.vector_index_repository import VectorIndexRepository
from vwait.features.visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
from vwait.features.visual_qa.domain.scaffold_entities import ScreenMatch as Stage1ScreenMatch


class FakeEmbeddingProvider(EmbeddingProvider):
    def embed_image(self, image_path: str) -> np.ndarray:
        assert isinstance(image_path, str)
        return np.array([1.0, 0.0, 0.0], dtype=np.float32)


class FakeVectorIndexRepository(VectorIndexRepository):
    def __init__(self, search_rows):
        self._search_rows = list(search_rows)
        self.loaded_index_dir = None
        self.last_top_k = None

    def build(self, vectors: np.ndarray, metadata):
        raise NotImplementedError

    def search(self, query_vector: np.ndarray, top_k: int):
        self.last_top_k = top_k
        return self._search_rows[:top_k]

    def save(self, index_dir: str):
        raise NotImplementedError

    def load(self, index_dir: str):
        self.loaded_index_dir = index_dir


def test_classify_best_strategy_uses_top_match_when_above_threshold():
    repo = FakeVectorIndexRepository(
        [
            {"score": 0.93, "metadata": {"screen_type": "home_screen", "image_path": "/tmp/home.png"}},
            {"score": 0.81, "metadata": {"screen_type": "login_screen", "image_path": "/tmp/login.png"}},
        ]
    )
    use_case = ClassifyScreenshot(embedding_provider=FakeEmbeddingProvider(), vector_repo=repo)

    result = use_case.execute(
        screenshot_path="/tmp/query.png",
        top_k=2,
        threshold=0.90,
        strategy="best",
        index_dir="/tmp/index",
    )

    assert repo.loaded_index_dir == "/tmp/index"
    assert result["predicted_screen_type"] == "home_screen"
    assert result["selected_baseline_image"] == "/tmp/home.png"
    assert result["classification_strategy"] == "best"
    assert isinstance(result["screen_match"], Stage1ScreenMatch)
    assert result["screen_match"].screen_type == "home_screen"
    assert len(result["screen_match"].top_k) == 2


def test_classify_best_strategy_returns_unknown_when_below_threshold():
    repo = FakeVectorIndexRepository(
        [
            {"score": 0.39, "metadata": {"screen_type": "home_screen", "image_path": "/tmp/home.png"}},
            {"score": 0.20, "metadata": {"screen_type": "login_screen", "image_path": "/tmp/login.png"}},
        ]
    )
    use_case = ClassifyScreenshot(embedding_provider=FakeEmbeddingProvider(), vector_repo=repo)

    result = use_case.execute(
        screenshot_path="/tmp/query.png",
        top_k=2,
        threshold=0.40,
        strategy="best",
    )

    assert repo.loaded_index_dir is None
    assert result["predicted_screen_type"] == "unknown"
    assert result["selected_baseline_image"] is None
    assert result["screen_match"].screen_type == "unknown"


def test_classify_vote_strategy_uses_weighted_majority_and_threshold():
    repo = FakeVectorIndexRepository(
        [
            {"score": 0.62, "metadata": {"screen_type": "home_screen", "image_path": "/tmp/home_1.png"}},
            {"score": 0.59, "metadata": {"screen_type": "login_screen", "image_path": "/tmp/login_1.png"}},
            {"score": 0.58, "metadata": {"screen_type": "login_screen", "image_path": "/tmp/login_2.png"}},
        ]
    )
    use_case = ClassifyScreenshot(embedding_provider=FakeEmbeddingProvider(), vector_repo=repo)

    result = use_case.execute(
        screenshot_path="/tmp/query.png",
        top_k=3,
        threshold=1.10,
        strategy="vote",
    )

    assert repo.last_top_k == 3
    assert result["predicted_screen_type"] == "login_screen"
    assert result["selected_baseline_image"] == "/tmp/login_1.png"
    assert result["winning_score"] == pytest.approx(1.17, rel=1e-6)
    assert result["screen_match"].screen_type == "login_screen"


def test_classify_rejects_invalid_strategy():
    repo = FakeVectorIndexRepository([])
    use_case = ClassifyScreenshot(embedding_provider=FakeEmbeddingProvider(), vector_repo=repo)

    with pytest.raises(ValueError, match="strategy must be one of"):
        use_case.execute(
            screenshot_path="/tmp/query.png",
            top_k=3,
            threshold=0.1,
            strategy="invalid",
        )
