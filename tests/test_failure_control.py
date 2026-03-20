from __future__ import annotations

import json
from pathlib import Path

from KPM.failure_control import CONTROL_FILENAME, list_failure_records, update_failure_control


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_list_failure_records_uses_default_control_state(tmp_path):
    report_dir = tmp_path / "audio" / "teste_a" / "2026-03-20T10-00-00"
    _write_json(
        report_dir / "failure_report.json",
        {
            "generated_at": "2026-03-20T10:00:00",
            "short_text": "Falha visual na home.",
            "summary": {"failed_actions": 1, "total_actions": 4, "status": "FAIL"},
            "dashboard_summary": {"resultado_final": "reprovado"},
            "radio_log": {"status": "capturado"},
            "test": {
                "category": "audio",
                "name": "teste_a",
                "test_dir": str(tmp_path / "Data" / "audio" / "teste_a"),
            },
        },
    )

    records = list_failure_records(tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record["workflow_status"] == "novo"
    assert record["jira_sync_status"] == "nao_enviado"
    assert record["priority"] == "media"
    assert record["failed_actions"] == 1
    assert record["total_actions"] == 4
    assert record["report_dir"] == str(report_dir.resolve())


def test_update_failure_control_persists_user_tracking_fields(tmp_path):
    report_dir = tmp_path / "video" / "teste_b" / "2026-03-20T11-00-00"
    report = {
        "generated_at": "2026-03-20T11:00:00",
        "short_text": "Falha de toggle.",
        "test": {"category": "video", "name": "teste_b", "test_dir": str(tmp_path / "Data" / "video" / "teste_b")},
    }
    _write_json(report_dir / "failure_report.json", report)

    saved = update_failure_control(
        report_dir,
        report,
        {
            "workflow_status": "enviado_para_jira",
            "jira_sync_status": "enviado",
            "jira_issue_key": "QA-123",
            "jira_issue_url": "https://jira.exemplo.local/browse/QA-123",
            "jira_issue_status": "To Do",
            "assignee": "time_qa",
            "priority": "alta",
            "notes": "Ticket criado manualmente.",
        },
    )

    assert saved["workflow_status"] == "enviado_para_jira"
    assert saved["jira_sync_status"] == "enviado"
    assert saved["jira_issue_key"] == "QA-123"
    assert saved["priority"] == "alta"

    persisted = json.loads((report_dir / CONTROL_FILENAME).read_text(encoding="utf-8"))
    assert persisted["jira_issue_url"] == "https://jira.exemplo.local/browse/QA-123"

    records = list_failure_records(tmp_path)
    assert records[0]["jira_issue_key"] == "QA-123"
    assert records[0]["workflow_status"] == "enviado_para_jira"
