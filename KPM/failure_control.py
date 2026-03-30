from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from KPM.paths import REPORTS_DIR


CONTROL_FILENAME = "failure_control.json"
WORKFLOW_STATUS_OPTIONS = (
    "novo",
    "triagem",
    "pronto_para_jira",
    "enviado_para_jira",
    "em_correcao",
    "resolvido",
    "descartado",
)
JIRA_SYNC_STATUS_OPTIONS = (
    "nao_enviado",
    "pronto_para_envio",
    "enviado",
    "erro",
)
PRIORITY_OPTIONS = ("baixa", "media", "alta", "critica")
_RESOLVED_ISSUE_STATUS_MARKERS = (
    "done",
    "closed",
    "resolved",
    "resolvido",
    "fechado",
    "encerrado",
    "concluido",
    "concluído",
    "homologado",
    "finalizado",
)
_DISCARDED_ISSUE_STATUS_MARKERS = (
    "descartado",
    "cancelado",
    "cancelled",
    "duplicado",
    "duplicate",
    "won't fix",
    "wont fix",
    "won't do",
    "wont do",
    "rejected",
    "rejeitado",
    "invalid",
    "inválido",
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_status_token(value: Any) -> str:
    text = _clean_text(value).lower()
    text = text.replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def _classify_issue_status(value: Any) -> str:
    token = _normalize_status_token(value)
    if not token:
        return ""
    if any(marker in token for marker in _DISCARDED_ISSUE_STATUS_MARKERS):
        return "discarded"
    if any(marker in token for marker in _RESOLVED_ISSUE_STATUS_MARKERS):
        return "resolved"
    return "opened"


def _derive_tracking_statuses(merged: dict[str, Any], base: dict[str, Any]) -> None:
    workflow_status = _clean_text(merged.get("workflow_status")).lower()
    jira_sync_status = _clean_text(merged.get("jira_sync_status")).lower()
    jira_issue_key = _clean_text(merged.get("jira_issue_key"))
    jira_issue_url = _clean_text(merged.get("jira_issue_url"))
    jira_issue_status = _clean_text(merged.get("jira_issue_status"))

    issue_status_bucket = _classify_issue_status(jira_issue_status)
    has_opened_ticket = bool(jira_issue_key or jira_issue_url or issue_status_bucket)

    if issue_status_bucket == "discarded":
        merged["workflow_status"] = "descartado"
        merged["jira_sync_status"] = "enviado"
        return

    if issue_status_bucket == "resolved":
        merged["workflow_status"] = "resolvido"
        merged["jira_sync_status"] = "enviado"
        return

    if has_opened_ticket:
        merged["jira_sync_status"] = "enviado"
        if workflow_status in {
            "",
            base["workflow_status"],
            "novo",
            "triagem",
            "pronto_para_jira",
        }:
            merged["workflow_status"] = "enviado_para_jira"
        return

    if jira_sync_status == "enviado" and workflow_status in {
        "",
        base["workflow_status"],
        "novo",
        "triagem",
        "pronto_para_jira",
    }:
        merged["workflow_status"] = "enviado_para_jira"


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def control_file_path(report_dir: str | Path) -> Path:
    return Path(report_dir) / CONTROL_FILENAME


def _default_control(report: dict[str, Any]) -> dict[str, Any]:
    stamp = _clean_text(report.get("generated_at")) or datetime.now().isoformat()
    return {
        "workflow_status": "novo",
        "jira_sync_status": "nao_enviado",
        "jira_issue_key": "",
        "jira_issue_url": "",
        "jira_issue_status": "",
        "assignee": "",
        "priority": "media",
        "root_cause": "",
        "notes": "",
        "created_at": stamp,
        "updated_at": stamp,
    }


def normalize_failure_control(payload: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    base = _default_control(report)
    merged = {**base, **(payload or {})}

    workflow_status = _clean_text(merged.get("workflow_status")).lower()
    jira_sync_status = _clean_text(merged.get("jira_sync_status")).lower()
    priority = _clean_text(merged.get("priority")).lower()

    merged["workflow_status"] = workflow_status if workflow_status in WORKFLOW_STATUS_OPTIONS else base["workflow_status"]
    merged["jira_sync_status"] = (
        jira_sync_status if jira_sync_status in JIRA_SYNC_STATUS_OPTIONS else base["jira_sync_status"]
    )
    merged["priority"] = priority if priority in PRIORITY_OPTIONS else base["priority"]

    for key in (
        "jira_issue_key",
        "jira_issue_url",
        "jira_issue_status",
        "assignee",
        "root_cause",
        "notes",
        "created_at",
        "updated_at",
    ):
        merged[key] = _clean_text(merged.get(key))

    _derive_tracking_statuses(merged, base)

    if not merged["created_at"]:
        merged["created_at"] = base["created_at"]
    if not merged["updated_at"]:
        merged["updated_at"] = merged["created_at"]
    return merged


def load_failure_control(report_dir: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    return normalize_failure_control(_load_optional_json(control_file_path(report_dir)), report)


def update_failure_control(report_dir: str | Path, report: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    path = control_file_path(report_dir)
    current = load_failure_control(report_dir, report)
    merged = {**current, **(updates or {})}
    merged["updated_at"] = datetime.now().isoformat()
    normalized = normalize_failure_control(merged, report)
    _atomic_write_json(path, normalized)
    return normalized


def _build_record(report_path: Path) -> dict[str, Any] | None:
    report = _load_optional_json(report_path)
    if not report:
        return None

    report_dir = report_path.parent
    control = load_failure_control(report_dir, report)
    test_payload = report.get("test") or {}
    summary = report.get("summary") or {}
    dashboard_summary = report.get("dashboard_summary") or {}
    radio_log = report.get("radio_log") or {}

    category = _clean_text(test_payload.get("category"))
    test_name = _clean_text(test_payload.get("name"))
    generated_at = _clean_text(report.get("generated_at"))
    record_id = f"{category}/{test_name}/{generated_at}"

    return {
        "record_id": record_id,
        "category": category,
        "test_name": test_name,
        "generated_at": generated_at,
        "short_text": _clean_text(report.get("short_text")),
        "workflow_status": control["workflow_status"],
        "jira_sync_status": control["jira_sync_status"],
        "jira_issue_key": control["jira_issue_key"],
        "jira_issue_url": control["jira_issue_url"],
        "jira_issue_status": control["jira_issue_status"],
        "assignee": control["assignee"],
        "priority": control["priority"],
        "root_cause": control["root_cause"],
        "notes": control["notes"],
        "created_at": control["created_at"],
        "updated_at": control["updated_at"],
        "failed_actions": int(summary.get("failed_actions", 0) or 0),
        "total_actions": int(summary.get("total_actions", 0) or 0),
        "resultado_final": _clean_text(dashboard_summary.get("resultado_final") or summary.get("status")),
        "log_capture_status": _clean_text(radio_log.get("status") or dashboard_summary.get("log_capture_status")),
        "report_dir": str(report_dir.resolve()),
        "report_json_path": str(report_path.resolve()),
        "report_markdown_path": str((report_dir / "failure_report.md").resolve()),
        "report_csv_path": str((report_dir / "failure_report.csv").resolve()),
        "test_dir": _clean_text(test_payload.get("test_dir")),
        "report": report,
        "control": control,
    }


def list_failure_records(reports_root: str | Path = REPORTS_DIR) -> list[dict[str, Any]]:
    root = Path(reports_root)
    if not root.exists() or not root.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for report_path in root.rglob("failure_report.json"):
        record = _build_record(report_path)
        if record:
            records.append(record)

    records.sort(
        key=lambda item: (
            _clean_text(item.get("generated_at")),
            _clean_text(item.get("record_id")),
        ),
        reverse=True,
    )
    return records
