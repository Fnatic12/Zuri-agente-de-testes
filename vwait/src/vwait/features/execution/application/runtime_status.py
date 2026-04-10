from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable


LoadPayloadFn = Callable[[str, str, str], dict[str, Any]]
SaveStatusFn = Callable[[dict[str, Any], str, str], None]
TestRefFn = Callable[[str, str], str]


def initialize_runtime_status(
    bancada_key: str,
    categoria: str,
    teste_nome: str,
    total_acoes: int,
    *,
    load_payload: LoadPayloadFn,
    save_status: SaveStatusFn,
    test_ref_fn: TestRefFn,
    execution_start_times: dict[str, float],
    now_iso_fn: Callable[[], str] | None = None,
    now_ts_fn: Callable[[], float] | None = None,
) -> None:
    now_iso_fn = now_iso_fn or (lambda: datetime.now().isoformat())
    now_ts_fn = now_ts_fn or time.time
    agora = now_iso_fn()
    anterior = load_payload(categoria, teste_nome, bancada_key)
    execution_start_times[bancada_key] = now_ts_fn()
    save_status(
        {
            bancada_key: {
                "serial": bancada_key,
                "categoria": categoria,
                "teste": test_ref_fn(categoria, teste_nome),
                "status": "executando",
                "acoes_totais": int(total_acoes),
                "acoes_executadas": 0,
                "progresso": 0.0,
                "ultima_acao": "-",
                "ultima_acao_idx": 0,
                "ultima_acao_status": "-",
                "tempo_decorrido_s": 0.0,
                "inicio": anterior.get("inicio") or agora,
                "fim": None,
                "atualizado_em": agora,
                "resultados_ok": 0,
                "resultados_divergentes": 0,
                "similaridade_media": 0.0,
                "ultima_similaridade": None,
                "ultimo_screenshot": None,
                "resultado_final": "pendente",
                "log_capture_status": "nao_necessario",
                "log_capture_dir": None,
                "log_capture_error": None,
                "log_capture_sequence": None,
                "failure_report_status": "nao_gerado",
                "failure_report_dir": None,
                "failure_report_json": None,
                "failure_report_markdown": None,
                "failure_report_csv": None,
                "failure_report_short_text": None,
                "failure_report_generated_at": None,
                "failure_report_error": None,
            }
        },
        categoria,
        teste_nome,
    )


def update_runtime_status(
    bancada_key: str,
    categoria: str,
    teste_nome: str,
    total_acoes: int,
    executadas: int,
    ultima_acao: str,
    *,
    load_payload: LoadPayloadFn,
    save_status: SaveStatusFn,
    test_ref_fn: TestRefFn,
    execution_start_times: dict[str, float],
    status_resultado: str | None = None,
    similaridade: float | None = None,
    screenshot_rel: str | None = None,
    now_iso_fn: Callable[[], str] | None = None,
    now_ts_fn: Callable[[], float] | None = None,
) -> None:
    now_iso_fn = now_iso_fn or (lambda: datetime.now().isoformat())
    now_ts_fn = now_ts_fn or time.time
    anterior = load_payload(categoria, teste_nome, bancada_key)
    inicio = execution_start_times.get(bancada_key, now_ts_fn())
    tempo_decorrido = now_ts_fn() - inicio
    progresso = round(((executadas or 0) / max(total_acoes, 1)) * 100, 1)
    ok_count = int(anterior.get("resultados_ok", 0) or 0)
    divergente_count = int(anterior.get("resultados_divergentes", 0) or 0)
    if str(status_resultado).strip().lower() == "ok":
        ok_count += 1
    elif str(status_resultado).strip().lower() == "divergente":
        divergente_count += 1

    media_anterior = float(anterior.get("similaridade_media", 0.0) or 0.0)
    similaridade_media = media_anterior
    if similaridade is not None and int(executadas or 0) > 0:
        similaridade_media = (
            (media_anterior * max(int(executadas) - 1, 0)) + float(similaridade)
        ) / float(executadas)

    velocidade_acoes_min = 0.0
    if tempo_decorrido > 0 and int(executadas or 0) > 0:
        velocidade_acoes_min = round((float(executadas) / tempo_decorrido) * 60.0, 2)

    save_status(
        {
            bancada_key: {
                "serial": bancada_key,
                "categoria": categoria,
                "teste": test_ref_fn(categoria, teste_nome),
                "status": "executando",
                "acoes_totais": int(total_acoes),
                "acoes_executadas": int(executadas),
                "progresso": progresso,
                "ultima_acao": str(ultima_acao),
                "ultima_acao_idx": int(executadas),
                "ultima_acao_status": str(
                    status_resultado or anterior.get("ultima_acao_status") or "-"
                ),
                "tempo_decorrido_s": float(tempo_decorrido),
                "inicio": anterior.get("inicio") or now_iso_fn(),
                "fim": None,
                "atualizado_em": now_iso_fn(),
                "resultados_ok": ok_count,
                "resultados_divergentes": divergente_count,
                "similaridade_media": round(similaridade_media, 4)
                if similaridade is not None
                else round(float(anterior.get("similaridade_media", 0.0) or 0.0), 4),
                "ultima_similaridade": round(float(similaridade), 4)
                if similaridade is not None
                else anterior.get("ultima_similaridade"),
                "ultimo_screenshot": str(
                    screenshot_rel or anterior.get("ultimo_screenshot") or ""
                ),
                "velocidade_acoes_min": velocidade_acoes_min,
                "resultado_final": anterior.get("resultado_final") or "pendente",
                "log_capture_status": anterior.get("log_capture_status")
                or "nao_necessario",
                "log_capture_dir": anterior.get("log_capture_dir"),
                "log_capture_error": anterior.get("log_capture_error"),
                "log_capture_sequence": anterior.get("log_capture_sequence"),
                "failure_report_status": anterior.get("failure_report_status")
                or "nao_gerado",
                "failure_report_dir": anterior.get("failure_report_dir"),
                "failure_report_json": anterior.get("failure_report_json"),
                "failure_report_markdown": anterior.get("failure_report_markdown"),
                "failure_report_csv": anterior.get("failure_report_csv"),
                "failure_report_short_text": anterior.get("failure_report_short_text"),
                "failure_report_generated_at": anterior.get(
                    "failure_report_generated_at"
                ),
                "failure_report_error": anterior.get("failure_report_error"),
            }
        },
        categoria,
        teste_nome,
    )


def finalize_runtime_status(
    bancada_key: str,
    categoria: str,
    teste_nome: str,
    *,
    load_payload: LoadPayloadFn,
    save_status: SaveStatusFn,
    test_ref_fn: TestRefFn,
    resultado: str = "finalizado",
    motivo: str | None = None,
    resultado_final: str | None = None,
    log_capture_status: str | None = None,
    log_capture_dir: str | None = None,
    log_capture_error: str | None = None,
    log_capture_sequence: str | None = None,
    failure_report_status: str | None = None,
    failure_report_dir: str | None = None,
    failure_report_json: str | None = None,
    failure_report_markdown: str | None = None,
    failure_report_csv: str | None = None,
    failure_report_short_text: str | None = None,
    failure_report_generated_at: str | None = None,
    failure_report_error: str | None = None,
    now_iso_fn: Callable[[], str] | None = None,
) -> None:
    now_iso_fn = now_iso_fn or (lambda: datetime.now().isoformat())
    anterior = load_payload(categoria, teste_nome, bancada_key)
    agora = now_iso_fn()
    payload = {
        "serial": bancada_key,
        "categoria": categoria,
        "teste": anterior.get("teste") or test_ref_fn(categoria, teste_nome),
        "status": resultado,
        "acoes_totais": int(anterior.get("acoes_totais", 0) or 0),
        "acoes_executadas": int(anterior.get("acoes_executadas", 0) or 0),
        "progresso": float(anterior.get("progresso", 0.0) or 0.0),
        "ultima_acao": anterior.get("ultima_acao", "-"),
        "ultima_acao_idx": int(anterior.get("ultima_acao_idx", 0) or 0),
        "ultima_acao_status": anterior.get("ultima_acao_status", "-"),
        "tempo_decorrido_s": float(anterior.get("tempo_decorrido_s", 0.0) or 0.0),
        "inicio": anterior.get("inicio"),
        "fim": agora if resultado in {"finalizado", "erro"} else None,
        "atualizado_em": agora,
        "resultados_ok": int(anterior.get("resultados_ok", 0) or 0),
        "resultados_divergentes": int(anterior.get("resultados_divergentes", 0) or 0),
        "similaridade_media": round(float(anterior.get("similaridade_media", 0.0) or 0.0), 4),
        "ultima_similaridade": anterior.get("ultima_similaridade"),
        "ultimo_screenshot": anterior.get("ultimo_screenshot"),
        "velocidade_acoes_min": float(anterior.get("velocidade_acoes_min", 0.0) or 0.0),
        "resultado_final": resultado_final or anterior.get("resultado_final") or "pendente",
        "log_capture_status": log_capture_status or anterior.get("log_capture_status") or "nao_necessario",
        "log_capture_dir": log_capture_dir if log_capture_dir is not None else anterior.get("log_capture_dir"),
        "log_capture_error": log_capture_error if log_capture_error is not None else anterior.get("log_capture_error"),
        "log_capture_sequence": log_capture_sequence if log_capture_sequence is not None else anterior.get("log_capture_sequence"),
        "failure_report_status": failure_report_status or anterior.get("failure_report_status") or "nao_gerado",
        "failure_report_dir": failure_report_dir if failure_report_dir is not None else anterior.get("failure_report_dir"),
        "failure_report_json": failure_report_json if failure_report_json is not None else anterior.get("failure_report_json"),
        "failure_report_markdown": failure_report_markdown if failure_report_markdown is not None else anterior.get("failure_report_markdown"),
        "failure_report_csv": failure_report_csv if failure_report_csv is not None else anterior.get("failure_report_csv"),
        "failure_report_short_text": failure_report_short_text if failure_report_short_text is not None else anterior.get("failure_report_short_text"),
        "failure_report_generated_at": failure_report_generated_at if failure_report_generated_at is not None else anterior.get("failure_report_generated_at"),
        "failure_report_error": failure_report_error if failure_report_error is not None else anterior.get("failure_report_error"),
        "erro_motivo": motivo,
    }
    if resultado in {"finalizado", "coletando_logs"} and payload["acoes_totais"] > 0:
        payload["progresso"] = 100.0
    save_status({bancada_key: payload}, categoria, teste_nome)


def update_log_capture_status(
    bancada_key: str,
    categoria: str,
    teste_nome: str,
    log_capture_status: str,
    *,
    load_payload: LoadPayloadFn,
    save_status: SaveStatusFn,
    test_ref_fn: TestRefFn,
    log_capture_dir: str | None = None,
    log_capture_error: str | None = None,
    log_capture_sequence: str | None = None,
    now_iso_fn: Callable[[], str] | None = None,
) -> None:
    now_iso_fn = now_iso_fn or (lambda: datetime.now().isoformat())
    anterior = load_payload(categoria, teste_nome, bancada_key)
    save_status(
        {
            bancada_key: {
                "serial": bancada_key,
                "categoria": categoria,
                "teste": anterior.get("teste") or test_ref_fn(categoria, teste_nome),
                "status": anterior.get("status") or "finalizado",
                "acoes_totais": int(anterior.get("acoes_totais", 0) or 0),
                "acoes_executadas": int(anterior.get("acoes_executadas", 0) or 0),
                "progresso": float(anterior.get("progresso", 0.0) or 0.0),
                "ultima_acao": anterior.get("ultima_acao", "-"),
                "ultima_acao_idx": int(anterior.get("ultima_acao_idx", 0) or 0),
                "ultima_acao_status": anterior.get("ultima_acao_status", "-"),
                "tempo_decorrido_s": float(anterior.get("tempo_decorrido_s", 0.0) or 0.0),
                "inicio": anterior.get("inicio"),
                "fim": anterior.get("fim"),
                "atualizado_em": now_iso_fn(),
                "resultados_ok": int(anterior.get("resultados_ok", 0) or 0),
                "resultados_divergentes": int(anterior.get("resultados_divergentes", 0) or 0),
                "similaridade_media": round(float(anterior.get("similaridade_media", 0.0) or 0.0), 4),
                "ultima_similaridade": anterior.get("ultima_similaridade"),
                "ultimo_screenshot": anterior.get("ultimo_screenshot"),
                "velocidade_acoes_min": float(anterior.get("velocidade_acoes_min", 0.0) or 0.0),
                "resultado_final": anterior.get("resultado_final") or "pendente",
                "log_capture_status": log_capture_status or anterior.get("log_capture_status") or "nao_necessario",
                "log_capture_dir": log_capture_dir if log_capture_dir is not None else anterior.get("log_capture_dir"),
                "log_capture_error": log_capture_error if log_capture_error is not None else anterior.get("log_capture_error"),
                "log_capture_sequence": log_capture_sequence if log_capture_sequence is not None else anterior.get("log_capture_sequence"),
                "failure_report_status": anterior.get("failure_report_status") or "nao_gerado",
                "failure_report_dir": anterior.get("failure_report_dir"),
                "failure_report_json": anterior.get("failure_report_json"),
                "failure_report_markdown": anterior.get("failure_report_markdown"),
                "failure_report_csv": anterior.get("failure_report_csv"),
                "failure_report_short_text": anterior.get("failure_report_short_text"),
                "failure_report_generated_at": anterior.get("failure_report_generated_at"),
                "failure_report_error": anterior.get("failure_report_error"),
                "erro_motivo": anterior.get("erro_motivo"),
            }
        },
        categoria,
        teste_nome,
    )
