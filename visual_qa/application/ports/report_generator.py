from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from visual_qa.domain.entities import Report


class ReportGenerator(ABC):
    """Generates markdown reports from structured JSON-like payloads."""

    @abstractmethod
    def generate_report(self, payload: Dict[str, Any]) -> Report:
        pass
