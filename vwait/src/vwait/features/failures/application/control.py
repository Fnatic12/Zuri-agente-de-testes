from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..domain.enums import CONTROL_FILENAME
from ..domain.models import JsonDict
from ..domain.status_rules import clean_text, normalize_failure_control


def _load_optional_json(path: Path) -> JsonDict:
    if not path.exists() or not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, payload: JsonDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def control_file_path(report_dir: str | Path) -> Path:
    return Path(report_dir) / CONTROL_FILENAME


def load_failure_control(report_dir: str | Path, report: JsonDict) -> JsonDict:
    return normalize_failure_control(_load_optional_json(control_file_path(report_dir)), report)


def update_failure_control(report_dir: str | Path, report: JsonDict, updates: JsonDict) -> JsonDict:
    path = control_file_path(report_dir)
    current = load_failure_control(report_dir, report)
    merged = {**current, **(updates or {})}
    merged["updated_at"] = datetime.now().isoformat()
    normalized = normalize_failure_control(merged, report)
    _atomic_write_json(path, normalized)
    return normalized


def _build_record(report_path: Path) -> JsonDict | None:
    report = _load_optional_json(report_path)
    if not report:
        return None

    report_dir = report_path.parent
    control = load_failure_control(report_dir, report)
    test_payload = report.get("test") or {}
    summary = report.get("summary") or {}
    dashboard_summary = report.get("dashboard_summary") or {}
    radio_log = report.get("radio_log") or {}

    category = clean_text(test_payload.get("category"))
    test_name = clean_text(test_payload.get("name"))
    generated_at = clean_text(report.get("generated_at"))
    record_id = f"{category}/{test_name}/{generated_at}"

    return {
        "record_id": record_id,
        "category": category,
        "test_name": test_name,
        "generated_at": generated_at,
        "short_text": clean_text(report.get("short_text")),
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
        "resultado_final": clean_text(dashboard_summary.get("resultado_final") or summary.get("status")),
        "log_capture_status": clean_text(radio_log.get("status") or dashboard_summary.get("log_capture_status")),
        "report_dir": str(report_dir.resolve()),
        "report_json_path": str(report_path.resolve()),
        "report_markdown_path": str((report_dir / "failure_report.md").resolve()),
        "report_csv_path": str((report_dir / "failure_report.csv").resolve()),
        "test_dir": clean_text(test_payload.get("test_dir")),
        "report": report,
        "control": control,
    }


def _iter_report_paths(reports_root: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(reports_root, (str, Path)):
        candidate_roots = [Path(reports_root)]
    else:
        candidate_roots = [Path(root) for root in reports_root]

    report_paths: list[Path] = []
    seen_paths: set[str] = set()
    for root in candidate_roots:
        if not root.exists() or not root.is_dir():
            continue
        for report_path in root.rglob("failure_report.json"):
            key = str(report_path.resolve())
            if key in seen_paths:
                continue
            seen_paths.add(key)
            report_paths.append(report_path)
    return report_paths


def list_failure_records(reports_root: str | Path | Iterable[str | Path]) -> list[JsonDict]:
    records: list[JsonDict] = []
    seen_record_ids: set[str] = set()
    for report_path in _iter_report_paths(reports_root):
        record = _build_record(report_path)
        if record:
            record_id = clean_text(record.get("record_id"))
            if record_id in seen_record_ids:
                continue
            seen_record_ids.add(record_id)
            records.append(record)

    records.sort(
        key=lambda item: (
            clean_text(item.get("generated_at")),
            clean_text(item.get("record_id")),
        ),
        reverse=True,
    )
    return records
