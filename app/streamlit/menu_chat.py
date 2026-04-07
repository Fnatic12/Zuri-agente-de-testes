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
import speech_recognition as sr
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
import tempfile
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import TypedDict
from colorama import Fore, Style
from app.shared.project_paths import project_root, root_path
from app.shared.adb_utils import resolve_adb_path
from app.shared import ui_theme as _ui_theme

apply_dark_background = _ui_theme.apply_dark_background


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()

def _sanitize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    # Tenta corrigir mojibake comum e normaliza para ASCII simples
    try:
        if any(ch in s for ch in ["Ã", "â", "�"]):
            s = s.encode("latin1", "ignore").decode("utf-8", "ignore")
    except Exception:
        pass
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


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

STT_CAPTURE_TIMEOUT_S = float(os.getenv("STT_CAPTURE_TIMEOUT_S", "8"))
STT_PHRASE_LIMIT_S = float(os.getenv("STT_PHRASE_LIMIT_S", "12"))
STT_WHISPER_TIMEOUT_S = float(os.getenv("STT_WHISPER_TIMEOUT_S", "8"))

_STT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")


class STTRuntimeProfile(TypedDict):
    provider: str
    model_name: str
    compute_cfg: str
    timeout_s: float
    device_index: int | None



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

def configurar_reconhecedor() -> sr.Recognizer:
    r = sr.Recognizer()
    # torna o nÃ­vel de corte adaptativo ao ruÃ­do
    r.dynamic_energy_threshold = True
    # base razoÃ¡vel; serÃ¡ recalibrado pelo adjust_for_ambient_noise
    r.energy_threshold = 250
    # tolerÃ¢ncia para pequenas pausas no meio da frase
    r.pause_threshold = 1.0
    # considera silÃªncio curtinho antes de encerrar
    r.non_speaking_duration = 0.2
    r.phrase_threshold = 0.25
    setattr(r, "operation_timeout", float(max(6, int(STT_CAPTURE_TIMEOUT_S))))
    return r


def _stt_command_prompt() -> str:
    catalogo: list[str] = []
    try:
        for categoria in listar_categorias()[:8]:
            for teste in listar_testes(categoria)[:8]:
                catalogo.append(teste)
    except Exception:
        catalogo = []
    catalogo_txt = ", ".join(catalogo[:20])
    return (
        "Comandos de automacao por voz em portugues do Brasil: "
        "executar, rodar, gravar, coletar, processar, apagar, listar, listar bancadas, "
        "resetar, pausar, retomar, parar, menu tester, validacao hmi, dashboard, mapa neural, "
        "bancada um, bancada dois, bancada tres, audio, video, bluetooth, carplay, android auto. "
        f"Testes conhecidos no ambiente: {catalogo_txt}."
    )


def _stt_runtime_profile() -> STTRuntimeProfile:
    device = _detectar_dispositivo_whisper()
    if device == "cuda":
        return {
            "provider": "whisper",
            "model_name": "medium",
            "compute_cfg": "auto",
            "timeout_s": 10.0,
            "device_index": None,
        }
    return {
        "provider": "auto",
        "model_name": "medium",
        "compute_cfg": "auto",
        "timeout_s": max(12.0, float(STT_WHISPER_TIMEOUT_S)),
        "device_index": None,
    }


def _detectar_dispositivo_whisper() -> str:
    try:
        import torch  # type: ignore

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _resolver_compute_type(device: str, compute_cfg: str) -> str:
    mode = str(compute_cfg or "auto").strip().lower()
    if mode and mode != "auto":
        return mode
    return "float16" if device == "cuda" else "int8"


@lru_cache(maxsize=8)
def _load_faster_whisper_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel  # type: ignore

    cpu_threads = max(2, int(os.cpu_count() or 2))
    return WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=cpu_threads)


def _preload_whisper_default() -> None:
    try:
        stt_profile = _stt_runtime_profile()
        device = _detectar_dispositivo_whisper()
        compute_type = _resolver_compute_type(device, str(stt_profile["compute_cfg"]))
        _load_faster_whisper_model(str(stt_profile["model_name"]), device, compute_type)
    except Exception:
        pass


def _transcrever_com_faster_whisper(audio: sr.AudioData, model_name: str, compute_cfg: str) -> str | None:
    wav_bytes = audio.get_wav_data(convert_rate=16000, convert_width=2)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="voz_cmd_", suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name

        device = _detectar_dispositivo_whisper()
        compute_type = _resolver_compute_type(device, compute_cfg)
        try:
            model = _load_faster_whisper_model(model_name, device, compute_type)
        except Exception:
            if compute_type != "float32":
                model = _load_faster_whisper_model(model_name, device, "float32")
            else:
                raise

        segments, _ = model.transcribe(
            tmp_path,
            language="pt",
            task="transcribe",
            beam_size=3,
            best_of=3,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
            initial_prompt=_stt_command_prompt(),
        )
        text = " ".join(segment.text.strip() for segment in segments if getattr(segment, "text", "").strip()).strip()
        return text or None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _transcrever_com_faster_whisper_timeout(
    audio: sr.AudioData, model_name: str, compute_cfg: str, timeout_s: float
) -> str | None:
    future = _STT_EXECUTOR.submit(_transcrever_com_faster_whisper, audio, model_name, compute_cfg)
    try:
        return future.result(timeout=max(2.0, float(timeout_s)))
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError(f"Whisper timeout ({timeout_s:.1f}s)") from exc


def _transcrever_google_best_effort(recognizer: sr.Recognizer, audio: sr.AudioData) -> str | None:
    try:
        raw = recognizer.recognize_google(audio, language="pt-BR", show_all=True)  # type: ignore[attr-defined]
        if isinstance(raw, dict):
            alternatives = raw.get("alternative") or []
            if alternatives:
                best = sorted(alternatives, key=lambda alt: float(alt.ge3t("confidence", 0.0)), reverse=True)[0]
                text = str(best.get("transcript") or "").strip()
                if text:
                    return text
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    except Exception:
        pass
    try:
        text = recognizer.recognize_google(audio, language="pt-BR")  # type: ignore[attr-defined]
        return str(text).strip() if text else None
    except Exception:
        return None


def _transcrever_audio_comando(recognizer: sr.Recognizer, audio: sr.AudioData) -> tuple[str | None, str, str]:
    stt_profile = _stt_runtime_profile()
    provider = str(stt_profile["provider"]).strip().lower()
    model_name = str(stt_profile["model_name"]).strip().lower()
    compute_cfg = str(stt_profile["compute_cfg"]).strip().lower()
    whisper_timeout_s = float(stt_profile["timeout_s"])
    errors = []

    # Auto agora prioriza acuracia: Whisper primeiro; se falhar, cai para Google.
    if provider in {"auto", "whisper"}:
        model_candidates = [model_name]
        if model_name in {"large-v3", "medium"}:
            model_candidates.append("small")

        for candidate in model_candidates:
            try:
                text = _transcrever_com_faster_whisper_timeout(
                    audio,
                    model_name=candidate,
                    compute_cfg=compute_cfg,
                    timeout_s=whisper_timeout_s,
                )
                if text:
                    engine = "Whisper" if candidate == model_name else f"Whisper ({candidate})"
                    return text, engine, " | ".join(errors)
                errors.append(f"Whisper {candidate} sem texto")
            except Exception as exc:
                errors.append(f"Whisper {candidate} indisponivel: {exc}")

    text_google = _transcrever_google_best_effort(recognizer, audio)
    if text_google:
        return text_google, "Google", " | ".join(errors)

    if provider == "google":
        errors.append("Google sem texto")
    return None, "Nenhum", " | ".join(errors)


def _audio_input_to_sr_audio(uploaded_audio: object) -> sr.AudioData:
    getvalue = getattr(uploaded_audio, "getvalue", None)
    if not callable(getvalue):
        raise RuntimeError("Gravacao do navegador indisponivel.")
    audio_bytes = getvalue()
    if not audio_bytes:
        raise RuntimeError("Nenhum audio recebido do navegador.")
    with sr.AudioFile(BytesIO(audio_bytes)) as source:
        recognizer = configurar_reconhecedor()
        return recognizer.record(source)


def _processar_comando_de_voz(command_text: str) -> None:
    command_text = normalizar_pos_fala(command_text)
    st.session_state.chat_history.append({"role": "user", "content": command_text})
    with st.spinner("Processando comando..."):
        if st.session_state.pending_gravacao is not None:
            resposta = continuar_fluxo_gravacao(command_text)
        elif MODO_CONVERSA:
            resposta = responder_conversacional(command_text)
        else:
            resposta = resolver_comando_com_llm_ou_fallback(command_text)
    if resposta:
        st.session_state.chat_history.append({"role": "assistant", "content": resposta})

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


def render_mapa_neural_ia() -> None:
    nodes = [
        {
            "id": "controller",
            "label": "IA Controladora",
            "role": "Orquestrador central",
            "detail": "Interpreta comandos, decide rotas e coordena os subagentes do projeto.",
            "x": 50,
            "y": 47,
            "kind": "core",
        },
        {
            "id": "voice",
            "label": "Voz Browser",
            "role": "Entrada por fala",
            "detail": "Captura comandos pelo microfone do navegador e envia para transcricao.",
            "x": 21,
            "y": 18,
            "kind": "input",
        },
        {
            "id": "intent",
            "label": "Intencao",
            "role": "Roteador semantico",
            "detail": "Transforma linguagem natural em acoes: executar, gravar, validar, logs e navegacao.",
            "x": 50,
            "y": 16,
            "kind": "agent",
        },
        {
            "id": "llm",
            "label": "LLM Local",
            "role": "Raciocinio assistido",
            "detail": "Usa Ollama e fallbacks para classificar comandos e responder conversas.",
            "x": 78,
            "y": 19,
            "kind": "agent",
        },
        {
            "id": "tester",
            "label": "Menu Tester",
            "role": "Agente executor",
            "detail": "Dispara testes, coletas, paralelismo e execucoes por categoria.",
            "x": 18,
            "y": 48,
            "kind": "agent",
        },
        {
            "id": "adb",
            "label": "ADB Runner",
            "role": "Ponte Android",
            "detail": "Conecta bancadas, envia toques, coleta screenshots e monitora dispositivos.",
            "x": 30,
            "y": 78,
            "kind": "device",
        },
        {
            "id": "hmi",
            "label": "Validador HMI",
            "role": "Agente visual",
            "detail": "Compara capturas reais contra a biblioteca GEI/Figma e gera status visual.",
            "x": 73,
            "y": 48,
            "kind": "agent",
        },
        {
            "id": "malagueta",
            "label": "Malagueta/scrcpy",
            "role": "Observador de tela",
            "detail": "Acompanha a tela do radio via scrcpy/ADB e grava capturas em Data/HMI_TESTE.",
            "x": 86,
            "y": 73,
            "kind": "device",
        },
        {
            "id": "figma",
            "label": "Biblioteca GEI",
            "role": "Memoria visual",
            "detail": "Guarda as telas base exportadas do Figma para matching e validacao.",
            "x": 64,
            "y": 84,
            "kind": "memory",
        },
        {
            "id": "logs",
            "label": "Painel de Logs",
            "role": "Agente observador",
            "detail": "Organiza logs do radio e apoia investigacao de comportamento.",
            "x": 9,
            "y": 70,
            "kind": "agent",
        },
        {
            "id": "failures",
            "label": "Controle de Falhas",
            "role": "Triagem",
            "detail": "Agrupa falhas, prepara evidencias e estrutura encaminhamentos.",
            "x": 9,
            "y": 29,
            "kind": "agent",
        },
        {
            "id": "dashboard",
            "label": "Dashboard",
            "role": "Supervisao",
            "detail": "Mostra status, execucoes e resultados para acompanhamento em tempo real.",
            "x": 90,
            "y": 34,
            "kind": "output",
        },
        {
            "id": "data",
            "label": "Data Lake",
            "role": "Memoria operacional",
            "detail": "Persistencia local de resultados, manifests, capturas, relatorios e caches.",
            "x": 50,
            "y": 93,
            "kind": "memory",
        },
    ]
    links = [
        ("controller", "voice"),
        ("controller", "intent"),
        ("controller", "llm"),
        ("controller", "tester"),
        ("controller", "hmi"),
        ("controller", "logs"),
        ("controller", "failures"),
        ("controller", "dashboard"),
        ("tester", "adb"),
        ("adb", "malagueta"),
        ("hmi", "malagueta"),
        ("hmi", "figma"),
        ("hmi", "data"),
        ("malagueta", "data"),
        ("tester", "data"),
        ("logs", "data"),
        ("failures", "dashboard"),
        ("data", "dashboard"),
    ]
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    components.html(
        f"""
        <div class="brain-shell">
          <div class="brain-orb brain-orb-a"></div>
          <div class="brain-orb brain-orb-b"></div>
          <section class="brain-hero">
            <div>
              <p class="eyebrow">Arquitetura Cognitiva VWAIT</p>
              <h1>Mapa Neural da IA</h1>
              <p class="hero-copy">
                Uma visao viva da IA controladora e dos subagentes que operam testes,
                logs, HMI, scrcpy, ADB, dashboards e memoria local do projeto.
              </p>
            </div>
            <div class="hero-badge">
              <span class="pulse-dot"></span>
              Sistema em orquestracao
            </div>
          </section>
          <section class="brain-stage" id="brain-stage">
            <svg class="brain-links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"></svg>
            <div class="brain-grid"></div>
            <div class="brain-halo"></div>
            <div id="brain-nodes"></div>
          </section>
          <section class="brain-footer">
            <div class="detail-card">
              <p class="detail-kicker">Nodo em foco</p>
              <h2 id="detail-title">IA Controladora</h2>
              <p id="detail-role">Orquestrador central</p>
              <p id="detail-copy">Interpreta comandos, decide rotas e coordena os subagentes do projeto.</p>
            </div>
            <div class="signal-card"><strong>{len(nodes)}</strong><span>nodos cognitivos</span></div>
            <div class="signal-card"><strong>{len(links)}</strong><span>conexoes ativas</span></div>
            <div class="signal-card"><strong>0 CDN</strong><span>visual local</span></div>
          </section>
        </div>
        <style>
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            background: transparent;
            color: #eef6ff;
            font-family: "Aptos", "Segoe UI", sans-serif;
          }}
          .brain-shell {{
            position: relative;
            min-height: 860px;
            overflow: hidden;
            border: 1px solid rgba(119, 201, 255, 0.22);
            border-radius: 34px;
            padding: 34px;
            background:
              radial-gradient(circle at 18% 18%, rgba(39, 201, 255, 0.18), transparent 30%),
              radial-gradient(circle at 84% 24%, rgba(45, 255, 146, 0.13), transparent 29%),
              linear-gradient(145deg, rgba(4, 13, 26, 0.98), rgba(1, 6, 14, 0.96));
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 34px 90px rgba(0, 0, 0, .45);
          }}
          .brain-orb {{
            position: absolute;
            width: 360px;
            height: 360px;
            border-radius: 999px;
            filter: blur(38px);
            opacity: .34;
            pointer-events: none;
          }}
          .brain-orb-a {{ left: -100px; top: 130px; background: #0cc9ff; animation: drift 8s ease-in-out infinite alternate; }}
          .brain-orb-b {{ right: -120px; bottom: 70px; background: #1dff9b; animation: drift 10s ease-in-out infinite alternate-reverse; }}
          @keyframes drift {{
            from {{ transform: translate3d(0, 0, 0) scale(.95); }}
            to {{ transform: translate3d(42px, -24px, 0) scale(1.06); }}
          }}
          .brain-hero {{
            position: relative;
            z-index: 2;
            display: flex;
            justify-content: space-between;
            gap: 24px;
            align-items: flex-start;
            margin-bottom: 24px;
          }}
          .eyebrow {{
            margin: 0 0 8px;
            color: #5ee6ff;
            text-transform: uppercase;
            letter-spacing: .24em;
            font-size: 12px;
            font-weight: 800;
          }}
          h1 {{
            margin: 0;
            font-size: clamp(42px, 7vw, 82px);
            line-height: .88;
            letter-spacing: -.07em;
            background: linear-gradient(90deg, #f8fbff, #9eeaff 44%, #2cff98 88%);
            -webkit-background-clip: text;
            color: transparent;
          }}
          .hero-copy {{
            max-width: 720px;
            margin: 18px 0 0;
            color: rgba(226, 238, 255, .72);
            font-size: 17px;
            line-height: 1.65;
          }}
          .hero-badge {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 13px 16px;
            border: 1px solid rgba(98, 255, 183, .28);
            border-radius: 999px;
            background: rgba(7, 22, 32, .68);
            color: #baffdc;
            font-size: 13px;
            font-weight: 800;
            white-space: nowrap;
          }}
          .pulse-dot {{
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #2cff98;
            box-shadow: 0 0 0 0 rgba(44,255,152,.72);
            animation: pulse 1.6s ease-out infinite;
          }}
          @keyframes pulse {{
            to {{ box-shadow: 0 0 0 14px rgba(44,255,152,0); }}
          }}
          .brain-stage {{
            position: relative;
            height: 560px;
            border: 1px solid rgba(145, 215, 255, .18);
            border-radius: 30px;
            overflow: hidden;
            background:
              radial-gradient(circle at center, rgba(66, 178, 255, .18), transparent 35%),
              linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));
          }}
          .brain-grid {{
            position: absolute;
            inset: 0;
            opacity: .18;
            background-image:
              linear-gradient(rgba(118, 202, 255, .18) 1px, transparent 1px),
              linear-gradient(90deg, rgba(118, 202, 255, .18) 1px, transparent 1px);
            background-size: 42px 42px;
            mask-image: radial-gradient(circle at center, black, transparent 72%);
          }}
          .brain-halo {{
            position: absolute;
            width: 340px;
            height: 340px;
            left: calc(50% - 170px);
            top: calc(47% - 170px);
            border-radius: 999px;
            border: 1px dashed rgba(111, 225, 255, .34);
            box-shadow: 0 0 90px rgba(21, 220, 255, .18);
            animation: spin 18s linear infinite;
          }}
          @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
          .brain-links {{
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
          }}
          .brain-link {{
            stroke: rgba(94, 230, 255, .38);
            stroke-width: .22;
            filter: drop-shadow(0 0 5px rgba(94,230,255,.34));
          }}
          .brain-link.hot {{
            stroke: rgba(44, 255, 152, .74);
            stroke-width: .32;
          }}
          .node {{
            position: absolute;
            z-index: 3;
            width: 132px;
            min-height: 76px;
            transform: translate(-50%, -50%);
            padding: 13px 13px 12px;
            border-radius: 22px;
            border: 1px solid rgba(153, 221, 255, .25);
            background: linear-gradient(180deg, rgba(18, 31, 54, .92), rgba(6, 13, 27, .88));
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,.08),
              0 18px 36px rgba(0,0,0,.28);
            cursor: pointer;
            transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
          }}
          .node::before {{
            content: "";
            position: absolute;
            width: 9px;
            height: 9px;
            right: 14px;
            top: 14px;
            border-radius: 999px;
            background: var(--accent);
            box-shadow: 0 0 18px var(--accent);
          }}
          .node:hover, .node.active {{
            transform: translate(-50%, -50%) scale(1.07);
            border-color: var(--accent);
            box-shadow:
              0 0 0 1px color-mix(in srgb, var(--accent), transparent 35%),
              0 22px 46px rgba(0,0,0,.34),
              0 0 44px color-mix(in srgb, var(--accent), transparent 58%);
          }}
          .node.core {{
            width: 190px;
            min-height: 112px;
            border-radius: 30px;
            background:
              radial-gradient(circle at 28% 12%, rgba(255,255,255,.16), transparent 34%),
              linear-gradient(145deg, rgba(18, 72, 102, .98), rgba(5, 24, 35, .94));
          }}
          .node-title {{
            display: block;
            color: #f8fbff;
            font-weight: 900;
            line-height: 1.02;
            letter-spacing: -.03em;
            font-size: 15px;
            padding-right: 16px;
          }}
          .node-role {{
            display: block;
            margin-top: 8px;
            color: rgba(218, 234, 255, .62);
            font-size: 11px;
            line-height: 1.25;
            text-transform: uppercase;
            letter-spacing: .08em;
          }}
          .core .node-title {{ font-size: 21px; }}
          .core .node-role {{ font-size: 12px; color: #9bf7ff; }}
          .detail-card, .signal-card {{
            border: 1px solid rgba(145, 215, 255, .16);
            border-radius: 24px;
            background: rgba(6, 14, 27, .72);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
          }}
          .brain-footer {{
            position: relative;
            z-index: 2;
            display: grid;
            grid-template-columns: minmax(0, 1.7fr) repeat(3, minmax(150px, .55fr));
            gap: 16px;
            margin-top: 18px;
          }}
          .detail-card {{ padding: 20px 22px; }}
          .detail-kicker {{
            margin: 0 0 8px;
            font-size: 11px;
            letter-spacing: .18em;
            text-transform: uppercase;
            color: #5ee6ff;
            font-weight: 900;
          }}
          .detail-card h2 {{
            margin: 0;
            font-size: 30px;
            letter-spacing: -.04em;
          }}
          #detail-role {{
            margin: 8px 0;
            color: #2cff98;
            font-weight: 900;
          }}
          #detail-copy {{
            margin: 0;
            color: rgba(226, 238, 255, .72);
            line-height: 1.55;
          }}
          .signal-card {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 18px;
            min-height: 122px;
          }}
          .signal-card strong {{
            color: #f8fbff;
            font-size: 34px;
            line-height: 1;
          }}
          .signal-card span {{
            margin-top: 10px;
            color: rgba(226, 238, 255, .6);
            text-transform: uppercase;
            letter-spacing: .1em;
            font-size: 11px;
            font-weight: 800;
          }}
          @media (max-width: 880px) {{
            .brain-shell {{ padding: 22px; min-height: 980px; }}
            .brain-hero {{ flex-direction: column; }}
            .brain-stage {{ height: 640px; }}
            .node {{ width: 116px; font-size: 12px; }}
            .brain-footer {{ grid-template-columns: 1fr; }}
          }}
        </style>
        <script>
          const nodes = {nodes_json};
          const links = {links_json};
          const accents = {{
            core: "#5ee6ff",
            agent: "#2cff98",
            input: "#f7c96b",
            device: "#ff7f5f",
            memory: "#a990ff",
            output: "#77d7ff"
          }};
          const nodeRoot = document.getElementById("brain-nodes");
          const svg = document.querySelector(".brain-links");
          const title = document.getElementById("detail-title");
          const role = document.getElementById("detail-role");
          const copy = document.getElementById("detail-copy");
          const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

          function renderLinks(activeId) {{
            svg.innerHTML = "";
            links.forEach(([from, to]) => {{
              const a = byId[from];
              const b = byId[to];
              if (!a || !b) return;
              const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
              line.setAttribute("x1", a.x);
              line.setAttribute("y1", a.y);
              line.setAttribute("x2", b.x);
              line.setAttribute("y2", b.y);
              line.setAttribute("class", "brain-link" + (activeId && (activeId === from || activeId === to) ? " hot" : ""));
              svg.appendChild(line);
            }});
          }}

          function focusNode(node) {{
            document.querySelectorAll(".node").forEach((el) => el.classList.toggle("active", el.dataset.nodeId === node.id));
            title.textContent = node.label;
            role.textContent = node.role;
            copy.textContent = node.detail;
            renderLinks(node.id);
          }}

          nodes.forEach((node, index) => {{
            const el = document.createElement("button");
            el.type = "button";
            el.className = "node " + node.kind;
            el.dataset.nodeId = node.id;
            el.style.left = node.x + "%";
            el.style.top = node.y + "%";
            el.style.setProperty("--accent", accents[node.kind] || "#5ee6ff");
            el.style.animation = `nodeFloat ${{5 + (index % 5) * .6}}s ease-in-out ${{index * .08}}s infinite alternate`;
            el.innerHTML = `<span class="node-title">${{node.label}}</span><span class="node-role">${{node.role}}</span>`;
            el.addEventListener("mouseenter", () => focusNode(node));
            el.addEventListener("focus", () => focusNode(node));
            nodeRoot.appendChild(el);
          }});
          const style = document.createElement("style");
          style.textContent = `@keyframes nodeFloat {{ from {{ margin-top: -3px; }} to {{ margin-top: 7px; }} }}`;
          document.head.appendChild(style);
          renderLinks("controller");
          focusNode(byId.controller);
        </script>
        """,
        height=900,
        scrolling=False,
    )

def render_mapa_neural_ia_coder() -> None:
    nodes = [
        {"id": "kernel", "label": "zuri.kernel", "role": "IA controladora", "detail": "Nucleo que decide rota, delega agentes e sincroniza estado da interface.", "x": 50, "y": 45, "w": 1.45, "group": "core"},
        {"id": "intent", "label": "intent.parser", "role": "classificacao", "detail": "Normaliza linguagem natural e converte comandos em intencoes operacionais.", "x": 36, "y": 22, "w": 1.0, "group": "logic"},
        {"id": "router", "label": "nav.router", "role": "roteamento", "detail": "Abre paginas, aciona fluxos e controla a navegacao do operador.", "x": 54, "y": 20, "w": 1.0, "group": "logic"},
        {"id": "llm", "label": "ollama.llm", "role": "raciocinio", "detail": "Fallback semantico local para entender comandos ambigos e responder contexto.", "x": 68, "y": 25, "w": 1.05, "group": "logic"},
        {"id": "voice", "label": "browser.stt", "role": "voz", "detail": "Entrada de comando por audio via navegador, sem PyAudio.", "x": 22, "y": 18, "w": 0.9, "group": "input"},
        {"id": "chat", "label": "chat.ui", "role": "console", "detail": "Campo principal de comando e historico do operador.", "x": 18, "y": 39, "w": 0.95, "group": "ui"},
        {"id": "tester", "label": "tester.panel", "role": "execucao", "detail": "Menu Tester para iniciar, retomar e executar lotes de testes.", "x": 27, "y": 61, "w": 1.0, "group": "agent"},
        {"id": "queue", "label": "run.queue", "role": "fila", "detail": "Fila de execucoes ativas e finalizacoes pendentes.", "x": 38, "y": 72, "w": 0.9, "group": "runtime"},
        {"id": "adb", "label": "adb.bridge", "role": "android", "detail": "Camada de comunicacao com bancadas e dispositivos Android.", "x": 52, "y": 76, "w": 1.05, "group": "device"},
        {"id": "bench", "label": "bench.pool", "role": "bancadas", "detail": "Serializa bancadas conectadas e seleciona alvos de execucao.", "x": 66, "y": 75, "w": 0.95, "group": "device"},
        {"id": "scrcpy", "label": "scrcpy.malagueta", "role": "espelho", "detail": "Janela do radio e origem visual para captura durante testes HMI.", "x": 78, "y": 61, "w": 1.1, "group": "device"},
        {"id": "touch", "label": "touch.monitor", "role": "eventos", "detail": "Monitora clique/toque/mudanca visual e grava screenshots.", "x": 80, "y": 42, "w": 1.0, "group": "agent"},
        {"id": "hmi", "label": "hmi.validator", "role": "comparacao", "detail": "Orquestra captura, biblioteca GEI e comparacao automatica.", "x": 68, "y": 47, "w": 1.18, "group": "agent"},
        {"id": "engine", "label": "hmi.engine", "role": "diff engine", "detail": "Calcula similaridade, pixel match, grids e status HMI.", "x": 64, "y": 34, "w": 0.95, "group": "logic"},
        {"id": "figma", "label": "gei.library", "role": "baseline", "detail": "Pasta GEI/Figma com referencias de tela para matching.", "x": 82, "y": 25, "w": 0.9, "group": "memory"},
        {"id": "vision", "label": "visual.qa", "role": "qa visual", "detail": "Pipeline complementar de classificacao e validacao visual.", "x": 88, "y": 35, "w": 0.85, "group": "logic"},
        {"id": "shots", "label": "screenshot.store", "role": "capturas", "detail": "Cache de capturas ao vivo, normalizadas e nativas.", "x": 67, "y": 88, "w": 0.9, "group": "memory"},
        {"id": "hmiteste", "label": "Data/HMI_TESTE", "role": "evidencias", "detail": "Pasta permanente com screenshots capturados da malagueta/ADB.", "x": 84, "y": 84, "w": 0.9, "group": "memory"},
        {"id": "manifest", "label": "manifest.jsonl", "role": "timeline", "detail": "Linha do tempo append-only de capturas e eventos.", "x": 49, "y": 91, "w": 0.78, "group": "memory"},
        {"id": "reports", "label": "report.builder", "role": "relatorio", "detail": "Consolida resultados em payloads e relatorios exportaveis.", "x": 29, "y": 86, "w": 0.85, "group": "output"},
        {"id": "dashboard", "label": "dashboard.live", "role": "observabilidade", "detail": "Mostra status, capturas recentes e execucoes em andamento.", "x": 18, "y": 75, "w": 0.95, "group": "output"},
        {"id": "logs", "label": "logs.panel", "role": "telemetria", "detail": "Leitura e analise de logs do radio.", "x": 12, "y": 55, "w": 0.85, "group": "output"},
        {"id": "failures", "label": "failure.control", "role": "triagem", "detail": "Agrupa falhas, evidencias e fluxo de encaminhamento.", "x": 12, "y": 27, "w": 0.85, "group": "output"},
        {"id": "cache", "label": "hmi.cache", "role": "estado", "detail": "Persistencia local de indices, results.json e estados do monitor.", "x": 50, "y": 62, "w": 0.9, "group": "memory"},
        {"id": "streamlit", "label": "streamlit.host", "role": "runtime UI", "detail": "Shell que hospeda as paginas e iframes internos.", "x": 35, "y": 38, "w": 0.95, "group": "ui"},
        {"id": "autoheal", "label": "process.guard", "role": "anti-duplicacao", "detail": "Evita monitores duplicados e recicla processos presos.", "x": 43, "y": 52, "w": 0.85, "group": "runtime"},
        {"id": "dataset", "label": "dataset.pipe", "role": "pre-process", "detail": "Processa capturas e artefatos para execucoes futuras.", "x": 25, "y": 48, "w": 0.82, "group": "runtime"},
    ]
    links = [
        ["kernel", "intent"], ["kernel", "router"], ["kernel", "llm"], ["kernel", "chat"], ["kernel", "streamlit"],
        ["kernel", "tester"], ["kernel", "hmi"], ["kernel", "dashboard"], ["kernel", "logs"], ["kernel", "failures"],
        ["voice", "intent"], ["chat", "intent"], ["intent", "llm"], ["intent", "router"], ["router", "dashboard"],
        ["router", "logs"], ["router", "failures"], ["router", "tester"], ["router", "hmi"], ["streamlit", "chat"],
        ["streamlit", "dashboard"], ["streamlit", "logs"], ["streamlit", "failures"], ["streamlit", "hmi"],
        ["tester", "queue"], ["tester", "adb"], ["tester", "dataset"], ["tester", "reports"], ["queue", "adb"],
        ["adb", "bench"], ["adb", "scrcpy"], ["bench", "touch"], ["scrcpy", "touch"], ["touch", "hmi"],
        ["touch", "shots"], ["touch", "hmiteste"], ["touch", "manifest"], ["hmi", "engine"], ["hmi", "figma"],
        ["hmi", "cache"], ["hmi", "shots"], ["hmi", "reports"], ["engine", "figma"], ["engine", "vision"],
        ["engine", "cache"], ["figma", "cache"], ["vision", "reports"], ["shots", "hmiteste"], ["shots", "manifest"],
        ["manifest", "reports"], ["reports", "dashboard"], ["cache", "dashboard"], ["cache", "autoheal"],
        ["autoheal", "touch"], ["autoheal", "hmi"], ["autoheal", "queue"], ["logs", "failures"], ["failures", "reports"],
        ["dataset", "cache"], ["dataset", "reports"], ["adb", "logs"], ["scrcpy", "dashboard"],
    ]
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    def _map_panel_online(port: int | None = None, default: bool = True) -> bool:
        if port is None:
            return default
        try:
            return _porta_local_ativa(int(port), timeout_s=0.05)
        except Exception:
            return False

    hmi_manifest_path = root_path("Data", "HMI_TESTE", "manifest.jsonl")
    try:
        hmi_recent = os.path.exists(hmi_manifest_path) and (time.time() - os.path.getmtime(hmi_manifest_path) < 300)
    except Exception:
        hmi_recent = False
    panel_states = [
        {"id": "control", "label": "control.plane", "node": "kernel", "online": True, "mode": "local"},
        {"id": "chat", "label": "chat.ui", "node": "chat", "online": True, "mode": "streamlit"},
        {"id": "tester", "label": "menu.tester", "node": "tester", "online": _map_panel_online(globals().get("MENU_TESTER_PORT", 8503), False), "mode": "port 8503"},
        {"id": "dashboard", "label": "dashboard.live", "node": "dashboard", "online": _map_panel_online(globals().get("DASHBOARD_PORT", 8504), False), "mode": "port 8504"},
        {"id": "logs", "label": "logs.panel", "node": "logs", "online": _map_panel_online(globals().get("LOGS_PANEL_PORT", 8505), False), "mode": "port 8505"},
        {"id": "failures", "label": "failure.control", "node": "failures", "online": _map_panel_online(globals().get("FAILURE_CONTROL_PORT", 8506), False), "mode": "port 8506"},
        {"id": "hmi", "label": "hmi.capture", "node": "hmi", "online": hmi_recent, "mode": "Data/HMI_TESTE"},
    ]
    panel_states_json = json.dumps(panel_states, ensure_ascii=False)
    html = r"""
    <div class="ops-map">
      <div class="scanline"></div>
      <section class="graph-card">
        <canvas id="ops-canvas"></canvas>
        <div class="graph-tools">
          <button type="button" id="graph-fit">fit</button>
          <button type="button" id="graph-zoom-out">-</button>
          <button type="button" id="graph-zoom-in">+</button>
          <button type="button" id="graph-expand">expand</button>
        </div>
        <div class="agent-bus" aria-label="fluxo operacional de agentes">
          <div class="bus-header">
            <span class="bus-pulse"></span>
            <span>agent bus</span>
            <code id="bus-clock">sync</code>
          </div>
          <div id="agent-bus-lines" class="bus-lines"></div>
          <div id="panel-state-strip" class="panel-state-strip"></div>
        </div>
      </section>
    </div>
    <style>
      :root {
        --paper: #050505;
        --ink: #f1efe7;
        --muted: rgba(241,239,231,.58);
        --hair: rgba(241,239,231,.14);
        --hair-strong: rgba(241,239,231,.3);
        --amber: #c8a968;
      }
      body {
        margin: 0;
        background: transparent;
        color: var(--ink);
        font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
        overflow: hidden;
      }
      .ops-map {
        position: relative;
        min-height: 760px;
        overflow: hidden;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        padding: 0;
      }
      .ops-map::before {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        opacity: .16;
        background-image:
          linear-gradient(rgba(255,255,255,.14) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.14) 1px, transparent 1px);
        background-size: 48px 48px;
        mask-image: radial-gradient(circle at center, black, transparent 82%);
      }
      .scanline {
        position: absolute;
        inset: -40% 0 auto;
        height: 42%;
        background: linear-gradient(180deg, transparent, rgba(255,255,255,.035), transparent);
        transform: rotate(-8deg);
        animation: scan 7s linear infinite;
        pointer-events: none;
      }
      @keyframes scan {
        from { top: -44%; }
        to { top: 110%; }
      }
      .graph-card {
        position: relative;
        z-index: 2;
        min-height: 760px;
        overflow: hidden;
        cursor: grab;
        user-select: none;
        touch-action: none;
        border: 1px solid rgba(118,156,228,.20);
        border-radius: 22px;
        background:
          radial-gradient(circle at 22% 18%, rgba(77, 109, 150, .16), transparent 34%),
          radial-gradient(circle at 78% 78%, rgba(200, 169, 104, .05), transparent 30%),
          linear-gradient(135deg, rgba(5, 12, 22, .98), rgba(2, 5, 10, .98));
        box-shadow:
          inset 0 1px 0 rgba(255,255,255,.04),
          0 18px 42px rgba(0,0,0,.34);
      }
      .graph-card.dragging {
        cursor: grabbing;
      }
      #ops-canvas {
        width: 100%;
        height: 760px;
        display: block;
      }
      .graph-tools {
        position: absolute;
        top: 14px;
        right: 14px;
        z-index: 3;
        display: flex;
        gap: 8px;
        padding: 8px;
        border: 1px solid var(--hair);
        border-radius: 16px;
        background: rgba(0,0,0,.58);
        backdrop-filter: blur(12px);
      }
      .graph-tools button {
        min-width: 42px;
        height: 32px;
        border: 1px solid rgba(241,239,231,.18);
        border-radius: 11px;
        background: rgba(241,239,231,.045);
        color: rgba(241,239,231,.82);
        font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: .06em;
        text-transform: uppercase;
        cursor: pointer;
      }
      .graph-tools button:hover {
        border-color: rgba(200,169,104,.72);
        color: var(--ink);
        background: rgba(200,169,104,.12);
      }
      .ops-map.expanded {
        min-height: 1080px;
      }
      .ops-map.expanded .graph-card {
        min-height: 1080px;
      }
      .ops-map.expanded #ops-canvas {
        height: 1080px;
      }
      .graph-card:fullscreen {
        width: 100vw;
        height: 100vh;
        min-height: 100vh;
        border-radius: 0;
      }
      .graph-card:fullscreen #ops-canvas {
        width: 100vw;
        height: 100vh;
      }
      .graph-card:fullscreen .graph-tools {
        top: 20px;
        right: 20px;
      }
      .agent-bus {
        position: absolute;
        right: 16px;
        bottom: 16px;
        z-index: 4;
        width: min(390px, calc(100% - 32px));
        padding: 12px;
        border: 1px solid rgba(241,239,231,.14);
        border-radius: 18px;
        background:
          linear-gradient(180deg, rgba(2,7,13,.72), rgba(0,0,0,.82)),
          radial-gradient(circle at 18% 0%, rgba(200,169,104,.11), transparent 42%);
        box-shadow:
          inset 0 1px 0 rgba(255,255,255,.05),
          0 18px 38px rgba(0,0,0,.42);
        backdrop-filter: blur(14px);
        pointer-events: none;
      }
      .bus-header {
        display: flex;
        align-items: center;
        gap: 9px;
        color: rgba(241,239,231,.82);
        font-size: 10px;
        font-weight: 900;
        letter-spacing: .18em;
        text-transform: uppercase;
      }
      .bus-header code {
        margin-left: auto;
        color: rgba(200,169,104,.82);
        font-size: 9px;
        letter-spacing: .08em;
      }
      .bus-pulse {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: var(--amber);
        box-shadow: 0 0 0 0 rgba(200,169,104,.7);
        animation: pulseOut 1.6s infinite;
      }
      @keyframes pulseOut {
        0% { box-shadow: 0 0 0 0 rgba(200,169,104,.72); }
        100% { box-shadow: 0 0 0 13px rgba(200,169,104,0); }
      }
      .bus-lines {
        display: grid;
        gap: 7px;
        margin-top: 12px;
      }
      .bus-line {
        position: relative;
        overflow: hidden;
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 10px;
        padding: 8px 10px;
        border: 1px solid rgba(241,239,231,.11);
        border-radius: 12px;
        background: rgba(255,255,255,.025);
        color: rgba(241,239,231,.68);
        font-size: 10px;
      }
      .bus-line::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 -55%;
        width: 52%;
        background: linear-gradient(90deg, transparent, rgba(200,169,104,.16), transparent);
        transform: skewX(-18deg);
      }
      .bus-line.live {
        border-color: rgba(200,169,104,.42);
        background: rgba(200,169,104,.055);
        color: rgba(241,239,231,.92);
      }
      .bus-line.live::before {
        animation: busSweep 3.6s cubic-bezier(.22, 1, .36, 1) infinite;
      }
      .bus-line.locked {
        border-color: rgba(200,169,104,.34);
        background: rgba(200,169,104,.045);
      }
      .bus-line.locked::before {
        display: none;
      }
      @keyframes busSweep {
        from { left: -55%; }
        to { left: 118%; }
      }
      .bus-path {
        position: relative;
        z-index: 1;
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .bus-status {
        position: relative;
        z-index: 1;
        color: rgba(200,169,104,.84);
        font-size: 9px;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .panel-state-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
      }
      .panel-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 8px;
        border: 1px solid rgba(241,239,231,.10);
        border-radius: 999px;
        color: rgba(241,239,231,.58);
        background: rgba(255,255,255,.02);
        font-size: 9px;
        letter-spacing: .04em;
      }
      .panel-chip::before {
        content: "";
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: rgba(241,239,231,.22);
      }
      .panel-chip.online {
        color: rgba(241,239,231,.82);
        border-color: rgba(200,169,104,.26);
        background: rgba(200,169,104,.055);
      }
      .panel-chip.online::before {
        background: var(--amber);
        box-shadow: 0 0 12px rgba(200,169,104,.72);
      }
      @media (max-width: 980px) {
        .ops-map,
        .graph-card,
        #ops-canvas { min-height: 720px; height: 720px; }
        .agent-bus {
          left: 12px;
          right: 12px;
          bottom: 12px;
          width: auto;
        }
      }
    </style>
    <script>
      const nodes = __NODES__;
      const rawLinks = __LINKS__;
      const panelStates = __PANEL_STATES__;
      const shell = document.querySelector(".ops-map");
      const graphCard = document.querySelector(".graph-card");
      const canvas = document.getElementById("ops-canvas");
      const ctx = canvas.getContext("2d");
      const fitBtn = document.getElementById("graph-fit");
      const zoomInBtn = document.getElementById("graph-zoom-in");
      const zoomOutBtn = document.getElementById("graph-zoom-out");
      const expandBtn = document.getElementById("graph-expand");
      const busLinesEl = document.getElementById("agent-bus-lines");
      const panelStateEl = document.getElementById("panel-state-strip");
      const busClockEl = document.getElementById("bus-clock");
      const colors = {
        core: "#f1efe7",
        logic: "#bbb7ab",
        input: "#aaa69a",
        ui: "#d0c9b7",
        agent: "#d8caa7",
        runtime: "#a9a9a0",
        device: "#c0b7a0",
        memory: "#b6b1a6",
        output: "#d3c4a2"
      };
      const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
      const FLOW_INTERVAL_MS = 3900;
      const FLOW_TAIL = .28;
      const AMBIENT_FLOW_COUNT = 6;
      const links = rawLinks.map(([a, b]) => ({ a: byId[a], b: byId[b], phase: Math.random(), speed: .00042 + Math.random() * .00062 })).filter((l) => l.a && l.b);
      const baseFlows = [
        { from: "chat", to: "intent", label: "command.ingest", status: "parse" },
        { from: "intent", to: "router", label: "intent.route", status: "route" },
        { from: "router", to: "tester", label: "tester.dispatch", status: "exec" },
        { from: "tester", to: "adb", label: "adb.session", status: "device" },
        { from: "adb", to: "scrcpy", label: "malagueta.mirror", status: "stream" },
        { from: "scrcpy", to: "touch", label: "click.capture", status: "event" },
        { from: "touch", to: "hmi", label: "hmi.validate", status: "compare" },
        { from: "hmi", to: "engine", label: "diff.engine", status: "score" },
        { from: "hmi", to: "shots", label: "screenshot.store", status: "persist" },
        { from: "shots", to: "hmiteste", label: "Data/HMI_TESTE", status: "archive" },
        { from: "manifest", to: "reports", label: "timeline.report", status: "emit" },
        { from: "reports", to: "dashboard", label: "dashboard.sync", status: "view" },
        { from: "logs", to: "failures", label: "log.triage", status: "risk" },
        { from: "failures", to: "reports", label: "failure.evidence", status: "trace" },
      ];
      const runtimeFlowMap = {
        tester: [
          { from: "kernel", to: "tester", label: "menu.tester.online", status: "runtime" },
          { from: "tester", to: "queue", label: "run.queue.watch", status: "queue" },
          { from: "tester", to: "adb", label: "adb.bridge.ready", status: "device" },
        ],
        dashboard: [
          { from: "kernel", to: "dashboard", label: "dashboard.live.online", status: "runtime" },
          { from: "reports", to: "dashboard", label: "report.feed", status: "view" },
          { from: "cache", to: "dashboard", label: "cache.hydrate", status: "state" },
        ],
        logs: [
          { from: "kernel", to: "logs", label: "logs.panel.online", status: "runtime" },
          { from: "adb", to: "logs", label: "radio.log.stream", status: "logcat" },
          { from: "logs", to: "failures", label: "failure.signal", status: "triage" },
        ],
        failures: [
          { from: "kernel", to: "failures", label: "failure.control.online", status: "runtime" },
          { from: "logs", to: "failures", label: "log.triage", status: "risk" },
          { from: "failures", to: "reports", label: "evidence.bundle", status: "trace" },
        ],
        hmi: [
          { from: "kernel", to: "hmi", label: "hmi.capture.recent", status: "runtime" },
          { from: "scrcpy", to: "touch", label: "malagueta.clicks", status: "event" },
          { from: "touch", to: "hmi", label: "screenshot.compare", status: "compare" },
          { from: "hmi", to: "engine", label: "diff.engine", status: "score" },
          { from: "hmi", to: "shots", label: "capture.cache", status: "persist" },
          { from: "shots", to: "hmiteste", label: "Data/HMI_TESTE", status: "archive" },
          { from: "shots", to: "manifest", label: "manifest.jsonl", status: "timeline" },
        ],
      };
      function uniqueFlows(flows) {
        const seen = new Set();
        return flows.filter((flow) => {
          const key = `${flow.from}->${flow.to}:${flow.label}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return byId[flow.from] && byId[flow.to];
        });
      }
      const runtimePanels = panelStates.filter((panel) => panel.online && !["control", "chat"].includes(panel.id));
      const runtimeMode = runtimePanels.length > 0;
      const runtimeFlows = uniqueFlows(runtimePanels.flatMap((panel) => runtimeFlowMap[panel.id] || [
        { from: "kernel", to: panel.node, label: `${panel.label}.online`, status: panel.mode || "runtime" }
      ]));
      const agentFlows = (runtimeMode && runtimeFlows.length ? runtimeFlows : uniqueFlows(baseFlows));
      let w = 1, h = 1, active = byId.kernel, mouse = { x: -9999, y: -9999 };
      let camera = { x: 0, y: 0, scale: 1 };
      let dragging = false;
      let dragStart = { x: 0, y: 0, camX: 0, camY: 0 };
      let activeFlowIndex = 0;
      let lastFlowTick = 0;
      let flowProgress = 0;

      function resize() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = Math.max(640, rect.width);
        h = Math.max(620, rect.height);
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        nodes.forEach((n) => {
          n.tx = (n.x / 100) * w;
          n.ty = (n.y / 100) * h;
          if (n.px == null) {
            n.px = n.tx + (Math.random() - .5) * 26;
            n.py = n.ty + (Math.random() - .5) * 26;
            n.vx = 0;
            n.vy = 0;
          }
        });
      }

      function screenToWorld(x, y) {
        return {
          x: (x - camera.x) / camera.scale,
          y: (y - camera.y) / camera.scale
        };
      }

      function clampCamera() {
        camera.scale = Math.max(.42, Math.min(3.2, camera.scale));
      }

      function zoomAt(screenX, screenY, factor) {
        const before = screenToWorld(screenX, screenY);
        camera.scale *= factor;
        clampCamera();
        camera.x = screenX - before.x * camera.scale;
        camera.y = screenY - before.y * camera.scale;
      }

      function fitGraph() {
        if (!nodes.length) return;
        const pad = 84;
        const xs = nodes.map((n) => n.px ?? n.tx ?? 0);
        const ys = nodes.map((n) => n.py ?? n.ty ?? 0);
        const minX = Math.min(...xs) - pad;
        const maxX = Math.max(...xs) + pad;
        const minY = Math.min(...ys) - pad;
        const maxY = Math.max(...ys) + pad;
        const graphW = Math.max(1, maxX - minX);
        const graphH = Math.max(1, maxY - minY);
        camera.scale = Math.min(2.4, Math.max(.45, Math.min(w / graphW, h / graphH)));
        camera.x = (w - graphW * camera.scale) / 2 - minX * camera.scale;
        camera.y = (h - graphH * camera.scale) / 2 - minY * camera.scale;
      }

      function setActive(node) {
        active = node || active;
      }

      function formatFlow(flow) {
        return `${flow.from} -> ${flow.to}  // ${flow.label}`;
      }

      function renderAgentBus() {
        const activeIndex = agentFlows.length ? activeFlowIndex % agentFlows.length : 0;
        const visibleFlows = runtimeMode
          ? agentFlows.slice(0, 7)
          : agentFlows.length
            ? Array.from({ length: Math.min(7, agentFlows.length) }, (_, offset) => agentFlows[(activeIndex + offset) % agentFlows.length])
            : [];
        const liveCount = runtimeMode ? visibleFlows.length : Math.min(AMBIENT_FLOW_COUNT, visibleFlows.length);
        busLinesEl.innerHTML = visibleFlows.map((flow, index) => {
          const isLive = index < liveCount;
          return `
            <div class="bus-line ${isLive ? "live" : ""} ${runtimeMode ? "locked" : ""}">
              <span class="bus-path">${formatFlow(flow)}</span>
              <span class="bus-status">${runtimeMode ? "real" : isLive ? flow.status : "standby"}</span>
            </div>
          `;
        }).join("");
        panelStateEl.innerHTML = panelStates.map((panel) => `
          <span class="panel-chip ${panel.online ? "online" : ""}">${panel.label}</span>
        `).join("");
        const now = new Date();
        busClockEl.textContent = `${runtimeMode ? "runtime.lock" : "ambient.flow"} t+${String(now.getSeconds()).padStart(2, "0")}.${String(Math.floor(now.getMilliseconds() / 10)).padStart(2, "0")}`;
      }

      function updateAgentFlow(timestamp) {
        if (!agentFlows.length) return;
        if (runtimeMode) {
          flowProgress = .72;
          if (!lastFlowTick || timestamp - lastFlowTick > 2600) {
            renderAgentBus();
            lastFlowTick = timestamp;
          }
          return;
        }
        if (!lastFlowTick || timestamp - lastFlowTick > FLOW_INTERVAL_MS) {
          activeFlowIndex = (activeFlowIndex + 1) % agentFlows.length;
          const flow = agentFlows[activeFlowIndex];
          setActive(byId[flow.to] || byId[flow.from]);
          renderAgentBus();
          lastFlowTick = timestamp;
        }
        const elapsed = Math.max(0, timestamp - lastFlowTick);
        const linear = Math.min(1, elapsed / FLOW_INTERVAL_MS);
        flowProgress = 1 - Math.pow(1 - linear, 3);
      }

      function activeFlowEntries() {
        if (!agentFlows.length) return [];
        if (runtimeMode) {
          return agentFlows.map((flow, slot) => ({ flow, slot, locked: true, progress: .56 + (slot % 3) * .12 }));
        }
        const count = Math.min(AMBIENT_FLOW_COUNT, agentFlows.length);
        return Array.from({ length: count }, (_, slot) => ({
          flow: agentFlows[(activeFlowIndex + slot) % agentFlows.length],
          slot,
          locked: false,
          progress: (flowProgress + slot * .16) % 1
        }));
      }

      function flowTouchesNode(nodeId) {
        return activeFlowEntries().some(({ flow }) => flow && (flow.from === nodeId || flow.to === nodeId));
      }

      function flowEntryForLink(link) {
        return activeFlowEntries().find(({ flow }) =>
          flow &&
          ((link.a.id === flow.from && link.b.id === flow.to) ||
           (link.a.id === flow.to && link.b.id === flow.from))
        );
      }

      function flowTouchesLink(link) {
        return Boolean(flowEntryForLink(link));
      }

      function quadraticPoint(x0, y0, cx, cy, x1, y1, t) {
        const mt = 1 - t;
        return {
          x: mt * mt * x0 + 2 * mt * t * cx + t * t * x1,
          y: mt * mt * y0 + 2 * mt * t * cy + t * t * y1
        };
      }

      function drawQuadraticSegment(x0, y0, cx, cy, x1, y1, t0, t1) {
        const start = Math.max(0, Math.min(1, t0));
        const end = Math.max(start, Math.min(1, t1));
        const steps = 18;
        const first = quadraticPoint(x0, y0, cx, cy, x1, y1, start);
        ctx.beginPath();
        ctx.moveTo(first.x, first.y);
        for (let i = 1; i <= steps; i++) {
          const t = start + (end - start) * (i / steps);
          const point = quadraticPoint(x0, y0, cx, cy, x1, y1, t);
          ctx.lineTo(point.x, point.y);
        }
      }

      function step() {
        nodes.forEach((n) => {
          n.vx += (n.tx - n.px) * .003;
          n.vy += (n.ty - n.py) * .003;
        });
        links.forEach((l) => {
          const dx = l.b.px - l.a.px;
          const dy = l.b.py - l.a.py;
          const dist = Math.hypot(dx, dy) || 1;
          const desired = 118 + (1.4 - Math.min(l.a.w, l.b.w)) * 52;
          const force = (dist - desired) * .0009;
          const fx = dx / dist * force;
          const fy = dy / dist * force;
          l.a.vx += fx; l.a.vy += fy;
          l.b.vx -= fx; l.b.vy -= fy;
        });
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            const dx = b.px - a.px;
            const dy = b.py - a.py;
            const dist = Math.max(22, Math.hypot(dx, dy));
            const repel = 58 / (dist * dist);
            a.vx -= dx * repel; a.vy -= dy * repel;
            b.vx += dx * repel; b.vy += dy * repel;
          }
        }
        nodes.forEach((n) => {
          n.vx *= .86;
          n.vy *= .86;
          n.px += n.vx;
          n.py += n.vy;
        });
      }

      function drawGrid() {
        ctx.save();
        ctx.translate(camera.x, camera.y);
        ctx.scale(camera.scale, camera.scale);
        ctx.strokeStyle = "rgba(241,239,231,.045)";
        ctx.lineWidth = 1 / camera.scale;
        const left = -camera.x / camera.scale;
        const top = -camera.y / camera.scale;
        const right = left + w / camera.scale;
        const bottom = top + h / camera.scale;
        for (let x = Math.floor(left / 42) * 42; x < right; x += 42) {
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        }
        for (let y = Math.floor(top / 42) * 42; y < bottom; y += 42) {
          ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
        }
        ctx.restore();
      }

      function draw() {
        ctx.clearRect(0, 0, w, h);
        drawGrid();
        ctx.save();
        ctx.translate(camera.x, camera.y);
        ctx.scale(camera.scale, camera.scale);
        links.forEach((l) => {
          const flowEntry = flowEntryForLink(l);
          const flowHot = Boolean(flowEntry);
          const nodeHot = l.a === active || l.b === active;
          const hot = flowHot || nodeHot;
          const cx = (l.a.px + l.b.px) / 2 + (l.b.py - l.a.py) * .045;
          const cy = (l.a.py + l.b.py) / 2 - (l.b.px - l.a.px) * .045;
          ctx.strokeStyle = flowHot ? "rgba(200,169,104,.34)" : (nodeHot ? "rgba(200,169,104,.20)" : "rgba(241,239,231,.13)");
          ctx.lineWidth = (flowHot ? 1.15 : nodeHot ? .9 : .62) / camera.scale;
          ctx.beginPath();
          ctx.moveTo(l.a.px, l.a.py);
          ctx.quadraticCurveTo(cx, cy, l.b.px, l.b.py);
          ctx.stroke();

          if (flowHot) {
            ctx.save();
            ctx.shadowColor = flowEntry.locked ? "rgba(200,169,104,.34)" : "rgba(200,169,104,.72)";
            ctx.shadowBlur = (flowEntry.locked ? 9 : 16) / camera.scale;
            ctx.strokeStyle = flowEntry.locked ? "rgba(220,197,147,.34)" : "rgba(220,197,147,.86)";
            ctx.lineWidth = (flowEntry.locked ? 1.75 : 2.55) / camera.scale;
            if (flowEntry.locked) {
              ctx.beginPath();
              ctx.moveTo(l.a.px, l.a.py);
              ctx.quadraticCurveTo(cx, cy, l.b.px, l.b.py);
            } else {
              const start = Math.max(0, flowEntry.progress - FLOW_TAIL);
              const end = Math.min(1, flowEntry.progress);
              drawQuadraticSegment(l.a.px, l.a.py, cx, cy, l.b.px, l.b.py, start, end);
            }
            ctx.stroke();
            ctx.restore();
          }

          l.phase = (l.phase + l.speed) % 1;
          const t = flowHot ? flowEntry.progress : l.phase;
          const point = quadraticPoint(l.a.px, l.a.py, cx, cy, l.b.px, l.b.py, t);
          ctx.fillStyle = flowHot ? (flowEntry.locked ? "rgba(241,224,176,.58)" : "rgba(241,224,176,.95)") : (hot ? "rgba(200,169,104,.46)" : "rgba(241,239,231,.20)");
          ctx.beginPath();
          ctx.arc(point.x, point.y, flowHot ? (flowEntry.locked ? 1.65 : 2.35) : hot ? 1.55 : .95, 0, Math.PI * 2);
          ctx.fill();
        });
        nodes.forEach((n) => {
          const dx = mouse.x - n.px;
          const dy = mouse.y - n.py;
          const hover = !dragging && Math.hypot(dx, dy) < 42;
          if (hover && active !== n) setActive(n);
          const hot = n === active || flowTouchesNode(n.id);
          const r = (n.group === "core" ? 22 : 12) * (n.w || 1);
          ctx.fillStyle = hot ? "rgba(200,169,104,.14)" : "rgba(7,7,7,.78)";
          ctx.strokeStyle = hot ? "rgba(200,169,104,.9)" : "rgba(241,239,231,.38)";
          ctx.lineWidth = (hot ? 1.7 : .85) / camera.scale;
          ctx.beginPath();
          ctx.arc(n.px, n.py, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          ctx.strokeStyle = hot ? "rgba(200,169,104,.52)" : "rgba(241,239,231,.18)";
          ctx.beginPath();
          ctx.moveTo(n.px - r - 7, n.py); ctx.lineTo(n.px + r + 7, n.py);
          ctx.moveTo(n.px, n.py - r - 7); ctx.lineTo(n.px, n.py + r + 7);
          ctx.stroke();
          ctx.fillStyle = hot ? "#f1efe7" : (colors[n.group] || "#bbb7ab");
          ctx.font = hot ? "700 12px Consolas, monospace" : "11px Consolas, monospace";
          ctx.textAlign = "center";
          ctx.fillText(n.label, n.px, n.py + r + 18);
          ctx.fillStyle = "rgba(241,239,231,.42)";
          ctx.font = "9px Consolas, monospace";
          ctx.fillText(n.role, n.px, n.py + r + 32);
        });
        ctx.restore();
      }

      function animate(timestamp) {
        step();
        updateAgentFlow(timestamp || performance.now());
        draw();
        requestAnimationFrame(animate);
      }

      canvas.addEventListener("pointerdown", (event) => {
        dragging = true;
        graphCard.classList.add("dragging");
        dragStart = { x: event.clientX, y: event.clientY, camX: camera.x, camY: camera.y };
        canvas.setPointerCapture(event.pointerId);
      });

      canvas.addEventListener("pointermove", (event) => {
        const rect = canvas.getBoundingClientRect();
        const sx = event.clientX - rect.left;
        const sy = event.clientY - rect.top;
        if (dragging) {
          camera.x = dragStart.camX + event.clientX - dragStart.x;
          camera.y = dragStart.camY + event.clientY - dragStart.y;
        }
        const world = screenToWorld(sx, sy);
        mouse.x = world.x;
        mouse.y = world.y;
      });

      canvas.addEventListener("pointerup", (event) => {
        dragging = false;
        graphCard.classList.remove("dragging");
        try { canvas.releasePointerCapture(event.pointerId); } catch (error) {}
      });

      canvas.addEventListener("pointercancel", () => {
        dragging = false;
        graphCard.classList.remove("dragging");
      });

      canvas.addEventListener("mouseleave", () => {
        if (!dragging) {
          mouse.x = -9999;
          mouse.y = -9999;
        }
      });

      canvas.addEventListener("dblclick", fitGraph);

      canvas.addEventListener("wheel", (event) => {
        event.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const sx = event.clientX - rect.left;
        const sy = event.clientY - rect.top;
        zoomAt(sx, sy, event.deltaY < 0 ? 1.12 : .89);
      }, { passive: false });

      fitBtn.addEventListener("click", fitGraph);
      zoomInBtn.addEventListener("click", () => zoomAt(w / 2, h / 2, 1.18));
      zoomOutBtn.addEventListener("click", () => zoomAt(w / 2, h / 2, .84));

      function afterViewportChange() {
        setTimeout(() => { resize(); fitGraph(); }, 90);
      }

      expandBtn.addEventListener("click", async () => {
        if (graphCard.requestFullscreen) {
          try {
            if (document.fullscreenElement === graphCard) {
              await document.exitFullscreen();
            } else {
              await graphCard.requestFullscreen();
            }
            return;
          } catch (error) {}
        }
        shell.classList.toggle("expanded");
        expandBtn.textContent = shell.classList.contains("expanded") ? "collapse" : "expand";
        afterViewportChange();
      });

      document.addEventListener("fullscreenchange", () => {
        expandBtn.textContent = document.fullscreenElement === graphCard ? "collapse" : "expand";
        afterViewportChange();
      });

      window.addEventListener("mouseup", () => {
        dragging = false;
        graphCard.classList.remove("dragging");
        mouse.x = -9999;
        mouse.y = -9999;
      });

      window.addEventListener("resize", resize);
      resize();
      setActive(byId.kernel);
      fitGraph();
      renderAgentBus();
      animate();
    </script>
    """
    html = (
        html.replace("__NODES__", nodes_json)
        .replace("__LINKS__", links_json)
        .replace("__PANEL_STATES__", panel_states_json)
        .replace("__NODE_COUNT__", str(len(nodes)))
        .replace("__LINK_COUNT__", str(len(links)))
    )
    components.html(html, height=790, scrolling=False)


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
RUN_SCRIPT = root_path("Run", "run_noia.py")
COLETOR_SCRIPT = root_path("Scripts", "coletor_adb.py")
PROCESSAR_SCRIPT = root_path("Pre_process", "processar_dataset.py")
PAUSE_FLAG_PATH = os.path.join(PROJECT_ROOT, "pause.flag")
# STATUS_PATH removido: status agora fica dentro de cada teste

# === MODO CONVERSACIONAL ===
MODO_CONVERSA = True  # Altere para False se quiser desativar as respostas naturais
PAGINA_CHAT = "Chat"
PAGINA_DASHBOARD = "Dashboard"
PAGINA_LOGS_RADIO = "Painel de Logs"
PAGINA_CONTROLE_FALHAS = "Controle de Falhas"
PAGINA_MENU_TESTER = "Menu Tester"
PAGINA_VALIDACAO_HMI = "Validação HMI"
PAGINA_MAPA_NEURAL_IA = "Mapa Neural IA"
NAV_RADIO_KEY = "pagina_navegacao"
NAV_PENDING_KEY = "pagina_navegacao_pendente"
DASHBOARD_PORT = 8504
LOGS_PANEL_PORT = 8505
FAILURE_CONTROL_PORT = 8506
MENU_TESTER_PORT = 8503


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
    threading.Thread(target=_preload_whisper_default, daemon=True).start()
if NAV_RADIO_KEY not in st.session_state:
    st.session_state[NAV_RADIO_KEY] = PAGINA_CHAT
if NAV_PENDING_KEY not in st.session_state:
    st.session_state[NAV_PENDING_KEY] = None

# =========================
# === SUPORTE A BANCADAS ===
# =========================
GLOBAL_LOG_SEQUENCE_CATEGORY = "__system__"
GLOBAL_LOG_SEQUENCE_TEST = "failure_log_sequence_global"
GLOBAL_LOG_SEQUENCE_CSV = os.path.join(DATA_ROOT, "failure_log_sequence.csv")
GLOBAL_LOG_SEQUENCE_RAW_JSON = os.path.join(DATA_ROOT, "failure_log_sequence.raw.json")
GLOBAL_LOG_SEQUENCE_META_JSON = os.path.join(DATA_ROOT, "failure_log_sequence.meta.json")


def _url_ativa(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5):
            return True
    except Exception:
        return False


def _porta_local_ativa(port: int, timeout_s: float = 0.35) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout_s):
            return True
    except OSError:
        return False


def _aguardar_porta_local(port: int, timeout_s: float = 12.0) -> bool:
    deadline = time.time() + max(1.0, float(timeout_s))
    while time.time() < deadline:
        if _porta_local_ativa(port):
            return True
        time.sleep(0.2)
    return False


def _streamlit_launch_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


def _iniciar_app_streamlit(script_path: str, port: int, silence_output: bool = False) -> None:
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        script_path,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--server.fileWatcherType",
        "none",
        "--server.runOnSave",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]
    kwargs = {
        "cwd": BASE_DIR,
        "env": _streamlit_launch_env(),
        **_subprocess_windowless_kwargs(),
    }
    if silence_output:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        return
    subprocess.Popen(cmd, **kwargs)


def _garantir_app_streamlit(script_path: str, port: int, silence_output: bool = False, timeout_s: float = 12.0) -> bool:
    if _porta_local_ativa(port):
        return True
    _iniciar_app_streamlit(script_path, port, silence_output=silence_output)
    return _aguardar_porta_local(port, timeout_s=timeout_s)


def _selecionar_pagina(nome_pagina: str) -> None:
    st.session_state[NAV_PENDING_KEY] = nome_pagina


def _abrir_menu_tester() -> str:
    tester_url = f"http://localhost:{MENU_TESTER_PORT}"
    try:
        pronto = _garantir_app_streamlit(
            root_path("app", "streamlit", "menu_tester.py"),
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
            root_path("Dashboard", "painel_logs_radio.py"),
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
            root_path("Dashboard", "controle_falhas.py"),
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
    texto_norm = _replace_number_words(_norm(texto))
    intencao_navegacao = any(
        trecho in texto_norm
        for trecho in [
            "abrir",
            "abre",
            "abra",
            "ir para",
            "ir pro",
            "ir pra",
            "vai para",
            "acesse",
            "acessar",
            "mostrar",
            "mostra",
        ]
    )
    comandos_diretos = {
        "dashboard",
        "painel de logs",
        "logs do radio",
        "painel de logs do radio",
        "controle de falhas",
        "falhas",
        "painel de falhas",
        "menu tester",
        "menu testers",
        "menu dos testers",
        "validacao hmi",
        "validar hmi",
        "hmi",
        "mapa neural",
        "mapa da ia",
        "cerebro da ia",
        "cerebro",
    }
    if not intencao_navegacao and texto_norm not in comandos_diretos:
        return None

    if "dashboard" in texto_norm:
        _selecionar_pagina(PAGINA_DASHBOARD)
        return "Abrindo o dashboard."

    if ("painel de logs" in texto_norm or "logs do radio" in texto_norm) and any(
        token in texto_norm for token in ["abrir", "abre", "abra", "mostrar", "mostra", "painel", "logs"]
    ):
        _selecionar_pagina(PAGINA_LOGS_RADIO)
        return "Abrindo o painel de logs."

    if "falha" in texto_norm and any(
        token in texto_norm
        for token in ["abrir", "abre", "abra", "mostrar", "mostra", "painel", "controle", "falhas"]
    ):
        _selecionar_pagina(PAGINA_CONTROLE_FALHAS)
        return "Abrindo o controle de falhas."

    if "hmi" in texto_norm and any(token in texto_norm for token in ["valid", "validacao", "validar", "hmi"]):
        _selecionar_pagina(PAGINA_VALIDACAO_HMI)
        return "Abrindo a validação HMI."

    if any(token in texto_norm for token in ["mapa neural", "mapa da ia", "cerebro da ia", "cerebro"]):
        _selecionar_pagina(PAGINA_MAPA_NEURAL_IA)
        return "Abrindo o mapa neural da IA."

    if re.search(r"\bmenu\s+(dos?\s+)?testers?\b", texto_norm) or "menu tester" in texto_norm:
        _selecionar_pagina(PAGINA_CHAT)
        return _abrir_menu_tester()

    return None


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
    from Run.run_noia import capturar_logs_teste

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

def interpretar_comando(comando: str) -> str:
    texto = comando.strip()
    texto_norm = _norm(texto)

    resposta_navegacao = _resolver_comando_navegacao(texto)
    if resposta_navegacao:
        return resposta_navegacao

    # 1) AJUDA
    if _has_any(texto_norm, KW_AJUDA):
        return (
            "**Comandos suportados**\n"
            "- **executar/rodar** `<teste>` [na bancada N|todas]\n"
            "- **executar em paralelo** `executar teste_x na bancada 1 e executar teste_y na bancada 2`\n"
            "- **gravar/coletar** `<teste>` [na bancada N|todas]\n"
            "- **capturar log** [do `<teste>`] [na bancada N]\n"
            "- **gravar sequencia padrao de coleta de logs** [na bancada N]\n"
            "- **processar** `<teste>`\n"
            "- **apagar/deletar/remover** `<teste>`\n"
            "- **listar/mostrar** categorias | testes [de <categoria>]\n"
            "- **listar bancadas**\n"
            "- **abrir** dashboard | mapa neural | painel de logs | controle de falhas | menu tester | validacao HMI\n"
            "Ex.: `execute o teste audio_1 na bancada 2`"
        )

    if st.session_state.log_sequence_recording and any(
        p in texto_norm
        for p in [
            "finalizar gravacao da sequencia de log",
            "finalizar sequencia de log",
            "salvar sequencia de log",
            "encerrar sequencia de log",
            "parar gravacao da sequencia de log",
        ]
    ):
        return finalizar_gravacao_sequencia_logs()

    # 2) LISTAR BANCADAS
    if _has_any(texto_norm, ["listar bancadas", "mostrar bancadas", "listar devices", "mostrar devices"]) \
       or (_has_any(texto_norm, KW_LISTAR) and any(k in texto_norm for k in ["bancada", "bancadas", "devices", "dispositivos"])):  
        return _formatar_bancadas_str(listar_bancadas())

    if any(
        p in texto_norm
        for p in [
            "capturar log",
            "capturar logs",
            "coletar log",
            "coletar logs",
            "capturar log do radio",
            "capturar logs do radio",
        ]
    ):
        return capturar_log_radio_comando(texto)

    # 3) EXECUTAR (rodar testes)
    if _has_any(texto_norm, KW_EXECUTAR):
        execucoes_paralelas, erro_paralelo = _extrair_execucoes_paralelas(texto)
        if erro_paralelo:
            return erro_paralelo
        if execucoes_paralelas:
            return executar_testes_em_paralelo(execucoes_paralelas)

        # Caso especial: "todos os testes da categoria X"
        if re.search(r"todos\s+os\s+testes\s+da\s+categoria", texto_norm):
            cat = _extrair_categoria(texto)
            if not cat:
                return "Aviso: especifique a categoria (ex: rodar todos os testes da categoria audio)."

            testes = listar_testes(cat)
            if not testes:
                return f"A categoria **{cat}** nao possui testes."

            bancada = _extrair_bancada(texto)
            respostas = [f"Rodando todos os testes da categoria **{cat}** na bancada {bancada or '(padrao)'}..."]

            for t in testes:
                respostas.append(executar_teste(cat, t, bancada))

            return "\n".join(respostas)

        # âœ… Caso normal: executar um teste especÃ­fico (ex: "executar teste geral_1" ou "executar geral 2")
        token = _extrair_token_teste(texto)
        if token:
            cat, nome = _resolver_teste(token)
            if cat and nome:
                bancada = _extrair_bancada(texto)
                return executar_teste(cat, nome, bancada)
            else:
                # tentativa extra: se o usuÃ¡rio disse apenas "geral 2" sem categoria explÃ­cita
                # busca qualquer teste com nome igual em todas as categorias
                for cat_try in listar_categorias():
                    if token in listar_testes(cat_try):
                        bancada = _extrair_bancada(texto)
                        return executar_teste(cat_try, token, bancada)
                return f"ERRO: teste **{token}** nao encontrado em `Data/*/`."
        return "Aviso: especifique o teste a executar (ex: `executar teste geral_1 na bancada 1`)."

    # 4) GRAVAR / COLETAR
    if _has_any(texto_norm, KW_GRAVAR):
        if _eh_comando_gravar_sequencia_logs(texto):
            bancada = _extrair_bancada(texto)
            return gravar_sequencia_global_logs(bancada)
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
            else:
                return "Aviso: use o formato categoria_nome (ex: audio_3)."

            bancada = _extrair_bancada(texto)
            return gravar_teste(cat, token, bancada)

        return "Aviso: especifique o teste (ex: `gravar audio_1 na bancada 1`)."

    # 5) PROCESSAR (gera dataset)
    if _has_any(texto_norm, KW_PROCESS):
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
                return processar_teste(cat, token)
            return "Aviso: use o formato categoria_nome (ex: audio_3)."
        return "Aviso: especifique o teste (ex: `processar audio_1`)."

    # 6) APAGAR / DELETAR
    if _has_any(texto_norm, KW_APAGAR):
        token = _extrair_token_teste(texto)
        if token:
            cat, teste = _resolver_teste(token)
            if cat and teste:
                return apagar_teste(cat, teste)
            return f"ERRO: nao encontrei o teste **{token}** em `Data/*/`."
        return "Aviso: especifique o teste (ex: `apagar audio_1`)."

    # 7) LISTAR / MOSTRAR
    if _has_any(texto_norm, KW_LISTAR):
        cat = _extrair_categoria(texto)
        if cat:
            testes = listar_testes(cat)
            if testes:
                return f"Testes em **{cat}**:\n- " + "\n- ".join(testes)
            return f"A categoria **{cat}** nao possui testes."
        cats = listar_categorias()
        if cats:
            return "Categorias disponiveis:\n- " + "\n- ".join(cats)
        return "Nenhuma categoria encontrada em `Data/`."

    # RESETAR INTERFACE / REVERTER ACOES
    if any(_norm(p) in texto_norm for p in ["reset", "resetar", "reverter", "restaurar", "desfazer"]):
        token = _extrair_token_teste(texto)
        if token:
            cat, nome = _resolver_teste(token)
            if cat and nome:
                bancada = _extrair_bancada(texto)
                try:
                    cmd = ["python", RUN_SCRIPT, "--reset", cat, nome]
                    if bancada:
                        cmd += ["--serial", bancada]
                    subprocess.Popen(cmd, cwd=BASE_DIR)
                    return f"Reset comportamental iniciado para **{cat}/{nome}** na bancada `{bancada or 'padrao'}`."
                except Exception as e:
                    return f"ERRO: falha ao iniciar reset: {e}"
            else:
                return f"ERRO: teste **{token}** nao encontrado."
        else:
            return "Aviso: especifique o teste para resetar (ex: `reset geral_1 na bancada 1`)."

    # 8) CONTROLE DE EXECUÃ‡ÃƒO (pausar, retomar, parar)
    if any(_norm(p) in texto_norm for p in ["pausar", "pause", "parar teste", "interromper", "stop"]):
        return pausar_execucao()

    if any(_norm(p) in texto_norm for p in ["retomar", "continuar", "resume", "seguir"]):
        return retomar_execucao()

    if any(_norm(p) in texto_norm for p in ["cancelar", "encerrar", "finalizar", "stop all", "terminar"]):
        return parar_execucao()

    return "ERRO: nao entendi o comando. Digite **ajuda** para ver exemplos."

def responder_conversacional(comando: str):
    """
    Interpreta comandos em linguagem natural e responde de forma humana,
    mantendo integraÃ§Ã£o com o interpretador tÃ©cnico.
    """

    # CorreÃ§Ãµes automÃ¡ticas comuns de fala
    substituicoes_voz = {
        "star bancadas": "listar bancadas",
        "esta bancadas": "listar bancadas",
        "instalar bancadas": "listar bancadas",
        "historia bancadas": "listar bancadas",
        "listar bancada": "listar bancadas",
        "listra bancadas": "listar bancadas",
        "ver bancadas": "listar bancadas",
        "mostra bancadas": "listar bancadas",
        "voltar": "resetar",
        "voltar teste": "resetar",
        "voltar o teste": "resetar",
        "voltar geral": "resetar geral",
        "volta geral": "resetar geral",
        "reset": "resetar",
        "refazer estado": "resetar",
    }

    for errado, certo in substituicoes_voz.items(): 
        if errado in comando.lower():
            comando = comando.lower().replace(errado, certo)


    comando_norm = _norm(comando)

    # fluxo guiado de gravacao
    if st.session_state.pending_gravacao is not None:
        return continuar_fluxo_gravacao(comando)

    resposta_navegacao = _resolver_comando_navegacao(comando)
    if resposta_navegacao:
        return resposta_navegacao

    # ExpressÃµes auxiliares para respostas naturais
    frases_iniciais = [
        "Entendido",
        "Certo",
        "Perfeito",
        "Beleza",
        "Ok, ja vou cuidar disso"
    ]

    frases_execucao = [
        "Iniciando o teste agora",
        "Rodando o caso de teste no radio",
        "Executando o cenario solicitado",
        "Comecando a sequencia de validacoes"
    ]

    frases_coleta = [
        "Iniciando gravacao",
        "Pode tocar na tela, estou coletando os gestos.",
        "Gravando as interacoes agora"
    ]

    frases_processamento = [
        "Gerando o dataset, aguarde um instante",
        "Transformando os logs em dados uteis",
        "Processando o dataset para voce"
    ]

    frases_bancadas = [
        "Consultando bancadas ADB conectadas",
        "Um segundo, vou listar as bancadas disponiveis",
        "Beleza, verificando conexoes com as bancadas"
    ]

    frases_ajuda = [
        "Aqui esta o que posso fazer",
        "Claro! Aqui estao alguns comandos que voce pode usar",
        "Lista de comandos a disposicao"
    ]

    respostas_rapidas = {
        "oi": "Ola! Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "ola": "Ola! Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "ola": "Ola! Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "eai": "Fala! Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "e a?": "Fala! Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "bom dia": "Bom dia! Posso ajudar com testes ou comandos.",
        "boa tarde": "Boa tarde! Posso ajudar com testes ou comandos.",
        "boa noite": "Boa noite! Posso ajudar com testes ou comandos.",
        "tudo bem": "Tudo sim! Posso ajudar com testes ou comandos.",
        "beleza": "Beleza! Posso ajudar com testes ou comandos.",
        "blz": "Blz! Posso ajudar com testes ou comandos."
    }

    saudacoes_rapidas = ["oi", "ola", "ola", "eai", "e a?", "bom dia", "boa tarde", "boa noite", "tudo bem", "beleza", "blz"]
    comando_norm_limpo = re.sub(r"[^a-z0-9\s]", "", comando_norm).strip()
    for s in saudacoes_rapidas:
        if comando_norm_limpo == s or comando_norm_limpo.startswith(s + " "):
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": respostas_rapidas.get(s, "Ola! Posso ajudar com testes ou comandos.")
            })
            return ""

    # Permite frases como "Zuri, listar bancadas"
    if comando_norm.startswith("zuri"):
        comando_norm = comando_norm.replace("zuri", "", 1).strip()

    if st.session_state.log_sequence_recording and any(
        p in comando_norm
        for p in [
            "finalizar gravacao da sequencia de log",
            "finalizar sequencia de log",
            "salvar sequencia de log",
            "encerrar sequencia de log",
            "parar gravacao da sequencia de log",
        ]
    ):
        resposta_pre = "Encerrando a gravacao da sequencia padrao de logs."
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return finalizar_gravacao_sequencia_logs()

    # === ROTEAMENTO ===
    if any(p in comando_norm for p in ["listar bancadas", "ver bancadas", "bancadas conectadas"]):
        resposta_pre = random.choice(frases_bancadas)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback("listar bancadas")

    if any(
        p in comando_norm
        for p in [
            "capturar log",
            "capturar logs",
            "coletar log",
            "coletar logs",
            "capturar log do radio",
            "capturar logs do radio",
        ]
    ):
        resposta_pre = "Capturando os logs do radio para a bancada solicitada."
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback(comando)

    # â™»ï¸ RESETAR TESTE / REVERTER AÃ‡Ã•ES
    if any(p in comando_norm for p in ["reset", "resetar", "reverter", "restaurar", "desfazer", "voltar estado inicial"]):
        resposta_pre = f"{random.choice(frases_iniciais)}. Restaurando estado inicial do teste..."
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        if _extrair_token_teste(comando) is None and "gravar" in comando_norm:
            return iniciar_fluxo_gravacao()
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["executar", "rodar", "testar", "rodar o teste"]):
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_execucao)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        if _extrair_token_teste(comando) is None and "gravar" in comando_norm:
            return iniciar_fluxo_gravacao()
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["gravar teste", "gravar", "coletar teste", "coletar", "capturar"]):
        if _eh_comando_gravar_sequencia_logs(comando):
            resposta_pre = "Iniciando a gravacao da sequencia padrao de coleta de logs."
            st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
            return resolver_comando_com_llm_ou_fallback(comando)
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_coleta)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        if _extrair_token_teste(comando) is None and "gravar" in comando_norm:
            return iniciar_fluxo_gravacao()
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["processar", "gerar dataset", "montar csv"]):
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_processamento)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        if _extrair_token_teste(comando) is None and "gravar" in comando_norm:
            return iniciar_fluxo_gravacao()
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["ajuda", "comandos", "socorro", "me ajuda"]):
        resposta_pre = random.choice(frases_ajuda)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback("ajuda")

    # Caso n?o tenha correspond?ncia
    resposta_llm = llm_responder_chat(comando) if MODO_CONVERSA else None
    if resposta_llm:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": resposta_llm
        })
        return ""

    st.session_state.chat_history.append({
        "role": "assistant",
        "content": "Posso ajudar com comandos de testes. Ex.: `executar audio_1 na bancada 1`"
    })
    return ""
pagina_pendente = st.session_state.get(NAV_PENDING_KEY)
if pagina_pendente:
    st.session_state[NAV_RADIO_KEY] = pagina_pendente
    st.session_state[NAV_PENDING_KEY] = None

st.sidebar.title("Menu")
pagina = st.sidebar.radio(
    "",
    [
        PAGINA_CHAT,
        PAGINA_MAPA_NEURAL_IA,
        PAGINA_DASHBOARD,
        PAGINA_LOGS_RADIO,
        PAGINA_CONTROLE_FALHAS,
        PAGINA_MENU_TESTER,
        PAGINA_VALIDACAO_HMI,
    ],
    key=NAV_RADIO_KEY,
)

# Botao de voz (sidebar)
with st.sidebar:
    browser_audio = None
    audio_input_widget = getattr(st, "audio_input", None)
    if callable(audio_input_widget):
        browser_audio = audio_input_widget("Falar comando", key="chat_voice_browser_audio")
        st.caption("Use o microfone do navegador para gravar seu comando.")
    else:
        st.button("Falar comando", use_container_width=True, disabled=True)
        st.caption("Gravacao por navegador indisponivel nesta versao do Streamlit.")

if browser_audio is not None:
    try:
        getvalue = getattr(browser_audio, "getvalue", None)
        audio_bytes = getvalue() if callable(getvalue) else b""
        audio_sig = hashlib.sha1(audio_bytes).hexdigest() if audio_bytes else ""
        if audio_sig and audio_sig != st.session_state.get("chat_voice_browser_audio_sig", ""):
            st.session_state.chat_voice_browser_audio_sig = audio_sig
            recognizer = configurar_reconhecedor()
            st.toast("Reconhecendo fala do navegador...")
            audio = _audio_input_to_sr_audio(browser_audio)
            command_text, stt_engine, stt_error = _transcrever_audio_comando(recognizer, audio)
            if not command_text:
                detail = f" Detalhes: {stt_error}" if stt_error else ""
                raise RuntimeError("Falha ao reconhecer fala do navegador." + detail)
            st.toast(f"Reconhecido via {stt_engine}")
            _processar_comando_de_voz(command_text)
            st.rerun()
    except Exception as exc:
        st.session_state.chat_history.append({"role": "assistant", "content": f"Falha ao reconhecer fala do navegador: {exc}"})
        st.rerun()


# Side info: bancadas
with st.sidebar.expander("Bancadas (ADB)"):
    st.markdown(_formatar_bancadas_str(listar_bancadas()))
    if st.button("Atualizar lista de bancadas"):
        st.rerun()

# ============
# === CHAT ===
# ============
if pagina == PAGINA_CHAT:
    titulo_painel("VWAIT - Inteligência Artificial")
    if not st.session_state.chat_history:
        render_saudacao_menu_chat("Victor")

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

    checar_finalizacoes()
    checar_execucoes_finalizadas()
    if st.session_state.execucoes_ativas and st_autorefresh is not None:
        st_autorefresh(interval=2000, limit=None, key="chat_exec_watch")
    # === Exibio do hist?rico ===
    for idx, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(_sanitize_text(msg["content"]))
            if msg["role"] == "assistant" and (
                "Gravando" in msg["content"] or "sequencia padrao de coleta de logs" in msg["content"]
            ):
                m = re.search(
                    r"Gravando\s+\**([a-z0-9_]+)/([a-z0-9_]+)\**\s+na bancada\s+`?([0-9A-Za-z._:-]+)`?",
                    msg["content"],
                )
                cat = nome = serial = None
                if m:
                    cat, nome, serial = m.group(1), m.group(2), m.group(3)
                elif "sequencia padrao de coleta de logs" in msg["content"] and st.session_state.log_sequence_recording:
                    recording = st.session_state.log_sequence_recording
                    if isinstance(recording, dict):
                        cat_raw = recording.get("categoria")
                        nome_raw = recording.get("nome")
                        serial_raw = recording.get("bancada")
                        cat = cat_raw if isinstance(cat_raw, str) else None
                        nome = nome_raw if isinstance(nome_raw, str) else None
                        serial = serial_raw if isinstance(serial_raw, str) else None
                if st.button("Salvar esperado", key=f"esperado_{idx}"):
                    if cat and nome:
                        msg_resp = salvar_resultado_parcial(cat, nome, serial)
                    else:
                        msg_resp = "Aviso: nao consegui identificar categoria e nome da gravacao para salvar o esperado."
                    st.session_state.chat_history.append({"role": "assistant", "content": msg_resp})
                    st.rerun()
                if st.button("Finalizar gravacao", key=f"finalizar_{idx}"):
                    msg_resp = finalizar_gravacao(cat, nome, serial)
                    st.session_state.chat_history.append({"role": "assistant", "content": msg_resp})
                    st.rerun()
                if st.button("Cancelar gravacao", key=f"cancelar_{idx}"):
                    msg_resp = cancelar_gravacao(cat, nome) if cat and nome else "Aviso: nao consegui identificar a gravacao para cancelar."
                    st.session_state.chat_history.append({"role": "assistant", "content": msg_resp})
                    st.rerun()

        processing_placeholder = st.empty()

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

        with st.spinner("Processando comando..."):
            if st.session_state.pending_gravacao is not None:
                resposta = continuar_fluxo_gravacao(user_input)
            elif MODO_CONVERSA:
                resposta = responder_conversacional(user_input)
            else:
                resposta = resolver_comando_com_llm_ou_fallback(user_input)

        if resposta:
            st.session_state.chat_history.append({"role": "assistant", "content": resposta})
        st.session_state.chat_inline_input_nonce += 1
        st.rerun()

elif pagina == PAGINA_DASHBOARD:
    st.title("Dashboard")
    st.caption("Visualizando o mesmo dashboard do Menu Tester.")

    dash_port = DASHBOARD_PORT
    dash_url = f"http://localhost:{dash_port}"
    dash_script = root_path("Dashboard", "visualizador_execucao.py")

    if not _porta_local_ativa(dash_port):
        try:
            _garantir_app_streamlit(dash_script, dash_port, silence_output=True)
        except Exception as e:
            st.error(f"Falha ao iniciar dashboard: {e}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Recarregar dashboard"):
            st.rerun()
    with col2:
        if st.button("Abrir em nova aba"):
            try:
                import webbrowser
                webbrowser.open_new_tab(dash_url)
            except Exception:
                pass

    if _porta_local_ativa(dash_port):
        components.iframe(dash_url, height=1700, scrolling=True)
    else:
        st.warning("Dashboard ainda iniciando. Clique em 'Recarregar dashboard' em alguns segundos.")

elif pagina == PAGINA_MAPA_NEURAL_IA:
    render_mapa_neural_ia_coder()

elif pagina == PAGINA_LOGS_RADIO:
    st.title("Painel de Logs")
    st.caption("Exploracao local dos logs capturados e analise assistida por IA.")

    logs_port = LOGS_PANEL_PORT
    logs_url = f"http://localhost:{logs_port}"
    logs_script = root_path("Dashboard", "painel_logs_radio.py")

    if not _porta_local_ativa(logs_port):
        try:
            _garantir_app_streamlit(logs_script, logs_port, silence_output=True)
        except Exception as e:
            st.error(f"Falha ao iniciar painel de logs: {e}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Recarregar painel de logs"):
            st.rerun()
    with col2:
        if st.button("Abrir painel em nova aba"):
            try:
                import webbrowser
                webbrowser.open_new_tab(logs_url)
            except Exception:
                pass

    if _porta_local_ativa(logs_port):
        components.iframe(logs_url, height=1700, scrolling=True)
    else:
        st.warning("Painel de logs ainda iniciando. Clique em 'Recarregar painel de logs' em alguns segundos.")

elif pagina == PAGINA_CONTROLE_FALHAS:
    st.title("Controle de Falhas")
    st.caption("Painel dedicado para triagem, acompanhamento e preparo das falhas para Jira.")

    failure_port = FAILURE_CONTROL_PORT
    failure_url = f"http://localhost:{failure_port}"
    failure_script = root_path("Dashboard", "controle_falhas.py")

    if not _porta_local_ativa(failure_port):
        try:
            _garantir_app_streamlit(failure_script, failure_port, silence_output=True)
        except Exception as e:
            st.error(f"Falha ao iniciar controle de falhas: {e}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Recarregar controle de falhas"):
            st.rerun()
    with col2:
        if st.button("Abrir controle em nova aba"):
            try:
                import webbrowser
                webbrowser.open_new_tab(failure_url)
            except Exception:
                pass

    if _porta_local_ativa(failure_port):
        components.iframe(failure_url, height=1900, scrolling=True)
    else:
        st.warning("Controle de falhas ainda iniciando. Clique em 'Recarregar controle de falhas' em alguns segundos.")

elif pagina == PAGINA_MENU_TESTER:
    st.title("Menu Tester - VWAIT")
    st.info("Abra o menu_tester em uma nova aba para executar coletas e testes.")
    if st.button("Abrir Menu Tester"):
        resposta = _abrir_menu_tester()
        if resposta.startswith("Falha"):
            st.error(resposta)
        else:
            st.success(resposta)

elif pagina == PAGINA_VALIDACAO_HMI:
    from HMI.validacao_hmi import render_hmi_validation_page
    render_hmi_validation_page(PROJECT_ROOT, DATA_ROOT)

else:
    st.error(f"Pagina desconhecida: {pagina}")
