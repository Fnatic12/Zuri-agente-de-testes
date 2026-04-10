from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class ScreenMatchCandidate(Mapping[str, Any]):
    """Vector-search candidate with compatibility keys for legacy callers."""

    image_path: str
    screen_type: str
    score: float
    vector_id: int | None = None
    tags: list[str] = field(default_factory=list)

    def metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "image_path": self.image_path,
            "screen_type": self.screen_type,
        }
        if self.tags:
            data["tags"] = list(self.tags)
        return data

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.vector_id,
            "score": self.score,
            "metadata": self.metadata(),
            "image_path": self.image_path,
            "screen_type": self.screen_type,
            "tags": list(self.tags),
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())
