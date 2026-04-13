import cv2
import numpy as np

from visual_qa.application.use_cases.build_vector_index import BuildVectorIndex
from visual_qa.application.ports.embedding_provider import EmbeddingProvider
from visual_qa.application.ports.vector_index_repository import VectorIndexRepository


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.calls = []

    def embed_image(self, image_path: str) -> np.ndarray:
        self.calls.append(image_path)
        vec = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        return vec / np.linalg.norm(vec)


class InMemoryVectorRepo(VectorIndexRepository):
    def __init__(self) -> None:
        self.vectors = None
        self.metadata = None
        self.saved_dir = None

    def build(self, vectors: np.ndarray, metadata):
        self.vectors = vectors
        self.metadata = metadata

    def search(self, query_vector: np.ndarray, top_k: int):
        raise NotImplementedError

    def save(self, index_dir: str):
        self.saved_dir = index_dir

    def load(self, index_dir: str):
        raise NotImplementedError


def test_embedding_provider_interface_used_by_build_index(tmp_path):
    ref_dir = tmp_path / "refs"
    ref_dir.mkdir(parents=True)

    img = np.zeros((20, 20, 3), dtype=np.uint8)
    cv2.imwrite(str(ref_dir / "home_screen_1.png"), img)

    provider = FakeEmbeddingProvider()
    repo = InMemoryVectorRepo()
    use_case = BuildVectorIndex(embedding_provider=provider, vector_repo=repo)

    summary = use_case.execute(str(ref_dir), str(tmp_path / "index"))

    assert summary["images_indexed"] == 1
    assert len(provider.calls) == 1
    assert repo.vectors is not None
    assert repo.vectors.shape == (1, 3)
    assert repo.metadata[0]["screen_type"] == "home_screen"
