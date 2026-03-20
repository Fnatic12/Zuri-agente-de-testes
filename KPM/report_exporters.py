from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from KPM.paths import ensure_reports_dir


def make_report_dir(category: str, test_name: str, generated_at: str) -> Path:
    safe_stamp = generated_at.replace(":", "-")
    out_dir = ensure_reports_dir() / category / test_name / safe_stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def export_json(report: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "failure_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_markdown(report: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "failure_report.md"
    radio_log = report.get("radio_log") or {}
    lines = [
        f"# Failure Report - {report['test']['category']}/{report['test']['name']}",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "## Precondition",
        report["precondition"],
        "",
        "## Short text",
        report["short_text"],
        "",
        "## Operation steps",
    ]
    lines.extend(f"- {step}" for step in report["operation_steps"])
    lines.extend(
        [
            "",
            "## Test Result",
            report["test_result"],
            "",
            "## Expected Result",
            report["expected_result"],
            "",
            "## Actual Results",
            report["actual_results"],
            "",
            "## Radio Log",
            radio_log.get("summary", "Nenhum log de radio registrado."),
            "",
            "## Occurrence Rate",
            report["occurrence_rate"]["label"],
            "",
            "## Recovery Conditions",
            report["recovery_conditions"],
            "",
            "## Bug Occurrence Time",
            f"Timestamp: {report['bug_occurrence_time']['first_failure_timestamp']}",
            f"Elapsed from start: {report['bug_occurrence_time']['elapsed_seconds_from_start']}s",
            "",
            "## Version Information",
        ]
    )
    for key, value in report["version_information"].items():
        lines.append(f"- {key}: {value}")
    if radio_log.get("capture_dir"):
        lines.extend(
            [
                "",
                "### Radio Log Details",
                f"- status: {radio_log.get('status')}",
                f"- capture_dir: {radio_log.get('capture_dir')}",
                f"- sequence: {radio_log.get('sequence') or '-'}",
                f"- error: {radio_log.get('error') or '-'}",
            ]
        )
    if radio_log.get("files"):
        lines.extend(["", "### Radio Log Files"])
        lines.extend(f"- {item}" for item in radio_log["files"])
    lines.extend(["", "## Failed Steps"])
    for step in report["failed_steps"]:
        lines.append(
            f"- Action {step['action_id']} | {step['action_type']} | "
            f"similarity={step['similarity']:.3f} | {step['status']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def export_csv(report: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "failure_report.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
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
        )
        writer.writerow(
            [
                report["precondition"],
                report["short_text"],
                " | ".join(report["operation_steps"]),
                report["test_result"],
                report["expected_result"],
                report["actual_results"],
                report.get("radio_log", {}).get("summary"),
                report["occurrence_rate"]["label"],
                report["recovery_conditions"],
                report["bug_occurrence_time"]["first_failure_timestamp"],
                json.dumps(report["version_information"], ensure_ascii=False),
            ]
        )
    return path
