from vwait.features.chat.ui.streamlit.controller import build_chat_controller
from vwait.features.chat.ui.streamlit.launchers import open_panel


def initialize_chat_page(*, configure_page_fn, initialize_chat_state_fn, session_state, apply_dark_background_fn, apply_panel_button_theme_fn, preload_whisper_default_fn, init_navigation_state_fn) -> None:
    configure_page_fn(
        apply_dark_background=apply_dark_background_fn,
        apply_panel_button_theme=apply_panel_button_theme_fn,
    )
    initialize_chat_state_fn(
        session_state=session_state,
        preload_whisper_default=preload_whisper_default_fn,
        init_navigation_state=init_navigation_state_fn,
    )


def ensure_streamlit_app(*, ensure_app_streamlit_fn, base_dir: str, script_path: str, port: int, silence_output: bool = False, timeout_s: float = 12.0) -> bool:
    return ensure_app_streamlit_fn(
        script_path,
        port,
        base_dir=base_dir,
        silence_output=silence_output,
        timeout_s=timeout_s,
    )


def open_menu_tester(*, menu_tester_port: int, root_path_fn, ensure_streamlit_app_fn) -> str:
    return open_panel(
        url=f"http://localhost:{menu_tester_port}",
        script_path=root_path_fn("src", "vwait", "entrypoints", "streamlit", "menu_tester.py"),
        port=menu_tester_port,
        ensure_app_streamlit_fn=ensure_streamlit_app_fn,
        label="Menu Tester",
    )


def open_logs_panel(*, logs_panel_port: int, root_path_fn, ensure_streamlit_app_fn) -> str:
    return open_panel(
        url=f"http://localhost:{logs_panel_port}",
        script_path=root_path_fn("src", "vwait", "entrypoints", "streamlit", "painel_logs_radio.py"),
        port=logs_panel_port,
        ensure_app_streamlit_fn=ensure_streamlit_app_fn,
        silence_output=True,
        label="Painel de Logs",
    )


def open_failure_control(*, failure_control_port: int, root_path_fn, ensure_streamlit_app_fn) -> str:
    return open_panel(
        url=f"http://localhost:{failure_control_port}",
        script_path=root_path_fn("src", "vwait", "entrypoints", "streamlit", "controle_falhas.py"),
        port=failure_control_port,
        ensure_app_streamlit_fn=ensure_streamlit_app_fn,
        silence_output=True,
        label="Controle de Falhas",
    )


def create_chat_controller(**kwargs):
    return build_chat_controller(**kwargs)


def render_chat_page(**kwargs):
    return kwargs["render_page_layout_fn"](
        apply_pending_navigation_fn=kwargs["apply_pending_navigation_fn"],
        sidebar_page_selector_fn=kwargs["sidebar_page_selector_fn"],
        render_voice_sidebar_fn=kwargs["render_voice_sidebar_fn"],
        configure_recognizer_fn=kwargs["configure_recognizer_fn"],
        audio_input_to_sr_audio_fn=kwargs["audio_input_to_sr_audio_fn"],
        transcribe_command_audio_fn=kwargs["transcribe_command_audio_fn"],
        process_voice_command_fn=kwargs["process_voice_command_fn"],
        list_categories_fn=kwargs["list_categories_fn"],
        list_tests_fn=kwargs["list_tests_fn"],
        render_benches_sidebar_fn=kwargs["render_benches_sidebar_fn"],
        list_benches_fn=kwargs["list_benches_fn"],
        format_benches_fn=kwargs["format_benches_fn"],
        selected_chat_page=kwargs["selected_chat_page"],
        render_chat_shell_fn=kwargs["render_chat_shell_fn"],
        title_panel_fn=kwargs["title_panel_fn"],
        render_greeting_fn=kwargs["render_greeting_fn"],
        check_finalizations_fn=kwargs["check_finalizations_fn"],
        check_finished_executions_fn=kwargs["check_finished_executions_fn"],
        st_autorefresh_module=kwargs["st_autorefresh_module"],
        sanitize_text_fn=kwargs["sanitize_text_fn"],
        save_partial_result_fn=kwargs["save_partial_result_fn"],
        finalize_recording_fn=kwargs["finalize_recording_fn"],
        cancel_recording_fn=kwargs["cancel_recording_fn"],
        process_user_input_fn=kwargs["process_user_input_fn"],
        render_selected_page_fn=kwargs["render_selected_page_fn"],
        render_mapa_neural_ia_coder_fn=kwargs["render_mapa_neural_ia_coder_fn"],
        apply_panel_button_theme_fn=kwargs["apply_panel_button_theme_fn"],
        open_menu_tester_fn=kwargs["open_menu_tester_fn"],
    )
