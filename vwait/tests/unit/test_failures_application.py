from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures.domain.enums import CONTROL_FILENAME
from vwait.features.failures.application.build_board_payload import (
    LANE_NEW,
    LANE_RESOLVED,
    LANE_SENT,
    build_board_payload,
    lane_from_record,
)
from vwait.features.failures.application.create_jira_issue import create_jira_issue_for_record
from vwait.features.failures.application.sync_jira_status import sync_jira_statuses
from vwait.features.failures.integrations.jira.models import JiraCreateIssueResult


class _FakeJiraSettings:
    is_configured = True
    missing_fields = ()


class _FakeCreateJiraService:
    def __init__(self) -> None:
        self.settings = _FakeJiraSettings()
        self.last_draft = None

    def build_issue_draft(self, **kwargs):
        self.last_draft = kwargs
        return kwargs

    def create_issue(self, draft):
        return JiraCreateIssueResult(
            issue_id="1001",
            issue_key="IK-321",
            issue_url="https://jira.exemplo.com/browse/IK-321",
            attachment_names=tuple(draft.get("attachment_paths") or ()),
        )


class _FakeSyncJiraService:
    def __init__(self) -> None:
        self.settings = _FakeJiraSettings()

    def get_issue_status(self, issue_key: str) -> str:
        if issue_key == "IK-404":
            raise RuntimeError("nao encontrado")
        return "Done"

    def issue_browse_url(self, issue_key: str) -> str:
        return f"https://jira.exemplo.com/browse/{issue_key}"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_board_payload_routes_cards_to_expected_lanes():
    records = [
        {"record_id": "1", "category": "radio", "test_name": "a", "generated_at": "2026-04-09T10:00:00"},
        {
            "record_id": "2",
            "category": "radio",
            "test_name": "b",
            "generated_at": "2026-04-09T10:00:00",
            "workflow_status": "enviado_para_jira",
        },
        {
            "record_id": "3",
            "category": "radio",
            "test_name": "c",
            "generated_at": "2026-04-09T10:00:00",
            "workflow_status": "resolvido",
        },
    ]

    assert lane_from_record(records[0]) == LANE_NEW
    assert lane_from_record(records[1]) == LANE_SENT
    assert lane_from_record(records[2]) == LANE_RESOLVED

    payload = build_board_payload(records)
    lane_map = {item["id"]: item["items"] for item in payload}

    assert len(lane_map[LANE_NEW]) == 1
    assert len(lane_map[LANE_SENT]) == 1
    assert len(lane_map[LANE_RESOLVED]) == 1


def test_create_jira_issue_for_record_updates_failure_control(tmp_path):
    report_dir = tmp_path / "reports" / "radio" / "teste_a" / "2026-04-09T10-00-00"
    report = {
        "generated_at": "2026-04-09T10:00:00",
        "short_text": "Falha visual",
        "test": {"category": "radio", "name": "teste_a"},
    }
    _write_json(report_dir / "failure_report.json", report)
    record = {
        "record_id": "radio/teste_a/2026-04-09T10:00:00",
        "report_dir": str(report_dir),
        "report": report,
    }

    result = create_jira_issue_for_record(
        record,
        summary="Falha visual",
        description="Detalhes",
        labels=["vwait", "radio"],
        attachment_paths=["/tmp/a.txt"],
        priority="alta",
        assignee="victor",
        root_cause="Possivel regressao",
        notes="Validar bancada A",
        jira_issue_status="To Do",
        service=_FakeCreateJiraService(),
    )

    assert result.issue_key == "IK-321"
    persisted = json.loads((report_dir / CONTROL_FILENAME).read_text(encoding="utf-8"))
    assert persisted["workflow_status"] == "enviado_para_jira"
    assert persisted["jira_issue_key"] == "IK-321"
    assert persisted["priority"] == "alta"
    assert persisted["assignee"] == "victor"


def test_sync_jira_statuses_updates_issue_metadata(tmp_path):
    report_dir = tmp_path / "reports" / "radio" / "teste_b" / "2026-04-09T11-00-00"
    report = {
        "generated_at": "2026-04-09T11:00:00",
        "short_text": "Falha com ticket",
        "test": {"category": "radio", "name": "teste_b"},
    }
    _write_json(report_dir / "failure_report.json", report)
    record = {
        "record_id": "radio/teste_b/2026-04-09T11:00:00",
        "report_dir": str(report_dir),
        "report": report,
        "jira_issue_key": "IK-999",
    }

    result = sync_jira_statuses([record], service=_FakeSyncJiraService())

    assert result["total"] == 1
    assert result["updated"] == 1
    persisted = json.loads((report_dir / CONTROL_FILENAME).read_text(encoding="utf-8"))
    assert persisted["jira_issue_status"] == "Done"
    assert persisted["jira_issue_url"] == "https://jira.exemplo.com/browse/IK-999"
