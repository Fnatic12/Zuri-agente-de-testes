import os
import json
import sys
from datetime import datetime, timedelta
import subprocess
import re
from typing import Any, cast

import cv2
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from PIL import Image
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
from vwait.features.execution.ui.streamlit import (
    abrir_pasta_local as _ui_abrir_pasta_local,
    age_text as _ui_age_text,
    apply_panel_button_theme as _ui_apply_panel_button_theme,
    calculate_metrics as _ui_calculate_metrics,
    clean_display_text as _ui_clean_display_text,
    clean_status_text as _ui_clean_status_text,
    compare_expected_with_final as _ui_compare_expected_with_final,
    compare_images_cv as _ui_compare_images_cv,
    estimativa_restante as _ui_estimativa_restante,
    filtrar_bancadas_reais as _ui_filtrar_bancadas_reais,
    find_bboxes as _ui_find_bboxes,
    is_live_status as _ui_is_live_status,
    nome_bancada as _ui_nome_bancada,
    normalizar_execucao as _ui_normalizar_execucao,
    parse_datetime as _ui_parse_datetime,
    percent_text as _ui_percent_text,
    portfolio_live_summary as _ui_portfolio_live_summary,
    saude_chip_html as _ui_saude_chip_html,
    saude_execucao as _ui_saude_execucao,
    render_actions as _ui_render_actions,
    render_expected_comparison as _ui_render_expected_comparison,
    render_failure_report as _ui_render_failure_report,
    render_final_validation as _ui_render_final_validation,
    render_metrics as _ui_render_metrics,
    render_realtime_dashboard as _ui_render_realtime_dashboard,
    render_timeline as _ui_render_timeline,
    render_toggle_comparison as _ui_render_toggle_comparison,
    quality_snapshot as _ui_quality_snapshot,
    sanitize_value as _ui_sanitize_value,
    simple_similarity as _ui_simple_similarity,
    status_age_seconds as _ui_status_age_seconds,
    status_chip_html as _ui_status_chip_html,
    status_human as _ui_status_human,
    status_normalized as _ui_status_normalized,
    tempo_formatado as _ui_tempo_formatado,
    titulo_painel as _ui_titulo_painel,
    velocidade_live as _ui_velocidade_live,
)


def apply_panel_button_theme() -> None:
    _ui_apply_panel_button_theme()

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None


def _identity_decorator(func):
    return func


_REALTIME_FRAGMENT = st.fragment(run_every="3s") if hasattr(st, "fragment") else _identity_decorator


def _subprocess_windowless_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def titulo_painel(titulo: str, subtitulo: str = ""):
    _ui_titulo_painel(titulo, subtitulo)


# === CONFIGURACOES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
BANCADA_LABELS = {
    "2801761952320038": "Bancada 1",
    "2801780E52320038": "Bancada 2",
    "2801780c52320038": "Bancada 2",
    "2801839552320038": "Bancada 3",
}
BANCADA_LABELS_NORM = {str(k).lower(): v for k, v in BANCADA_LABELS.items()}

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


# === FUNCOES AUXILIARES ===
def carregar_logs(data_root=DATA_ROOT):
    """Lista execucoes disponiveis"""
    logs = []
    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if os.path.isdir(cat_path):
            for teste in os.listdir(cat_path):
                teste_path = os.path.join(cat_path, teste)
                if os.path.isdir(teste_path):
                    arq = os.path.join(teste_path, "execucao_log.json")
                    if os.path.exists(arq):
                        logs.append((f"{categoria}/{teste}", arq))
    return logs


def _tempo_formatado(segundos: float) -> str:
    return _ui_tempo_formatado(segundos)


def _parse_datetime(value) -> datetime | None:
    return _ui_parse_datetime(value)


def _clean_display_text(value) -> str:
    return _ui_clean_display_text(value)


def _clean_status_text(value) -> str:
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


def _extract_status_payload(serial: str, raw: dict) -> dict:
    return _execution_extract_status_payload(serial, raw)


def _carregar_status_bancadas(data_root=DATA_ROOT):
    return _execution_carregar_status_bancadas(data_root)


def _status_human(status: str) -> str:
    return _ui_status_human(status)


def _status_chip_html(status: str) -> str:
    return _ui_status_chip_html(status)


def _estimativa_restante(info: dict) -> float | None:
    return _ui_estimativa_restante(info)


def _status_age_seconds(info: dict, now: datetime) -> float:
    return _ui_status_age_seconds(info, now)


def _is_live_status(info: dict, now: datetime) -> bool:
    return _ui_is_live_status(info, now)


def _filtrar_bancadas_reais(status_map: dict, conectadas: set[str]) -> dict:
    return _ui_filtrar_bancadas_reais(status_map, conectadas)


def _nome_bancada(serial: str) -> str:
    return _ui_nome_bancada(serial)


def _status_normalized(status: str) -> str:
    return _ui_status_normalized(status)


def _abrir_pasta_local(path: str) -> tuple[bool, str]:
    return _ui_abrir_pasta_local(path)


def _resolver_diretorio_teste(info: dict) -> str | None:
    return _execution_resolve_test_dir(info, DATA_ROOT)


def _resolver_logs_root(info: dict) -> str | None:
    return _execution_resolve_logs_root(info, DATA_ROOT)


def _resolver_log_capture_dir(info: dict) -> str | None:
    return _execution_resolve_log_capture_dir(info, DATA_ROOT)


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


def _ultima_screenshot_bancada(info: dict) -> str | None:
    return _execution_latest_screenshot_path(info, DATA_ROOT)


def _contar_arquivos_imagem(dir_path: str | None) -> int:
    return _execution_count_image_files(dir_path)


def _carregar_execucao_parcial(info: dict) -> list[dict]:
    return _execution_load_execution_entries(info, DATA_ROOT, normalizer=_normalizar_execucao)


def _quality_snapshot(info: dict, execucao: list[dict]) -> dict:
    return _ui_quality_snapshot(info, execucao)


def _velocidade_live(info: dict) -> float | None:
    return _ui_velocidade_live(info)


def _percent_text(value: float | None, digits: int = 1) -> str:
    return _ui_percent_text(value, digits=digits)


def _age_text(age_s: float) -> str:
    return _ui_age_text(age_s)


def _saude_execucao(info: dict, now: datetime, quality: dict) -> dict:
    return _ui_saude_execucao(info, now, quality)


def _saude_chip_html(saude: dict) -> str:
    return _ui_saude_chip_html(saude)


def _portfolio_live_summary(executando_rows: dict, finalizado_rows: dict, erro_rows: dict, conectadas: set[str]) -> dict:
    return _ui_portfolio_live_summary(
        executando_rows,
        finalizado_rows,
        erro_rows,
        conectadas,
        load_execucao=_carregar_execucao_parcial,
    )


@_REALTIME_FRAGMENT
def exibir_bancadas_tempo_real():
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


def calcular_metricas(execucao):
    return _ui_calculate_metrics(execucao)


def _kpi_card(label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='clean-card'>"
            f"<div class='card-kpi-label'>{label}</div>"
            f"<div class='card-kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _style_axes_clean(ax):
    ax.set_facecolor("#0f172a")
    ax.grid(axis="y", color="#1f2937", linewidth=0.9)
    ax.tick_params(colors="#cbd5e1", labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#334155")
        spine.set_linewidth(0.8)


# === DASHBOARD ===
def exibir_metricas(metricas):
    _ui_render_metrics(metricas)


def exibir_timeline(execucao):
    _ui_render_timeline(execucao)


def exibir_acoes(execucao, base_dir):
    _ui_render_actions(execucao, base_dir)

def _simples_similarity(img_a: Image.Image, img_b: Image.Image) -> float:
    return _ui_simple_similarity(img_a, img_b)


def _apply_ignore_mask(mask: np.ndarray, ignore_regions):
    from vwait.features.execution.ui.streamlit.analysis_blocks import apply_ignore_mask

    return apply_ignore_mask(mask, ignore_regions)


def _compute_diff_mask_cv(img_a: np.ndarray, img_b: np.ndarray, diff_threshold=25):
    from vwait.features.execution.ui.streamlit.analysis_blocks import compute_diff_mask_cv

    return compute_diff_mask_cv(img_a, img_b, diff_threshold=diff_threshold)


def _find_bboxes(mask: np.ndarray, min_area=200, max_area=200000):
    return _ui_find_bboxes(mask, min_area=min_area, max_area=max_area)


def _is_toggle_candidate(bbox, img_shape, aspect_min=1.7, aspect_max=5.5):
    from vwait.features.execution.ui.streamlit.analysis_blocks import is_toggle_candidate

    return is_toggle_candidate(bbox, img_shape, aspect_min=aspect_min, aspect_max=aspect_max)


def _toggle_state_by_color(img_roi: np.ndarray):
    from vwait.features.execution.ui.streamlit.analysis_blocks import toggle_state_by_color

    return toggle_state_by_color(img_roi)


def _toggle_state_by_knob(img_roi: np.ndarray):
    from vwait.features.execution.ui.streamlit.analysis_blocks import toggle_state_by_knob

    return toggle_state_by_knob(img_roi)


def _compare_images_cv(img_a: np.ndarray, img_b: np.ndarray, ignore_regions=None):
    return _ui_compare_images_cv(img_a, img_b, ignore_regions=ignore_regions)


def _carregar_ignore_regions(esperados_dir: str) -> list:
    from vwait.features.execution.ui.streamlit.analysis_blocks import load_ignore_regions

    return load_ignore_regions(esperados_dir)


def _comparar_esperado_com_final(exp_path: str, final_path: str, ignore_regions=None):
    return _ui_compare_expected_with_final(exp_path, final_path, ignore_regions=ignore_regions)


def exibir_comparacao_esperados(base_dir):
    _ui_render_expected_comparison(base_dir)


def exibir_comparacao_toggles(base_dir):
    _ui_render_toggle_comparison(base_dir)


def exibir_validacao_final(execucao, base_dir):
    _ui_render_final_validation(execucao, base_dir)


def _render_text_block(text: Any, fallback: str = "-") -> None:
    from vwait.features.execution.ui.streamlit.analysis_blocks import _render_text_block as render_text_block

    render_text_block(text, fallback=fallback)


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

    if not os.path.isdir(DATA_ROOT):
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
    except Exception as e:
        st.error(f"Falha ao ler execucao_log.json: {e}")
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


def main() -> None:
    st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")
    apply_panel_button_theme()
    render_dashboard_page()


if __name__ == "__main__":
    main()
