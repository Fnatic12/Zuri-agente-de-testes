from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.error import HTTPError, URLError

from visual_qa.application.ports.report_generator import ReportGenerator
from visual_qa.domain.entities import Report


SYSTEM_PROMPT = (
    "You are a strict Visual QA reporting assistant.\n"
    "You must ONLY use fields present in the provided JSON payload.\n"
    "Do not hallucinate. Do not infer unseen data. Do not use outside knowledge.\n"
    "If data is missing, explicitly state it as unavailable.\n"
    "Return Markdown with exactly these sections and this order:\n"
    "## Summary\n"
    "## Findings\n"
    "## Issues\n"
    "## Risk\n"
    "## Recommendation\n"
)


class OllamaReportGenerator(ReportGenerator):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: int = 45,
        max_retries: int = 2,
    ) -> None:
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        self._model = (model or os.getenv("OLLAMA_MODEL") or "llama3").strip()
        self._timeout_s = int(timeout_s)
        self._max_retries = max(0, min(int(max_retries), 2))

    @staticmethod
    def _sanitize_json(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): OllamaReportGenerator._sanitize_json(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [OllamaReportGenerator._sanitize_json(v) for v in value]
        return str(value)

    def _build_request_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        structured_payload = self._sanitize_json(payload)
        user_input = json.dumps(structured_payload, ensure_ascii=False, sort_keys=True, indent=2)
        return {
            "model": self._model,
            "stream": False,
            "options": {"temperature": 0.0},
            "prompt": (
                "[SYSTEM]\n"
                f"{SYSTEM_PROMPT}\n"
                "[USER]\n"
                "Use only the JSON below to generate the report.\n"
                f"{user_input}"
            ),
        }

    def _call_ollama(self, payload: Dict[str, Any]) -> str:
        request_payload = self._build_request_payload(payload)
        body = json.dumps(request_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
                text = str(data.get("response") or "").strip()
                if not text:
                    raise RuntimeError("Ollama returned empty report content.")
                return text
            except (URLError, HTTPError, socket.timeout, TimeoutError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt >= attempts:
                    break
        raise RuntimeError(
            f"Failed to generate report with Ollama after {attempts} attempt(s): {type(last_error).__name__}"
        ) from last_error

    def generate_report(self, payload: Dict[str, Any]) -> Report:
        markdown = self._call_ollama(payload)
        return Report(
            provider="ollama",
            model=self._model,
            markdown=markdown,
            generated_at=datetime.now(timezone.utc),
            prompt_snapshot=SYSTEM_PROMPT,
        )
