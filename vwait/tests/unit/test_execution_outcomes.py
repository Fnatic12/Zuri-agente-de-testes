from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.application.outcomes import (
    build_action_outcome,
    conclude_execution_flow,
    resolve_execution_final_result,
    sanitize_action_payload,
)


def test_sanitize_action_payload_converts_missing_values():
    payload = {"x": 10, "y": None, "texto": "abc"}
    result = sanitize_action_payload(payload)
    assert result == {"x": 10, "y": None, "texto": "abc"}


def test_build_action_outcome_marks_divergence_from_threshold():
    outcome = build_action_outcome(
        1,
        "tap",
        {"x": 10, "y": 20},
        "resultados/resultado_01.png",
        "frames/frame_01.png",
        0.84,
        1.25,
        threshold=0.85,
        timestamp_fn=lambda: "2026-04-10T10:00:00",
    )
    assert outcome["status"] == "Divergente"
    assert outcome["divergent"] is True
    assert outcome["log_record"]["acao"] == "tap"


def test_resolve_execution_final_result_maps_visual_divergence():
    assert resolve_execution_final_result(True) == ("reprovado", "divergencia_visual")
    assert resolve_execution_final_result(False) == ("aprovado", None)


def test_conclude_execution_flow_orchestrates_capture_and_report():
    final_calls = []
    messages = []

    def finalize_status(*args, **kwargs):
        final_calls.append((args, kwargs))

    def capture_logs_fn(_categoria, _teste, _serial, _motivo):
        return {
            "status": "capturado",
            "artifact_dir": "logs/20260410_103000",
            "error": None,
            "sequence_path": "/tmp/base/logs/20260410_103000/failure_log_sequence.json",
        }

    def generate_report_fn(_categoria, _teste, _log_path, _threshold):
        return {
            "status": "gerado",
            "report_dir": "/tmp/report",
            "json_path": "/tmp/report/report.json",
            "markdown_path": "/tmp/report/report.md",
            "csv_path": "/tmp/report/report.csv",
            "short_text": "falha visual",
            "generated_at": "2026-04-10T10:02:00",
            "error": None,
        }

    result = conclude_execution_flow(
        "SERIAL1",
        "radio",
        "home",
        "SERIAL1",
        "finalizado",
        "reprovado",
        motivo="divergencia_visual",
        capture_logs=True,
        log_path="/tmp/base/execucao_log.json",
        similarity_threshold=0.85,
        status_dir="/tmp/base",
        finalize_status=finalize_status,
        capture_logs_fn=capture_logs_fn,
        generate_report_fn=generate_report_fn,
        emit_message=lambda message, color: messages.append((message, color)),
    )

    assert len(final_calls) == 2
    assert final_calls[0][1]["resultado"] == "coletando_logs"
    assert final_calls[1][1]["resultado"] == "finalizado"
    assert result["log_capture_status"] == "capturado"
    assert result["failure_report_status"] == "gerado"
    assert any("Relatorio estruturado" in message for message, _ in messages)
