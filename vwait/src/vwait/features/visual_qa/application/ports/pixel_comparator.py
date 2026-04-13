from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from vwait.features.visual_qa.domain.entities import PixelDiffResult


class PixelComparator(ABC):
    """Adapter over existing pixel-level validator."""

    @abstractmethod
    def compare(
        self,
        actual_image_path: str,
        expected_image_path: str,
        output_dir: Optional[str] = None,
    ) -> PixelDiffResult:
        pass
