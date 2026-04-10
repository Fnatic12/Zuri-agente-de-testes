from __future__ import annotations

from visual_qa.application.ports.report_generator import ReportGenerator
from visual_qa.config import VisualQaConfig
from visual_qa.infrastructure.llm.null_report_generator import NullReportGenerator
from visual_qa.infrastructure.llm.ollama_report_generator import OllamaReportGenerator


def build_report_generator(config: VisualQaConfig) -> ReportGenerator:
    mode = (config.report_mode or "null").strip().lower()
    if mode in {"ollama", "llm"}:
        return OllamaReportGenerator(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout_s=config.ollama_timeout_s,
        )
    return NullReportGenerator()
