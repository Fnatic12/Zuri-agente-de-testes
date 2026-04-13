from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from vwait.features.visual_qa.infrastructure.embeddings.mobileclip_provider import MobileCLIPEmbeddingProvider
from vwait.features.visual_qa.infrastructure.embeddings.openclip_provider import OpenCLIPEmbeddingProvider


class _DummyTensor:
    def unsqueeze(self, _dim: int) -> "_DummyTensor":
        return self


class _NoGrad:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeModel:
    def eval(self) -> None:
        return None

    def encode_image(self, _tensor) -> np.ndarray:
        return np.array([[3.0, 4.0]], dtype=np.float32)


def _write_image(path: Path) -> None:
    image = Image.new("RGB", (8, 8), color=(10, 20, 30))
    image.save(path)


def _patch_clip_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_open_clip = SimpleNamespace(
        create_model_and_transforms=lambda model_name, pretrained=None: (
            _FakeModel(),
            None,
            lambda _img: _DummyTensor(),
        )
    )
    fake_torch = SimpleNamespace(no_grad=lambda: _NoGrad())

    real_import_module = importlib.import_module

    def fake_import_module(name: str, *args, **kwargs):
        if name == "open_clip":
            return fake_open_clip
        if name == "torch":
            return fake_torch
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)


def _assert_normalized_vector(vector: np.ndarray) -> None:
    assert isinstance(vector, np.ndarray)
    assert vector.dtype == np.float32
    assert vector.shape == (2,)
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-6)


def test_mobileclip_embed_image_returns_l2_normalized_vector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_clip_deps(monkeypatch)
    image_path = tmp_path / "sample.png"
    _write_image(image_path)

    provider = MobileCLIPEmbeddingProvider()
    vector = provider.embed_image(str(image_path))

    _assert_normalized_vector(vector)


def test_openclip_embed_image_returns_l2_normalized_vector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_clip_deps(monkeypatch)
    image_path = tmp_path / "sample.jpg"
    _write_image(image_path)

    provider = OpenCLIPEmbeddingProvider()
    vector = provider.embed_image(str(image_path))

    _assert_normalized_vector(vector)


def test_mobileclip_raises_clear_error_on_missing_dependencies(monkeypatch: pytest.MonkeyPatch):
    real_import_module = importlib.import_module

    def fake_import_module(name: str, *args, **kwargs):
        if name in {"open_clip", "torch"}:
            raise ImportError("missing dependency")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(RuntimeError, match="Missing dependencies for MobileCLIPEmbeddingProvider"):
        MobileCLIPEmbeddingProvider()


def test_openclip_rejects_unsupported_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_clip_deps(monkeypatch)
    image_path = tmp_path / "sample.bmp"
    _write_image(image_path)

    provider = OpenCLIPEmbeddingProvider()

    with pytest.raises(ValueError, match="Unsupported image extension"):
        provider.embed_image(str(image_path))
