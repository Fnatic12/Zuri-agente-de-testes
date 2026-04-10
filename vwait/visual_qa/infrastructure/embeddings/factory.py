from __future__ import annotations

from visual_qa.application.ports.embedding_provider import EmbeddingProvider
from visual_qa.config import VisualQaConfig
from visual_qa.infrastructure.embeddings.fallback_provider import LocalFeatureEmbeddingProvider
from visual_qa.infrastructure.embeddings.mobileclip_provider import MobileCLIPEmbeddingProvider
from visual_qa.infrastructure.embeddings.openclip_provider import OpenCLIPEmbeddingProvider


def build_embedding_provider(config: VisualQaConfig) -> EmbeddingProvider:
    mode = (config.embedding_provider or "auto").strip().lower()

    if mode in {"auto", "mobileclip"}:
        try:
            return MobileCLIPEmbeddingProvider(model_name=config.mobileclip_model)
        except Exception:
            if mode == "mobileclip":
                raise

    if mode in {"auto", "openclip", "mobileclip"}:
        try:
            return OpenCLIPEmbeddingProvider(
                model_name=config.openclip_model,
                pretrained=config.openclip_pretrained,
            )
        except Exception:
            if mode == "openclip":
                raise

    return LocalFeatureEmbeddingProvider()
