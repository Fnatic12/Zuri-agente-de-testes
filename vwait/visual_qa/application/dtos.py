"""Application DTO scaffolding for Visual QA use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from visual_qa.domain.scaffold_entities import Report, ScreenMatch, ValidationRun


@dataclass(frozen=True)
class BuildVectorIndexRequest:
    """Input for building a vector index from baseline images."""

    reference_root: Path
    index_output_dir: Path
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildVectorIndexResult:
    """Output metadata generated after index build."""

    indexed_images: int
    index_dir: Path
    metadata_path: Path


@dataclass(frozen=True)
class ClassifyScreenshotRequest:
    """Input for Stage 1 screen classification."""

    screenshot_path: Path
    top_k: int = 5
    threshold: float = 0.0


@dataclass(frozen=True)
class ClassifyScreenshotResult:
    """Output for Stage 1 classification."""

    screen_match: ScreenMatch


@dataclass(frozen=True)
class ValidateScreenshotRequest:
    """Input for full validation pipeline execution."""

    screenshot_path: Path
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidateScreenshotResult:
    """Output wrapper for completed pipeline execution."""

    validation_run: ValidationRun
    report: Report
