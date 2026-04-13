from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScreenType:
    value: str

    def __post_init__(self) -> None:
        normalized = (self.value or "unknown").strip().lower().replace(" ", "_")
        object.__setattr__(self, "value", normalized or "unknown")


@dataclass(frozen=True)
class SimilarityScore:
    value: float

    def __post_init__(self) -> None:
        v = float(self.value)
        if v < 0.0:
            v = 0.0
        if v > 1.0:
            v = 1.0
        object.__setattr__(self, "value", v)


@dataclass(frozen=True)
class Paths:
    index_dir: Path
    runs_dir: Path
    working_dir: Path
