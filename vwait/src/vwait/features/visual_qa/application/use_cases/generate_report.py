from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from visual_qa.application.ports.report_generator import ReportGenerator
from visual_qa.domain.entities import Report


@dataclass
class GenerateReport:
    report_generator: ReportGenerator

    def execute(self, payload: Dict[str, Any]) -> Report:
        return self.report_generator.generate_report(payload)
