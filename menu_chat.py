import os
import re
import json
import shutil
import subprocess
from shutil import which
import speech_recognition as sr
try:
    import requests
except Exception:
    requests = None
import streamlit as st
from unicodedata import normalize
from PIL import Image
import matplotlib.pyplot as plt
import time
import urllib.request
from threading import Lock
from datetime import datetime
from difflib import SequenceMatcher
import random
import seaborn as sns
import colorama
import threading
from colorama import Fore, Style
colorama.init(autoreset=True)

status_lock = Lock()  # lock global de escrita

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:3b")
OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "40"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "256"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")


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
    # torna o nível de corte adaptativo ao ruído
    r.dynamic_energy_threshold = True
    # base razoável; será recalibrado pelo adjust_for_ambient_noise
    r.energy_threshold = 250
    # tolerância para pequenas pausas no meio da frase
    r.pause_threshold = 0.9
    # considera silêncio curtinho antes de encerrar
    r.non_speaking_duration = 0.3
    return r

def normalizar_pos_fala(txt: str) -> str:
    # correções comuns da fala -> texto
    m = {
        "executa": "executar",
        "rode": "rodar",
        "voltar ": "resetar ",
        "volta ": "resetar ",
        "reset ": "resetar ",
        "geral um": "geral 1",
        "geral dois": "geral 2",
        "geral tres": "geral 3",
        "bancada um": "bancada 1",
        "bancada dois": "bancada 2",
        "bancada três": "bancada 3",
        "na bancada um": "na bancada 1",
        "na bancada dois": "na bancada 2",
        "na bancada três": "na bancada 3",
        "rodar todos os teste": "rodar todos os testes",
        "listar a bancada": "listar bancadas",
        "listar bancada": "listar bancadas",
    }
    s = txt.strip().lower()
    for k, v in m.items():
        s = s.replace(k, v)
    # se você já tem _replace_number_words/_norm, aplique aqui também se quiser:
    # s = _replace_number_words(s)
    return s

def titulo_painel(titulo: str, subtitulo: str = ""):
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
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True
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
    return msg  # opcional: retorna a string limpa, útil se quiser exibir no chat

# === CONFIGURAÇÕES ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
RUN_SCRIPT = os.path.join(BASE_DIR, "Run", "run_noia.py")
COLETOR_SCRIPT = os.path.join(BASE_DIR, "Scripts", "coletor_adb.py")
PROCESSAR_SCRIPT = os.path.join(BASE_DIR, "Pre_process", "processar_dataset.py")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PAUSE_FLAG_PATH = os.path.join(PROJECT_ROOT, "pause.flag")
STATUS_PATH = os.path.join(DATA_ROOT, "status_bancadas.json")

# === MODO CONVERSACIONAL ===
MODO_CONVERSA = True  # Altere para False se quiser desativar as respostas naturais


st.set_page_config(page_title="Agente de Testes", page_icon="🤖", layout="wide")


# === SESSION STATE ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "coletas_ativas" not in st.session_state:
    st.session_state.coletas_ativas = set()

# =========================
# === SUPORTE A BANCADAS ===
# =========================
def _parse_adb_devices(raw_lines):
    """
    Converte a saída do 'adb devices' em lista de seriais válidos.
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
        result = subprocess.check_output(["adb", "devices"], text=True).strip().splitlines()
        devices = _parse_adb_devices(result)
        return {str(i + 1): dev for i, dev in enumerate(devices)}
    except Exception:
        return {}

def _formatar_bancadas_str(bancadas: dict) -> str:
    if not bancadas:
        return "📡 Nenhuma bancada conectada."
    linhas = ["📡 **Bancadas disponíveis:**"]
    for k, v in bancadas.items():
        linhas.append(f"{k} → `{v}`")
    return "\n".join(linhas)

def _resolver_teste(nome_ou_token: str):
    """
    Localiza (categoria, teste) em Data/<categoria>/<teste> aceitando variações:
    'geral2' == 'geral_2' == 'geral-2' == 'geral 2' == 'geral um'.
    """
    if not nome_ou_token:
        return None, None

    alvo_norm = _normalize_token(nome_ou_token)

    cats = listar_categorias()

    # 1) Busca direta por equivalência normalizada em todas as categorias
    for cat in cats:
        for t in listar_testes(cat):
            if _normalize_token(t) == alvo_norm:
                return cat, t

    # 2) Caso o token venha no formato "categoria_nome" (com qualquer separador)
    parts = re.split(r"[_\-\s]+", _norm(nome_ou_token))
    if parts:
        cand_cat = parts[0]
        if cand_cat in cats:
            resto_norm = _normalize_token("".join(parts[1:]))  # só o nome do teste
            for t in listar_testes(cand_cat):
                if _normalize_token(t) in (alvo_norm, resto_norm):
                    return cand_cat, t

    # 3) Fallback: fuzzy match leve (>= 0,92) entre nomes normalizados
    candidatos = []
    for cat in cats:
        for t in listar_testes(cat):
            if SequenceMatcher(None, _normalize_token(t), alvo_norm).ratio() >= 0.92:
                candidatos.append((cat, t))
    if len(candidatos) == 1:
        return candidatos[0]

    return None, None

def _selecionar_bancada(bancada: str | None, bancadas: dict):
    """
    Seleciona o serial a partir da 'bancada' informada.
    Regras:
      - 'todas' => retorna lista com todos os seriais (paralelo)
      - número válido => retorna lista com um serial
      - None => pega a primeira disponível (se houver)
    Retorna (lista_de_seriais, mensagem_erro_ou_None)
    """
    if not bancadas:
        return [], "❌ Nenhuma bancada conectada."

    if bancada is None or str(bancada).strip() == "":
        # primeira disponível
        return [bancadas[sorted(bancadas.keys(), key=int)[0]]], None

    txt = str(bancada).strip().lower()
    if txt in ("todas", "todas as bancadas", "todas-bancadas", "all"):
        return list(bancadas.values()), None

    if txt.isdigit() and txt in bancadas:
        return [bancadas[txt]], None

    return [], f"❌ Bancada '{bancada}' não encontrada. Use **listar bancadas**."

def _popen_host_python(cmd):
    """Wrapper para subprocess.Popen no host (sem adb shell)."""
    try:
        subprocess.Popen(cmd, cwd=BASE_DIR)
        return True, None
    except Exception as e:
        return False, f"Falha ao executar comando: {e}"

def atualizar_status_bancada(serial, status, teste=None):
    """Atualiza o status atual de cada bancada (executando, ociosa, etc.) de forma isolada e thread-safe."""
    try:
        with status_lock:
            # usa um arquivo separado por bancada para evitar conflito
            status_file = os.path.join(DATA_ROOT, f"status_{serial}.json")

            data = {}
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            data.update({"status": status, "teste": teste, "atualizado_em": datetime.now().isoformat()})

            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"⚠️ Erro ao atualizar status da bancada {serial}: {e}")



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
    Usa LLM local (Ollama) para transformar frase livre em comando can?nico.
    Retorna None se o LLM estiver indispon?vel ou com baixa confian?a.
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
    Retorna None se indispon?vel.
    """
    prompt = f"""
Responda em pt-BR com no m?ximo 2 frases.
Se a pergunta for sobre uso, d? 1 exemplo de comando.
Usu?rio: "{frase}"
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


def executar_teste(categoria, nome_teste, bancada: str | None = None):
    """
    Executa teste no host em background, permitindo paralelismo entre bancadas.
    Cada processo é isolado e atualizado em status_bancadas.json.
    """
    caminho_teste = os.path.join(DATA_ROOT, categoria, nome_teste)
    dataset_path = os.path.join(caminho_teste, "dataset.csv")
    log_path = os.path.join(caminho_teste, "execucao_log.json")

    os.makedirs(caminho_teste, exist_ok=True)

    # 1️⃣ Garante que o dataset existe antes da execução
    if not os.path.exists(dataset_path):
        printc(f"⚙️ Dataset não encontrado para {categoria}/{nome_teste}, gerando automaticamente...", "yellow")
        processar_teste(categoria, nome_teste)

        # 🕒 Aguarda dataset ser realmente criado (timeout 60s)
        for _ in range(60):
            if os.path.exists(dataset_path):
                printc("✅ Dataset gerado com sucesso.", "green")
                break
            time.sleep(1)
        else:
            return f"❌ O dataset de {categoria}/{nome_teste} não foi gerado em tempo hábil."

    # 2️⃣ Mapeia bancadas ADB
    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro

    respostas = []

    for serial in seriais:
        # Evita executar 2 vezes na mesma bancada
        status_file = os.path.join(DATA_ROOT, f"status_{serial}.json")
        status_atual = {}
        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    status_atual = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ status_bancadas.json corrompido — recriando automaticamente.")
                status_atual = {}
            except Exception as e:
                print(f"⚠️ Erro ao ler status_bancadas.json: {e}")
                status_atual = {}
        else:
            print("ℹ️ status_bancadas.json não encontrado — criando novo.")
            status_atual = {}

        if str(status_atual.get("status", "")).lower() == "executando":
            respostas.append(f"⚠️ A bancada `{serial}` já está executando outro teste.")
            continue

        atualizar_status_bancada(serial, "executando", f"{categoria}/{nome_teste}")

        # Log inicial
        inicio = datetime.now().isoformat()
        log_entry = {
            "acao": "execucao_iniciada",
            "categoria": categoria,
            "teste": nome_teste,
            "serial": serial,
            "inicio": inicio
        }
        _registrar_log(log_path, log_entry)

        # 🚀 Executa em background isolado
        cmd = ["python", RUN_SCRIPT, categoria, nome_teste, "--serial", serial]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # =============================
            # 🧠 MONITOR DE EXECUÇÃO (THREAD)
            # =============================
            def _monitor_processo(p, serial, categoria, nome_teste):
                stdout, stderr = p.communicate()
                if p.returncode != 0:
                    atualizar_status_bancada(serial, "erro")
                    printc(f"❌ Erro na execução do teste {categoria}/{nome_teste} na bancada {serial}.", "red")
                    print(stdout.decode(errors="ignore"))
                    print(stderr.decode(errors="ignore"))

                    # Envia mensagem para o chat (modo conversa)
                    if MODO_CONVERSA and "chat_history" in st.session_state:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": f"❌ O teste **{categoria}/{nome_teste}** falhou na bancada `{serial}`."
                        })
                else:
                    atualizar_status_bancada(serial, "finalizado")
                    printc(f"✅ Teste {categoria}/{nome_teste} finalizado com sucesso na bancada {serial}.", "green")

                    # Envia mensagem para o chat (modo conversa)
                    if MODO_CONVERSA and "chat_history" in st.session_state:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": f"✅ Teste **{categoria}/{nome_teste}** finalizado com sucesso na bancada `{serial}`."
                        })

                    # Atualiza a interface automaticamente após finalização
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass

            # 🔹 Inicia o monitoramento do processo (thread em background)
            threading.Thread(
                target=_monitor_processo,
                args=(proc, serial, categoria, nome_teste),
                daemon=True
            ).start()

            # Mensagem inicial
            respostas.append(f"▶️ Executando **{categoria}/{nome_teste}** na bancada `{serial}` em background...")
            printc(f"🚀 Teste {categoria}/{nome_teste} iniciado em {serial} (PID={proc.pid})", "cyan")

        except Exception as e:
            respostas.append(f"❌ Falha ao iniciar execução na bancada `{serial}`: {e}")
            atualizar_status_bancada(serial, "erro")

    return "\n".join(respostas)


def _registrar_log(caminho_log, nova_entrada):
    """Adiciona entrada ao execucao_log.json, criando se não existir."""
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
        print(f"⚠️ Falha ao registrar log: {e}")


def gravar_teste(categoria, nome_teste, bancada: str | None = None):
    """
    Grava teste no host, encaminhando o serial como parâmetro para o coletor.
    Obs.: espera que Scripts/coletor_adb.py aceite '--serial <SERIAL>'.
    """
    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro

    respostas = []
    for serial in seriais:
        cmd = ["python", COLETOR_SCRIPT, categoria, nome_teste, "--serial", serial]
        ok, msg = _popen_host_python(cmd)
        if ok:
            respostas.append(f"🎥 Gravando **{categoria}/{nome_teste}** na bancada `{serial}`...")
        else:
            respostas.append(f"❌ {msg}")
    return "\n".join(respostas)


def finalizar_gravacao():
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
        return "Finalizando gravacao... toque na tela do radio para capturar o print final."
    except Exception as e:
        return f"Falha ao finalizar gravacao: {e}"
        return f"Falha ao finalizar gravacao: {e}"

def processar_teste(categoria, nome_teste):
    cmd = ["python", PROCESSAR_SCRIPT, categoria, nome_teste]
    ok, msg = _popen_host_python(cmd)
    if ok:
        return f"⚙️ Processando dataset de **{categoria}/{nome_teste}**..."
    return f"❌ {msg}"

def apagar_teste(categoria, nome_teste):
    caminho = os.path.join(DATA_ROOT, categoria, nome_teste)
    if os.path.exists(caminho):
        shutil.rmtree(caminho)
        return f"🗑️ Teste **{categoria}/{nome_teste}** apagado com sucesso."
    return f"❌ Teste {categoria}/{nome_teste} não encontrado."

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
    Cria o arquivo pause.flag para pausar a execução em andamento.
    """
    try:
        with open(PAUSE_FLAG_PATH, "w") as f:
            f.write("PAUSED")
        return "⏸️ Execução pausada. O runner será interrompido no próximo checkpoint."
    except Exception as e:
        return f"❌ Falha ao pausar execução: {e}"

def retomar_execucao():
    """
    Remove o arquivo pause.flag, permitindo continuar a execução.
    """
    try:
        if os.path.exists(PAUSE_FLAG_PATH):
            os.remove(PAUSE_FLAG_PATH)
            return "▶️ Execução retomada."
        else:
            return "⚠️ Nenhuma execução estava pausada."
    except Exception as e:
        return f"❌ Falha ao retomar execução: {e}"

def parar_execucao():
    """
    Cria o arquivo stop.flag para parar completamente o runner.
    """
    stop_path = os.path.join(PROJECT_ROOT, "stop.flag")
    try:
        with open(stop_path, "w") as f:
            f.write("STOP")
        return "🛑 Execução interrompida completamente."
    except Exception as e:
        return f"❌ Falha ao interromper execução: {e}"

# ======================================
# === FUNÇÕES AUXILIARES DO DASHBOARD ===
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
    acertos = sum(1 for a in execucao if "✅" in a.get("status", ""))
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
    st.subheader("📈 Métricas Gerais")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Ações", metricas["total_acoes"])
    col2.metric("Acertos", metricas["acertos"])
    col3.metric("Falhas", metricas["falhas"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Precisão (%)", metricas["precisao_percentual"])
    col5.metric("Flakes", metricas["flakes"])
    col6.metric("Cobertura de Telas (%)", metricas["cobertura_telas"])

    st.metric("⏱️ Tempo Total Execução (s)", metricas["tempo_total"])

    if metricas["resultado_final"] == "APROVADO":
        st.success("✅ APROVADO")
    else:
        st.error("❌ REPROVADO")

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
    st.subheader("⏳ Timeline da Execução")

    # Extrai e normaliza dados
    tempos = [float(a.get("duracao", 1)) for a in execucao]
    ids = []
    for idx, a in enumerate(execucao):
        # Garante que o ID seja numérico
        val = a.get("id", idx + 1)
        try:
            ids.append(int(val))
        except (ValueError, TypeError):
            ids.append(idx + 1)

    # Cores por status
    status = ["green" if "✅" in a.get("status", "") else "red" for a in execucao]

    # Cria o gráfico
    fig, ax = plt.subplots()
    ax.bar(ids, tempos, color=status)
    ax.set_xlabel("Ação")
    ax.set_ylabel("Duração (s)")
    ax.set_title("Tempo por Ação")

    # Deixa o eixo X limpo (sem notação científica)
    ax.xaxis.get_major_formatter().set_useOffset(False)

    st.pyplot(fig)

def exibir_acoes(execucao, base_dir):
    st.subheader("📋 Detalhes das Ações")
    for acao in execucao:
        titulo = f"Ação {acao.get('id')} - {str(acao.get('acao','')).upper()} | {acao.get('status','')}"
        with st.expander(titulo):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao.get("frame_esperado",""))
            resultado_path = os.path.join(base_dir, acao.get("screenshot",""))

            if frame_path and os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {acao.get('frame_esperado','')}", use_container_width=True)
            else:
                col1.warning("Frame esperado não encontrado")

            if resultado_path and os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Obtido: {acao.get('screenshot','')}", use_container_width=True)
            else:
                col2.warning("Screenshot não encontrado")

            if "similaridade" in acao:
                st.write(f"🎯 Similaridade: **{acao['similaridade']:.2f}**")
            st.write(f"⏱️ Duração: **{acao.get('duracao', 0)}s**")
            if "coordenadas" in acao:
                st.json(acao.get("coordenadas", {}))
            if "log" in acao:
                st.code(acao["log"], language="bash")

def exibir_mapa_calor(execucao):
    st.subheader("🔥 Mapa de Calor dos Toques")
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
    st.subheader("🖼️ Validação Final da Tela")
    resultado_final_path = os.path.join(base_dir, "resultado_final.png")

    col1, col2 = st.columns(2)
    if execucao:
        ultima = execucao[-1]
        frame_path = os.path.join(base_dir, ultima.get("frame_esperado",""))

        if frame_path and os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (Última Ação)", use_container_width=True)
        else:
            col1.error("Frame esperado não encontrado")

        if os.path.exists(resultado_final_path):
            col2.image(Image.open(resultado_final_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png não encontrado")

        if "similaridade" in ultima:
            st.write(f"🎯 Similaridade Final: **{ultima['similaridade']:.2f}**")
        if "✅" in ultima.get("status",""):
            st.success("✅ Tela final validada")
        else:
            st.error("❌ Tela final divergente")
    else:
        st.warning("Nenhuma ação registrada")

def exibir_regressoes(execucao):
    st.subheader("📉 Análise de Regressões")
    falhas = [a for a in execucao if "❌" in a.get("status","")]
    if falhas:
        st.write("Top falhas nesta execução:")
        for f in falhas:
            sim = f.get("similaridade")
            sim_str = f"{sim:.2f}" if isinstance(sim, (int, float)) else "N/A"
            st.write(f"- Ação {f.get('id')} ({f.get('acao','')}): Similaridade {sim_str}")
    else:
        st.success("Nenhuma falha registrada")

# ===========================
# === PARSER DE COMANDOS  ===
# ===========================
# Palavras-chave com variações comuns (sem acento e lower)
KW_EXECUTAR = [
    "executar", "execute", "rodar", "rode", "run", "iniciar teste",
    "inicia o teste", "começa o teste", "roda o teste", "faz o teste",
    "testa", "teste agora", "starta o teste", "começar teste", "faça o teste",
    "rodar tudo", "rodar todos", "rodar todos os testes", "executa tudo"
]

KW_GRAVAR = [
    "gravar", "grave", "coletar", "colete", "capturar", "record",
    "começar gravação", "iniciar gravação", "grava agora", "fazer gravação",
    "fazer coleta", "começar coleta", "startar gravação", "inicia a coleta",
    "começa a gravar", "grava o gesto", "grava o teste"
]

KW_PROCESS = [
    "processar", "processa", "pré-processar", "preprocessar", "pre", "gerar dataset",
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
    "me exibe", "quais são", "ver", "ver lista", "ver testes", "mostra pra mim",
    "quero ver", "ver categorias", "mostrar categorias", "mostrar testes"
]

KW_BANCADAS = [
    "bancada", "bancadas", "devices", "dispositivos", "adb", "hardware conectado",
    "listar bancadas", "mostrar bancadas", "listar dispositivos", "mostrar dispositivos",
    "quais bancadas", "tem bancada", "quais estão conectadas", "ver bancadas",
    "ver dispositivos", "me mostra as bancadas", "fala as bancadas", "lista as bancadas"
]

KW_AJUDA = [
    "ajuda", "help", "comandos", "o que posso dizer", "fala os comandos",
    "me ajuda", "quais comandos", "mostra os comandos", "explica comandos",
    "fala os exemplos", "ensina", "socorro"
]

_NUM_PT = {
    "zero":"0","um":"1","uma":"1","dois":"2","duas":"2","tres":"3","três":"3",
    "quatro":"4","cinco":"5","seis":"6","sete":"7","oito":"8","nove":"9","dez":"10",
    "onze":"11","doze":"12","treze":"13","catorze":"14","quatorze":"14","quinze":"15",
    "dezesseis":"16","dezessete":"17","dezoito":"18","dezenove":"19","vinte":"20"
}

def _replace_number_words(s: str) -> str:
    """Troca números por extenso (pt-BR) por dígitos no texto normalizado."""
    for k, v in _NUM_PT.items():
        s = re.sub(rf"\b{k}\b", v, s)
    return s

def _normalize_token(s: str) -> str:
    """Normaliza nomes de teste para comparação: lower, sem acentos e sem separadores."""
    s = _norm(s)
    s = re.sub(r"[\s_-]+", "", s)  # remove espaço, _ e -
    return s

def _norm(s: str) -> str:
    """Lower + remove acentos para matching robusto."""
    s = s.strip().lower()
    return normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")

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
    Extrai o nome do teste em diferentes formatos e devolve forma canônica 'base_numero':
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

    # 3) com espaço: 'geral 2'
    m = re.search(r"\b([a-z]+)\s+(\d+)\b", t)
    if m:
        return f"{m.group(1)}_{m.group(2)}"

    return None

def _extrair_categoria(texto: str) -> str | None:
    """
    Se o usuário pedir 'testes de <categoria>' ou mencionar explicitamente uma categoria existente.
    """
    t = _norm(texto)
    # padrão 'de <categoria>'
    m = re.search(r"\bde\s+([a-z0-9_-]+)\b", t)
    if m and m.group(1) in listar_categorias():
        return m.group(1)
    # ou se o nome da categoria aparecer diretamente no texto
    for cat in listar_categorias():  
        if _norm(cat) in t:
            return cat
    return None

def interpretar_comando(comando: str):
    texto = comando.strip()
    texto_norm = _norm(texto)

    # 1) AJUDA
    if _has_any(texto_norm, KW_AJUDA):
        return (
            "🧭 **Comandos suportados**\n"
            "- **executar/rodar** `<teste>` [na bancada N|todas]\n"
            "- **gravar/coletar** `<teste>` [na bancada N|todas]\n"
            "- **processar** `<teste>`\n"
            "- **apagar/deletar/remover** `<teste>`\n"
            "- **listar/mostrar** categorias | testes [de <categoria>]\n"
            "- **listar bancadas**\n"
            "Ex.: `execute o teste audio_1 na bancada 2`"
        )

    # 2) LISTAR BANCADAS
    if _has_any(texto_norm, ["listar bancadas", "mostrar bancadas", "listar devices", "mostrar devices"]) \
       or (_has_any(texto_norm, KW_LISTAR) and any(k in texto_norm for k in ["bancada", "bancadas", "devices", "dispositivos"])):  
        return _formatar_bancadas_str(listar_bancadas())

    # 3) EXECUTAR (rodar testes)
    if _has_any(texto_norm, KW_EXECUTAR):
        # Caso especial: "todos os testes da categoria X"
        if re.search(r"todos\s+os\s+testes\s+da\s+categoria", texto_norm):
            cat = _extrair_categoria(texto)
            if not cat:
                return "⚠️ Especifique a categoria (ex: rodar todos os testes da categoria audio)."

            testes = listar_testes(cat)
            if not testes:
                return f"📂 A categoria **{cat}** não possui testes."

            bancada = _extrair_bancada(texto)
            respostas = [f"▶️ Rodando todos os testes da categoria **{cat}** na bancada {bancada or '(padrão)'}..."]

            for t in testes:
                respostas.append(executar_teste(cat, t, bancada))

            return "\n".join(respostas)

        # ✅ Caso normal: executar um teste específico (ex: "executar teste geral_1" ou "executar geral 2")
        token = _extrair_token_teste(texto)
        if token:
            cat, nome = _resolver_teste(token)
            if cat and nome:
                bancada = _extrair_bancada(texto)
                return executar_teste(cat, nome, bancada)
            else:
                # tentativa extra: se o usuário disse apenas "geral 2" sem categoria explícita
                # busca qualquer teste com nome igual em todas as categorias
                for cat_try in listar_categorias():
                    if token in listar_testes(cat_try):
                        bancada = _extrair_bancada(texto)
                        return executar_teste(cat_try, token, bancada)
                return f"❌ Teste **{token}** não encontrado em `Data/*/`."
        return "⚠️ Especifique o teste a executar (ex: `executar teste geral_1 na bancada 1`)."

    # 4) GRAVAR / COLETAR
    if _has_any(texto_norm, KW_GRAVAR):
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
            else:
                return "⚠️ Use o formato categoria_nome (ex: audio_3)."

            bancada = _extrair_bancada(texto)
            return gravar_teste(cat, token, bancada)

        return "⚠️ Especifique o teste (ex: `gravar audio_1 na bancada 1`)."

    # 5) PROCESSAR (gera dataset)
    if _has_any(texto_norm, KW_PROCESS):
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
                return processar_teste(cat, token)
            return "⚠️ Use o formato categoria_nome (ex: audio_3)."
        return "⚠️ Especifique o teste (ex: `processar audio_1`)."

    # 6) APAGAR / DELETAR
    if _has_any(texto_norm, KW_APAGAR):
        token = _extrair_token_teste(texto)
        if token:
            cat, teste = _resolver_teste(token)
            if cat and teste:
                return apagar_teste(cat, teste)
            return f"❌ Não encontrei o teste **{token}** em `Data/*/`."
        return "⚠️ Especifique o teste (ex: `apagar audio_1`)."

    # 7) LISTAR / MOSTRAR
    if _has_any(texto_norm, KW_LISTAR):
        cat = _extrair_categoria(texto)
        if cat:
            testes = listar_testes(cat)
            if testes:
                return f"📝 Testes em **{cat}**:\n- " + "\n- ".join(testes)
            return f"📂 A categoria **{cat}** não possui testes."
        cats = listar_categorias()
        if cats:
            return "📂 Categorias disponíveis:\n- " + "\n- ".join(cats)
        return "📂 Nenhuma categoria encontrada em `Data/`."

    # ✅ RESETAR INTERFACE / REVERTER AÇÕES
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
                    return f"♻️ Reset comportamental iniciado para **{cat}/{nome}** na bancada `{bancada or 'padrão'}`."
                except Exception as e:
                    return f"❌ Erro ao iniciar reset: {e}"
            else:
                return f"❌ Teste **{token}** não encontrado."
        else:
            return "⚠️ Especifique o teste para resetar (ex: `reset geral_1 na bancada 1`)."

    # 8) CONTROLE DE EXECUÇÃO (pausar, retomar, parar)
    if any(_norm(p) in texto_norm for p in ["pausar", "pause", "parar teste", "interromper", "stop"]):
        return pausar_execucao()

    if any(_norm(p) in texto_norm for p in ["retomar", "continuar", "resume", "seguir"]):
        return retomar_execucao()

    if any(_norm(p) in texto_norm for p in ["cancelar", "encerrar", "finalizar", "stop all", "terminar"]):
        return parar_execucao()

    return "❌ Não entendi o comando. Digite **ajuda** para ver exemplos."

def responder_conversacional(comando: str):
    """
    Interpreta comandos em linguagem natural e responde de forma humana,
    mantendo integração com o interpretador técnico.
    """

    # Correções automáticas comuns de fala
    substituicoes_voz = {
        "star bancadas": "listar bancadas",
        "esta bancadas": "listar bancadas",
        "instalar bancadas": "listar bancadas",
        "história bancadas": "listar bancadas",
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

    # Expressões auxiliares para respostas naturais
    frases_iniciais = [
        "Entendido 💫",
        "Certo!",
        "Perfeito 😎",
        "Beleza ⚙️",
        "Ok, já vou cuidar disso 👇"
    ]

    frases_execucao = [
        "Iniciando o teste agora 🚀",
        "Rodando o caso de teste no rádio...",
        "Executando o cenário solicitado 💻",
        "Começando a sequência de validações..."
    ]

    frases_coleta = [
        "Iniciando gravação 🎥",
        "Pode tocar na tela — estou coletando os gestos.",
        "Gravando as interações agora 👇"
    ]

    frases_processamento = [
        "Gerando o dataset, aguarde um instante ⚙️",
        "Transformando os logs em dados úteis...",
        "Processando o dataset pra você 💾"
    ]

    frases_bancadas = [
        "Consultando bancadas ADB conectadas 📡",
        "Um segundo... vou listar as bancadas disponíveis 🔍",
        "Beleza, verificando conexões com as bancadas ⚙️"
    ]

    frases_ajuda = [
        "Aqui está o que posso fazer 👇",
        "Claro! Aqui estão alguns comandos que você pode usar 🧭",
        "Lista de comandos à disposição 👇"
    ]

    respostas_rapidas = {
        "oi": "Ol?! ?? Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "ola": "Ol?! ?? Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "ol?": "Ol?! ?? Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "eai": "Fala! ?? Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "e a?": "Fala! ?? Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "bom dia": "Bom dia! Posso ajudar com testes ou comandos.",
        "boa tarde": "Boa tarde! Posso ajudar com testes ou comandos.",
        "boa noite": "Boa noite! Posso ajudar com testes ou comandos.",
        "tudo bem": "Tudo sim! Posso ajudar com testes ou comandos.",
        "beleza": "Beleza! Posso ajudar com testes ou comandos.",
        "blz": "Blz! Posso ajudar com testes ou comandos."
    }

    saudacoes_rapidas = ["oi", "ola", "ol?", "eai", "e a?", "bom dia", "boa tarde", "boa noite", "tudo bem", "beleza", "blz"]
    comando_norm_limpo = re.sub(r"[^a-z0-9\s]", "", comando_norm).strip()
    for s in saudacoes_rapidas:
        if comando_norm_limpo == s or comando_norm_limpo.startswith(s + " "):
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": respostas_rapidas.get(s, "Ol?! ?? Posso ajudar com testes ou comandos.")
            })
            return ""

    # Permite frases como "Zuri, listar bancadas"
    if comando_norm.startswith("zuri"):
        comando_norm = comando_norm.replace("zuri", "", 1).strip()

    # === ROTEAMENTO ===
    if any(p in comando_norm for p in ["listar bancadas", "ver bancadas", "bancadas conectadas"]):
        resposta_pre = random.choice(frases_bancadas)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback("listar bancadas")

    # ♻️ RESETAR TESTE / REVERTER AÇÕES
    if any(p in comando_norm for p in ["reset", "resetar", "reverter", "restaurar", "desfazer", "voltar estado inicial"]):
        resposta_pre = f"{random.choice(frases_iniciais)} ♻️ Restaurando estado inicial do teste..."
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["executar", "rodar", "testar", "rodar o teste"]):
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_execucao)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["gravar", "coletar", "capturar"]):
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_coleta)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
        return resolver_comando_com_llm_ou_fallback(comando)

    if any(p in comando_norm for p in ["processar", "gerar dataset", "montar csv"]):
        resposta_pre = f"{random.choice(frases_iniciais)} {random.choice(frases_processamento)}"
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_pre})
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

# ==================
# === UI LATERAL  ===
# ==================
st.sidebar.title("☰ VWAIT - Menu")
pagina = st.sidebar.radio("Navegacao", ["Chat", "Dashboard", "Menu Tester"])

# Side info: bancadas
with st.sidebar.expander("📡 Bancadas (ADB)"):
    st.markdown(_formatar_bancadas_str(listar_bancadas()))
    if st.button("🔄 Atualizar lista de bancadas"):
        st.rerun()

# ============
# === CHAT ===
# ============
if pagina == "Chat":
    titulo_painel("VWAIT - Agente de Testes", "Digite <b>ajuda</b> para ver exemplos de comandos.")

    # === EXEMPLOS DE PROMPTS ESTILIZADOS ===
    st.markdown(
        """
        <div style="
            background-color: rgba(50, 50, 50, 0.6);
            border: 1px solid rgba(100, 100, 100, 0.5);
            border-radius: 10px;
            padding: 20px;
            margin-top: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
        ">
            <h3 style="color:#E0E0E0; margin-bottom:8px;">Exemplos de comandos</h3>
            <ul style="color:#CCCCCC; line-height:1.6; font-size:15px;">
                <li><code>gravar audio_1 na bancada 1</code> - inicia gravacao do teste de audio na bancada 1</li>
                <li><code>processar audio_1</code> - processa o dataset coletado</li>
                <li><code>executar audio_1 na bancada 1</code> - roda o teste gravado</li>
                <li><code>rodar todos os testes da categoria video</code> - executa todos os testes de uma categoria</li>
                <li><code>listar bancadas</code> - mostra bancadas ADB conectadas</li>
                <li><code>ajuda</code> - exibe a lista completa de comandos</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True
    )

    # === Exibi??o do hist?rico ===
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and "Gravando" in msg["content"]:
                if st.button("Finalizar gravacao", key=f"finalizar_{len(st.session_state.chat_history)}"):
                    msg_resp = finalizar_gravacao()
                    st.session_state.chat_history.append({"role": "assistant", "content": msg_resp})
                    st.rerun()

    processing_placeholder = st.empty()
    user_input = st.chat_input("Digite seu comando...")

    # Botao de voz no sidebar (parte de baixo)
    st.sidebar.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)
    mic_clicked = st.sidebar.button("Falar comando")

    if mic_clicked:
        recognizer = configurar_reconhecedor()

        try:
            mic = sr.Microphone()
        except Exception as e:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"Microfone indisponivel: {e}"
            })
            st.rerun()

        with mic as source:
            st.toast("Ouvindo... fale seu comando completo.")
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            audio = recognizer.listen(source, phrase_time_limit=12)

        try:
            st.toast("Reconhecendo fala...")
            command_text = recognizer.recognize_google(audio, language="pt-BR")
            command_text = normalizar_pos_fala(command_text)

            st.session_state.chat_history.append({"role": "user", "content": command_text})

            with st.spinner("Processando comando..."):
                if MODO_CONVERSA:
                    resposta = responder_conversacional(command_text)
                else:
                    resposta = resolver_comando_com_llm_ou_fallback(command_text)

            if resposta:
                st.session_state.chat_history.append({"role": "assistant", "content": resposta})
            st.rerun()

        except sr.UnknownValueError:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Nao consegui entender claramente. Pode repetir mais pausado?"
            })
            st.rerun()
        except sr.RequestError as e:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"Falha no servico de voz: {e}"
            })
            st.rerun()
        except sr.UnknownValueError:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Nao consegui entender o que voce disse."
            })
            st.rerun()
        except sr.RequestError:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Erro ao conectar ao servico de reconhecimento de voz."
            })
            st.rerun()

    # ENTRADA MANUAL
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.spinner("Processando comando..."):
            if MODO_CONVERSA:
                resposta = responder_conversacional(user_input)
            else:
                resposta = resolver_comando_com_llm_ou_fallback(user_input)

        if resposta:
            st.session_state.chat_history.append({"role": "assistant", "content": resposta})
        st.rerun()

elif pagina == "📊 Dashboard":
    st.title("📊 Dashboard de Execução de Testes - Rádio Android")

    logs = carregar_logs()
    if not logs:
        st.error("Nenhum execucao_log.json encontrado em Data/*/*/")
        st.stop()

    opcao = st.selectbox("Selecione a execução", [r[0] for r in logs])
    log_path = dict(logs)[opcao]

    with open(log_path, "r", encoding="utf-8") as f:
        execucao = json.load(f)

    base_dir = os.path.dirname(log_path)

    metricas = calcular_metricas(execucao)
    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_acoes(execucao, base_dir)
    exibir_mapa_calor(execucao)
    exibir_validacao_final(execucao, base_dir)
    exibir_regressoes(execucao)

    if st.button("📤 Exportar Relatório JSON"):
        st.download_button("Baixar JSON", data=json.dumps(execucao, indent=2), file_name="relatorio_execucao.json")
