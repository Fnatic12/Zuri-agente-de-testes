from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterable


class ArtifactStore(ABC):
    @abstractmethod
    def create_run_dir(self, run_id: str) -> Path:
        pass

    @abstractmethod
    def save_json(self, run_dir: Path, filename: str, payload: Dict[str, Any]) -> Path:
        pass

    @abstractmethod
    def save_markdown(self, run_dir: Path, filename: str, markdown: str) -> Path:
        pass

    @abstractmethod
    def save_json_lines(self, run_dir: Path, filename: str, rows: Iterable[Dict[str, Any]]) -> Path:
        pass

    @abstractmethod
    def append_runs_index(self, row: Dict[str, Any]) -> Path:
        pass

    @abstractmethod
    def load_runs_index(self) -> list[Dict[str, Any]]:
        pass
