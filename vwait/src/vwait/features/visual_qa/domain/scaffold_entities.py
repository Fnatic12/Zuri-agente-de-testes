"""Scaffold domain entities for the Visual QA clean architecture layer.

These dataclasses are intentionally minimal and independent from concrete
infrastructure implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScreenMatch:
    """Result of screen-type classification for a single input screenshot."""

    screen_type: str
    similarity_score: float
    matched_baseline_path: Path | None
    top_k: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PixelDiffResult:
    """Normalized pixel-comparison output from the existing validator adapter."""

    ssim: float | None
    diff_percent: float | None
    issues: list[str] = field(default_factory=list)
    diff_image_path: Path | None = None
    raw_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Report:
    """Paths to generated report artifacts."""

    markdown_path: Path
    json_path: Path


@dataclass(frozen=True)
class ValidationRun:
    """Aggregate root for one full visual validation execution."""

    run_id: str
    timestamp: datetime
    input_image_path: Path
    screen_match: ScreenMatch
    pixel_result: PixelDiffResult | None
    report_paths: Report
    metadata: dict[str, Any] = field(default_factory=dict)
