from __future__ import annotations

import os
from threading import Lock

import colorama
import streamlit as st

try:
    import requests
except Exception:
    requests = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from vwait.core.paths import project_root, root_path
from vwait.platform.adb import resolve_adb_path
from vwait.features.chat.application.config import load_chat_page_config
from vwait.features.chat.application.llm import (
    init_colorama_safely as _init_colorama_safely_app,
    resolve_ollama_cli as _resolve_ollama_cli_app,
    warmup_ollama_once as _warmup_ollama_once,
)
from vwait.features.chat.application.operations import (
    append_execution_log as _append_execution_log,
    capture_radio_log_command as _capture_radio_log_command,
    capture_radio_logs_for_test as _capture_radio_logs_for_test,
    ensure_execution_dataset as _ensure_execution_dataset,
    export_global_log_sequence as _export_global_log_sequence,
    format_benches as _format_benches,
    list_benches as _list_benches,
    llm_chat_response as _llm_chat_response,
    llm_command as _llm_command,
    ollama_generate as _ollama_generate_app,
    parse_adb_devices as _parse_adb_devices_app,
    popen_host_python as _popen_host_python_app,
    read_serial_status as _read_serial_status,
    resolve_command_with_llm_or_fallback as _resolve_command_with_llm_or_fallback,
    resolve_test as _resolve_test_app,
    run_parallel_tests as _run_parallel_tests,
    select_bench as _select_bench,
    start_execution_on_serial as _start_execution_on_serial,
    update_bench_status as _update_bench_status,
)
from vwait.features.chat.application.parsing import (
    KW_AJUDA,
    KW_APAGAR,
    KW_EXECUTAR,
    KW_GRAVAR,
    KW_LISTAR,
    KW_PROCESS,
    extract_bench as _extract_bench_app,
    extract_category as _extract_category_app,
    extract_parallel_executions as _extract_parallel_executions_app,
    extract_test_token as _extract_test_token_app,
    has_any as _has_any_app,
    norm as _norm_app,
    normalize_token as _normalize_token_app,
    replace_number_words as _replace_number_words_app,
    resolve_execution_from_chunk as _resolve_execution_from_chunk_app,
)
from vwait.features.chat.application.recording import (
    cancel_recording as _cancel_recording,
    continue_recording_flow as _continue_recording_flow,
    delete_test as _delete_test,
    is_log_sequence_command as _is_log_sequence_command,
    list_categories as _list_categories,
    list_tests as _list_tests,
    pause_execution as _pause_execution,
    process_test as _process_test,
    record_test as _record_test,
    resume_execution as _resume_execution,
    save_partial_result as _save_partial_result,
    start_recording_flow as _start_recording_flow,
    stop_execution as _stop_execution,
    finalize_recording as _finalize_recording,
)
from vwait.features.chat.application.speech import normalize_post_speech as _normalize_post_speech
from vwait.features.chat.ui.streamlit.bindings import (
    build_chat_page_bindings,
    build_chat_page_utilities,
)
from vwait.features.chat.ui.streamlit.bootstrap import (
    create_chat_controller,
    initialize_chat_page,
    open_menu_tester,
    render_chat_page,
)
from vwait.features.chat.ui.streamlit.chat_runtime import (
    check_finalizations as _check_finalizations,
    check_finished_executions as _check_finished_executions,
    finalize_global_log_sequence as _finalize_global_log_sequence,
    record_global_log_sequence as _record_global_log_sequence,
)
from vwait.features.chat.ui.streamlit.composition import (
    process_user_input as _process_user_input_app,
    render_page_layout as _render_page_layout,
)
from vwait.features.chat.ui.streamlit.display import (
    panel_title as _panel_title,
    render_chat_greeting as _render_chat_greeting,
)
from vwait.features.chat.ui.streamlit.maps import render_mapa_neural_ia_coder
from vwait.features.chat.ui.streamlit.navigation import (
    MENU_TESTER_PORT,
    PAGINA_CHAT,
    PAGINA_CONTROLE_FALHAS,
    PAGINA_DASHBOARD,
    PAGINA_LOGS_RADIO,
    PAGINA_MAPA_NEURAL_IA,
    PAGINA_VALIDACAO_HMI,
    apply_pending_navigation,
    init_navigation_state,
    render_selected_page,
    select_page as _selecionar_pagina,
    sidebar_page_selector,
)
from vwait.features.chat.ui.streamlit.routing import (
    interpret_command as _interpret_command,
    resolve_navigation_command as _resolve_navigation_command,
    respond_conversational as _respond_conversational,
)
from vwait.features.chat.ui.streamlit.runtime import (
    garantir_app_streamlit as _runtime_garantir_app_streamlit,
    subprocess_windowless_kwargs as _subprocess_windowless_kwargs,
)
from vwait.features.chat.ui.streamlit.shell import (
    render_benches_sidebar,
    render_chat_shell,
    render_voice_sidebar,
)
from vwait.features.chat.ui.streamlit.state import (
    configure_page as _configure_page,
    initialize_chat_state as _initialize_chat_state,
)
from vwait.features.chat.ui.streamlit.theme import (
    apply_dark_background,
    apply_panel_button_theme,
    sanitize_text as _sanitize_text,
)
from vwait.features.chat.ui.streamlit.voice import (
    audio_input_to_sr_audio,
    configure_recognizer,
    preload_whisper_default,
    process_voice_command,
    transcribe_command_audio,
)


def _init_colorama_safely() -> None:
    _init_colorama_safely_app(colorama_module=colorama, os_name=os.name)


def _resolve_ollama_cli() -> str:
    return _resolve_ollama_cli_app(OLLAMA_CLI)


def _warmup_ollama() -> None:
    _warmup_ollama_once(
        session_state=st.session_state,
        warmup_key="ollama_warm",
        warmup_fn=lambda: _ollama_generate_app(
            "Responda apenas com 'ok'.",
            ollama_url=OLLAMA_URL,
            ollama_model=OLLAMA_MODEL,
            ollama_keep_alive=OLLAMA_KEEP_ALIVE,
            num_predict=OLLAMA_NUM_PREDICT,
            temperature=OLLAMA_TEMPERATURE,
            top_p=OLLAMA_TOP_P,
            num_ctx=OLLAMA_NUM_CTX,
            requests_module=requests,
            resolve_ollama_cli=_resolve_ollama_cli,
            timeout_s=8,
            allow_cli=False,
        ),
    )


_init_colorama_safely()

status_lock = Lock()
CONFIG = load_chat_page_config(
    project_root_fn=project_root,
    root_path_fn=root_path,
    resolve_adb_path_fn=resolve_adb_path,
)
PROJECT_ROOT = CONFIG.project_root
BASE_DIR = CONFIG.base_dir
DATA_ROOT = CONFIG.data_root
RUN_SCRIPT = CONFIG.run_script
COLETOR_SCRIPT = CONFIG.collector_script
PROCESSAR_SCRIPT = CONFIG.process_script
PAUSE_FLAG_PATH = CONFIG.pause_flag_path
GLOBAL_LOG_SEQUENCE_CATEGORY = CONFIG.global_log_sequence_category
GLOBAL_LOG_SEQUENCE_TEST = CONFIG.global_log_sequence_test
GLOBAL_LOG_SEQUENCE_CSV = CONFIG.global_log_sequence_csv
MODO_CONVERSA = CONFIG.conversation_mode
ADB_PATH = CONFIG.adb_path
OLLAMA_URL = CONFIG.ollama_url
OLLAMA_MODEL = CONFIG.ollama_model
OLLAMA_CLI = CONFIG.ollama_cli
OLLAMA_NUM_PREDICT = CONFIG.ollama_num_predict
OLLAMA_TEMPERATURE = CONFIG.ollama_temperature
OLLAMA_TOP_P = CONFIG.ollama_top_p
OLLAMA_NUM_CTX = CONFIG.ollama_num_ctx
OLLAMA_KEEP_ALIVE = CONFIG.ollama_keep_alive

_warmup_ollama()

utilities = build_chat_page_utilities(
    normalize_post_speech_impl_fn=_normalize_post_speech,
    replace_number_words_fn=_replace_number_words_app,
    norm_fn=_norm_app,
    extract_test_token_fn=_extract_test_token_app,
    extract_bench_fn=_extract_bench_app,
    resolve_test_fn=_resolve_test_app,
    ensure_streamlit_app_impl_fn=_runtime_garantir_app_streamlit,
    base_dir=BASE_DIR,
    open_menu_tester_impl_fn=open_menu_tester,
    menu_tester_port=MENU_TESTER_PORT,
    root_path_fn=root_path,
)

initialize_chat_page(
    configure_page_fn=_configure_page,
    initialize_chat_state_fn=_initialize_chat_state,
    session_state=st.session_state,
    apply_dark_background_fn=apply_dark_background,
    apply_panel_button_theme_fn=apply_panel_button_theme,
    preload_whisper_default_fn=preload_whisper_default,
    init_navigation_state_fn=init_navigation_state,
)

controller = create_chat_controller(
    session_state=st.session_state,
    conversation_mode=MODO_CONVERSA,
    adb_path=ADB_PATH,
    data_root=DATA_ROOT,
    base_dir=BASE_DIR,
    run_script=RUN_SCRIPT,
    process_script=PROCESSAR_SCRIPT,
    status_lock=status_lock,
    global_log_sequence_category=GLOBAL_LOG_SEQUENCE_CATEGORY,
    global_log_sequence_test=GLOBAL_LOG_SEQUENCE_TEST,
    global_log_sequence_csv=GLOBAL_LOG_SEQUENCE_CSV,
    pause_flag_path=PAUSE_FLAG_PATH,
    ollama_url=OLLAMA_URL,
    ollama_model=OLLAMA_MODEL,
    ollama_keep_alive=OLLAMA_KEEP_ALIVE,
    ollama_num_predict=OLLAMA_NUM_PREDICT,
    ollama_temperature=OLLAMA_TEMPERATURE,
    ollama_top_p=OLLAMA_TOP_P,
    ollama_num_ctx=OLLAMA_NUM_CTX,
    requests_module=requests,
    resolve_ollama_cli_fn=_resolve_ollama_cli,
    rerun_fn=st.rerun,
    normalize_post_speech_fn=utilities.normalize_post_speech,
    process_voice_command_fn=process_voice_command,
    parse_adb_devices_fn=_parse_adb_devices_app,
    list_benches_fn=_list_benches,
    subprocess_windowless_kwargs_fn=_subprocess_windowless_kwargs,
    format_benches_fn=_format_benches,
    replace_number_words_fn=_replace_number_words_app,
    normalize_token_fn=_normalize_token_app,
    norm_fn=_norm_app,
    has_any_fn=_has_any_app,
    resolve_test_fn=_resolve_test_app,
    select_bench_fn=_select_bench,
    popen_host_python_fn=_popen_host_python_app,
    read_serial_status_fn=_read_serial_status,
    capture_radio_logs_for_test_fn=_capture_radio_logs_for_test,
    capture_radio_log_command_fn=_capture_radio_log_command,
    update_bench_status_fn=_update_bench_status,
    ollama_generate_fn=_ollama_generate_app,
    llm_command_fn=_llm_command,
    llm_chat_response_fn=_llm_chat_response,
    resolve_command_with_llm_or_fallback_fn=_resolve_command_with_llm_or_fallback,
    append_execution_log_fn=_append_execution_log,
    ensure_chat_execution_dataset_fn=_ensure_execution_dataset,
    start_execution_on_serial_fn=_start_execution_on_serial,
    execute_test_fn=_execute_test_app,
    extract_bench_fn=_extract_bench_app,
    extract_test_token_fn=_extract_test_token_app,
    extract_category_fn=_extract_category_app,
    list_categories_impl_fn=_list_categories,
    list_tests_impl_fn=_list_tests,
    resolve_execution_from_chunk_fn=_resolve_execution_from_chunk_app,
    extract_parallel_executions_fn=_extract_parallel_executions_app,
    execute_parallel_tests_fn=_run_parallel_tests,
    resolve_navigation_command_fn=_resolve_navigation_command,
    select_page_fn=_selecionar_pagina,
    open_menu_tester_fn=utilities.open_menu_tester,
    dashboard_page=PAGINA_DASHBOARD,
    logs_page=PAGINA_LOGS_RADIO,
    failures_page=PAGINA_CONTROLE_FALHAS,
    hmi_page=PAGINA_VALIDACAO_HMI,
    brain_page=PAGINA_MAPA_NEURAL_IA,
    chat_page=PAGINA_CHAT,
    continue_recording_flow_fn=lambda response: _continue_recording_flow(
        response,
        session_state=st.session_state,
        list_benches_fn=controller.list_benches,
        extract_bench_fn=controller.extract_bench,
        record_test_fn=lambda category, test_name, bench=None: _record_test(
            category,
            test_name,
            bench,
            project_root=PROJECT_ROOT,
            collector_script=COLETOR_SCRIPT,
            list_benches_fn=controller.list_benches,
            select_bench_fn=controller.select_bench,
            popen_host_python_fn=controller.popen_host_python,
        ),
    ),
    respond_conversational_fn=_respond_conversational,
    record_global_log_sequence_fn=lambda bench=None: _record_global_log_sequence(
        bench,
        session_state=st.session_state,
        record_test_fn=lambda category, test_name, bench_label=None: _record_test(
            category,
            test_name,
            bench_label,
            project_root=PROJECT_ROOT,
            collector_script=COLETOR_SCRIPT,
            list_benches_fn=controller.list_benches,
            select_bench_fn=controller.select_bench,
            popen_host_python_fn=controller.popen_host_python,
        ),
        list_benches_fn=controller.list_benches,
        select_bench_fn=controller.select_bench,
        global_log_sequence_category=GLOBAL_LOG_SEQUENCE_CATEGORY,
        global_log_sequence_test=GLOBAL_LOG_SEQUENCE_TEST,
        global_log_sequence_csv=GLOBAL_LOG_SEQUENCE_CSV,
    ),
    record_test_fn=lambda category, test_name, bench=None: _record_test(
        category,
        test_name,
        bench,
        project_root=PROJECT_ROOT,
        collector_script=COLETOR_SCRIPT,
        list_benches_fn=controller.list_benches,
        select_bench_fn=controller.select_bench,
        popen_host_python_fn=controller.popen_host_python,
    ),
    start_recording_flow_fn=lambda: _start_recording_flow(st.session_state),
    process_test_fn=lambda category, test_name: _process_test(
        category,
        test_name,
        process_script=PROCESSAR_SCRIPT,
        popen_host_python_fn=controller.popen_host_python,
    ),
    delete_test_fn=lambda category, test_name: _delete_test(category, test_name, data_root=DATA_ROOT),
    finalize_log_sequence_fn=lambda: _finalize_global_log_sequence(
        session_state=st.session_state,
        finalize_recording_fn=lambda category=None, test_name=None, serial=None: _finalize_recording(
            project_root=PROJECT_ROOT,
            session_state=st.session_state,
            category=category,
            test_name=test_name,
            serial=serial,
            global_log_sequence_category=GLOBAL_LOG_SEQUENCE_CATEGORY,
            global_log_sequence_test=GLOBAL_LOG_SEQUENCE_TEST,
        ),
    ),
    pause_execution_fn=lambda: _pause_execution(pause_flag_path=PAUSE_FLAG_PATH),
    resume_execution_fn=lambda: _resume_execution(pause_flag_path=PAUSE_FLAG_PATH),
    stop_execution_fn=lambda: _stop_execution(project_root=PROJECT_ROOT),
    is_log_sequence_command_fn=lambda text: _is_log_sequence_command(text, norm_fn=controller.norm),
    execute_keywords=KW_EXECUTAR,
    record_keywords=KW_GRAVAR,
    process_keywords=KW_PROCESS,
    delete_keywords=KW_APAGAR,
    list_keywords=KW_LISTAR,
    help_keywords=KW_AJUDA,
    interpret_command_fn=_interpret_command,
)

bindings = build_chat_page_bindings(
    controller=controller,
    session_state=st.session_state,
    project_root=PROJECT_ROOT,
    data_root=DATA_ROOT,
    adb_path=ADB_PATH,
    process_script=PROCESSAR_SCRIPT,
    collector_script=COLETOR_SCRIPT,
    pause_flag_path=PAUSE_FLAG_PATH,
    global_log_sequence_category=GLOBAL_LOG_SEQUENCE_CATEGORY,
    global_log_sequence_test=GLOBAL_LOG_SEQUENCE_TEST,
    global_log_sequence_csv=GLOBAL_LOG_SEQUENCE_CSV,
    start_recording_flow_impl_fn=_start_recording_flow,
    is_log_sequence_command_impl_fn=_is_log_sequence_command,
    record_global_log_sequence_impl_fn=_record_global_log_sequence,
    finalize_global_log_sequence_impl_fn=_finalize_global_log_sequence,
    continue_recording_flow_impl_fn=_continue_recording_flow,
    check_finalizations_impl_fn=_check_finalizations,
    check_finished_executions_impl_fn=_check_finished_executions,
    save_partial_result_impl_fn=_save_partial_result,
    record_test_impl_fn=_record_test,
    finalize_recording_impl_fn=_finalize_recording,
    cancel_recording_impl_fn=_cancel_recording,
    process_test_impl_fn=_process_test,
    delete_test_impl_fn=_delete_test,
    list_categories_impl_fn=_list_categories,
    list_tests_impl_fn=_list_tests,
    pause_execution_impl_fn=_pause_execution,
    resume_execution_impl_fn=_resume_execution,
    stop_execution_impl_fn=_stop_execution,
    export_global_log_sequence_fn=_export_global_log_sequence,
)

render_chat_page(
    render_page_layout_fn=_render_page_layout,
    apply_pending_navigation_fn=apply_pending_navigation,
    sidebar_page_selector_fn=sidebar_page_selector,
    render_voice_sidebar_fn=render_voice_sidebar,
    configure_recognizer_fn=configure_recognizer,
    audio_input_to_sr_audio_fn=audio_input_to_sr_audio,
    transcribe_command_audio_fn=transcribe_command_audio,
    process_voice_command_fn=bindings.process_voice_command,
    list_categories_fn=bindings.list_categories,
    list_tests_fn=bindings.list_tests,
    render_benches_sidebar_fn=render_benches_sidebar,
    list_benches_fn=bindings.list_benches,
    format_benches_fn=bindings.format_benches,
    selected_chat_page=PAGINA_CHAT,
    render_chat_shell_fn=render_chat_shell,
    title_panel_fn=_panel_title,
    render_greeting_fn=_render_chat_greeting,
    check_finalizations_fn=bindings.check_finalizations,
    check_finished_executions_fn=bindings.check_finished_executions,
    st_autorefresh_module=st_autorefresh,
    sanitize_text_fn=_sanitize_text,
    save_partial_result_fn=bindings.save_partial_result,
    finalize_recording_fn=bindings.finalize_recording,
    cancel_recording_fn=bindings.cancel_recording,
    process_user_input_fn=lambda user_input: _process_user_input_app(
        user_input,
        session_state=st.session_state,
        conversation_mode=MODO_CONVERSA,
        continue_recording_flow_fn=bindings.continue_recording_flow,
        conversational_responder_fn=bindings.respond_conversational,
        command_resolver_fn=bindings.resolve_command_with_llm_or_fallback,
    ),
    render_selected_page_fn=render_selected_page,
    render_mapa_neural_ia_coder_fn=render_mapa_neural_ia_coder,
    apply_panel_button_theme_fn=apply_panel_button_theme,
    open_menu_tester_fn=utilities.open_menu_tester,
)
