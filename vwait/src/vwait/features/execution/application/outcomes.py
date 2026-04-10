from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Callable


FinalizeStatusFn = Callable[..., None]
CaptureLogsFn = Callable[[str, str, str | None, str | None], dict[str, Any]]
GenerateReportFn = Callable[[str, str, str, float | None], dict[str, Any]]
MessageFn = Callable[[str, str], None]


def sanitize_action_payload(
    payload: dict[str, Any],
    *,
    is_missing: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    is_missing = is_missing or (lambda value: value is None)
    return {
        key: (None if is_missing(value) else value)
        for key, value in payload.items()
    }


def build_action_outcome(
    action_id: int,
    action_type: str,
    action_payload: dict[str, Any],
    screenshot_rel: str,
    expected_frame_rel: str,
    similarity: float,
    duration_s: float,
    *,
    threshold: float,
    timestamp_fn: Callable[[], str] | None = None,
) -> dict[str, Any]:
    timestamp_fn = timestamp_fn or (lambda: datetime.now().isoformat())
    status = "OK" if similarity >= threshold else "Divergente"
    return {
        "status": status,
        "divergent": status != "OK",
        "log_record": {
            "id": action_id,
            "timestamp": timestamp_fn(),
            "acao": action_type,
            "coordenadas": dict(action_payload),
            "screenshot": screenshot_rel,
            "frame_esperado": expected_frame_rel,
            "similaridade": similarity,
            "status": status,
            "duracao": duration_s,
        },
    }


def resolve_execution_final_result(has_divergence: bool) -> tuple[str, str | None]:
    if has_divergence:
        return "reprovado", "divergencia_visual"
    return "aprovado", None


def conclude_execution_flow(
    bancada_key: str,
    categoria: str,
    teste_nome: str,
    serial: str | None,
    final_status: str,
    result_label: str,
    *,
    motivo: str | None = None,
    capture_logs: bool = False,
    log_path: str,
    similarity_threshold: float,
    status_dir: str,
    finalize_status: FinalizeStatusFn,
    capture_logs_fn: CaptureLogsFn,
    generate_report_fn: GenerateReportFn,
    emit_message: MessageFn | None = None,
) -> dict[str, Any]:
    emit_message = emit_message or (lambda _message, _color: None)

    capture_status = "nao_necessario"
    capture_dir = None
    capture_error = None
    capture_sequence = None
    failure_report_status = "nao_gerado"
    failure_report_dir = None
    failure_report_json = None
    failure_report_markdown = None
    failure_report_csv = None
    failure_report_short_text = None
    failure_report_generated_at = None
    failure_report_error = None

    if capture_logs:
        emit_message("🧾 Falha detectada — iniciando captura de logs da peca...", "yellow")
        try:
            finalize_status(
                bancada_key,
                categoria,
                teste_nome,
                resultado="coletando_logs",
                motivo=motivo,
                resultado_final=result_label,
                log_capture_status="executando",
            )
        except Exception as exc:
            emit_message(
                f"⚠️ Nao foi possivel marcar status de coleta de logs: {exc}",
                "yellow",
            )

        capture_result = capture_logs_fn(
            categoria,
            teste_nome,
            serial,
            motivo or result_label,
        )
        capture_status = capture_result.get("status") or "falha"
        capture_dir = capture_result.get("artifact_dir")
        capture_error = capture_result.get("error")
        sequence_path = capture_result.get("sequence_path")
        if sequence_path:
            if sequence_path == "default_auto_capture":
                capture_sequence = sequence_path
            else:
                try:
                    capture_sequence = os.path.relpath(sequence_path, status_dir)
                except Exception:
                    capture_sequence = sequence_path

        if capture_status == "capturado":
            emit_message(
                f"✅ Logs da peca capturados em Data/{categoria}/{teste_nome}/{capture_dir}",
                "green",
            )
        elif capture_status == "sem_artefatos":
            emit_message(
                f"⚠️ Nenhum log novo encontrado apos a falha. Pasta gerada: Data/{categoria}/{teste_nome}/{capture_dir}",
                "yellow",
            )
        elif capture_status == "sem_roteiro":
            emit_message(
                f"⚠️ Falha detectada, mas sem roteiro de captura configurado: {capture_error}",
                "yellow",
            )
        else:
            emit_message(f"❌ Captura de logs falhou: {capture_error}", "red")

    if result_label == "reprovado":
        report_result = generate_report_fn(
            categoria,
            teste_nome,
            log_path,
            similarity_threshold,
        )
        failure_report_status = report_result.get("status") or "falha"
        failure_report_dir = report_result.get("report_dir")
        failure_report_json = report_result.get("json_path")
        failure_report_markdown = report_result.get("markdown_path")
        failure_report_csv = report_result.get("csv_path")
        failure_report_short_text = report_result.get("short_text")
        failure_report_generated_at = report_result.get("generated_at")
        failure_report_error = report_result.get("error")

        if failure_report_status == "gerado":
            emit_message(
                f"📄 Relatorio estruturado de falha gerado em {failure_report_dir}",
                "green",
            )
        else:
            emit_message(
                f"⚠️ Nao foi possivel gerar relatorio estruturado: {failure_report_error}",
                "yellow",
            )

    try:
        finalize_status(
            bancada_key,
            categoria,
            teste_nome,
            resultado=final_status,
            motivo=motivo,
            resultado_final=result_label,
            log_capture_status=capture_status,
            log_capture_dir=capture_dir,
            log_capture_error=capture_error,
            log_capture_sequence=capture_sequence,
            failure_report_status=failure_report_status,
            failure_report_dir=failure_report_dir,
            failure_report_json=failure_report_json,
            failure_report_markdown=failure_report_markdown,
            failure_report_csv=failure_report_csv,
            failure_report_short_text=failure_report_short_text,
            failure_report_generated_at=failure_report_generated_at,
            failure_report_error=failure_report_error,
        )
    except Exception as exc:
        emit_message(f"⚠️ Falha ao atualizar status final: {exc}", "yellow")

    return {
        "log_capture_status": capture_status,
        "log_capture_dir": capture_dir,
        "log_capture_error": capture_error,
        "log_capture_sequence": capture_sequence,
        "failure_report_status": failure_report_status,
        "failure_report_dir": failure_report_dir,
        "failure_report_json": failure_report_json,
        "failure_report_markdown": failure_report_markdown,
        "failure_report_csv": failure_report_csv,
        "failure_report_short_text": failure_report_short_text,
        "failure_report_generated_at": failure_report_generated_at,
        "failure_report_error": failure_report_error,
    }


__all__ = [
    "build_action_outcome",
    "conclude_execution_flow",
    "resolve_execution_final_result",
    "sanitize_action_payload",
]
