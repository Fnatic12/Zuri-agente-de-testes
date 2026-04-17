from __future__ import annotations

import os

import streamlit as st

from ...application import (
    analysis_prompt_for_capture,
    analysis_prompt_for_file,
    human_size,
    load_log_captures,
    ollama_generate,
    open_folder,
    read_file_for_view,
    scan_capture_signals,
    scan_text_signals,
)
from ...domain import HEURISTICS, MAX_VIEW_CHARS
from ...paths import DATA_ROOT
from .theme import titulo_painel


DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("LOGS_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
DEFAULT_OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")
DEFAULT_OLLAMA_NUM_PREDICT = int(os.getenv("LOGS_OLLAMA_NUM_PREDICT", os.getenv("OLLAMA_NUM_PREDICT", "700")))
DEFAULT_OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
DEFAULT_OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
DEFAULT_OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
DEFAULT_OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
DEFAULT_OLLAMA_TIMEOUT_S = int(os.getenv("LOGS_OLLAMA_TIMEOUT_S", os.getenv("OLLAMA_TIMEOUT_S", "120")))


def _analysis_key(kind: str, value: str) -> str:
    return f"ai_result::{kind}::{value}"


def _render_metadata(capture: dict) -> None:
    metadata = capture["metadata"] or {}
    status = str(metadata.get("status") or "desconhecido")
    motivo = str(metadata.get("motivo") or "-")
    total_artifacts = metadata.get("total_artifacts")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Teste", f"{capture['categoria']}/{capture['teste']}")
    col2.metric("Captura", capture["capture_name"])
    col3.metric("Status", status.upper())
    col4.metric("Arquivos", str(len(capture["files"])))

    col5, col6 = st.columns(2)
    col5.caption(f"Motivo: {motivo}")
    if total_artifacts is not None:
        col6.caption(f"Artefatos capturados: {total_artifacts}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Abrir pasta da captura", key=f"open_capture_{capture['capture_dir']}"):
            ok_open, detail_open = open_folder(capture["capture_dir"])
            if ok_open:
                st.success(f"Pasta aberta: {detail_open}")
            else:
                st.error(f"Falha ao abrir pasta: {detail_open}")
    with b2:
        if st.button("Abrir raiz logs/", key=f"open_logs_{capture['logs_dir']}"):
            ok_open, detail_open = open_folder(capture["logs_dir"])
            if ok_open:
                st.success(f"Pasta aberta: {detail_open}")
            else:
                st.error(f"Falha ao abrir pasta: {detail_open}")


def _render_local_analysis(capture: dict) -> None:
    totals, highlights = scan_capture_signals(capture["files"])
    st.markdown("##### Sinais locais detectados")
    cols = st.columns(len(HEURISTICS))
    for idx, label in enumerate(HEURISTICS):
        cols[idx].metric(label.upper(), str(totals.get(label, 0)))

    if not highlights:
        st.info("Nenhum sinal forte encontrado nos trechos lidos localmente.")
        return

    for item in highlights[:8]:
        signal_labels = [f"{label}:{info['count']}" for label, info in item["signals"].items() if info["count"] > 0]
        st.markdown(f"- `{item['arquivo']}` | score `{item['score']}` | {' | '.join(signal_labels)}")


def _render_file_viewer(capture: dict) -> None:
    st.markdown("##### Explorador de arquivos")
    files = capture["files"]
    if not files:
        st.warning("Nenhum arquivo encontrado nesta captura.")
        return

    file_labels = [f"{file_info['relpath']} ({human_size(int(file_info['size']))})" for file_info in files]
    label_map = {label: file_info for label, file_info in zip(file_labels, files)}
    selected_label = st.selectbox("Arquivo", file_labels, key=f"log_file_{capture['capture_dir']}")
    selected_file = label_map[selected_label]

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.caption(f"Tipo: {'imagem' if selected_file['image'] else 'texto' if selected_file['text_like'] else 'binario'}")
    c2.caption(f"Tamanho: {human_size(int(selected_file['size']))}")
    c3.caption(f"Caminho: {selected_file['relpath']}")

    if selected_file["image"]:
        st.image(selected_file["path"], caption=selected_file["relpath"], use_container_width=True)
        return

    if selected_file["text_like"]:
        content, truncated = read_file_for_view(selected_file["path"], max_chars=MAX_VIEW_CHARS)
        signals = scan_text_signals(content)
        badges = [f"{label}:{item['count']}" for label, item in signals.items() if item["count"] > 0]
        if badges:
            st.caption("Sinais no arquivo: " + " | ".join(badges))
        if truncated:
            st.warning("Conteudo truncado para visualizacao.")
        st.text_area("Conteudo do arquivo", content, height=480, key=f"viewer_{selected_file['path']}")
        return

    st.info("Arquivo binario ou nao legivel em texto. Abra a pasta local para inspecao externa.")


def _run_ai_analysis(*, result_key: str, latest_key: str, title: str, prompt: str) -> None:
    st.session_state["vwait_auto_refresh_paused"] = True
    model = str(st.session_state.get("log_ollama_model", DEFAULT_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL)
    base_url = str(st.session_state.get("log_ollama_base_url", DEFAULT_OLLAMA_URL) or DEFAULT_OLLAMA_URL)
    try:
        with st.spinner(f"Analisando com Ollama {model}..."):
            response = ollama_generate(
                prompt,
                base_url=base_url,
                model=model,
                ollama_cli=DEFAULT_OLLAMA_CLI,
                timeout_s=DEFAULT_OLLAMA_TIMEOUT_S,
                num_predict=DEFAULT_OLLAMA_NUM_PREDICT,
                temperature=DEFAULT_OLLAMA_TEMPERATURE,
                top_p=DEFAULT_OLLAMA_TOP_P,
                num_ctx=DEFAULT_OLLAMA_NUM_CTX,
                keep_alive=DEFAULT_OLLAMA_KEEP_ALIVE,
            )
    finally:
        st.session_state["vwait_auto_refresh_paused"] = False

    result_text = response or (
        "Falha ao obter resposta do Ollama. "
        f"Verifique se `{model}` esta disponivel em `{base_url}`."
    )
    st.session_state[result_key] = result_text
    st.session_state[latest_key] = {
        "title": title,
        "content": result_text,
        "model": model,
        "base_url": base_url,
    }
    if response:
        st.success("Analise concluida.")
    else:
        st.error("Ollama nao retornou resposta para esta analise.")


def render_logs_panel_page() -> None:
    titulo_painel("Painel de Logs - GEI", "Exploracao local dos logs capturados e analise assistida por IA")

    if not st.session_state.get("log_ollama_base_url"):
        st.session_state["log_ollama_base_url"] = DEFAULT_OLLAMA_URL
    if not st.session_state.get("log_ollama_model") or st.session_state.get("log_ollama_model") == "llama3.1:3b":
        st.session_state["log_ollama_model"] = DEFAULT_OLLAMA_MODEL

    captures = load_log_captures(DATA_ROOT)
    if not captures:
        st.info("Nenhuma captura de logs encontrada em Data/runs/tester/*/*/*/logs/.")
        return

    filter_text = st.text_input("Filtrar por teste ou pasta", placeholder="Ex.: audio, bluetooth, teste1")
    filtered = captures
    if filter_text.strip():
        token = filter_text.strip().lower()
        filtered = [
            capture
            for capture in captures
            if token in capture["label"].lower() or token in capture["capture_dir"].lower()
        ]

    if not filtered:
        st.warning("Nenhuma captura encontrada para o filtro informado.")
        return

    labels = [f"{capture['label']} | {capture['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}" for capture in filtered]
    capture_map = {label: capture for label, capture in zip(labels, filtered)}
    selected_label = st.selectbox("Selecione a captura de logs", labels)
    capture = capture_map[selected_label]

    with st.expander("Configuracao da IA", expanded=False):
        st.text_input("OLLAMA base URL", key="log_ollama_base_url")
        st.text_input("OLLAMA model", key="log_ollama_model")
        st.caption("O painel usa o mesmo servidor Ollama local do ambiente VWAIT.")

    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    _render_metadata(capture)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    _render_local_analysis(capture)
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        _render_file_viewer(capture)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        st.markdown("##### Analise com IA")
        question = st.text_area(
            "Pergunta opcional",
            value="",
            placeholder="Ex.: houve ANR? qual a causa mais provavel? tem evidencias de bluetooth?",
            key=f"log_ai_question::{capture['capture_dir']}",
            height=100,
        )

        files = capture["files"]
        file_labels = [f"{file_info['relpath']} ({human_size(int(file_info['size']))})" for file_info in files]
        label_map = {label: file_info for label, file_info in zip(file_labels, files)}
        selected_ai_label = st.selectbox("Arquivo para analise individual", file_labels, key=f"ai_file_{capture['capture_dir']}")
        selected_ai_file = label_map[selected_ai_label]

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Analisar arquivo", key=f"analyze_file::{selected_ai_file['path']}"):
                prompt = analysis_prompt_for_file(capture, selected_ai_file, question)
                _run_ai_analysis(
                    result_key=_analysis_key("file", selected_ai_file["path"]),
                    latest_key=_analysis_key("latest", capture["capture_dir"]),
                    title=f"Resultado da analise do arquivo: {selected_ai_file['relpath']}",
                    prompt=prompt,
                )
        with col2:
            if st.button("Analisar captura", key=f"analyze_capture::{capture['capture_dir']}"):
                prompt, used_files = analysis_prompt_for_capture(capture, question)
                _run_ai_analysis(
                    result_key=_analysis_key("capture", capture["capture_dir"]),
                    latest_key=_analysis_key("latest", capture["capture_dir"]),
                    title="Resultado da analise da captura",
                    prompt=prompt,
                )
                st.session_state[f"ai_used_files::{capture['capture_dir']}"] = used_files

        latest_result = st.session_state.get(_analysis_key("latest", capture["capture_dir"]))
        if isinstance(latest_result, dict) and latest_result.get("content"):
            st.markdown(f"###### {latest_result.get('title') or 'Ultima analise'}")
            st.caption(
                f"Modelo: {latest_result.get('model') or '-'} | "
                f"Servidor: {latest_result.get('base_url') or '-'}"
            )
            st.markdown(str(latest_result["content"]))

        file_result = st.session_state.get(_analysis_key("file", selected_ai_file["path"]))
        if file_result:
            with st.expander("Ver resultado salvo para o arquivo selecionado", expanded=False):
                st.markdown(file_result)

        capture_result = st.session_state.get(_analysis_key("capture", capture["capture_dir"]))
        if capture_result:
            used_files = st.session_state.get(f"ai_used_files::{capture['capture_dir']}", [])
            with st.expander("Ver resultado salvo para a captura completa", expanded=False):
                if used_files:
                    st.caption("Arquivos usados: " + ", ".join(used_files))
                st.markdown(capture_result)
        st.markdown("</div>", unsafe_allow_html=True)
