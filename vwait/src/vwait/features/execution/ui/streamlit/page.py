from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[6]
SRC_DIR = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.shared.adb_utils import candidate_adb_paths
from vwait.features.execution.application import (
    carregar_status_bancadas as _execution_carregar_status_bancadas,
    carregar_status_teste as _execution_carregar_status_teste,
    count_image_files as _execution_count_image_files,
    extract_status_payload as _execution_extract_status_payload,
    latest_screenshot_path as _execution_latest_screenshot_path,
    load_execution_entries as _execution_load_execution_entries,
    load_failure_report_bundle as _execution_load_failure_report_bundle,
    load_optional_json_file as _execution_load_optional_json_file,
    resolve_existing_path as _execution_resolve_existing_path,
    resolve_latest_log_capture_from_base_dir as _execution_resolve_latest_log_capture_from_base_dir,
    resolve_log_capture_dir as _execution_resolve_log_capture_dir,
    resolve_logs_root as _execution_resolve_logs_root,
    resolve_logs_root_from_base_dir as _execution_resolve_logs_root_from_base_dir,
    resolve_test_dir as _execution_resolve_test_dir,
)

from .analysis_blocks import (
    render_expected_comparison as _ui_render_expected_comparison,
    render_failure_report as _ui_render_failure_report,
    render_final_validation as _ui_render_final_validation,
    render_toggle_comparison as _ui_render_toggle_comparison,
)
from .dashboard_blocks import (
    calculate_metrics as _ui_calculate_metrics,
    portfolio_live_summary as _ui_portfolio_live_summary,
    render_actions as _ui_render_actions,
    render_metrics as _ui_render_metrics,
    render_realtime_dashboard as _ui_render_realtime_dashboard,
    render_timeline as _ui_render_timeline,
)
from .helpers import (
    abrir_pasta_local as _ui_abrir_pasta_local,
    age_text as _ui_age_text,
    clean_display_text as _ui_clean_display_text,
    clean_status_text as _ui_clean_status_text,
    estimativa_restante as _ui_estimativa_restante,
    filtrar_bancadas_reais as _ui_filtrar_bancadas_reais,
    is_live_status as _ui_is_live_status,
    nome_bancada as _ui_nome_bancada,
    normalizar_execucao as _ui_normalizar_execucao,
    parse_datetime as _ui_parse_datetime,
    percent_text as _ui_percent_text,
    quality_snapshot as _ui_quality_snapshot,
    saude_chip_html as _ui_saude_chip_html,
    saude_execucao as _ui_saude_execucao,
    sanitize_value as _ui_sanitize_value,
    status_age_seconds as _ui_status_age_seconds,
    status_chip_html as _ui_status_chip_html,
    status_human as _ui_status_human,
    status_normalized as _ui_status_normalized,
    tempo_formatado as _ui_tempo_formatado,
    velocidade_live as _ui_velocidade_live,
)
from .theme import titulo_painel as _ui_titulo_painel

DATA_ROOT = PROJECT_ROOT / "Data"


try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None


def _identity_decorator(func):
    return func


_REALTIME_FRAGMENT = st.fragment(run_every="3s") if hasattr(st, "fragment") else _identity_decorator


def carregar_logs(data_root: str | Path = DATA_ROOT) -> list[tuple[str, str]]:
    logs: list[tuple[str, str]] = []
    root = Path(data_root)
    if not root.is_dir():
        return logs
    for categoria in root.iterdir():
        if not categoria.is_dir():
            continue
        for teste in categoria.iterdir():
            if not teste.is_dir():
                continue
            arq = teste / "execucao_log.json"
            if arq.exists():
                logs.append((f"{categoria.name}/{teste.name}", str(arq)))
    return logs


def _subprocess_windowless_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def titulo_painel(titulo: str, subtitulo: str = "") -> None:
    _ui_titulo_painel(titulo, subtitulo)


def _tempo_formatado(segundos: float) -> str:
    return _ui_tempo_formatado(segundos)


def _parse_datetime(value: Any) -> datetime | None:
    return _ui_parse_datetime(value)


def _clean_display_text(value: Any) -> str:
    return _ui_clean_display_text(value)


def _clean_status_text(value: Any) -> str:
    return _ui_clean_status_text(value)


def _sanitize_value(value: Any) -> Any:
    return _ui_sanitize_value(value)


def _normalizar_execucao(execucao: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _ui_normalizar_execucao(execucao)


def _candidate_adb_commands() -> list[str]:
    return candidate_adb_paths()


def _listar_dispositivos_adb() -> set[str]:
    for adb_cmd in _candidate_adb_commands():
        try:
            out = subprocess.run(
                [adb_cmd, "devices"],
                capture_output=True,
                text=True,
                timeout=4,
                **_subprocess_windowless_kwargs(),
            )
        except Exception:
            continue

        if out.returncode != 0:
            continue

        seriais = set()
        for line in out.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                seriais.add(parts[0])
        return seriais
    return set()


def _extract_status_payload(serial: str, raw: dict[str, Any]) -> dict[str, Any]:
    return _execution_extract_status_payload(serial, raw)


def _carregar_status_bancadas(data_root: str | Path = DATA_ROOT):
    return _execution_carregar_status_bancadas(str(data_root))


def _status_human(status: str) -> str:
    return _ui_status_human(status)


def _status_chip_html(status: str) -> str:
    return _ui_status_chip_html(status)


def _estimativa_restante(info: dict[str, Any]) -> float | None:
    return _ui_estimativa_restante(info)


def _status_age_seconds(info: dict[str, Any], now: datetime) -> float:
    return _ui_status_age_seconds(info, now)


def _is_live_status(info: dict[str, Any], now: datetime) -> bool:
    return _ui_is_live_status(info, now)


def _filtrar_bancadas_reais(status_map: dict[str, Any], conectadas: set[str]) -> dict[str, Any]:
    return _ui_filtrar_bancadas_reais(status_map, conectadas)


def _nome_bancada(serial: str) -> str:
    return _ui_nome_bancada(serial)


def _status_normalized(status: str) -> str:
    return _ui_status_normalized(status)


def _abrir_pasta_local(path: str) -> tuple[bool, str]:
    return _ui_abrir_pasta_local(path)


def _resolver_diretorio_teste(info: dict[str, Any]) -> str | None:
    return _execution_resolve_test_dir(info, str(DATA_ROOT))


def _resolver_logs_root(info: dict[str, Any]) -> str | None:
    return _execution_resolve_logs_root(info, str(DATA_ROOT))


def _resolver_log_capture_dir(info: dict[str, Any]) -> str | None:
    return _execution_resolve_log_capture_dir(info, str(DATA_ROOT))


def _resolver_logs_root_from_base_dir(base_dir: str) -> str | None:
    return _execution_resolve_logs_root_from_base_dir(base_dir)


def _resolver_latest_log_capture_from_base_dir(base_dir: str) -> str | None:
    return _execution_resolve_latest_log_capture_from_base_dir(base_dir)


def _load_optional_json_file(path: str | None) -> dict[str, Any]:
    return _execution_load_optional_json_file(path)


def _resolve_existing_path(base_dir: str, raw_path: Any, expected: str = "file") -> str | None:
    return _execution_resolve_existing_path(base_dir, raw_path, expected=expected)


def _carregar_status_teste(base_dir: str) -> dict[str, Any]:
    return cast(dict[str, Any], _execution_carregar_status_teste(base_dir))


def _carregar_relatorio_falha(base_dir: str, status_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _execution_load_failure_report_bundle(base_dir, status_payload, cleaner=_clean_display_text)


def _ultima_screenshot_bancada(info: dict[str, Any]) -> str | None:
    return _execution_latest_screenshot_path(info, str(DATA_ROOT))


def _contar_arquivos_imagem(dir_path: str | None) -> int:
    return _execution_count_image_files(dir_path)


def _carregar_execucao_parcial(info: dict[str, Any]) -> list[dict[str, Any]]:
    return _execution_load_execution_entries(info, str(DATA_ROOT), normalizer=_normalizar_execucao)


def _quality_snapshot(info: dict[str, Any], execucao: list[dict[str, Any]]) -> dict[str, Any]:
    return _ui_quality_snapshot(info, execucao)


def _velocidade_live(info: dict[str, Any]) -> float | None:
    return _ui_velocidade_live(info)


def _percent_text(value: float | None, digits: int = 1) -> str:
    return _ui_percent_text(value, digits=digits)


def _age_text(age_s: float) -> str:
    return _ui_age_text(age_s)


def _saude_execucao(info: dict[str, Any], now: datetime, quality: dict[str, Any]) -> dict[str, Any]:
    return _ui_saude_execucao(info, now, quality)


def _saude_chip_html(saude: dict[str, Any]) -> str:
    return _ui_saude_chip_html(saude)


def _portfolio_live_summary(
    executando_rows: dict[str, Any],
    finalizado_rows: dict[str, Any],
    erro_rows: dict[str, Any],
    conectadas: set[str],
) -> dict[str, Any]:
    return _ui_portfolio_live_summary(
        executando_rows,
        finalizado_rows,
        erro_rows,
        conectadas,
        load_execucao=_carregar_execucao_parcial,
    )


@_REALTIME_FRAGMENT
def exibir_bancadas_tempo_real() -> None:
    _ui_render_realtime_dashboard(
        list_adb_devices=_listar_dispositivos_adb,
        load_status_map=lambda: _carregar_status_bancadas(DATA_ROOT),
        filter_real_benches=_filtrar_bancadas_reais,
        load_execucao=_carregar_execucao_parcial,
        latest_screenshot=_ultima_screenshot_bancada,
        resolve_test_dir=_resolver_diretorio_teste,
        count_images=_contar_arquivos_imagem,
        autorefresh_available=st_autorefresh is not None and not hasattr(st, "fragment"),
    )


def calcular_metricas(execucao: list[dict[str, Any]]) -> dict[str, Any]:
    return _ui_calculate_metrics(execucao)


def exibir_metricas(metricas: dict[str, Any]) -> None:
    _ui_render_metrics(metricas)


def exibir_timeline(execucao: list[dict[str, Any]]) -> None:
    _ui_render_timeline(execucao)


def exibir_acoes(execucao: list[dict[str, Any]], base_dir: str) -> None:
    _ui_render_actions(execucao, base_dir)


def exibir_comparacao_esperados(base_dir: str) -> None:
    _ui_render_expected_comparison(base_dir)


def exibir_comparacao_toggles(base_dir: str) -> None:
    _ui_render_toggle_comparison(base_dir)


def exibir_validacao_final(execucao: list[dict[str, Any]], base_dir: str) -> None:
    _ui_render_final_validation(execucao, base_dir)


def exibir_relatorio_falha(base_dir: str, selected: str, status_payload: dict[str, Any]) -> None:
    _ui_render_failure_report(
        base_dir,
        selected,
        status_payload,
        load_failure_report=_carregar_relatorio_falha,
        open_folder=_abrir_pasta_local,
        resolve_existing_path=lambda base, raw, expected: _resolve_existing_path(base, raw, expected=expected),
    )


def render_dashboard_page() -> None:
    titulo_painel("Dashboard de Execução de Testes - VWAIT", "")
    exibir_bancadas_tempo_real()
    st.markdown("---")
    st.subheader("Execução detalhada por teste")

    if not DATA_ROOT.is_dir():
        st.error(f"Pasta de dados nao encontrada: {DATA_ROOT}")
        return

    logs = carregar_logs()
    if not logs:
        st.info("Nenhum execucao_log.json encontrado em Data/*/*/.")
        return

    labels = [label for label, _ in logs]
    selected = st.selectbox("Selecione a execucao", labels)
    path_map = {label: path for label, path in logs}
    log_path = path_map.get(selected)
    if not log_path or not os.path.exists(log_path):
        st.error("Execucao selecionada nao encontrada.")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        st.error(f"Falha ao ler execucao_log.json: {exc}")
        return

    execucao = data.get("execucao") if isinstance(data, dict) else data
    if not isinstance(execucao, list):
        st.error("Formato invalido de execucao_log.json (esperado lista ou {'execucao': []}).")
        return

    execucao = _normalizar_execucao(execucao)

    base_dir = os.path.dirname(log_path)
    status_payload = _carregar_status_teste(base_dir)
    logs_root = _resolver_logs_root_from_base_dir(base_dir)
    latest_log_capture = _resolver_latest_log_capture_from_base_dir(base_dir)
    metricas = calcular_metricas(execucao)

    st.markdown("##### Logs do radio")
    log_col1, log_col2 = st.columns(2)
    with log_col1:
        if st.button("Abrir pasta logs/", key=f"open_logs_root_{selected}"):
            if not logs_root:
                st.error("Nenhuma pasta logs encontrada para este teste.")
            else:
                ok_open, detalhe_open = _abrir_pasta_local(logs_root)
                if ok_open:
                    st.success(f"Pasta aberta: {logs_root}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")
    with log_col2:
        if st.button("Abrir ultima captura de logs", key=f"open_logs_latest_{selected}"):
            if not latest_log_capture:
                st.error("Nenhuma captura de logs encontrada para este teste.")
            else:
                ok_open, detalhe_open = _abrir_pasta_local(latest_log_capture)
                if ok_open:
                    st.success(f"Pasta aberta: {latest_log_capture}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")

    if logs_root:
        st.caption(f"Raiz dos logs: {logs_root}")
    else:
        st.caption("Raiz dos logs: nenhuma pasta logs/ encontrada para esta execucao.")

    exibir_relatorio_falha(base_dir, selected, status_payload)
    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_comparacao_toggles(base_dir)
    exibir_comparacao_esperados(base_dir)
    exibir_validacao_final(execucao, base_dir)
    exibir_acoes(execucao, base_dir)


__all__ = ["render_dashboard_page"]
