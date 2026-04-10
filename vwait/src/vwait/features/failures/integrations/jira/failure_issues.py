from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


MAX_FAILURE_JIRA_DESCRIPTION_CHARS = 12000


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truncate(text: str, max_chars: int = MAX_FAILURE_JIRA_DESCRIPTION_CHARS) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    half = max_chars // 2
    return f"{normalized[:half]}\n\n... [conteudo truncado para Jira] ...\n\n{normalized[-half:]}"


def build_failure_issue_summary(record: Mapping[str, Any]) -> str:
    category = _clean(record.get("category")) or "categoria"
    test_name = _clean(record.get("test_name")) or "teste"
    short_text = _clean(record.get("short_text"))
    prefix = f"[Falha] {category}/{test_name}"
    if short_text:
        return " ".join(f"{prefix} - {short_text}".split())[:255]
    return prefix[:255]


def build_failure_issue_labels(record: Mapping[str, Any]) -> tuple[str, ...]:
    labels = [
        "vwait",
        "falha",
        _clean(record.get("category")),
        _clean(record.get("priority")),
    ]
    seen: set[str] = set()
    normalized: list[str] = []
    for item in labels:
        token = _clean(item)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return tuple(normalized)


def collect_failure_issue_attachments(record: Mapping[str, Any]) -> list[dict[str, str]]:
    attachment_candidates = [
        ("Relatorio JSON", _clean(record.get("report_json_path"))),
        ("Relatorio Markdown", _clean(record.get("report_markdown_path"))),
        ("Relatorio CSV", _clean(record.get("report_csv_path"))),
    ]

    report = record.get("report") or {}
    attachments = report.get("attachments") or {}
    attachment_candidates.append(("Imagem resultado", _clean(attachments.get("result_image"))))

    selected_failed = attachments.get("failed_screenshots") or []
    if isinstance(selected_failed, list):
        for idx, raw_path in enumerate(selected_failed[:3], start=1):
            attachment_candidates.append((f"Screenshot falha {idx}", _clean(raw_path)))

    existing: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for label, raw_path in attachment_candidates:
        if not raw_path or raw_path in seen_paths:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        seen_paths.add(raw_path)
        existing.append({"label": label, "path": str(path)})
    return existing


def build_failure_issue_description(
    record: Mapping[str, Any],
    *,
    root_cause: str = "",
    notes: str = "",
) -> str:
    report = record.get("report") or {}
    summary = report.get("summary") or {}
    occurrence = report.get("occurrence_rate") or {}
    bug_time = report.get("bug_occurrence_time") or {}
    version = report.get("version_information") or {}
    radio_log = report.get("radio_log") or {}
    failed_steps = report.get("failed_steps") or []

    failed_lines = []
    if isinstance(failed_steps, list):
        for item in failed_steps[:5]:
            if not isinstance(item, dict):
                continue
            action_id = _clean(item.get("action_id")) or "?"
            action_type = _clean(item.get("action_type")) or "acao"
            similarity = item.get("similarity")
            similarity_text = (
                f"{float(similarity):.3f}" if isinstance(similarity, (float, int)) else _clean(similarity)
            )
            status = _clean(item.get("status")) or "-"
            failed_lines.append(
                f"- acao {action_id} | tipo {action_type} | similaridade {similarity_text or '-'} | status {status}"
            )

    if not failed_lines:
        failed_lines.append("- Nenhum passo com falha detalhado no relatorio.")

    version_lines = [
        f"- adb_serial: {_clean(version.get('adb_serial')) or '-'}",
        f"- device_name: {_clean(version.get('device_name')) or '-'}",
        f"- system_build: {_clean(version.get('system_build')) or '-'}",
        f"- sw_version: {_clean(version.get('sw_version')) or '-'}",
        f"- hw_version: {_clean(version.get('hw_version')) or '-'}",
        f"- app_version: {_clean(version.get('app_version')) or '-'}",
    ]

    sections = [
        "\n".join(
            [
                "Contexto:",
                f"- record_id: {_clean(record.get('record_id')) or '-'}",
                f"- categoria: {_clean(record.get('category')) or '-'}",
                f"- teste: {_clean(record.get('test_name')) or '-'}",
                f"- gerado_em: {_clean(record.get('generated_at')) or '-'}",
                f"- prioridade local: {_clean(record.get('priority')) or '-'}",
                f"- resultado_final: {_clean(record.get('resultado_final')) or '-'}",
                f"- status_logs: {_clean(record.get('log_capture_status')) or '-'}",
            ]
        ),
        "Resumo executivo:\n" + (_clean(record.get("short_text")) or "Falha sem resumo."),
        "\n".join(
            [
                "Sinais da falha:",
                f"- total_actions: {_clean(summary.get('total_actions')) or '-'}",
                f"- failed_actions: {_clean(summary.get('failed_actions')) or '-'}",
                f"- first_failed_action_id: {_clean(summary.get('first_failed_action_id')) or '-'}",
                f"- first_failed_similarity: {_clean(summary.get('first_failed_similarity')) or '-'}",
                f"- occurrence: {_clean(occurrence.get('label')) or '-'}",
                f"- first_failure_timestamp: {_clean(bug_time.get('first_failure_timestamp')) or '-'}",
                f"- elapsed_seconds_from_start: {_clean(bug_time.get('elapsed_seconds_from_start')) or '-'}",
            ]
        ),
        "Pre-condicao:\n" + (_clean(report.get("precondition")) or "-"),
        "Resultado obtido:\n" + (_clean(report.get("actual_results")) or "-"),
        "Condicoes de recuperacao:\n" + (_clean(report.get("recovery_conditions")) or "-"),
        "Passos com falha:\n" + "\n".join(failed_lines),
        "Versao e ambiente:\n" + "\n".join(version_lines),
    ]

    radio_summary = _clean(radio_log.get("summary"))
    if radio_summary:
        sections.append("Resumo de logs/radio:\n" + radio_summary)

    effective_root_cause = _clean(root_cause) or _clean(record.get("root_cause"))
    if effective_root_cause:
        sections.append("Causa raiz:\n" + effective_root_cause)

    effective_notes = _clean(notes) or _clean(record.get("notes"))
    if effective_notes:
        sections.append("Notas internas:\n" + effective_notes)

    return _truncate("\n\n".join(section for section in sections if section.strip()))
