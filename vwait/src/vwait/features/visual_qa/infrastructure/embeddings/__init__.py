"""Embedding providers for Stage 1 screen similarity."""

from visual_qa.infrastructure.embeddings.factory import build_embedding_provider
from visual_qa.infrastructure.embeddings.fallback_provider import LocalFeatureEmbeddingProvider
from visual_qa.infrastructure.embeddings.mobileclip_provider import MobileCLIPEmbeddingProvider
from visual_qa.infrastructure.embeddings.openclip_provider import OpenCLIPEmbeddingProvider

__all__ = [
    "build_embedding_provider",
    "LocalFeatureEmbeddingProvider",
    "MobileCLIPEmbeddingProvider",
    "OpenCLIPEmbeddingProvider",
]
