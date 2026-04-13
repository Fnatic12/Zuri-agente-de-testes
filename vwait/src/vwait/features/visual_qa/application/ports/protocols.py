"""Application port interfaces for Visual QA.

Ports are modeled as Protocols to support dependency inversion and easy mocking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np

from vwait.features.visual_qa.domain.scaffold_entities import PixelDiffResult, Report, ScreenMatch


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Provides L2-normalized image embeddings as float32 vectors."""

    def embed_image(self, image_path: Path | str) -> np.ndarray:
        """Embed one image into a vector with shape ``(D,)``."""


@runtime_checkable
class VectorIndexRepository(Protocol):
    """Persists and queries vectors plus metadata for nearest-neighbor search."""

    def build(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        """Build an index using precomputed vectors and aligned metadata."""

    def search(self, query_vector: np.ndarray, top_k: int) -> list[dict[str, Any]]:
        """Return top-k nearest neighbors and their metadata."""

    def save(self, index_dir: Path | str) -> None:
        """Persist index and metadata to disk."""

    def load(self, index_dir: Path | str) -> None:
        """Load index and metadata from disk."""


@runtime_checkable
class PixelComparator(Protocol):
    """Adapter over the existing pixel-to-pixel validator implementation."""

    def compare(
        self,
        actual_image_path: Path | str,
        expected_image_path: Path | str,
        output_dir: Path | str | None = None,
    ) -> PixelDiffResult:
        """Compare actual vs expected image and return normalized metrics."""


@runtime_checkable
class ReportGenerator(Protocol):
    """Generates Markdown/JSON report artifacts from structured payloads."""

    def generate_report(self, payload: Mapping[str, Any]) -> Report:
        """Generate report artifacts using only structured fields."""


@runtime_checkable
class ArtifactStore(Protocol):
    """Handles filesystem persistence for pipeline artifacts."""

    def create_run_dir(self, run_id: str) -> Path:
        """Create the run output directory."""

    def save_json(self, run_dir: Path, filename: str, payload: Mapping[str, Any]) -> Path:
        """Save a JSON artifact and return its path."""

    def save_markdown(self, run_dir: Path, filename: str, content: str) -> Path:
        """Save a Markdown artifact and return its path."""

    def append_runs_index(self, row: Mapping[str, Any]) -> Path:
        """Append one row to historical runs index (JSONL)."""
