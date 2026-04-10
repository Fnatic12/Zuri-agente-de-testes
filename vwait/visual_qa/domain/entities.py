from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ScreenMatch:
    rank: int
    screen_type: str
    image_path: str
    similarity: float
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PixelDiffResult:
    status: str
    baseline_image: str
    actual_image: str
    ssim_score: Optional[float]
    difference_percent: Optional[float]
    issues: List[str] = field(default_factory=list)
    diff_image_path: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    provider: str
    model: str
    markdown: str
    generated_at: datetime
    prompt_snapshot: Optional[str] = None


@dataclass
class ValidationRun:
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime]
    screenshot_path: str
    predicted_screen_type: str
    classification_threshold: float
    selected_baseline_image: Optional[str]
    matches: List[ScreenMatch]
    pixel_result: Optional[PixelDiffResult]
    report_path: Optional[Path]
    json_path: Optional[Path]
    config_snapshot: Dict[str, Any]
    reproducibility: Dict[str, Any]
    historical_stats: Dict[str, Any] = field(default_factory=dict)
