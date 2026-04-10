import cv2
import numpy as np

from HMI.hmi_indexer import build_library_index
from HMI.hmi_stage1 import build_runtime_index, classify_with_runtime


def _screen(color, with_box=False):
    img = np.zeros((140, 240, 3), dtype=np.uint8)
    img[:] = color
    if with_box:
        cv2.rectangle(img, (25, 30), (210, 95), (250, 250, 250), 2)
    return img


def test_stage1_classification_and_index_embeddings(tmp_path):
    figma_dir = tmp_path / "ref"
    figma_dir.mkdir(parents=True)

    home = _screen((20, 100, 180), with_box=True)
    login = _screen((120, 40, 40), with_box=False)
    query = _screen((20, 100, 180), with_box=True)

    cv2.imwrite(str(figma_dir / "home_screen_1.png"), home)
    cv2.imwrite(str(figma_dir / "login_screen.png"), login)

    index = build_library_index(str(figma_dir))
    assert index["screen_count"] == 2
    for entry in index["screens"]:
        assert isinstance(entry.get("embedding"), list) and len(entry["embedding"]) > 0
        assert isinstance(entry.get("screen_type"), str) and entry["screen_type"]

    runtime = build_runtime_index(index["screens"], backend="local", use_faiss=False)
    result = classify_with_runtime(query, runtime, top_k=2, backend="local")

    assert result["predicted_screen_type"] == "home_screen"
    assert len(result["matches"]) >= 1
    assert result["matches"][0]["screen_type"] == "home_screen"
