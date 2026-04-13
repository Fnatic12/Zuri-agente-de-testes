import streamlit as st


def process_user_input(
    user_input: str,
    *,
    session_state,
    conversation_mode: bool,
    continue_recording_flow_fn,
    conversational_responder_fn,
    command_resolver_fn,
) -> str:
    with st.spinner("Processando comando..."):
        if session_state.pending_gravacao is not None:
            return continue_recording_flow_fn(user_input)
        if conversation_mode:
            return conversational_responder_fn(user_input)
        return command_resolver_fn(user_input)


def render_page_layout(
    *,
    apply_pending_navigation_fn,
    sidebar_page_selector_fn,
    render_voice_sidebar_fn,
    configure_recognizer_fn,
    audio_input_to_sr_audio_fn,
    transcribe_command_audio_fn,
    process_voice_command_fn,
    list_categories_fn,
    list_tests_fn,
    render_benches_sidebar_fn,
    list_benches_fn,
    format_benches_fn,
    selected_chat_page,
    render_chat_shell_fn,
    title_panel_fn,
    render_greeting_fn,
    check_finalizations_fn,
    check_finished_executions_fn,
    st_autorefresh_module,
    sanitize_text_fn,
    save_partial_result_fn,
    finalize_recording_fn,
    cancel_recording_fn,
    process_user_input_fn,
    render_selected_page_fn,
    render_mapa_neural_ia_coder_fn,
    apply_panel_button_theme_fn,
    open_menu_tester_fn,
):
    apply_pending_navigation_fn()
    page = sidebar_page_selector_fn()
    render_voice_sidebar_fn(
        configure_recognizer=configure_recognizer_fn,
        audio_input_to_sr_audio=audio_input_to_sr_audio_fn,
        transcribe_command_audio=transcribe_command_audio_fn,
        process_voice_command=process_voice_command_fn,
        list_categories=list_categories_fn,
        list_tests=list_tests_fn,
    )
    render_benches_sidebar_fn(list_benches=list_benches_fn, format_benches=format_benches_fn)

    if page == selected_chat_page:
        render_chat_shell_fn(
            title_panel=title_panel_fn,
            render_greeting=render_greeting_fn,
            check_finalizations=check_finalizations_fn,
            check_finished_executions=check_finished_executions_fn,
            st_autorefresh=st_autorefresh_module,
            sanitize_text=sanitize_text_fn,
            save_partial_result=save_partial_result_fn,
            finalize_recording=finalize_recording_fn,
            cancel_recording=cancel_recording_fn,
            process_user_input=process_user_input_fn,
        )
        return

    render_selected_page_fn(
        page,
        render_mapa_neural_ia_coder=render_mapa_neural_ia_coder_fn,
        apply_panel_button_theme=apply_panel_button_theme_fn,
        abrir_menu_tester=open_menu_tester_fn,
    )
