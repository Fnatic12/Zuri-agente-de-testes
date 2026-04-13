from __future__ import annotations

import json
import socket

from visual_qa.infrastructure.llm.null_report_generator import NullReportGenerator
from visual_qa.infrastructure.llm.ollama_report_generator import OllamaReportGenerator


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_ollama_report_generator_uses_env_and_retries(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    attempts = {"count": 0}
    seen_requests = []

    def fake_urlopen(req, timeout):
        attempts["count"] += 1
        seen_requests.append((req, timeout))
        if attempts["count"] == 1:
            raise socket.timeout("timeout")
        return _FakeResponse(
            {
                "response": "## Summary\nok\n## Findings\nok\n## Issues\nnone\n## Risk\nlow\n## Recommendation\nship",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    generator = OllamaReportGenerator(timeout_s=3, max_retries=2)
    report = generator.generate_report({"run": {"run_id": "abc"}})

    assert attempts["count"] == 2
    assert report.provider == "ollama"
    assert report.model == "llama3"
    assert "## Summary" in report.markdown
    req, timeout = seen_requests[-1]
    assert req.full_url == "http://localhost:11434/api/generate"
    assert timeout == 3


def test_ollama_report_generator_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.timeout()))
    generator = OllamaReportGenerator(base_url="http://127.0.0.1:11434", model="llama3", max_retries=2)

    try:
        generator.generate_report({"run": {"run_id": "x"}})
    except RuntimeError as exc:
        assert "after 3 attempt(s)" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when Ollama keeps timing out")


def test_null_report_generator_output_is_stable():
    payload = {
        "run": {"run_id": "run-1"},
        "classification": {
            "predicted_screen_type": "home_screen",
            "selected_baseline_image": "/tmp/home.png",
            "classification_threshold": 0.5,
            "winning_score": 0.92,
            "matches": [
                {"rank": 1, "screen_type": "home_screen", "similarity": 0.92, "image_path": "/tmp/home.png"}
            ],
        },
        "pixel_result": {"status": "PASS", "ssim_score": 0.99, "difference_percent": 0.4, "issues": []},
        "historical": {"average_diff_percent": 0.8},
    }
    generator = NullReportGenerator()

    md1 = generator.generate_report(payload).markdown
    md2 = generator.generate_report(payload).markdown

    assert md1 == md2
    assert "## Summary" in md1
    assert "## Findings" in md1
    assert "## Issues" in md1
    assert "## Risk" in md1
    assert "## Recommendation" in md1
