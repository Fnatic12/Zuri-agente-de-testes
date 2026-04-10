from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures.integrations.jira.failure_issues import (
    build_failure_issue_description,
    build_failure_issue_labels,
    build_failure_issue_summary,
    collect_failure_issue_attachments,
)


def test_build_failure_issue_summary_and_labels_are_stable():
    record = {
        "category": "radio",
        "test_name": "scan_fm",
        "short_text": "Falha ao iniciar radio apos reboot",
        "priority": "alta",
    }

    summary = build_failure_issue_summary(record)
    labels = build_failure_issue_labels(record)

    assert summary.startswith("[Falha] radio/scan_fm - Falha ao iniciar radio")
    assert labels == ("vwait", "falha", "radio", "alta")


def test_collect_failure_issue_attachments_only_returns_existing_files(tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    json_path = report_dir / "failure_report.json"
    md_path = report_dir / "failure_report.md"
    json_path.write_text("{}", encoding="utf-8")
    md_path.write_text("# report", encoding="utf-8")

    record = {
        "report_json_path": str(json_path),
        "report_markdown_path": str(md_path),
        "report_csv_path": str(report_dir / "missing.csv"),
        "report": {"attachments": {"result_image": str(report_dir / "missing.png")}},
    }

    attachments = collect_failure_issue_attachments(record)

    assert attachments == [
        {"label": "Relatorio JSON", "path": str(json_path)},
        {"label": "Relatorio Markdown", "path": str(md_path)},
    ]


def test_build_failure_issue_description_includes_root_cause_and_failed_steps():
    record = {
        "record_id": "radio/teste/2026-04-09T10:00:00",
        "category": "radio",
        "test_name": "teste",
        "generated_at": "2026-04-09T10:00:00",
        "priority": "media",
        "resultado_final": "FAIL",
        "log_capture_status": "capturado",
        "short_text": "Falha visual apos reboot",
        "report": {
            "summary": {"total_actions": 5, "failed_actions": 1, "first_failed_action_id": 3},
            "precondition": "Radio ligado e baseline disponivel.",
            "actual_results": "Tela divergente apos acao 3.",
            "recovery_conditions": "Sem recuperacao.",
            "failed_steps": [
                {"action_id": 3, "action_type": "tap", "similarity": 0.71, "status": "Divergente"}
            ],
            "version_information": {"device_name": "HU-01"},
            "radio_log": {"summary": "Erro de tuner detectado."},
        },
    }

    text = build_failure_issue_description(record, root_cause="Possivel erro de tuner", notes="Priorizar bancada A")

    assert "Falha visual apos reboot" in text
    assert "acao 3 | tipo tap" in text
    assert "Erro de tuner detectado." in text
    assert "Possivel erro de tuner" in text
    assert "Priorizar bancada A" in text
