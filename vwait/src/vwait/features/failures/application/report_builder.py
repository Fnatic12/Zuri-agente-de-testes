from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..paths import DATA_DIR, test_dir


def fix_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    replacements = {
        "âŒ": "❌",
        "âœ…": "✅",
        "âš ï¸": "⚠️",
        "ðŸ›‘": "🛑",
        "ðŸ‘‰": "👉",
    }
    for raw, clean in replacements.items():
        text = text.replace(raw, clean)
    try:
        if any(token in text for token in ("Ã", "â", "�")):
            text = text.encode("latin1", "ignore").decode("utf-8", "ignore")
    except Exception:
        pass
    return text.strip()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return json.load(handle)


def find_execution_logs(data_dir: Path | None = None) -> list[tuple[str, str, Path]]:
    logs: list[tuple[str, str, Path]] = []
    root_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    if not root_dir.exists():
        return logs

    for category_dir in root_dir.iterdir():
        if not category_dir.is_dir():
            continue
        for test_path in category_dir.iterdir():
            log_path = test_path / "execucao_log.json"
            if test_path.is_dir() and log_path.exists():
                logs.append((category_dir.name, test_path.name, log_path))
    return sorted(logs)


def _is_failed_step(step: dict[str, Any], similarity_threshold: float) -> bool:
    status = fix_text(step.get("status", "")).lower()
    similarity = float(step.get("similaridade", 1.0) or 0.0)
    return "divergente" in status or "fail" in status or similarity < similarity_threshold


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def _guess_status_payload(test_path: Path) -> dict[str, Any]:
    candidates = sorted(test_path.glob("status_*.json"))
    if not candidates:
        return {}
    raw_payload = _load_optional_json(candidates[0])
    serial = candidates[0].stem.replace("status_", "", 1)

    payload: dict[str, Any] = {}
    nested = raw_payload.get(serial) if isinstance(raw_payload, dict) else None
    if isinstance(nested, dict):
        payload.update(nested)

    if isinstance(raw_payload, dict):
        for key, value in raw_payload.items():
            if isinstance(value, dict):
                continue
            payload.setdefault(key, value)

    payload.setdefault("_source_file", str(candidates[0]))
    payload.setdefault("serial", serial)
    return payload


def _build_precondition(category: str, test_name: str, test_meta: dict[str, Any], context: dict[str, Any]) -> str:
    if test_meta.get("precondition"):
        return fix_text(test_meta["precondition"])
    serial = fix_text(context.get("serial") or context.get("adb_serial") or "desconhecido")
    return (
        f"Teste automatizado `{category}/{test_name}` iniciado em bancada `{serial}` "
        "com dataset previamente gravado e baseline visual disponivel."
    )


def _build_short_text(category: str, test_name: str, failed_steps: list[dict[str, Any]]) -> str:
    first = failed_steps[0]
    action_id = first.get("action_id")
    action_type = fix_text(first.get("action_type", "acao"))
    similarity = float(first.get("similarity", 0.0) or 0.0)
    return (
        f"{category.upper()} - falha visual na acao {action_id} "
        f"({action_type}) do teste {test_name} com similaridade {similarity:.2f}"
    )


def _build_operation_steps(events: list[dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    for event in events:
        action_id = event.get("id")
        action_type = fix_text(event.get("acao", "acao"))
        coords = event.get("coordenadas") or {}
        x = coords.get("x")
        y = coords.get("y")
        steps.append(f"Acao {action_id}: {action_type} em ({x}, {y})")
    return steps


def _build_actual_results(failed_steps: list[dict[str, Any]]) -> str:
    lines = []
    for step in failed_steps:
        lines.append(
            f"Acao {step['action_id']} retornou '{step['status']}' "
            f"com similaridade {step['similarity']:.3f}. "
            f"Screenshot atual: {step['actual_screenshot']} | esperado: {step['expected_screenshot']}."
        )
    return "\n".join(lines)


def _build_dashboard_summary(
    events: list[dict[str, Any]],
    failed_steps: list[dict[str, Any]],
    status_payload: dict[str, Any],
) -> dict[str, Any]:
    total_actions = len(events)
    failed_actions = len(failed_steps)
    passed_actions = max(0, total_actions - failed_actions)

    similarities = []
    for event in events:
        try:
            similarities.append(float(event.get("similaridade", 0.0) or 0.0))
        except Exception:
            continue

    average_similarity = round(sum(similarities) / len(similarities), 4) if similarities else 0.0
    return {
        "total_actions": total_actions,
        "passed_actions": passed_actions,
        "failed_actions": failed_actions,
        "average_similarity": average_similarity,
        "resultado_final": fix_text(status_payload.get("resultado_final") or "reprovado").lower(),
        "log_capture_status": fix_text(status_payload.get("log_capture_status") or "nao_necessario").lower(),
    }


def _build_test_result(
    failed_steps: list[dict[str, Any]],
    dashboard_summary: dict[str, Any],
) -> str:
    first_failure = failed_steps[0]
    return (
        f"Teste reprovado com {dashboard_summary['failed_actions']} divergencia(s) visual(is) "
        f"em {dashboard_summary['total_actions']} acao(oes). "
        f"A primeira falha ocorreu na acao {first_failure['action_id']} "
        f"({first_failure['action_type']}) com similaridade {first_failure['similarity']:.3f}."
    )


def _build_expected_result(
    failed_steps: list[dict[str, Any]],
    similarity_threshold: float,
) -> str:
    expected_steps = [
        f"Acao {step['action_id']} deveria concluir com status OK usando o baseline {step['expected_screenshot']}."
        for step in failed_steps
    ]
    return (
        f"O teste deveria terminar aprovado, sem divergencias visuais, "
        f"com similaridade minima de {similarity_threshold:.2f} em cada validacao comparada.\n"
        + "\n".join(expected_steps)
    )


def _build_occurrence_rate(context: dict[str, Any]) -> dict[str, Any]:
    if context.get("occurrence_rate"):
        return context["occurrence_rate"]
    return {
        "label": "1/1 execucao falhou",
        "failed_runs": 1,
        "total_runs": 1,
        "rerun_policy": "nao configurada",
    }


def _build_recovery_conditions(context: dict[str, Any]) -> str:
    if context.get("recovery_conditions"):
        return fix_text(context["recovery_conditions"])
    return "Nenhuma rotina formal de recuperacao registrada. A execucao seguiu apos detectar a divergencia."


def _build_version_information(context: dict[str, Any], status_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "adb_serial": fix_text(
            context.get("serial")
            or context.get("adb_serial")
            or status_payload.get("serial")
            or "desconhecido"
        ),
        "device_name": fix_text(context.get("device_name") or "nao coletado"),
        "system_build": fix_text(context.get("system_build") or "nao coletado"),
        "sw_version": fix_text(context.get("sw_version") or "nao coletado"),
        "hw_version": fix_text(context.get("hw_version") or "nao coletado"),
        "app_version": fix_text(context.get("app_version") or "nao coletado"),
    }


def _relative_file_list(root_dir: Path, limit: int = 40) -> list[str]:
    if not root_dir.exists() or not root_dir.is_dir():
        return []
    files: list[str] = []
    for path in sorted(root_dir.rglob("*")):
        if not path.is_file():
            continue
        files.append(str(path.relative_to(root_dir)).replace("\\", "/"))
        if len(files) >= limit:
            break
    return files


def _build_radio_log(test_path: Path, status_payload: dict[str, Any]) -> dict[str, Any]:
    capture_status = fix_text(status_payload.get("log_capture_status") or "nao_necessario").lower()
    capture_dir_rel = fix_text(status_payload.get("log_capture_dir"))
    capture_error = fix_text(status_payload.get("log_capture_error"))
    capture_sequence = fix_text(status_payload.get("log_capture_sequence"))

    capture_dir = test_path / capture_dir_rel if capture_dir_rel else None
    metadata_path = capture_dir / "capture_metadata.json" if capture_dir else None
    metadata = _load_optional_json(metadata_path) if metadata_path else {}
    files = _relative_file_list(capture_dir) if capture_dir else []

    if capture_dir and capture_dir.exists():
        summary = (
            f"Captura de logs finalizada com status '{capture_status}' em {capture_dir}. "
            f"Foram indexados {len(files)} arquivo(s) principais para a falha."
        )
    elif capture_status == "nao_necessario":
        summary = "Nenhuma captura de logs foi necessaria para esta execucao."
    else:
        summary = (
            f"Captura de logs registrada com status '{capture_status}', "
            f"mas a pasta de artefatos nao foi localizada."
        )

    return {
        "status": capture_status,
        "capture_dir": str(capture_dir.resolve()) if capture_dir and capture_dir.exists() else "",
        "capture_dir_relative": capture_dir_rel,
        "metadata_path": str(metadata_path.resolve()) if metadata_path and metadata_path.exists() else "",
        "sequence": capture_sequence,
        "error": capture_error,
        "summary": summary,
        "metadata": metadata,
        "files": files,
    }


def build_failure_report(
    category: str,
    test_name: str,
    log_path: Path,
    similarity_threshold: float = 0.85,
    resolve_test_dir: Callable[[str, str], Path] | None = None,
) -> dict[str, Any] | None:
    raw_events = load_json(log_path)
    events = raw_events.get("execucao") if isinstance(raw_events, dict) else raw_events
    if not isinstance(events, list) or not events:
        return None

    resolver = resolve_test_dir or test_dir
    test_path = resolver(category, test_name)
    test_meta = _load_optional_json(test_path / "test_meta.json")
    context = _load_optional_json(test_path / "execution_context.json")
    status_payload = _guess_status_payload(test_path)

    failed_steps: list[dict[str, Any]] = []
    elapsed_until_failure = 0.0
    first_failure_elapsed = None

    for event in events:
        duration_s = float(event.get("duracao", 0.0) or 0.0)
        elapsed_until_failure += duration_s
        if not _is_failed_step(event, similarity_threshold):
            continue

        failed_step = {
            "action_id": event.get("id"),
            "action_type": fix_text(event.get("acao")),
            "timestamp": fix_text(event.get("timestamp")),
            "coordinates": event.get("coordenadas") or {},
            "actual_screenshot": str((test_path / fix_text(event.get("screenshot"))).resolve()),
            "expected_screenshot": str((test_path / fix_text(event.get("frame_esperado"))).resolve()),
            "similarity": float(event.get("similaridade", 0.0) or 0.0),
            "status": fix_text(event.get("status")),
            "duration_s": duration_s,
        }
        failed_steps.append(failed_step)
        if first_failure_elapsed is None:
            first_failure_elapsed = round(elapsed_until_failure, 2)

    if not failed_steps:
        return None

    first_failure = failed_steps[0]
    report_time = datetime.now().isoformat()
    operation_steps = _build_operation_steps(events)
    dashboard_summary = _build_dashboard_summary(events, failed_steps, status_payload)
    test_result = _build_test_result(failed_steps, dashboard_summary)
    expected_result = _build_expected_result(failed_steps, similarity_threshold)
    radio_log = _build_radio_log(test_path, status_payload)

    report = {
        "schema_version": "1.0",
        "report_type": "failure_report",
        "generated_at": report_time,
        "test": {
            "category": category,
            "name": test_name,
            "test_dir": str(test_path.resolve()),
            "execution_log": str(log_path.resolve()),
        },
        "summary": {
            "status": "FAIL",
            "total_actions": len(events),
            "failed_actions": len(failed_steps),
            "first_failed_action_id": first_failure["action_id"],
            "first_failed_similarity": first_failure["similarity"],
        },
        "dashboard_summary": dashboard_summary,
        "precondition": _build_precondition(category, test_name, test_meta, context | status_payload),
        "short_text": _build_short_text(category, test_name, failed_steps),
        "operation_steps": operation_steps,
        "test_result": test_result,
        "expected_result": expected_result,
        "actual_results": _build_actual_results(failed_steps),
        "radio_log": radio_log,
        "occurrence_rate": _build_occurrence_rate(context),
        "recovery_conditions": _build_recovery_conditions(context),
        "bug_occurrence_time": {
            "first_failure_timestamp": first_failure["timestamp"],
            "elapsed_seconds_from_start": first_failure_elapsed,
        },
        "version_information": _build_version_information(context, status_payload),
        "attachments": {
            "failed_screenshots": [step["actual_screenshot"] for step in failed_steps],
            "expected_screenshots": [step["expected_screenshot"] for step in failed_steps],
            "result_image": str((test_path / "resultado_final.png").resolve()),
            "radio_log_dir": radio_log["capture_dir"],
        },
        "failed_steps": failed_steps,
        "source_files": {
            "test_meta": str((test_path / "test_meta.json").resolve()),
            "execution_context": str((test_path / "execution_context.json").resolve()),
            "status_file": fix_text(status_payload.get("_source_file")),
        },
    }
    return report
