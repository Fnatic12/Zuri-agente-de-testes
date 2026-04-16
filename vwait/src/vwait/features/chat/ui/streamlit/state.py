import threading

import streamlit as st


def configure_page(*, apply_dark_background, apply_panel_button_theme) -> None:
    st.set_page_config(
        page_title="Inteligência Artificial - VWAIT",
        page_icon="",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_dark_background(hide_header=True)
    apply_panel_button_theme()


def initialize_chat_state(*, session_state, preload_whisper_default, init_navigation_state) -> None:
    if "chat_history" not in session_state:
        session_state.chat_history = []
    if "chat_voice_browser_audio_sig" not in session_state:
        session_state.chat_voice_browser_audio_sig = ""
    if "chat_voice_browser_audio_key" not in session_state:
        session_state.chat_voice_browser_audio_key = 0
    if "chat_voice_last_status" not in session_state:
        session_state.chat_voice_last_status = "idle"
    if "coletas_ativas" not in session_state:
        session_state.coletas_ativas = set()
    if "coleta_atual" not in session_state:
        session_state.coleta_atual = None
    if "log_sequence_recording" not in session_state:
        session_state.log_sequence_recording = None
    if "pending_gravacao" not in session_state:
        session_state.pending_gravacao = None
    if "finalizacoes_pendentes" not in session_state:
        session_state.finalizacoes_pendentes = []
    if "execucoes_ativas" not in session_state:
        session_state.execucoes_ativas = []
    if "stt_whisper_warmup_started" not in session_state:
        session_state.stt_whisper_warmup_started = True
        threading.Thread(target=preload_whisper_default, daemon=True).start()
    init_navigation_state()
