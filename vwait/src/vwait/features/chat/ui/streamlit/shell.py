import hashlib
import re
from typing import Callable

import streamlit as st
import streamlit.components.v1 as components


def _render_voice_orb(status: str = "idle") -> None:
    label = {
        "idle": "",
        "listening": "Ouvindo...",
        "processing": "",
        "done": "",
    }.get(status, "")
    st.markdown(
        f"""
        <style>
        .voice-sidebar-offset {{
            height: 1.55rem;
        }}
        .voice-command-shell {{
            position: relative;
            display: none;
            place-items: center;
            padding: 0.15rem 0 0.65rem 0;
        }}
        .voice-orb {{
            width: 86px;
            height: 86px;
            border-radius: 999px;
            position: relative;
            display: grid;
            place-items: center;
            background:
                radial-gradient(circle at 35% 30%, rgba(255,255,255,0.88), rgba(125, 211, 252, 0.45) 18%, transparent 32%),
                radial-gradient(circle at 55% 58%, rgba(59, 130, 246, 0.88), rgba(37, 99, 235, 0.72) 46%, rgba(15, 23, 42, 0.96) 78%);
            box-shadow:
                0 0 0 1px rgba(147, 197, 253, 0.28),
                0 18px 42px rgba(37, 99, 235, 0.28),
                inset 0 1px 12px rgba(255,255,255,0.18);
            animation: voiceIdle 3.2s ease-in-out infinite;
        }}
        .voice-orb::before,
        .voice-orb::after {{
            content: "";
            position: absolute;
            inset: -12px;
            border-radius: inherit;
            border: 1px solid rgba(96, 165, 250, 0.28);
            opacity: 0.75;
            animation: voiceRing 2.2s ease-out infinite;
        }}
        .voice-orb::after {{
            inset: -24px;
            animation-delay: 0.55s;
            opacity: 0.42;
        }}
        .voice-bars {{
            display: flex;
            gap: 4px;
            align-items: center;
            height: 38px;
            z-index: 1;
        }}
        .voice-bars span {{
            width: 5px;
            border-radius: 999px;
            background: rgba(240, 249, 255, 0.96);
            box-shadow: 0 0 12px rgba(240, 249, 255, 0.45);
            animation: voiceBar 1.05s ease-in-out infinite;
        }}
        .voice-bars span:nth-child(1) {{ height: 13px; animation-delay: 0.0s; }}
        .voice-bars span:nth-child(2) {{ height: 24px; animation-delay: 0.12s; }}
        .voice-bars span:nth-child(3) {{ height: 33px; animation-delay: 0.24s; }}
        .voice-bars span:nth-child(4) {{ height: 21px; animation-delay: 0.36s; }}
        .voice-bars span:nth-child(5) {{ height: 15px; animation-delay: 0.48s; }}
        .voice-command-label {{
            margin-top: 0.72rem;
            color: rgba(226, 232, 240, 0.86);
            font-size: 0.86rem;
            text-align: center;
            letter-spacing: 0.01em;
        }}
        body:not(.vwait-voice-listening) .voice-bars span {{
            animation-duration: 1.95s;
            opacity: 0.68;
        }}
        body.vwait-voice-listening .voice-command-shell {{
            display: grid;
        }}
        body.vwait-voice-listening .voice-orb {{
            animation: voiceLive 0.72s ease-in-out infinite;
            box-shadow:
                0 0 0 1px rgba(56, 189, 248, 0.45),
                0 0 34px rgba(14, 165, 233, 0.40),
                0 22px 52px rgba(37, 99, 235, 0.30),
                inset 0 1px 12px rgba(255,255,255,0.22);
        }}
        body.vwait-voice-listening .voice-command-label::after {{
            content: " falando";
            color: #7dd3fc;
        }}
        div[data-testid="stAudioInput"] label {{
            display: none !important;
        }}
        div[data-testid="stAudioInput"] [role="alert"],
        div[data-testid="stAudioInput"] [data-testid="stAlert"],
        div[data-testid="stAudioInput"] p:has(+ div),
        div[data-testid="stAudioInput"] div:has(> p) {{
            border-color: rgba(30, 41, 59, 0.2) !important;
        }}
        div[data-testid="stAudioInput"] {{
            margin-top: -0.15rem;
        }}
        @keyframes voiceIdle {{
            0%, 100% {{ transform: scale(0.96); }}
            50% {{ transform: scale(1.02); }}
        }}
        @keyframes voiceLive {{
            0%, 100% {{ transform: scale(0.98); }}
            50% {{ transform: scale(1.08); }}
        }}
        @keyframes voiceRing {{
            0% {{ transform: scale(0.72); opacity: 0.58; }}
            100% {{ transform: scale(1.35); opacity: 0; }}
        }}
        @keyframes voiceBar {{
            0%, 100% {{ transform: scaleY(0.42); }}
            50% {{ transform: scaleY(1.08); }}
        }}
        </style>
        <div class="voice-command-shell">
            <div class="voice-orb" aria-hidden="true">
                <div class="voice-bars">
                    <span></span><span></span><span></span><span></span><span></span>
                </div>
            </div>
            <div class="voice-command-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _install_voice_widget_state_bridge() -> None:
    components.html(
        """
        <script>
        const root = window.parent?.document || document;
        function hasRecordingSignal() {
          const audioInputs = Array.from(root.querySelectorAll('[data-testid="stAudioInput"]'));
          const text = audioInputs.map(el => el.innerText || '').join(' ').toLowerCase();
          const hasTimer = /0:0[1-9]|0:[1-5][0-9]/.test(text);
          const hasStopLike = /stop|parar|recording|gravando/.test(text);
          return hasTimer || hasStopLike;
        }
        function tick() {
          root.body.classList.toggle('vwait-voice-listening', hasRecordingSignal());
          const audioInputs = Array.from(root.querySelectorAll('[data-testid="stAudioInput"]'));
          for (const el of audioInputs) {
            const nodes = Array.from(el.querySelectorAll('*'));
            for (const node of nodes) {
              const txt = (node.innerText || '').trim();
              if (txt === 'An error has occurred, please try again.') {
                node.style.display = 'none';
              }
            }
          }
        }
        tick();
        setInterval(tick, 180);
        </script>
        """,
        height=0,
        width=0,
    )


def render_voice_sidebar(
    *,
    configure_recognizer: Callable[[], object],
    audio_input_to_sr_audio: Callable[[object], object],
    transcribe_command_audio,
    process_voice_command,
    list_categories,
    list_tests,
) -> None:
    with st.sidebar:
        browser_audio = None
        audio_input_widget = getattr(st, "audio_input", None)
        if callable(audio_input_widget):
            st.markdown('<div class="voice-sidebar-offset"></div>', unsafe_allow_html=True)
            voice_status = str(st.session_state.get("chat_voice_last_status", "idle") or "idle")
            _render_voice_orb(voice_status)
            _install_voice_widget_state_bridge()
            audio_key = int(st.session_state.get("chat_voice_browser_audio_key", 0) or 0)
            browser_audio = audio_input_widget("Falar comando", key=f"chat_voice_browser_audio_{audio_key}")
            st.caption("Use o microfone do navegador para gravar seu comando.")
        else:
            st.button("Falar comando", use_container_width=True, disabled=True)
            st.caption("Gravacao por navegador indisponivel nesta versao do Streamlit.")

    if browser_audio is None:
        return

    try:
        getvalue = getattr(browser_audio, "getvalue", None)
        audio_bytes = getvalue() if callable(getvalue) else b""
        audio_sig = hashlib.sha1(audio_bytes).hexdigest() if audio_bytes else ""
        if audio_sig and audio_sig != st.session_state.get("chat_voice_browser_audio_sig", ""):
            st.session_state.chat_voice_browser_audio_sig = audio_sig
            st.session_state.chat_voice_last_status = "processing"
            recognizer = configure_recognizer()
            st.toast("Reconhecendo fala do navegador...")
            audio = audio_input_to_sr_audio(browser_audio)
            command_text, stt_engine, stt_error = transcribe_command_audio(
                recognizer,
                audio,
                list_categories=list_categories,
                list_tests=list_tests,
            )
            if not command_text:
                detail = f" Detalhes: {stt_error}" if stt_error else ""
                raise RuntimeError("Falha ao reconhecer fala do navegador." + detail)
            st.toast(f"Reconhecido via {stt_engine}")
            st.session_state.chat_voice_last_status = "done"
            process_voice_command(command_text)
            st.session_state.chat_voice_browser_audio_key = int(st.session_state.get("chat_voice_browser_audio_key", 0) or 0) + 1
            st.rerun()
    except Exception as exc:
        st.session_state.chat_voice_last_status = "idle"
        st.session_state.chat_voice_browser_audio_key = int(st.session_state.get("chat_voice_browser_audio_key", 0) or 0) + 1
        st.toast(f"Falha ao reconhecer fala do navegador: {exc}")
        st.rerun()


def render_benches_sidebar(*, list_benches: Callable[[], dict], format_benches: Callable[[dict], str]) -> None:
    with st.sidebar.expander("Bancadas (ADB)"):
        st.markdown(format_benches(list_benches()))
        if st.button("Atualizar lista de bancadas"):
            st.rerun()


def render_chat_shell(
    *,
    title_panel: Callable[[str], None],
    render_greeting: Callable[[str], None],
    check_finalizations: Callable[[], None],
    check_finished_executions: Callable[[], None],
    st_autorefresh,
    sanitize_text: Callable[[str], str],
    save_partial_result: Callable[[str, str, str | None], str],
    finalize_recording: Callable[[str | None, str | None, str | None], str],
    cancel_recording: Callable[[str, str], str],
    process_user_input: Callable[[str], str],
) -> None:
    title_panel("VWAIT - Inteligência Artificial")
    if not st.session_state.chat_history:
        render_greeting("Victor")

    st.markdown(
        """
        <style>
        div[data-testid="InputInstructions"],
        div[data-testid="stTextInput"] [data-testid="InputInstructions"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        div[data-testid="stTextInput"] > div {
            background:
                linear-gradient(180deg, rgba(47, 52, 68, 0.96) 0%, rgba(34, 38, 52, 0.96) 100%) !important;
            border: 1px solid rgba(118, 156, 228, 0.24) !important;
            border-radius: 999px !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.06),
                inset 0 -1px 0 rgba(0, 0, 0, 0.16),
                0 14px 34px rgba(0, 0, 0, 0.28) !important;
            backdrop-filter: blur(8px) !important;
            min-height: 4.85rem !important;
        }
        div[data-testid="stTextInput"] input {
            background: transparent !important;
            border: 0 !important;
            color: #f3f6fb !important;
            font-size: 1.05rem !important;
            min-height: 4.55rem !important;
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }
        div[data-testid="stTextInput"] input::placeholder {
            color: rgba(233, 238, 248, 0.64) !important;
        }
        div[data-testid="stFormSubmitButton"] button,
        div.st-key-chat_inline_submit button {
            height: 4.85rem !important;
            background:
                linear-gradient(180deg, rgba(22, 28, 42, 0.98) 0%, rgba(15, 20, 32, 0.98) 100%) !important;
            border: 1px solid rgba(118, 156, 228, 0.22) !important;
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.05),
                0 10px 24px rgba(0, 0, 0, 0.24) !important;
            border-radius: 999px !important;
            padding: 0 1.3rem !important;
            font-size: 0.92rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.01em !important;
        }
        .chat-help-inline {
            text-align: center;
            color: #9ca3af;
            font-size: 0.95rem;
            margin: -0.25rem 0 1.35rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    check_finalizations()
    check_finished_executions()
    if st.session_state.execucoes_ativas and st_autorefresh is not None:
        st_autorefresh(interval=2000, limit=None, key="chat_exec_watch")

    for idx, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(sanitize_text(msg["content"]))
            if msg["role"] == "assistant" and (
                "Gravando" in msg["content"] or "sequencia padrao de coleta de logs" in msg["content"]
            ):
                match = re.search(
                    r"Gravando\s+\**([a-z0-9_]+)/([a-z0-9_]+)\**\s+na bancada\s+`?([0-9A-Za-z._:-]+)`?",
                    msg["content"],
                )
                category = name = serial = None
                if match:
                    category, name, serial = match.group(1), match.group(2), match.group(3)
                elif "sequencia padrao de coleta de logs" in msg["content"] and st.session_state.log_sequence_recording:
                    recording = st.session_state.log_sequence_recording
                    if isinstance(recording, dict):
                        category_raw = recording.get("categoria")
                        name_raw = recording.get("nome")
                        serial_raw = recording.get("bancada")
                        category = category_raw if isinstance(category_raw, str) else None
                        name = name_raw if isinstance(name_raw, str) else None
                        serial = serial_raw if isinstance(serial_raw, str) else None

                if st.button("Salvar esperado", key=f"esperado_{idx}"):
                    if category and name:
                        response = save_partial_result(category, name, serial)
                    else:
                        response = "Aviso: nao consegui identificar categoria e nome da gravacao para salvar o esperado."
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()

                if st.button("Finalizar gravacao", key=f"finalizar_{idx}"):
                    response = finalize_recording(category, name, serial)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()

                if st.button("Cancelar gravacao", key=f"cancelar_{idx}"):
                    response = (
                        cancel_recording(category, name)
                        if category and name
                        else "Aviso: nao consegui identificar a gravacao para cancelar."
                    )
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    st.rerun()

        st.empty()

    st.session_state.setdefault("chat_inline_input_nonce", 0)
    chat_inline_text_key = f"chat_inline_text_{int(st.session_state.chat_inline_input_nonce)}"
    input_col, submit_col = st.columns([14, 1])
    with input_col:
        user_input = st.text_input(
            "Digite seu comando...",
            key=chat_inline_text_key,
            label_visibility="collapsed",
            placeholder="Digite seu comando...",
            autocomplete="off",
        )
    with submit_col:
        submitted = st.button("ok", use_container_width=True, key="chat_inline_submit")

    st.markdown(
        '<p class="chat-help-inline">Digite ajuda para ver os comandos disponiveis.</p>',
        unsafe_allow_html=True,
    )

    if submitted and user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        response = process_user_input(user_input)
        if response:
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.session_state.chat_inline_input_nonce += 1
        st.rerun()
