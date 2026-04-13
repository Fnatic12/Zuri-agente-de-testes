from __future__ import annotations

import streamlit as st

from vwait.platform.adb import resolve_adb_path
from vwait.features.tester.application.execution import (
    garantir_dataset_execucao as _execution_garantir_dataset_execucao,
    iniciar_execucoes_configuradas as _execution_iniciar_execucoes_configuradas,
    iniciar_execucoes_teste_unico as _execution_iniciar_execucoes_teste_unico,
)
from vwait.features.tester.application.paths import BASE_DIR, SCRIPTS, STOP_FLAG_PATH
from vwait.features.tester.application.runtime import (
    abrir_pasta_local as _runtime_abrir_pasta_local,
    capturar_logs_radio as _runtime_capturar_logs_radio,
    garantir_painel_streamlit as _runtime_garantir_painel_streamlit,
    listar_bancadas as _runtime_listar_bancadas,
    salvar_resultado_parcial as _runtime_salvar_resultado_parcial,
)
from vwait.features.tester.application.status import (
    carregar_status_execucao as _status_carregar_status_execucao,
    clean_display_text as _status_clean_display_text,
    execucao_log_path_por_serial as _status_execucao_log_path_por_serial,
    formatar_resumo_execucao as _status_formatar_resumo_execucao,
    resolver_pasta_logs_teste as _status_resolver_pasta_logs_teste,
    resolver_teste_por_serial as _status_resolver_teste_por_serial,
    status_file_path as _status_status_file_path,
    tem_execucao_unica_ativa as _status_tem_execucao_unica_ativa,
)


def build_tester_context() -> dict[str, object]:
    adb_path = resolve_adb_path()

    def listar_bancadas():
        return _runtime_listar_bancadas(adb_path)

    def salvar_resultado_parcial(categoria, nome_teste, serial=None):
        return _runtime_salvar_resultado_parcial(BASE_DIR, adb_path, categoria, nome_teste, serial)

    def clean_display_text(value: str) -> str:
        return _status_clean_display_text(value)

    def execucao_log_path_por_serial(serial):
        return _status_execucao_log_path_por_serial(BASE_DIR, serial)

    def status_file_path(categoria, teste, serial):
        return _status_status_file_path(BASE_DIR, categoria, teste, serial)

    def carregar_status_execucao(categoria, teste, serial):
        return _status_carregar_status_execucao(BASE_DIR, categoria, teste, serial)

    def resolver_teste_por_serial(serial):
        return _status_resolver_teste_por_serial(BASE_DIR, serial)

    def capturar_logs_radio(categoria, nome_teste, serial, motivo="captura_manual_menu_tester"):
        return _runtime_capturar_logs_radio(categoria, nome_teste, serial, motivo=motivo)

    def abrir_pasta_local(path):
        return _runtime_abrir_pasta_local(path)

    def resolver_pasta_logs_teste(categoria, nome_teste, serial=None):
        return _status_resolver_pasta_logs_teste(BASE_DIR, categoria, nome_teste, serial)

    def formatar_resumo_execucao(payload, fallback_returncode=None):
        return _status_formatar_resumo_execucao(payload, fallback_returncode=fallback_returncode)

    def tem_execucao_unica_ativa():
        return _status_tem_execucao_unica_ativa(st.session_state.get("execucao_unica_processos", []))

    def garantir_dataset_execucao(categoria_exec, nome_teste_exec):
        return _execution_garantir_dataset_execucao(
            BASE_DIR,
            SCRIPTS,
            categoria_exec,
            nome_teste_exec,
            on_warning=st.warning,
            on_success=st.success,
        )

    def iniciar_execucoes_configuradas(execucoes):
        return _execution_iniciar_execucoes_configuradas(
            BASE_DIR,
            SCRIPTS,
            execucoes,
            st.session_state,
            tem_execucao_unica_ativa=tem_execucao_unica_ativa,
            garantir_dataset_execucao_fn=garantir_dataset_execucao,
            execucao_log_path_por_serial=execucao_log_path_por_serial,
        )

    def iniciar_execucoes_teste_unico(categoria_exec, nome_teste_exec, seriais):
        return _execution_iniciar_execucoes_teste_unico(
            categoria_exec,
            nome_teste_exec,
            seriais,
            iniciar_execucoes_configuradas_fn=iniciar_execucoes_configuradas,
        )

    def garantir_painel_streamlit(script_path: str, port: int, timeout_s: float = 12.0) -> bool:
        return _runtime_garantir_painel_streamlit(script_path, port, BASE_DIR, timeout_s=timeout_s)

    return {
        "adb_path": adb_path,
        "base_dir": BASE_DIR,
        "scripts": SCRIPTS,
        "stop_flag_path": STOP_FLAG_PATH,
        "listar_bancadas": listar_bancadas,
        "salvar_resultado_parcial": salvar_resultado_parcial,
        "clean_display_text": clean_display_text,
        "execucao_log_path_por_serial": execucao_log_path_por_serial,
        "status_file_path": status_file_path,
        "carregar_status_execucao": carregar_status_execucao,
        "resolver_teste_por_serial": resolver_teste_por_serial,
        "capturar_logs_radio": capturar_logs_radio,
        "abrir_pasta_local": abrir_pasta_local,
        "resolver_pasta_logs_teste": resolver_pasta_logs_teste,
        "formatar_resumo_execucao": formatar_resumo_execucao,
        "tem_execucao_unica_ativa": tem_execucao_unica_ativa,
        "garantir_dataset_execucao": garantir_dataset_execucao,
        "iniciar_execucoes_configuradas": iniciar_execucoes_configuradas,
        "iniciar_execucoes_teste_unico": iniciar_execucoes_teste_unico,
        "garantir_painel_streamlit": garantir_painel_streamlit,
    }


__all__ = ["build_tester_context"]
