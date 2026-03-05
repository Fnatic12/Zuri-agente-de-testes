"""Domain models for Visual QA."""

from visual_qa.domain.entities import PixelDiffResult, Report, ScreenMatch, ValidationRun
from visual_qa.domain.value_objects import Paths, ScreenType, SimilarityScore

__all__ = [
    "PixelDiffResult",
    "Report",
    "ScreenMatch",
    "ValidationRun",
    "Paths",
    "ScreenType",
    "SimilarityScore",
]
