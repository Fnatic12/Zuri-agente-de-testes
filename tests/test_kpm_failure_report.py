from __future__ import annotations

import csv
import json
from pathlib import Path

from KPM import report_builder, report_exporters


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_failure_report_includes_structured_sections(tmp_path, monkeypatch):
    category = "radio"
    test_name = "falha_home"
    test_dir = tmp_path / category / test_name
    log_path = test_dir / "execucao_log.json"

    _write_json(
        log_path,
        {
            "execucao": [
                {
                    "id": 1,
                    "acao": "tap",
                    "status": "OK",
                    "similaridade": 0.98,
                    "duracao": 1.2,
                    "timestamp": "2026-03-20T10:00:01",
                    "coordenadas": {"x": 10, "y": 20},
                    "screenshot": "resultados/acao_1.png",
                    "frame_esperado": "frames/acao_1.png",
                },
                {
                    "id": 2,
                    "acao": "swipe",
                    "status": "Divergente",
                    "similaridade": 0.41,
                    "duracao": 2.4,
                    "timestamp": "2026-03-20T10:00:04",
                    "coordenadas": {"x": 40, "y": 90},
                    "screenshot": "resultados/acao_2.png",
                    "frame_esperado": "frames/acao_2.png",
                },
            ]
        },
    )
    _write_json(test_dir / "test_meta.json", {"precondition": "Radio ligado e na tela inicial."})
    _write_json(test_dir / "execution_context.json", {"device_name": "Bench radio"})
    _write_json(
        test_dir / "status_SERIAL123.json",
        {
            "serial": "SERIAL123",
            "SERIAL123": {
                "resultado_final": "reprovado",
                "log_capture_status": "capturado",
                "log_capture_dir": "logs/capture_001",
                "log_capture_sequence": "SeqA",
            },
        },
    )
    _write_json(
        test_dir / "logs" / "capture_001" / "capture_metadata.json",
        {"source": "radio", "entries": 2},
    )
    (test_dir / "logs" / "capture_001" / "radio_logs").mkdir(parents=True, exist_ok=True)
    (test_dir / "logs" / "capture_001" / "radio_logs" / "system.log").write_text("boot ok", encoding="utf-8")

    monkeypatch.setattr(report_builder, "test_dir", lambda cat, name: tmp_path / cat / name)

    report = report_builder.build_failure_report(category, test_name, log_path, similarity_threshold=0.85)

    assert report is not None
    assert report["short_text"].startswith("RADIO - falha visual na acao 2")
    assert report["precondition"] == "Radio ligado e na tela inicial."
    assert len(report["operation_steps"]) == 2
    assert report["test_result"].startswith("Teste reprovado com 1 divergencia")
    assert "similaridade minima de 0.85" in report["expected_result"]
    assert "Acao 2 retornou 'Divergente'" in report["actual_results"]
    assert report["dashboard_summary"]["resultado_final"] == "reprovado"
    assert report["dashboard_summary"]["failed_actions"] == 1
    assert report["radio_log"]["status"] == "capturado"
    assert report["radio_log"]["sequence"] == "SeqA"
    assert "capture_metadata.json" in report["radio_log"]["files"]
    assert "radio_logs/system.log" in report["radio_log"]["files"]


def test_failure_report_exporters_include_new_fields(tmp_path):
    report = {
        "generated_at": "2026-03-20T10:00:10",
        "test": {"category": "radio", "name": "falha_home"},
        "precondition": "Radio ligado.",
        "short_text": "Falha visual detectada.",
        "operation_steps": ["Acao 1: tap em (10, 20)"],
        "test_result": "Teste reprovado por divergencia visual.",
        "expected_result": "O teste deveria terminar aprovado.",
        "actual_results": "Acao 1 retornou Divergente.",
        "radio_log": {
            "summary": "Captura realizada.",
            "status": "capturado",
            "capture_dir": str(tmp_path / "logs"),
            "sequence": "SeqA",
            "error": "",
            "files": ["radio_logs/system.log"],
        },
        "occurrence_rate": {"label": "1/1 execucao falhou"},
        "recovery_conditions": "Sem recuperacao automatica.",
        "bug_occurrence_time": {
            "first_failure_timestamp": "2026-03-20T10:00:04",
            "elapsed_seconds_from_start": 3.6,
        },
        "version_information": {"adb_serial": "SERIAL123"},
        "failed_steps": [
            {
                "action_id": 1,
                "action_type": "tap",
                "similarity": 0.41,
                "status": "Divergente",
            }
        ],
    }
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = report_exporters.export_markdown(report, out_dir)
    csv_path = report_exporters.export_csv(report, out_dir)

    markdown = md_path.read_text(encoding="utf-8")
    assert "## Test Result" in markdown
    assert "## Expected Result" in markdown
    assert "## Radio Log" in markdown
    assert "### Radio Log Files" in markdown

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == [
        "Precondition",
        "Short text",
        "Operation steps",
        "Test Result",
        "Expected Result",
        "Actual Results",
        "Radio Log",
        "Occurrence Rate",
        "Recovery Conditions",
        "Bug Occurrence Time",
        "Version Information",
    ]
    assert rows[1][3] == "Teste reprovado por divergencia visual."
    assert rows[1][4] == "O teste deveria terminar aprovado."
    assert rows[1][6] == "Captura realizada."
