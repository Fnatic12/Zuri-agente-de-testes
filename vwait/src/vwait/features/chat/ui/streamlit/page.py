import os
import re
import json
import csv
import hashlib
import shutil
import subprocess
import platform
import socket
import sys
from shutil import which
try:
    import requests
except Exception:
    requests = None
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None
import streamlit as st
import streamlit.components.v1 as components
import unicodedata
from PIL import Image
import matplotlib.pyplot as plt
import time
import urllib.request
from io import BytesIO
from threading import Lock
from datetime import datetime
from difflib import SequenceMatcher
import random
import seaborn as sns
import colorama
import threading
from colorama import Fore, Style
from app.shared.project_paths import project_root, root_path
from app.shared.adb_utils import resolve_adb_path
from vwait.features.chat.ui.streamlit.maps import (
    render_mapa_neural_ia,
    render_mapa_neural_ia_coder,
)
from vwait.features.chat.ui.streamlit.navigation import (
    DASHBOARD_PORT,
    FAILURE_CONTROL_PORT,
    LOGS_PANEL_PORT,
    MENU_TESTER_PORT,
    NAV_PENDING_KEY,
    NAV_RADIO_KEY,
    PAGINA_CHAT,
    PAGINA_CONTROLE_FALHAS,
    PAGINA_DASHBOARD,
    PAGINA_LOGS_RADIO,
    PAGINA_MAPA_NEURAL_IA,
    PAGINA_MENU_TESTER,
    PAGINA_VALIDACAO_HMI,
    apply_pending_navigation,
    init_navigation_state,
    render_selected_page,
    select_page as _selecionar_pagina,
    sidebar_page_selector,
)
from vwait.features.chat.ui.streamlit.runtime import (
    aguardar_porta_local as _aguardar_porta_local,
    garantir_app_streamlit as _runtime_garantir_app_streamlit,
    porta_local_ativa as _porta_local_ativa,
    streamlit_launch_env as _streamlit_launch_env,
    subprocess_windowless_kwargs as _subprocess_windowless_kwargs,
    url_ativa as _url_ativa,
)
from vwait.features.chat.ui.streamlit.routing import (
    interpret_command as _interpret_command,
    resolve_navigation_command as _resolve_navigation_command,
    respond_conversational as _respond_conversational,
)
from vwait.features.chat.ui.streamlit.shell import (
    render_benches_sidebar,
    render_chat_shell,
    render_voice_sidebar,
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
    try:
        if os.name == "nt" and hasattr(colorama, "just_fix_windows_console"):
            colorama.just_fix_windows_console()
            return
        colorama.init(autoreset=True)
    except Exception:
        pass


_init_colorama_safely()

status_lock = Lock()  # lock global de escrita

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:3b")
OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "40"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "256"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
ADB_PATH = resolve_adb_path()

def _resolve_ollama_cli() -> str:
    path = which(OLLAMA_CLI)
    if path:
        return path
    local_app = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "Programs", "Ollama", "ollama.exe")
    if candidate and os.path.exists(candidate):
        return candidate
    return OLLAMA_CLI




def _warmup_ollama():
    def _run():
        try:
            _ollama_generate("Responda apenas com 'ok'.", timeout_s=8, allow_cli=False)
        except Exception:
            pass
    t = threading.Thread(target=_run, daemon=True)
    t.start()

# aquece o modelo uma vez por sess?o
if "ollama_warm" not in st.session_state:
    st.session_state["ollama_warm"] = True
    _warmup_ollama()


























def normalizar_pos_fala(txt: str) -> str:
    # correÃ§Ãµes comuns da fala -> texto
    m = {
        "executa": "executar",
        "executarr": "executar",
        "executtar": "executar",
        "ezecutar": "executar",
        "rode": "rodar",
        "voltar ": "resetar ",
        "volta ": "resetar ",
        "reset ": "resetar ",
        "geral um": "geral 1",
        "geral dois": "geral 2",
        "geral tres": "geral 3",
        "bancada um": "bancada 1",
        "bancada dois": "bancada 2",
        "bancada trÃªs": "bancada 3",
        "na bancada um": "na bancada 1",
        "na bancada dois": "na bancada 2",
        "na bancada trÃªs": "na bancada 3",
        "na ba": "",
        "na ban": "",
        "na banca": "",
        "na bancada": "",
        "rodar todos os teste": "rodar todos os testes",
        "listar a bancada": "listar bancadas",
        "listar bancada": "listar bancadas",
    }
    s = txt.strip().lower()
    for k, v in m.items():
        s = s.replace(k, v)

    t = _replace_number_words(_norm(s))

    if len(re.findall(r"\b(executar|rodar|testar)\b", t)) >= 2 and len(re.findall(r"\bbancada\s+\d+\b", t)) >= 2:
        return s

    token = _extrair_token_teste(t)
    bancada = _extrair_bancada(t)

    if any(p in t for p in ["executar", "rodar", "testar", "rodar o teste"]):
        cat, nome = _resolver_teste(token) if token else (None, None)
        teste = nome or token
        if teste:
            return f"executar {teste}" + (f" na bancada {bancada}" if bancada else "")

    if any(p in t for p in ["gravar", "coletar", "capturar"]):
        cat, nome = _resolver_teste(token) if token else (None, None)
        teste = nome or token
        if teste:
            return f"gravar {teste}" + (f" na bancada {bancada}" if bancada else "")

    if "processar" in t:
        cat, nome = _resolver_teste(token) if token else (None, None)
        teste = nome or token
        if teste:
            return f"processar {teste}"

    if any(p in t for p in ["listar bancada", "listar bancadas", "mostra bancadas", "ver bancadas"]):
        return "listar bancadas"

    return s

def titulo_painel(titulo: str, subtitulo: str = ""):
    subtitulo_html = f'<p class="subtitle">{subtitulo}</p>' if subtitulo else ""
    st.markdown(
        f"""
        <style>
        .main-title {{
            font-size: 2.5rem;
            text-align: center;
            background: linear-gradient(90deg, #12c2e9, #c471ed, #f64f59);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 0.3em;
        }}
        .subtitle {{
            text-align: center;
            color: #AAAAAA;
            font-size: 1rem;
            margin-bottom: 1.8em;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        {subtitulo_html}
        """,
        unsafe_allow_html=True
    )


def saudacao_menu_chat(nome: str = "Victor") -> str:
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return f"Bom dia, {nome}"
    if 12 <= hora < 18:
        return f"Boa tarde, {nome}"
    return f"Boa noite, {nome}"


def render_saudacao_menu_chat(nome: str = "Victor") -> None:
    saudacao = saudacao_menu_chat(nome)
    st.markdown(
        f"""
        <style>
        .claude-greeting-shell {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 34vh;
            padding: 2.4rem 0 1rem 0;
            text-align: center;
        }}
        .claude-greeting {{
            margin: 0;
            font-size: clamp(10.4rem, 20vw, 16.8rem);
            line-height: 0.96;
            font-weight: 700;
            letter-spacing: -0.04em;
            color: #f3f5f7;
        }}
        </style>
        <div class="claude-greeting-shell">
            <h2 class="claude-greeting">{saudacao}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )





def printc(msg, color="white"):
    """
    Imprime mensagens coloridas no terminal e retorna string limpa para uso no Streamlit.
    """
    colors = {
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "red": Fore.RED,
        "white": Style.RESET_ALL,
        "cyan": Fore.CYAN,
        "blue": Fore.BLUE
    }
    print(f"{colors.get(color, '')}{msg}{Style.RESET_ALL}", flush=True)
    return msg  # opcional: retorna a string limpa, Ãºtil se quiser exibir no chat

# === CONFIGURAÃ‡Ã•ES ===
PROJECT_ROOT = project_root()
BASE_DIR = PROJECT_ROOT
DATA_ROOT = root_path("Data")
RUN_SCRIPT = root_path("src", "vwait", "entrypoints", "cli", "run_test.py")
COLETOR_SCRIPT = root_path("Scripts", "coletor_adb.py")
PROCESSAR_SCRIPT = root_path("Pre_process", "processar_dataset.py")
PAUSE_FLAG_PATH = os.path.join(PROJECT_ROOT, "pause.flag")
# STATUS_PATH removido: status agora fica dentro de cada teste

# === MODO CONVERSACIONAL ===
MODO_CONVERSA = True  # Altere para False se quiser desativar as respostas naturais
st.set_page_config(
    page_title="Inteligência Artificial - VWAIT",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_dark_background(hide_header=True)
apply_panel_button_theme()


# === SESSION STATE ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_voice_browser_audio_sig" not in st.session_state:
    st.session_state.chat_voice_browser_audio_sig = ""
if "coletas_ativas" not in st.session_state:
    st.session_state.coletas_ativas = set()
if "coleta_atual" not in st.session_state:
    st.session_state.coleta_atual = None
if "log_sequence_recording" not in st.session_state:
    st.session_state.log_sequence_recording = None
if "pending_gravacao" not in st.session_state:
    st.session_state.pending_gravacao = None
if "finalizacoes_pendentes" not in st.session_state:
    st.session_state.finalizacoes_pendentes = []
if "execucoes_ativas" not in st.session_state:
    st.session_state.execucoes_ativas = []
if "stt_whisper_warmup_started" not in st.session_state:
    st.session_state.stt_whisper_warmup_started = True
    threading.Thread(target=preload_whisper_default, daemon=True).start()
init_navigation_state()

# =========================
# === SUPORTE A BANCADAS ===
# =========================
GLOBAL_LOG_SEQUENCE_CATEGORY = "__system__"
GLOBAL_LOG_SEQUENCE_TEST = "failure_log_sequence_global"
GLOBAL_LOG_SEQUENCE_CSV = os.path.join(DATA_ROOT, "failure_log_sequence.csv")
GLOBAL_LOG_SEQUENCE_RAW_JSON = os.path.join(DATA_ROOT, "failure_log_sequence.raw.json")
GLOBAL_LOG_SEQUENCE_META_JSON = os.path.join(DATA_ROOT, "failure_log_sequence.meta.json")


def _garantir_app_streamlit(script_path: str, port: int, silence_output: bool = False, timeout_s: float = 12.0) -> bool:
    return _runtime_garantir_app_streamlit(
        script_path,
        port,
        base_dir=BASE_DIR,
        silence_output=silence_output,
        timeout_s=timeout_s,
    )


def _abrir_menu_tester() -> str:
    tester_url = f"http://localhost:{MENU_TESTER_PORT}"
    try:
        pronto = _garantir_app_streamlit(
            root_path("src", "vwait", "entrypoints", "streamlit", "menu_tester.py"),
            MENU_TESTER_PORT,
        )
        import webbrowser
        webbrowser.open_new_tab(tester_url)
        if pronto:
            return f"Abrindo o Menu Tester em {tester_url}."
        return f"Menu Tester em inicializacao: {tester_url}."
    except Exception as e:
        return f"Falha ao abrir Menu Tester: {e}"


def _abrir_painel_logs() -> str:
    logs_url = f"http://localhost:{LOGS_PANEL_PORT}"
    try:
        pronto = _garantir_app_streamlit(
            root_path("src", "vwait", "entrypoints", "streamlit", "painel_logs_radio.py"),
            LOGS_PANEL_PORT,
            silence_output=True,
        )
        import webbrowser
        webbrowser.open_new_tab(logs_url)
        if pronto:
            return f"Abrindo o Painel de Logs em {logs_url}."
        return f"Painel de Logs em inicializacao: {logs_url}."
    except Exception as e:
        return f"Falha ao abrir Painel de Logs: {e}"


def _abrir_controle_falhas() -> str:
    panel_url = f"http://localhost:{FAILURE_CONTROL_PORT}"
    try:
        pronto = _garantir_app_streamlit(
            root_path("src", "vwait", "entrypoints", "streamlit", "controle_falhas.py"),
            FAILURE_CONTROL_PORT,
            silence_output=True,
        )
        import webbrowser
        webbrowser.open_new_tab(panel_url)
        if pronto:
            return f"Abrindo o Controle de Falhas em {panel_url}."
        return f"Controle de Falhas em inicializacao: {panel_url}."
    except Exception as e:
        return f"Falha ao abrir Controle de Falhas: {e}"


def _resolver_comando_navegacao(texto: str) -> str | None:
    return _resolve_navigation_command(
        texto,
        normalize=_norm,
        replace_number_words=_replace_number_words,
        select_page=_selecionar_pagina,
        open_menu_tester=_abrir_menu_tester,
        dashboard_page=PAGINA_DASHBOARD,
        logs_page=PAGINA_LOGS_RADIO,
        failures_page=PAGINA_CONTROLE_FALHAS,
        hmi_page=PAGINA_VALIDACAO_HMI,
        brain_page=PAGINA_MAPA_NEURAL_IA,
        chat_page=PAGINA_CHAT,
    )


def _processar_comando_de_voz(command_text: str) -> None:
    process_voice_command(
        command_text,
        normalize_post_speech=normalizar_pos_fala,
        pending_recording=st.session_state.pending_gravacao,
        continue_recording_flow=continuar_fluxo_gravacao,
        conversation_mode=MODO_CONVERSA,
        conversational_responder=responder_conversacional,
        command_resolver=resolver_comando_com_llm_ou_fallback,
        chat_history=st.session_state.chat_history,
    )




def _parse_adb_devices(raw_lines):
    """
    Converte a saÃ­da do 'adb devices' em lista de seriais vÃ¡lidos.
    Considera apenas linhas que terminam com 'device' (online).
    """
    seriais = []
    for ln in raw_lines[1:]:  # pula a primeira linha "List of devices attached"
        ln = ln.strip()
        # Ex: "R58M12345AB\tdevice"
        m = re.match(r"^(\S+)\s+device$", ln)
        if m:
            seriais.append(m.group(1))
    return seriais


def listar_bancadas():
    """Mapeia dispositivos adb em bancadas numeradas: {'1': serial1, '2': serial2, ...}"""
    try:
        result = subprocess.check_output(
            ["adb", "devices"],
            text=True,
            **_subprocess_windowless_kwargs(),
        ).strip().splitlines()
        devices = _parse_adb_devices(result)
        return {str(i + 1): dev for i, dev in enumerate(devices)}
    except Exception:
        return {}

def _formatar_bancadas_str(bancadas: dict) -> str:
    if not bancadas:
        return "Nenhuma bancada conectada."
    linhas = ["**Bancadas disponiveis:**"]
    for k, v in bancadas.items():
        linhas.append(f"{k} -> `{v}`")
    return "\n".join(linhas)

def _resolver_teste(nome_ou_token: str):
    """
    Localiza (categoria, teste) em Data/<categoria>/<teste> aceitando variaÃ§Ãµes:
    'geral2' == 'geral_2' == 'geral-2' == 'geral 2' == 'geral um'.
    """
    if not nome_ou_token:
        return None, None

    alvo_norm = _normalize_token(nome_ou_token)

    cats = listar_categorias()

    # 1) Busca direta por equivalÃªncia normalizada em todas as categorias
    for cat in cats:
        for t in listar_testes(cat):
            if _normalize_token(t) == alvo_norm:
                return cat, t

    # 2) Caso o token venha no formato "categoria_nome" (com qualquer separador)
    parts = re.split(r"[_\-\s]+", _norm(nome_ou_token))
    if parts:
        cand_cat = parts[0]
        if cand_cat in cats:
            resto_norm = _normalize_token("".join(parts[1:]))  # sÃ³ o nome do teste
            for t in listar_testes(cand_cat):
                if _normalize_token(t) in (alvo_norm, resto_norm):
                    return cand_cat, t

    # 3) Fallback: fuzzy match mais tolerante para texto vindo de voz
    candidatos = []
    for cat in cats:
        for t in listar_testes(cat):
            ratio = SequenceMatcher(None, _normalize_token(t), alvo_norm).ratio()
            if ratio >= 0.82:
                candidatos.append((ratio, cat, t))
    candidatos.sort(reverse=True)
    if len(candidatos) == 1:
        _, cat, teste = candidatos[0]
        return cat, teste
    if len(candidatos) > 1 and (candidatos[0][0] - candidatos[1][0]) >= 0.08:
        _, cat, teste = candidatos[0]
        return cat, teste

    return None, None

def _selecionar_bancada(bancada: str | None, bancadas: dict):
    """
    Seleciona o serial a partir da 'bancada' informada.
    Regras:
      - 'todas' => retorna lista com todos os seriais (paralelo)
      - nÃºmero vÃ¡lido => retorna lista com um serial
      - None => pega a primeira disponÃ­vel (se houver)
    Retorna (lista_de_seriais, mensagem_erro_ou_None)
    """
    if not bancadas:
        return [], "ERRO: nenhuma bancada conectada."

    if bancada is None or str(bancada).strip() == "":
        # primeira disponÃ­vel
        return [bancadas[sorted(bancadas.keys(), key=int)[0]]], None

    txt = str(bancada).strip().lower()
    if txt in ("todas", "todas as bancadas", "todas-bancadas", "all"):
        return list(bancadas.values()), None

    if txt.isdigit() and txt in bancadas:
        return [bancadas[txt]], None

    return [], f"ERRO: bancada '{bancada}' nao encontrada. Use **listar bancadas**."

def _popen_host_python(cmd):
    """Wrapper para subprocess.Popen no host (sem adb shell)."""
    try:
        subprocess.Popen(cmd, cwd=BASE_DIR)
        return True, None
    except Exception as e:
        return False, f"Falha ao executar comando: {e}"


def _linhas_csv_sequencia_log(acoes: list[dict]) -> list[dict[str, str]]:
    linhas = []
    for idx, item in enumerate(acoes, start=1):
        acao = item.get("acao") or {}
        tipo = str(acao.get("tipo", "")).strip().lower()
        if not tipo:
            continue

        linha = {
            "tipo": tipo,
            "label": f"passo_{idx:02d}_{tipo}",
            "x": "",
            "y": "",
            "x1": "",
            "y1": "",
            "x2": "",
            "y2": "",
            "duracao_ms": "",
            "duracao_s": "",
            "espera_s": "1.0",
            "texto": "",
            "keyevent": "",
            "device_path": "",
            "output_name": "",
        }

        if tipo in {"tap", "long_press"}:
            linha["x"] = str(acao.get("x", ""))
            linha["y"] = str(acao.get("y", ""))
            if tipo == "long_press":
                linha["duracao_s"] = str(acao.get("duracao_s", "1.0"))
        elif tipo == "swipe":
            linha["x1"] = str(acao.get("x1", ""))
            linha["y1"] = str(acao.get("y1", ""))
            linha["x2"] = str(acao.get("x2", ""))
            linha["y2"] = str(acao.get("y2", ""))
            linha["duracao_ms"] = str(acao.get("duracao_ms", "300"))
        else:
            continue

        linhas.append(linha)
    return linhas


def _exportar_sequencia_global_logs(categoria: str, nome_teste: str, serial: str) -> tuple[bool, str]:
    acoes_path = os.path.join(DATA_ROOT, categoria, nome_teste, "json", "acoes.json")
    if not os.path.exists(acoes_path):
        return False, "acoes.json da sequencia de logs ainda nao foi gerado."

    try:
        with open(acoes_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception as exc:
        return False, f"Falha ao ler acoes.json da sequencia de logs: {exc}"

    acoes = raw.get("acoes") if isinstance(raw, dict) else None
    if not isinstance(acoes, list) or not acoes:
        return False, "Nenhuma acao valida encontrada na sequencia gravada."

    linhas = _linhas_csv_sequencia_log(acoes)
    if not linhas:
        return False, "A sequencia gravada nao gerou taps/swipes/long press exportaveis."

    os.makedirs(os.path.dirname(GLOBAL_LOG_SEQUENCE_CSV), exist_ok=True)
    fieldnames = [
        "tipo",
        "label",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "duracao_ms",
        "duracao_s",
        "espera_s",
        "texto",
        "keyevent",
        "device_path",
        "output_name",
    ]

    try:
        with open(GLOBAL_LOG_SEQUENCE_CSV, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(linhas)

        with open(GLOBAL_LOG_SEQUENCE_RAW_JSON, "w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)

        meta = {
            "categoria_origem": categoria,
            "teste_origem": nome_teste,
            "serial": serial,
            "exportado_em": datetime.now().isoformat(),
            "total_passos": len(linhas),
        }
        with open(GLOBAL_LOG_SEQUENCE_META_JSON, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        return False, f"Falha ao salvar a sequencia global de logs: {exc}"

    return True, f"Sequencia global de coleta de logs salva em `{GLOBAL_LOG_SEQUENCE_CSV}`."

def atualizar_status_bancada(serial, status, categoria=None, nome_teste=None):
    """Atualiza o status atual de cada bancada (executando, ociosa, etc.) de forma isolada e thread-safe."""
    try:
        with status_lock:
            # usa um arquivo separado por bancada dentro da pasta do teste
            status_dir = None
            if categoria and nome_teste:
                status_dir = os.path.join(DATA_ROOT, categoria, nome_teste)
            if not status_dir:
                # fallback seguro: evita gravar em Data raiz
                return
            os.makedirs(status_dir, exist_ok=True)
            status_file = os.path.join(status_dir, f"status_{serial}.json")

            data = {}
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            data.update({
                "status": status,
                "teste": f"{categoria}/{nome_teste}" if categoria and nome_teste else None,
                "atualizado_em": datetime.now().isoformat(),
                "serial": serial,
            })

            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"ERRO: falha ao atualizar status da bancada {serial}: {e}")


def _ler_status_serial(serial: str):
    """Busca o status mais recente do serial em Data/<categoria>/<teste>/status_<serial>.json."""
    latest = None
    latest_ts = None
    for root, _, files in os.walk(DATA_ROOT):
        for name in files:
            if name != f"status_{serial}.json":
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            ts = data.get("atualizado_em") or data.get("inicio")
            if ts is None:
                try:
                    ts = os.path.getmtime(path)
                except Exception:
                    ts = None
            if latest_ts is None or str(ts) > str(latest_ts):
                latest_ts = ts
                latest = data
    return latest


def _capturar_logs_radio_teste(categoria: str, nome_teste: str, serial: str, motivo: str = "captura_manual_chat"):
    src_dir = root_path("src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from vwait.entrypoints.cli.run_test import capturar_logs_teste

    return capturar_logs_teste(categoria, nome_teste, serial, motivo=motivo, limpar_antes=False)


def capturar_log_radio_comando(texto: str) -> str:
    bancadas = listar_bancadas()
    bancada = _extrair_bancada(texto)
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro
    if len(seriais) != 1:
        return "Aviso: informe uma bancada numerada para capturar logs do radio."

    serial = seriais[0]
    token = _extrair_token_teste(texto)
    categoria = None
    nome_teste = None

    if token:
        categoria, nome_teste = _resolver_teste(token)
        if categoria is None or nome_teste is None:
            for cat_try in listar_categorias():
                if token in listar_testes(cat_try):
                    categoria, nome_teste = cat_try, token
                    break
        if categoria is None or nome_teste is None:
            return f"ERRO: teste **{token}** nao encontrado em `Data/*/`."
    else:
        latest = _ler_status_serial(serial)
        teste_ref = str((latest or {}).get("teste", "") or "").strip()
        if "/" in teste_ref:
            categoria, nome_teste = teste_ref.split("/", 1)
        else:
            return "Aviso: informe o teste ou uma bancada que ja tenha execucao registrada para capturar os logs."

    resultado = _capturar_logs_radio_teste(categoria, nome_teste, serial)
    status_captura = str(resultado.get("status", "") or "")
    pasta_logs = resultado.get("artifact_dir")
    erro_logs = resultado.get("error")

    if status_captura == "capturado":
        return f"Logs do radio capturados em **Data/{categoria}/{nome_teste}/{pasta_logs}**."
    if status_captura == "sem_artefatos":
        return f"Nenhum log novo encontrado. Pasta gerada em **Data/{categoria}/{nome_teste}/{pasta_logs}**."
    return f"ERRO: falha ao capturar logs do radio: {erro_logs or 'erro desconhecido'}"



def _ollama_generate(prompt: str, timeout_s: int = 12, allow_cli: bool = True) -> str | None:
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE, "options": {"num_predict": OLLAMA_NUM_PREDICT, "temperature": OLLAMA_TEMPERATURE, "top_p": OLLAMA_TOP_P, "num_ctx": OLLAMA_NUM_CTX}}
    urls = [OLLAMA_URL]
    if "localhost" in OLLAMA_URL:
        urls.append(OLLAMA_URL.replace("localhost", "127.0.0.1"))

    # Prefer requests if available
    if requests is not None:
        for url in urls:
            try:
                r = requests.post(f"{url}/api/generate", json=payload, timeout=timeout_s)
                r.raise_for_status()
                data = r.json()
                return data.get("response", "").strip() or None
            except Exception:
                pass

    # Fallback to stdlib urllib
    for url in urls:
        try:
            req = urllib.request.Request(
                f"{url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                return (data.get("response", "").strip() or None)
        except Exception:
            pass

    # CLI fallback (ollama run)
    if allow_cli:
        try:
            result = subprocess.run(
                [_resolve_ollama_cli(), "run", OLLAMA_MODEL],
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s
            )
            if result.returncode == 0:
                out = (result.stdout or "").strip()
                return out or None
        except Exception:
            pass

    return None


def llm_para_comando(frase: str, testes_disponiveis: list[str], categorias: list[str]) -> str | None:
    """
    Usa LLM local (Ollama) para transformar frase livre em comando cananico.
    Retorna None se o LLM estiver indisponivel ou com baixa confiança.
    """
    prompt = f"""
Classifique em JSON.
Frase: "{frase}"
Comandos: executar/rodar, gravar/coletar, processar, apagar/deletar, listar categorias, listar testes, listar bancadas, resetar, pausar, retomar, parar.
Categorias: {categorias}
Testes: {testes_disponiveis[:25]}
Formato:
{{"acao":"executar|gravar|processar|apagar|listar_categorias|listar_testes|listar_bancadas|resetar|pausar|retomar|parar|nenhuma",
  "teste":"audio_1",
  "categoria":"audio",
  "bancada":"1|todas|",
  "confidence":0.0}}
""".strip()

    try:
        import json as _json
        resp = _ollama_generate(prompt, timeout_s=6, allow_cli=False)
        if not resp:
            return None
        parsed = _json.loads(resp)
    except Exception:
        return None

    if parsed.get("confidence", 0) < 0.6:
        return None

    acao = parsed.get("acao", "")
    teste = parsed.get("teste", "")
    categoria = parsed.get("categoria", "")
    bancada = parsed.get("bancada", "")

    if acao == "executar":
        return f"executar {teste} na bancada {bancada}".strip()
    if acao == "gravar":
        return f"gravar {teste} na bancada {bancada}".strip()
    if acao == "processar":
        return f"processar {teste}".strip()
    if acao == "apagar":
        return f"apagar {teste}".strip()
    if acao == "listar_categorias":
        return "listar categorias"
    if acao == "listar_testes":
        return f"listar testes de {categoria}".strip()
    if acao == "listar_bancadas":
        return "listar bancadas"
    if acao == "resetar":
        return f"resetar {teste} na bancada {bancada}".strip()
    if acao == "pausar":
        return "pausar"
    if acao == "retomar":
        return "retomar"
    if acao == "parar":
        return "parar"
    return None


def llm_responder_chat(frase: str) -> str | None:
    """
    Usa LLM local (Ollama) para responder conversa livre.
    Retorna None se indisponivel.
    """
    prompt = f"""
Responda em pt-BR com no maximo 2 frases.
Se a pergunta for sobre uso, de 1 exemplo de comando.
Usuario: "{frase}"
Assistente:
""".strip()

    try:
        resp = _ollama_generate(prompt, timeout_s=4, allow_cli=False)
        return resp or None
    except Exception:
        return None


def interpretar_comando(comando: str) -> str:
    return _interpret_command(
        comando,
        session_state=st.session_state,
        normalize=_norm,
        has_any=_has_any,
        resolve_navigation=_resolver_comando_navegacao,
        list_categories=listar_categorias,
        list_tests=listar_testes,
        format_benches=_formatar_bancadas_str,
        list_benches=listar_bancadas,
        extract_parallel_executions=_extrair_execucoes_paralelas,
        run_parallel_tests=executar_testes_em_paralelo,
        extract_category=_extrair_categoria,
        extract_test_token=_extrair_token_teste,
        resolve_test=_resolver_teste,
        execute_test=executar_teste,
        extract_bench=_extrair_bancada,
        is_log_sequence_command=_eh_comando_gravar_sequencia_logs,
        record_global_log_sequence=gravar_sequencia_global_logs,
        record_test=gravar_teste,
        process_test=processar_teste,
        delete_test=apagar_teste,
        capture_radio_logs=capturar_log_radio_comando,
        finalize_log_sequence=finalizar_gravacao_sequencia_logs,
        pause_execution=pausar_execucao,
        resume_execution=retomar_execucao,
        stop_execution=parar_execucao,
        execute_keywords=KW_EXECUTAR,
        record_keywords=KW_GRAVAR,
        process_keywords=KW_PROCESS,
        delete_keywords=KW_APAGAR,
        list_keywords=KW_LISTAR,
        help_keywords=KW_AJUDA,
        run_script=RUN_SCRIPT,
        base_dir=BASE_DIR,
    )


def responder_conversacional(comando: str):
    return _respond_conversational(
        comando,
        session_state=st.session_state,
        normalize=_norm,
        resolve_navigation=_resolver_comando_navegacao,
        resolve_command=resolver_comando_com_llm_ou_fallback,
        llm_respond=llm_responder_chat,
        conversation_mode=MODO_CONVERSA,
        continue_recording_flow=continuar_fluxo_gravacao,
        extract_test_token=_extrair_token_teste,
        is_log_sequence_command=_eh_comando_gravar_sequencia_logs,
        start_recording_flow=iniciar_fluxo_gravacao,
        finalize_log_sequence=finalizar_gravacao_sequencia_logs,
    )


def resolver_comando_com_llm_ou_fallback(texto: str) -> str:
    """Tenta LLM local e faz fallback para o parser atual."""
    try:
        cats = listar_categorias()
        testes_ex = []
        for c in cats:
            testes_ex.extend(listar_testes(c))
        cmd = llm_para_comando(texto, testes_ex, cats)
        if cmd:
            return interpretar_comando(cmd)
    except Exception:
        pass
    return interpretar_comando(texto)


def _garantir_dataset_execucao_chat(categoria: str, nome_teste: str) -> tuple[bool, str]:
    caminho_teste = os.path.join(DATA_ROOT, categoria, nome_teste)
    dataset_path = os.path.join(caminho_teste, "dataset.csv")

    os.makedirs(caminho_teste, exist_ok=True)

    if not os.path.exists(dataset_path):
        printc(f"âš™ï¸ Dataset nÃ£o encontrado para {categoria}/{nome_teste}, gerando automaticamente...", "yellow")
        try:
            proc_dataset = subprocess.run(
                [sys.executable, PROCESSAR_SCRIPT, categoria, nome_teste],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            return False, f"ERRO: falha ao processar dataset de {categoria}/{nome_teste}: {e}"

        if proc_dataset.returncode != 0 or not os.path.exists(dataset_path):
            detalhes = "\n".join(
                parte.strip()
                for parte in [proc_dataset.stdout, proc_dataset.stderr]
                if parte and parte.strip()
            )
            if detalhes:
                return False, f"ERRO: falha ao gerar dataset de {categoria}/{nome_teste}.\n{detalhes}"
            return False, f"ERRO: o dataset de {categoria}/{nome_teste} nao foi gerado."

        printc("âœ… Dataset gerado com sucesso.", "green")

    return True, ""


def _iniciar_execucao_no_serial(
    categoria: str, nome_teste: str, serial: str, bancada_label: str | None = None
) -> str:
    caminho_teste = os.path.join(DATA_ROOT, categoria, nome_teste)
    log_path = os.path.join(caminho_teste, "execucao_log.json")

    status_atual = _ler_status_serial(serial) or {}
    if str(status_atual.get("status", "")).lower() == "executando":
        return f"Aviso: a bancada `{serial}` ja esta executando outro teste."

    atualizar_status_bancada(serial, "executando", categoria, nome_teste)

    inicio = datetime.now().isoformat()
    log_entry = {
        "acao": "execucao_iniciada",
        "categoria": categoria,
        "teste": nome_teste,
        "serial": serial,
        "inicio": inicio
    }
    _registrar_log(log_path, log_entry)

    cmd = [sys.executable, RUN_SCRIPT, categoria, nome_teste, "--serial", serial]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        def _monitor_processo(p, serial, categoria, nome_teste):
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                atualizar_status_bancada(serial, "erro", categoria, nome_teste)
                printc(f"ERRO: execucao do teste {categoria}/{nome_teste} falhou na bancada {serial}.", "red")
                print(stdout.decode(errors="ignore"))
                print(stderr.decode(errors="ignore"))

                if MODO_CONVERSA and "chat_history" in st.session_state:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"ERRO: o teste **{categoria}/{nome_teste}** falhou na bancada `{serial}`."
                    })
            else:
                atualizar_status_bancada(serial, "finalizado", categoria, nome_teste)
                printc(f"OK: teste {categoria}/{nome_teste} finalizado na bancada {serial}.", "green")

                if MODO_CONVERSA and "chat_history" in st.session_state:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"OK: teste **{categoria}/{nome_teste}** finalizado na bancada `{serial}`."
                    })

                try:
                    st.rerun()
                except Exception:
                    pass

        threading.Thread(
            target=_monitor_processo,
            args=(proc, serial, categoria, nome_teste),
            daemon=True
        ).start()

        st.session_state.execucoes_ativas.append({
            "serial": serial,
            "categoria": categoria,
            "nome_teste": nome_teste,
            "status_file": os.path.join(DATA_ROOT, categoria, nome_teste, f"status_{serial}.json"),
            "proc": proc,
        })

        prefixo = f"{bancada_label}: " if bancada_label else ""
        printc(f"ðŸš€ Teste {categoria}/{nome_teste} iniciado em {serial} (PID={proc.pid})", "cyan")
        return f"{prefixo}Executando **{categoria}/{nome_teste}** na bancada `{serial}` em background..."

    except Exception as e:
        atualizar_status_bancada(serial, "erro", categoria, nome_teste)
        return f"ERRO: falha ao iniciar execucao na bancada `{serial}`: {e}"


def executar_teste(categoria: str, nome_teste: str, bancada: str | None = None) -> str:
    """
    Executa teste no host em background, permitindo paralelismo entre bancadas.
    Cada processo Ã© isolado e atualizado em status_bancadas.json.
    """
    ok_dataset, erro_dataset = _garantir_dataset_execucao_chat(categoria, nome_teste)
    if not ok_dataset:
        return erro_dataset or f"ERRO: falha ao preparar dataset de {categoria}/{nome_teste}."

    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return str(erro)

    respostas = []

    for serial in seriais:
        respostas.append(_iniciar_execucao_no_serial(categoria, nome_teste, serial))

    return "\n".join(respostas)


def _registrar_log(caminho_log, nova_entrada):
    """Adiciona entrada ao execucao_log.json, criando se nÃ£o existir."""
    try:
        if os.path.exists(caminho_log):
            with open(caminho_log, "r", encoding="utf-8") as f:
                dados = json.load(f)
        else:
            dados = []

        dados.append(nova_entrada)

        with open(caminho_log, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"âš ï¸ Falha ao registrar log: {e}")


def iniciar_fluxo_gravacao():
    st.session_state.pending_gravacao = {"step": "categoria"}
    return "Qual categoria voce quer gravar?"


def _eh_comando_gravar_sequencia_logs(texto: str) -> bool:
    texto_norm = _norm(texto)
    return (
        any(p in texto_norm for p in ["gravar", "grave", "coletar", "colete", "capturar"])
        and "sequencia" in texto_norm
        and "log" in texto_norm
        and any(p in texto_norm for p in ["padrao", "global", "coleta"])
    )


def gravar_sequencia_global_logs(bancada: str | None = None):
    resposta = gravar_teste(GLOBAL_LOG_SEQUENCE_CATEGORY, GLOBAL_LOG_SEQUENCE_TEST, bancada)
    if resposta.startswith("ERRO:"):
        return resposta

    serial_resolvido: str | None = None
    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if not erro and seriais:
        serial_resolvido = seriais[0]

    st.session_state.log_sequence_recording = {
        "categoria": GLOBAL_LOG_SEQUENCE_CATEGORY,
        "nome": GLOBAL_LOG_SEQUENCE_TEST,
        "bancada": serial_resolvido or bancada,
        "iniciado_em": datetime.now().isoformat(),
    }
    return (
        "Gravando **sequencia padrao de coleta de logs**. "
        "Quando terminar, use **finalizar gravacao da sequencia de log** ou clique em **Finalizar gravacao**. "
        f"O arquivo global sera salvo em `{GLOBAL_LOG_SEQUENCE_CSV}`."
    )


def finalizar_gravacao_sequencia_logs():
    recording = st.session_state.log_sequence_recording
    if not isinstance(recording, dict):
        return "Aviso: nao existe gravacao da sequencia de log em andamento."

    categoria = recording.get("categoria")
    nome = recording.get("nome")
    bancada = recording.get("bancada")
    if not isinstance(categoria, str) or not isinstance(nome, str) or not isinstance(bancada, str):
        return "Aviso: a gravacao da sequencia de log nao possui contexto suficiente para finalizar."

    return finalizar_gravacao(
        categoria,
        nome,
        bancada,
    )


def continuar_fluxo_gravacao(resposta: str):
    pg = st.session_state.pending_gravacao or {"step": "categoria"}
    step = pg.get("step")

    if step == "categoria":
        categoria = resposta.strip().lower().replace(" ", "_")
        if not categoria:
            return "Informe a categoria do teste."
        pg["categoria"] = categoria
        pg["step"] = "nome"
        st.session_state.pending_gravacao = pg
        return "Qual nome do teste voce quer gravar?"

    if step == "nome":
        nome = resposta.strip().lower().replace(" ", "_")
        if not nome:
            return "Informe o nome do teste."
        pg["nome"] = nome

        bancadas = listar_bancadas()
        if len(bancadas) > 1:
            pg["step"] = "bancada"
            st.session_state.pending_gravacao = pg
            return "Qual bancada voce esta? (ex: 1, 2, 3)"

        # executa direto (0 ou 1 bancada)
        st.session_state.pending_gravacao = None
        return gravar_teste(pg["categoria"], pg["nome"], None)

    if step == "bancada":
        b = _extrair_bancada(resposta)
        if not b:
            return "Informe a bancada (ex: 1, 2, 3)."
        st.session_state.pending_gravacao = None
        return gravar_teste(pg["categoria"], pg["nome"], b)

    st.session_state.pending_gravacao = None
    return "Nao entendi. Tente novamente."


def checar_finalizacoes():
    """Verifica se resultado_final.png foi gerado e avisa no chat."""
    pend = list(st.session_state.finalizacoes_pendentes)
    restantes = []
    for item in pend:
        modo: str | None = None
        cat: str | None = None
        nome: str | None = None
        serial: str | None = None
        if isinstance(item, dict):
            cat_raw = item.get("categoria")
            nome_raw = item.get("nome")
            serial_raw = item.get("serial")
            modo_raw = item.get("mode")
            cat = cat_raw if isinstance(cat_raw, str) and cat_raw else None
            nome = nome_raw if isinstance(nome_raw, str) and nome_raw else None
            serial = serial_raw if isinstance(serial_raw, str) and serial_raw else None
            modo = modo_raw if isinstance(modo_raw, str) and modo_raw else None
        else:
            try:
                cat_raw, nome_raw, serial_raw = item
            except Exception:
                continue
            cat = cat_raw if isinstance(cat_raw, str) and cat_raw else None
            nome = nome_raw if isinstance(nome_raw, str) and nome_raw else None
            serial = serial_raw if isinstance(serial_raw, str) and serial_raw else None

        if not cat or not nome:
            continue

        path_final = os.path.join(DATA_ROOT, cat, nome, "resultado_final.png")
        if os.path.exists(path_final):
            if modo == "global_log_sequence":
                if not serial:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": "Coleta finalizada, mas o serial da gravacao da sequencia global nao foi encontrado.",
                    })
                    st.session_state.log_sequence_recording = None
                    continue
                ok, msg = _exportar_sequencia_global_logs(cat, nome, serial)
                st.session_state.log_sequence_recording = None
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": msg if ok else f"Coleta finalizada, mas nao consegui exportar a sequencia global: {msg}",
                })
            else:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Coleta finalizada: {cat}/{nome} (bancada {serial})."
                })
        else:
            restantes.append(item)
    st.session_state.finalizacoes_pendentes = restantes


def checar_execucoes_finalizadas():
    """Verifica execucoes em background e notifica no chat quando finalizarem."""
    ativos = list(st.session_state.execucoes_ativas)
    restantes = []
    for item in ativos:
        serial = item.get("serial")
        categoria = item.get("categoria")
        nome_teste = item.get("nome_teste")
        status_file = item.get("status_file")
        proc = item.get("proc")

        finalizou = False
        sucesso = False

        try:
            if proc is not None and proc.poll() is not None:
                finalizou = True
                sucesso = proc.returncode == 0
        except Exception:
            pass

        if not finalizou and status_file and os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                st_b = str(status_data.get("status", "")).lower()
                if st_b in ("finalizado", "erro"):
                    finalizou = True
                    sucesso = st_b == "finalizado"
            except Exception:
                pass

        if finalizou:
            if sucesso:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": (
                        f"Teste {categoria}/{nome_teste} finalizado na bancada `{serial}`. "
                        "Voce ja pode verificar o resultado no dashboard."
                    ),
                })
            else:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": (
                        f"Teste {categoria}/{nome_teste} finalizou com erro na bancada `{serial}`. "
                        "Verifique os logs e o dashboard."
                    ),
                })
        else:
            restantes.append(item)

    st.session_state.execucoes_ativas = restantes


def _adb_cmd(serial=None):
    if serial:
        return [ADB_PATH, "-s", serial]
    return [ADB_PATH]


def salvar_resultado_parcial(categoria, nome_teste, serial=None):
    """Salva uma screenshot de resultado esperado sem parar a gravação."""
    base_dir = os.path.join(DATA_ROOT, categoria, nome_teste)
    esperados_dir = os.path.join(base_dir, "esperados")
    os.makedirs(esperados_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_name = f"esperado_{ts}.png"
    img_path = os.path.join(esperados_dir, img_name)
    try:
        cmd = _adb_cmd(serial) + ["exec-out", "screencap", "-p"]
        with open(img_path, "wb") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return f"Resultado esperado salvo: {img_name}"
        return "Falha ao salvar resultado esperado."
    except Exception as e:
        return f"Falha ao salvar resultado esperado: {e}"


def gravar_teste(categoria, nome_teste, bancada: str | None = None):
    """
    Grava teste no host, encaminhando o serial como parÃ¢metro para o coletor.
    Obs.: espera que Scripts/coletor_adb.py aceite '--serial <SERIAL>'.
    """
    # limpa flags antigas para nao encerrar a coleta imediatamente
    stop_path = os.path.join(PROJECT_ROOT, "stop.flag")
    if os.path.exists(stop_path):
        try:
            os.remove(stop_path)
        except Exception:
            pass

    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro

    respostas = []
    for serial in seriais:
        cmd = ["python", COLETOR_SCRIPT, categoria, nome_teste, "--serial", serial]
        ok, msg = _popen_host_python(cmd)
        if ok:
            respostas.append(f"Gravando **{categoria}/{nome_teste}** na bancada `{serial}`...")
        else:
            respostas.append(f"ERRO: {msg}")
    return "\n".join(respostas)


def finalizar_gravacao(categoria=None, nome_teste=None, serial=None):
    """Encerra coletas ativas criando stop.flag (igual ao menu_tester)."""
    stop_path = os.path.join(PROJECT_ROOT, "stop.flag")
    try:
        with open(stop_path, "w") as f:
            f.write("stop")

        def _cleanup():
            try:
                time.sleep(15)
                if os.path.exists(stop_path):
                    os.remove(stop_path)
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()
        if categoria and nome_teste and serial:
            if categoria == GLOBAL_LOG_SEQUENCE_CATEGORY and nome_teste == GLOBAL_LOG_SEQUENCE_TEST:
                st.session_state.finalizacoes_pendentes.append(
                    {
                        "categoria": categoria,
                        "nome": nome_teste,
                        "serial": serial,
                        "mode": "global_log_sequence",
                    }
                )
            else:
                st.session_state.finalizacoes_pendentes.append((categoria, nome_teste, serial))
        st.session_state.coleta_atual = None
        if categoria == GLOBAL_LOG_SEQUENCE_CATEGORY and nome_teste == GLOBAL_LOG_SEQUENCE_TEST:
            return (
                "Finalizando gravacao da sequencia de log... "
                "apos o print final, vou exportar automaticamente para o arquivo global."
            )
        return "Finalizando gravacao... toque na tela do radio para capturar o print final."
    except Exception as e:
        return f"Falha ao finalizar gravacao: {e}"

def cancelar_gravacao(categoria=None, nome_teste=None):
    if categoria and nome_teste:
        try:
            caminho = os.path.join(DATA_ROOT, categoria, nome_teste)
            if os.path.exists(caminho):
                shutil.rmtree(caminho)
        except Exception:
            pass
    stop_path = os.path.join(PROJECT_ROOT, "stop.flag")
    try:
        with open(stop_path, "w") as f:
            f.write("stop")
    except Exception:
        pass
    st.session_state.coleta_atual = None
    if categoria == GLOBAL_LOG_SEQUENCE_CATEGORY and nome_teste == GLOBAL_LOG_SEQUENCE_TEST:
        st.session_state.log_sequence_recording = None
    return "Gravacao cancelada e teste removido."


def processar_teste(categoria, nome_teste):
    cmd = ["python", PROCESSAR_SCRIPT, categoria, nome_teste]
    ok, msg = _popen_host_python(cmd)
    if ok:
        return f"Processando dataset de **{categoria}/{nome_teste}**..."
    return f"ERRO: {msg}"

def apagar_teste(categoria, nome_teste):
    caminho = os.path.join(DATA_ROOT, categoria, nome_teste)
    if os.path.exists(caminho):
        shutil.rmtree(caminho)
        return f"Teste **{categoria}/{nome_teste}** apagado com sucesso."
    return f"ERRO: teste {categoria}/{nome_teste} nao encontrado."

def listar_categorias():
    if not os.path.isdir(DATA_ROOT):
        return []
    return [c for c in os.listdir(DATA_ROOT) if os.path.isdir(os.path.join(DATA_ROOT, c))]

def listar_testes(categoria):
    cat_path = os.path.join(DATA_ROOT, categoria)
    if os.path.isdir(cat_path):
        return [t for t in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, t))]
    return []

def pausar_execucao():
    """
    Cria o arquivo pause.flag para pausar a execucao em andamento.
    """
    try:
        with open(PAUSE_FLAG_PATH, "w") as f:
            f.write("PAUSED")
        return "Execucao pausada. O runner sera interrompido no proximo checkpoint."
    except Exception as e:
        return f"ERRO: falha ao pausar execucao: {e}"

def retomar_execucao():
    """
    Remove o arquivo pause.flag, permitindo continuar a execucao.
    """
    try:
        if os.path.exists(PAUSE_FLAG_PATH):
            os.remove(PAUSE_FLAG_PATH)
            return "Execucao retomada."
        else:
            return "Aviso: nenhuma execucao estava pausada."
    except Exception as e:
        return f"ERRO: falha ao retomar execucao: {e}"

def parar_execucao():
    """
    Cria o arquivo stop.flag para parar completamente o runner.
    """
    stop_path = os.path.join(PROJECT_ROOT, "stop.flag")
    try:
        with open(stop_path, "w") as f:
            f.write("STOP")
        return "Execucao interrompida completamente."
    except Exception as e:
        return f"ERRO: falha ao interromper execucao: {e}"

# ======================================
# === FUNÃ‡Ã•ES AUXILIARES DO DASHBOARD ===
# ======================================
def carregar_logs(data_root=DATA_ROOT):
    logs = []
    if not os.path.isdir(data_root):
        return logs
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

def calcular_metricas(execucao):
    total = len(execucao)
    acertos = sum(1 for a in execucao if "OK" in a.get("status", "").upper())
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", "")) if total > 0 else 0
    tempo_total = sum(a.get("duracao", 1) for a in execucao)
    cobertura = round((len({a.get("tela", f"id{a.get('id')}") for a in execucao}) / total) * 100, 1) if total > 0 else 0
    precisao = round((acertos / total) * 100, 2) if total > 0 else 0

    return {
        "total_acoes": total,
        "acertos": acertos,
        "falhas": falhas,
        "flakes": flakes,
        "precisao_percentual": precisao,
        "tempo_total": tempo_total,
        "cobertura_telas": cobertura,
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO"
    }

def exibir_metricas(metricas):
    st.subheader("Metricas gerais")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de acoes", metricas["total_acoes"])
    col2.metric("Acertos", metricas["acertos"])
    col3.metric("Falhas", metricas["falhas"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Precisao (%)", metricas["precisao_percentual"])
    col5.metric("Instabilidades", metricas["flakes"])
    col6.metric("Cobertura de Telas (%)", metricas["cobertura_telas"])

    st.caption("Instabilidades = acoes com status `FLAKE`, indicando falha intermitente ou comportamento inconsistente.")

    st.metric("Tempo total de execucao (s)", metricas["tempo_total"])

    if metricas["resultado_final"] == "APROVADO":
        st.success("APROVADO")
    else:
        st.error("REPROVADO")

    fig, ax = plt.subplots()
    labels = ["Acertos", "Falhas"]
    sizes = [metricas["acertos"], metricas["falhas"]]
    colors = ["#4CAF50", "#F44336"]
    explode = (0.05, 0)
    ax.pie(sizes, explode=explode, labels=labels, colors=colors,
           autopct="%1.1f%%", shadow=True, startangle=90)
    ax.axis("equal")
    st.pyplot(fig)

def exibir_timeline(execucao):
    st.subheader("Timeline da execucao")

    # Extrai e normaliza dados
    tempos = [int(float(a.get("duracao", 1))) for a in execucao]
    ids = []
    for idx, a in enumerate(execucao):
        # Garante que o ID seja numÃ©rico
        val = a.get("id", idx + 1)
        try:
            ids.append(int(val))
        except (ValueError, TypeError):
            ids.append(idx + 1)

    # Cores por status
    status = ["green" if "OK" in a.get("status", "").upper() else "red" for a in execucao]

    # Cria o grÃ¡fico
    fig, ax = plt.subplots()
    ax.bar(ids, tempos, color=status)
    ax.set_xlabel("Acao")
    ax.set_ylabel("Duracao (s)")
    ax.set_title("Tempo por acao")

    # Deixa o eixo X limpo (sem notaÃ§Ã£o cientÃ­fica)
    # Evita warnings de stub: nÃ£o usar set_useOffset diretamente
    # (o formato padrÃ£o jÃ¡ Ã© suficiente para o grÃ¡fico)

    st.pyplot(fig)

def exibir_acoes(execucao, base_dir):
    st.subheader("Detalhes das acoes")
    for acao in execucao:
        titulo = f"Acao {acao.get('id')} - {str(acao.get('acao','')).upper()} | {acao.get('status','')}"
        with st.expander(titulo):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao.get("frame_esperado",""))
            resultado_path = os.path.join(base_dir, acao.get("screenshot",""))

            if frame_path and os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {acao.get('frame_esperado','')}", use_container_width=True)
            else:
                col1.warning("Frame esperado nao encontrado")

            if resultado_path and os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Obtido: {acao.get('screenshot','')}", use_container_width=True)
            else:
                col2.warning("Screenshot nao encontrado")

            if "similaridade" in acao:
                st.write(f"Similaridade: **{acao['similaridade']:.2f}**")
            st.write(f"Duracao: **{acao.get('duracao', 0)}s**")
            if "coordenadas" in acao:
                st.json(acao.get("coordenadas", {}))
            if "log" in acao:
                st.code(acao["log"], language="bash")

def exibir_mapa_calor(execucao):
    st.subheader("Mapa de calor dos toques")
    xs = [a["coordenadas"]["x"] for a in execucao if "coordenadas" in a and "x" in a["coordenadas"]]
    ys = [a["coordenadas"]["y"] for a in execucao if "coordenadas" in a and "y" in a["coordenadas"]]

    if xs and ys:
        fig, ax = plt.subplots()
        sns.kdeplot(x=xs, y=ys, cmap="Reds", fill=True, ax=ax, thresh=0.05)
        ax.invert_yaxis()
        st.pyplot(fig)
    else:
        st.warning("Sem coordenadas para gerar mapa de calor.")

def exibir_validacao_final(execucao, base_dir):
    st.subheader("Validacao final da tela")
    resultado_final_path = os.path.join(base_dir, "resultado_final.png")

    col1, col2 = st.columns(2)
    if execucao:
        ultima = execucao[-1]
        frame_path = os.path.join(base_dir, ultima.get("frame_esperado",""))

        if frame_path and os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (ultima acao)", use_container_width=True)
        else:
            col1.error("Frame esperado nao encontrado")

        if os.path.exists(resultado_final_path):
            col2.image(Image.open(resultado_final_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png nao encontrado")

        if "similaridade" in ultima:
            st.write(f"Similaridade final: **{ultima['similaridade']:.2f}**")
        if "OK" in ultima.get("status","").upper():
            st.success("Tela final validada")
        else:
            st.error("Tela final divergente")
    else:
        st.warning("Nenhuma acao registrada")

def exibir_regressoes(execucao):
    st.subheader("Analise de regressoes")
    falhas = [a for a in execucao if "OK" not in a.get("status","").upper()]
    if falhas:
        st.write("Top falhas nesta execucao:")
        for f in falhas:
            sim = f.get("similaridade")
            sim_str = f"{sim:.2f}" if isinstance(sim, (int, float)) else "N/A"
            st.write(f"- Acao {f.get('id')} ({f.get('acao','')}): Similaridade {sim_str}")
    else:
        st.success("Nenhuma falha registrada")

# ===========================
# === PARSER DE COMANDOS  ===
# ===========================
# Palavras-chave com variaÃ§Ãµes comuns (sem acento e lower)
KW_EXECUTAR = [
    "executar", "execute", "rodar", "rode", "run", "iniciar teste",
    "inicia o teste", "comeÃ§a o teste", "roda o teste", "faz o teste",
    "testa", "teste agora", "starta o teste", "comeÃ§ar teste", "faÃ§a o teste",
    "rodar tudo", "rodar todos", "rodar todos os testes", "executa tudo"
]

KW_GRAVAR = [
    "gravar", "grave", "coletar", "colete", "capturar", "record",
    "comeÃ§ar gravaÃ§Ã£o", "iniciar gravaÃ§Ã£o", "grava agora", "fazer gravaÃ§Ã£o",
    "fazer coleta", "comeÃ§ar coleta", "startar gravaÃ§Ã£o", "inicia a coleta",
    "comeÃ§a a gravar", "grava o gesto", "grava o teste"
]

KW_PROCESS = [
    "processar", "processa", "prÃ©-processar", "preprocessar", "pre", "gerar dataset",
    "processa o dataset", "gera o dataset", "montar dataset", "gerar base",
    "monta o csv", "gerar csv", "converter dados", "processa os dados"
]

KW_APAGAR = [
    "apagar", "apague", "deletar", "delete", "remover", "remova", "excluir", "exclua",
    "apaga", "apaga o teste", "deleta o teste", "limpa", "limpar teste", "remove o teste",
    "apagar teste", "excluir teste", "deleta tudo"
]

KW_LISTAR = [
    "listar", "liste", "mostrar", "mostre", "exibir", "exiba", "lista", "me mostra",
    "me exibe", "quais sÃ£o", "ver", "ver lista", "ver testes", "mostra pra mim",
    "quero ver", "ver categorias", "mostrar categorias", "mostrar testes"
]

KW_BANCADAS = [
    "bancada", "bancadas", "devices", "dispositivos", "adb", "hardware conectado",
    "listar bancadas", "mostrar bancadas", "listar dispositivos", "mostrar dispositivos",
    "quais bancadas", "tem bancada", "quais estÃ£o conectadas", "ver bancadas",
    "ver dispositivos", "me mostra as bancadas", "fala as bancadas", "lista as bancadas"
]

KW_AJUDA = [
    "ajuda", "help", "comandos", "o que posso dizer", "fala os comandos",
    "me ajuda", "quais comandos", "mostra os comandos", "explica comandos",
    "fala os exemplos", "ensina", "socorro"
]

_NUM_PT = {
    "zero":"0","um":"1","uma":"1","dois":"2","duas":"2","tres":"3","trÃªs":"3",
    "quatro":"4","cinco":"5","seis":"6","sete":"7","oito":"8","nove":"9","dez":"10",
    "onze":"11","doze":"12","treze":"13","catorze":"14","quatorze":"14","quinze":"15",
    "dezesseis":"16","dezessete":"17","dezoito":"18","dezenove":"19","vinte":"20"
}

def _replace_number_words(s: str) -> str:
    """Troca nÃºmeros por extenso (pt-BR) por dÃ­gitos no texto normalizado."""
    for k, v in _NUM_PT.items():
        s = re.sub(rf"\b{k}\b", v, s)
    return s

def _normalize_token(s: str) -> str:
    """Normaliza nomes de teste para comparaÃ§Ã£o: lower, sem acentos e sem separadores."""
    s = _norm(s)
    s = re.sub(r"[\s_-]+", "", s)  # remove espaÃ§o, _ e -
    return s

def _norm(s: str) -> str:
    """Lower + remove acentos para matching robusto."""
    s = s.strip().lower()
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")

from difflib import SequenceMatcher

def _has_any(texto_norm: str, termos: list[str]) -> bool:
    texto_norm = _norm(texto_norm)
    termos_norm = [_norm(t) for t in termos]
    for termo in termos_norm:
        ratio = SequenceMatcher(None, texto_norm, termo).ratio()
        if termo in texto_norm or ratio > 0.8:
            return True
    return False

def _extrair_bancada(texto: str) -> str | None:
    """
    Extrai a bancada do comando.
    Suporta: "na bancada 2", "bancada=2", "bancada2", "todas as bancadas", "bancada um".
    Retorna "2", "todas" ou None.
    """
    t = _replace_number_words(_norm(texto))

    # todas as bancadas
    if re.search(r"\btodas(\s+as\s+)?bancadas\b", t) or re.search(r"\ball\b", t):
        return "todas"

    m = re.search(r"bancada\s*=\s*(\d+)", t)
    if m:
        return m.group(1)

    m = re.search(r"\bbancada\s*(\d+)\b", t)
    if m:
        return m.group(1)

    return None

def _extrair_token_teste(texto: str) -> str | None:
    """
    Extrai o nome do teste em diferentes formatos e devolve forma canÃ´nica 'base_numero':
    - geral_2, geral-2, geral2, geral 2, geral um  -> sempre retorna 'geral_2'
    """
    t = _replace_number_words(_norm(texto))

    # 1) com _ ou -
    m = re.search(r"\b([a-z0-9]+)[_\-]([0-9]+)\b", t)
    if m:
        return f"{m.group(1)}_{m.group(2)}"

    # 2) colado: 'geral2'
    m = re.search(r"\b([a-z]+)(\d+)\b", t)
    if m:
        return f"{m.group(1)}_{m.group(2)}"

    # 3) com espaÃ§o: 'geral 2'
    m = re.search(r"\b([a-z]+)\s+(\d+)\b", t)
    if m:
        return f"{m.group(1)}_{m.group(2)}"

    return None

def _extrair_categoria(texto: str) -> str | None:
    """
    Se o usuÃ¡rio pedir 'testes de <categoria>' ou mencionar explicitamente uma categoria existente.
    """
    t = _norm(texto)
    # padrÃ£o 'de <categoria>'
    m = re.search(r"\bde\s+([a-z0-9_-]+)\b", t)
    if m and m.group(1) in listar_categorias():
        return m.group(1)
    # ou se o nome da categoria aparecer diretamente no texto
    for cat in listar_categorias():  
        if _norm(cat) in t:
            return cat
    return None


def _resolver_execucao_de_trecho(texto: str) -> tuple[str | None, str | None, str | None]:
    token = _extrair_token_teste(texto)
    if token:
        cat, nome = _resolver_teste(token)
        if cat and nome:
            return cat, nome, None

        for cat_try in listar_categorias():
            if token in listar_testes(cat_try):
                return cat_try, token, None

        return None, None, f"ERRO: teste **{token}** nao encontrado em `Data/*/`."

    return None, None, "Aviso: nao encontrei o nome do teste em um dos comandos paralelos."


def _extrair_execucoes_paralelas(texto: str) -> tuple[list[dict[str, str]] | None, str | None]:
    texto_norm = _replace_number_words(_norm(texto))
    partes = [
        parte.strip(" ,.;")
        for parte in re.split(r"\s+e\s+(?=(?:executar|rodar|testar)\b)", texto_norm)
        if parte.strip(" ,.;")
    ]

    partes_execucao = [parte for parte in partes if re.search(r"\b(executar|rodar|testar)\b", parte)]

    if len(partes_execucao) < 2:
        return None, None

    execucoes: list[dict[str, str]] = []
    for idx, parte in enumerate(partes_execucao, start=1):
        bancada = _extrair_bancada(parte)
        if not bancada or bancada == "todas":
            return [], f"Aviso: informe uma bancada numerada para cada execução paralela. Falha em Bancada {idx}."

        cat, nome, erro = _resolver_execucao_de_trecho(parte)
        if erro:
            return [], erro

        if cat is None or nome is None:
            return [], "Aviso: nao foi possivel resolver categoria e nome do teste em um dos comandos paralelos."

        execucoes.append(
            {
                "categoria": cat,
                "teste": nome,
                "bancada": bancada,
                "label": f"Bancada {bancada}",
            }
        )

    return execucoes, None


def executar_testes_em_paralelo(execucoes: list[dict[str, str]]) -> str:
    if len(execucoes) < 2:
        return "Aviso: informe pelo menos duas execucoes para rodar em paralelo."

    bancadas = listar_bancadas()
    if len(bancadas) < 2:
        return "ERRO: conecte pelo menos duas bancadas para executar testes em paralelo."

    seriais_usados = set()
    execucoes_resolvidas: list[dict[str, str]] = []

    for execucao in execucoes:
        bancada_num = str(execucao.get("bancada", "")).strip()
        if bancada_num not in bancadas:
            return f"ERRO: bancada '{bancada_num}' nao encontrada. Use **listar bancadas**."

        if bancada_num in seriais_usados:
            return "ERRO: nao e permitido usar a mesma bancada em duas execucoes paralelas."

        seriais_usados.add(bancada_num)

        categoria = str(execucao.get("categoria", "")).strip()
        nome_teste = str(execucao.get("teste", "")).strip()

        ok_dataset, erro_dataset = _garantir_dataset_execucao_chat(categoria, nome_teste)
        if not ok_dataset:
            return erro_dataset or f"ERRO: falha ao preparar dataset de {categoria}/{nome_teste}."

        execucoes_resolvidas.append(
            {
                "categoria": categoria,
                "teste": nome_teste,
                "serial": bancadas[bancada_num],
                "label": str(execucao.get("label", f"Bancada {bancada_num}")),
            }
        )

    respostas = ["Executando testes em paralelo:"]
    for execucao in execucoes_resolvidas:
        respostas.append(
            _iniciar_execucao_no_serial(
                execucao["categoria"],
                execucao["teste"],
                execucao["serial"],
                bancada_label=execucao["label"],
            )
        )

    return "\n".join(respostas)


apply_pending_navigation()
pagina = sidebar_page_selector()
render_voice_sidebar(
    configure_recognizer=configure_recognizer,
    audio_input_to_sr_audio=audio_input_to_sr_audio,
    transcribe_command_audio=transcribe_command_audio,
    process_voice_command=_processar_comando_de_voz,
    list_categories=listar_categorias,
    list_tests=listar_testes,
)
render_benches_sidebar(list_benches=listar_bancadas, format_benches=_formatar_bancadas_str)

if pagina == PAGINA_CHAT:
    def _process_user_input(user_input: str) -> str:
        with st.spinner("Processando comando..."):
            if st.session_state.pending_gravacao is not None:
                return continuar_fluxo_gravacao(user_input)
            if MODO_CONVERSA:
                return responder_conversacional(user_input)
            return resolver_comando_com_llm_ou_fallback(user_input)

    render_chat_shell(
        title_panel=titulo_painel,
        render_greeting=render_saudacao_menu_chat,
        check_finalizations=checar_finalizacoes,
        check_finished_executions=checar_execucoes_finalizadas,
        st_autorefresh=st_autorefresh,
        sanitize_text=_sanitize_text,
        save_partial_result=salvar_resultado_parcial,
        finalize_recording=finalizar_gravacao,
        cancel_recording=cancelar_gravacao,
        process_user_input=_process_user_input,
    )
else:
    render_selected_page(
        pagina,
        render_mapa_neural_ia_coder=render_mapa_neural_ia_coder,
        apply_panel_button_theme=apply_panel_button_theme,
        abrir_menu_tester=_abrir_menu_tester,
    )
