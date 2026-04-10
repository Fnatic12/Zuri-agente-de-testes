import streamlit as st

import subprocess

import os
import platform
import socket

import sys

import shutil

import time
import re
import json
import urllib.request
import webbrowser
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from app.shared.project_paths import project_root, root_path
from app.shared.adb_utils import resolve_adb_path
from app.shared import ui_theme as _ui_theme

apply_dark_background = _ui_theme.apply_dark_background


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()


def apply_menu_tester_styles() -> None:
    st.markdown(
        """
        <style>
        .exec-row {
            margin-top: 0.35rem;
        }
        .exec-card {
            min-height: 100%;
            padding: 1.1rem 1.15rem 1.2rem 1.15rem;
            border-radius: 22px;
            border: 1px solid rgba(118, 162, 228, 0.14);
            background: linear-gradient(180deg, rgba(15, 23, 36, 0.92) 0%, rgba(9, 16, 27, 0.96) 100%);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.04),
                0 18px 34px rgba(0, 0, 0, 0.22);
        }
        .exec-card.secondary {
            background: linear-gradient(180deg, rgba(12, 20, 31, 0.94) 0%, rgba(8, 14, 23, 0.98) 100%);
        }
        .exec-card h4 {
            margin: 0 0 1rem 0;
            font-size: 1.08rem;
            font-weight: 700;
            color: #edf3ff;
            letter-spacing: -0.01em;
        }
        .status-box {
            min-height: 5.3rem;
            padding: 0.9rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(118, 162, 228, 0.12);
            background: linear-gradient(180deg, rgba(23, 31, 45, 0.76) 0%, rgba(13, 20, 31, 0.88) 100%);
            color: rgba(236, 242, 251, 0.94);
            line-height: 1.45;
        }
        div.stButton > button {
            min-height: 4.65rem !important;
            padding: 0.95rem 1.15rem !important;
            border-radius: 18px !important;
        }
        div.stButton > button p {
            font-size: 1rem !important;
            font-weight: 600 !important;
            line-height: 1.24 !important;
        }
        [data-testid="column"] div.stButton > button {
            width: 100% !important;
            max-width: none !important;
        }
        .tester-link-row {
            margin-top: 0.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# === Caminho do ADB ===
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


def _streamlit_launch_env() -> dict[str, str]:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
    env["BROWSER_GATHER_USAGE_STATS"] = "false"
    return env


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


def _garantir_painel_streamlit(script_path: str, port: int, timeout_s: float = 12.0) -> bool:
    if _porta_local_ativa(port):
        return True

    subprocess.Popen(
        [
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
        ],
        cwd=BASE_DIR,
        env=_streamlit_launch_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_subprocess_windowless_kwargs(),
    )
    return _aguardar_porta_local(port, timeout_s=timeout_s)


def _parse_adb_devices(raw_lines):

    seriais = []

    for ln in raw_lines[1:]:

        ln = ln.strip()

        if not ln:

            continue

        if ln.endswith("\tdevice"):

            seriais.append(ln.split("\t")[0])

    return seriais



def listar_bancadas():

    try:

        result = subprocess.check_output(
            [ADB_PATH, "devices"],
            text=True,
            **_subprocess_windowless_kwargs(),
        ).strip().splitlines()

        devices = _parse_adb_devices(result)

        return devices

    except Exception:

        return []



def _adb_cmd(serial=None):

    if serial:

        return [ADB_PATH, "-s", serial]

    return [ADB_PATH]



def salvar_resultado_parcial(categoria, nome_teste, serial=None):

    """Salva uma screenshot de resultado esperado sem parar a coleta."""

    base_dir = os.path.join(BASE_DIR, "Data", categoria, nome_teste)

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

            return True, img_name

        return False, "Falha ao salvar resultado esperado."

    except Exception as e:

        return False, f"Falha ao salvar resultado esperado: {e}"



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


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _clean_display_text(value: str) -> str:
    text = value if isinstance(value, str) else str(value)
    text = ANSI_ESCAPE_RE.sub("", text)
    for _ in range(2):
        try:
            if any(mark in text for mark in ("Ã", "Â", "â", "�")):
                text = text.encode("latin1", "ignore").decode("utf-8", "ignore")
        except Exception:
            break
    text = text.replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()



# === CONFIG ===

BASE_DIR = project_root()




SCRIPTS = {
    "Coletar Teste": root_path("Scripts", "coletor_adb.py"),
    "Processar Dataset": root_path("Pre_process", "processar_dataset.py"),
    "Executar Teste": root_path("Run", "run_noia.py"),
    "Abrir Dashboard": root_path("Dashboard", "visualizador_execucao.py"),
    "Abrir Painel de Logs": root_path("src", "vwait", "entrypoints", "streamlit", "painel_logs_radio.py"),
    "Abrir Controle de Falhas": root_path("src", "vwait", "entrypoints", "streamlit", "controle_falhas.py"),
}


STOP_FLAG_PATH = os.path.join(BASE_DIR, "stop.flag")



# Guarda referencia do processo da coleta

if "proc_coleta" not in st.session_state:

    st.session_state.proc_coleta = None

if "coleta_log_path" not in st.session_state:

    st.session_state.coleta_log_path = None

if "coleta_log_file" not in st.session_state:

    st.session_state.coleta_log_file = None

if "proc_execucao_unica" not in st.session_state:

    st.session_state.proc_execucao_unica = None

if "execucao_unica_status" not in st.session_state:

    st.session_state.execucao_unica_status = ""

if "execucao_log_path" not in st.session_state:

    st.session_state.execucao_log_path = None



if "execucao_log_path" not in st.session_state:

    st.session_state.execucao_log_path = None







if "execucao_unica_processos" not in st.session_state:

    st.session_state["execucao_unica_processos"] = []



def _execucao_log_path_por_serial(serial):

    serial_seguro = re.sub(r"[^0-9A-Za-z_.-]", "_", str(serial or "sem_serial"))

    return os.path.join(BASE_DIR, "Data", f"execucao_live_{serial_seguro}.log")


def _status_file_path(categoria, teste, serial):
    return os.path.join(BASE_DIR, "Data", str(categoria), str(teste), f"status_{serial}.json")


def _carregar_status_execucao(categoria, teste, serial):
    status_path = _status_file_path(categoria, teste, serial)
    if not os.path.exists(status_path):
        return {}
    try:
        with open(status_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    if isinstance(data, dict):
        nested = data.get(str(serial))
        if isinstance(nested, dict):
            return nested
        return data
    return {}


def _resolver_teste_por_serial(serial):
    latest = None
    latest_ts = None
    if not serial:
        return None, None
    for root, _, files in os.walk(os.path.join(BASE_DIR, "Data")):
        for name in files:
            if name != f"status_{serial}.json":
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            ts = data.get("atualizado_em") or data.get("inicio") or os.path.getmtime(path)
            if latest_ts is None or str(ts) > str(latest_ts):
                latest_ts = ts
                latest = data

    if not isinstance(latest, dict):
        return None, None
    teste_ref = str(latest.get("teste", "") or "").strip()
    if "/" not in teste_ref:
        return None, None
    categoria, nome_teste = teste_ref.split("/", 1)
    return categoria, nome_teste


def _capturar_logs_radio(categoria, nome_teste, serial, motivo="captura_manual_menu_tester"):
    from Run.run_noia import capturar_logs_teste

    return capturar_logs_teste(categoria, nome_teste, serial, motivo=motivo, limpar_antes=False)


def _abrir_pasta_local(path):
    path = os.path.abspath(str(path or "").strip())
    if not path or not os.path.exists(path):
        return False, "Pasta nao encontrada."
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True, path
    except Exception as exc:
        return False, str(exc)


def _resolver_pasta_logs_teste(categoria, nome_teste, serial=None):
    base_dir = os.path.join(BASE_DIR, "Data", str(categoria or "").strip(), str(nome_teste or "").strip())
    logs_root = os.path.join(base_dir, "logs")
    status_payload = _carregar_status_execucao(categoria, nome_teste, serial) if serial else {}
    relative_capture_dir = str((status_payload or {}).get("log_capture_dir", "") or "").strip()

    if relative_capture_dir:
        capture_dir = os.path.join(base_dir, relative_capture_dir)
        if os.path.isdir(capture_dir):
            return capture_dir

    if not os.path.isdir(logs_root):
        return None

    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def _formatar_resumo_execucao(payload, fallback_returncode=None):
    status = str(payload.get("status", "")).strip().lower()
    resultado_final = str(payload.get("resultado_final", "")).strip().lower()
    log_capture_status = str(payload.get("log_capture_status", "")).strip().lower()
    log_capture_dir = str(payload.get("log_capture_dir", "") or "").strip()

    if status == "executando":
        return "Executando"
    if status == "coletando_logs":
        return "Coletando logs da peca"
    if status == "erro":
        detalhe = str(payload.get("erro_motivo", "") or "").strip()
        return f"Erro tecnico ({detalhe})" if detalhe else "Erro tecnico"
    if resultado_final == "aprovado":
        return "Finalizado aprovado"
    if resultado_final == "reprovado":
        if log_capture_status == "capturado":
            return f"Finalizado reprovado | logs capturados em {log_capture_dir}"
        if log_capture_status == "executando":
            return "Finalizado reprovado | capturando logs"
        if log_capture_status == "sem_artefatos":
            return "Finalizado reprovado | nenhum log novo encontrado"
        if log_capture_status == "sem_roteiro":
            return "Finalizado reprovado | sem roteiro de logs"
        if log_capture_status == "falha":
            return "Finalizado reprovado | falha ao capturar logs"
        return "Finalizado reprovado"
    if fallback_returncode is not None:
        return "Finalizado com sucesso" if fallback_returncode == 0 else f"Erro ({fallback_returncode})"
    return "Sem status"



def _tem_execucao_unica_ativa():

    for item in st.session_state.get("execucao_unica_processos", []):

        proc = item.get("proc")

        if proc is not None and proc.poll() is None:

            return True

    return False



def _garantir_dataset_execucao(categoria_exec, nome_teste_exec):

    teste_path = os.path.join(BASE_DIR, "Data", categoria_exec, nome_teste_exec)

    dataset_path = os.path.join(teste_path, "dataset.csv")

    if os.path.exists(dataset_path):

        return True, ""

    st.warning("Dataset nao encontrado. Gerando automaticamente...")

    proc_dataset = subprocess.run(

        [sys.executable, SCRIPTS["Processar Dataset"], categoria_exec, nome_teste_exec],

        cwd=BASE_DIR

    )

    if proc_dataset.returncode == 0:

        st.success("Dataset processado com sucesso.")

        return True, ""

    return False, "Falha ao processar dataset."



def _iniciar_execucoes_configuradas(execucoes):

    if not execucoes:

        return False, "Nenhuma execucao informada.", []

    if _tem_execucao_unica_ativa():

        return False, "Ja existe teste em execucao. Aguarde finalizar antes de iniciar outro.", []

    execucoes_validas = []

    seriais_usados = set()

    for idx, execucao in enumerate(execucoes, start=1):

        categoria_exec = str(execucao.get("categoria", "")).strip()

        nome_teste_exec = str(execucao.get("teste", "")).strip()

        serial = str(execucao.get("serial", "")).strip()

        label = str(execucao.get("label", f"Bancada {idx}")).strip() or f"Bancada {idx}"

        if not categoria_exec or not nome_teste_exec:

            return False, f"Informe categoria e nome do teste para {label}.", []

        if not serial:

            return False, f"Nenhum dispositivo ADB definido para {label}.", []

        if serial in seriais_usados:

            return False, "Selecione bancadas diferentes para executar em paralelo.", []

        seriais_usados.add(serial)

        ok_dataset, msg_dataset = _garantir_dataset_execucao(categoria_exec, nome_teste_exec)

        if not ok_dataset:

            return False, f"{label}: {msg_dataset}", []

        execucoes_validas.append(

            {

                "categoria": categoria_exec,

                "teste": nome_teste_exec,

                "serial": serial,

                "label": label,

            }

        )

    processos_iniciados = []

    try:

        for execucao in execucoes_validas:

            categoria_exec = execucao["categoria"]

            nome_teste_exec = execucao["teste"]

            serial = execucao["serial"]

            label = execucao["label"]

            log_path = _execucao_log_path_por_serial(serial)

            log_file = open(log_path, "w", encoding="utf-8", errors="ignore", buffering=1)

            proc_exec = subprocess.Popen(

                [sys.executable, SCRIPTS["Executar Teste"], categoria_exec, nome_teste_exec, "--serial", serial],

                cwd=BASE_DIR,

                stdout=log_file,

                stderr=subprocess.STDOUT,

                text=True

            )

            processos_iniciados.append(

                {

                    "proc": proc_exec,

                    "serial": serial,

                    "categoria": categoria_exec,

                    "teste": nome_teste_exec,

                    "label": label,

                    "status_text": f"{label}: executando {categoria_exec}/{nome_teste_exec} na bancada {serial}...",

                    "log_path": log_path,

                    "log_file": log_file,

                    "log_closed": False,

                }

            )

    except Exception as e:

        for item in processos_iniciados:

            try:

                if item["proc"].poll() is None:

                    item["proc"].terminate()

            except Exception:

                pass

            try:

                item["log_file"].close()

            except Exception:

                pass

        return False, f"Falha ao iniciar execucao: {e}", []

    st.session_state["execucao_unica_processos"] = processos_iniciados

    st.session_state["proc_execucao_unica"] = processos_iniciados[0]["proc"] if len(processos_iniciados) == 1 else None

    st.session_state["execucao_unica_status"] = " | ".join(item["status_text"] for item in processos_iniciados)

    st.session_state["execucao_log_path"] = processos_iniciados[0]["log_path"]

    st.session_state["teste_em_execucao"] = True

    st.session_state["teste_pausado"] = False

    return True, "", processos_iniciados



def _iniciar_execucoes_teste_unico(categoria_exec, nome_teste_exec, seriais):

    seriais_validos = [str(serial).strip() for serial in seriais if str(serial).strip()]

    return _iniciar_execucoes_configuradas(

        [

            {

                "categoria": categoria_exec,

                "teste": nome_teste_exec,

                "serial": serial,

                "label": "Bancada selecionada" if len(seriais_validos) == 1 else f"Bancada {idx}",

            }

            for idx, serial in enumerate(seriais_validos, start=1)

        ]

    )



st.set_page_config(page_title="Menu Tester", page_icon="", layout="centered")
apply_dark_background(hide_header=True)
apply_panel_button_theme()
apply_menu_tester_styles()
titulo_painel("Painel de Automação de Testes", "Plataforma <b>para</b> Coletar e Processar Testes")
st.divider() 



# === COLETA ===

st.subheader("Coletar Gestos")

categoria = st.text_input("Categoria do Teste (ex: audio, video, bluetooth)", key="cat_coleta")

nome_teste = st.text_input("Nome do Teste (ex: audio_1, bt_pareamento)", key="nome_coleta")

bancadas = listar_bancadas()

serial_sel = None

if bancadas:

    serial_sel = st.selectbox("Bancada/Dispositivo ADB", options=bancadas, index=0)

else:

    st.info("Nenhum dispositivo ADB encontrado. Conecte o radio e clique em iniciar.")



col1, col2, col3, col4, col5 = st.columns(5)


with col1:
    if st.button("Iniciar Coleta", use_container_width=True):
        if categoria and nome_teste:

            if st.session_state.proc_coleta is None:

                # 1) Remove stop.flag antigo

                pause_path = os.path.join(BASE_DIR, "pause.flag")

                if os.path.exists(pause_path):

                    try:

                        os.remove(pause_path)

                    except Exception:

                        pass

                if os.path.exists(STOP_FLAG_PATH):

                    try:

                        os.remove(STOP_FLAG_PATH)

                    except Exception:

                        pass



                # Inicia coleta

                log_path = os.path.join(BASE_DIR, "Data", "coleta_live.log")

                st.session_state.coleta_log_path = log_path

                log_file = open(log_path, "w", encoding="utf-8", errors="ignore", buffering=1)

                st.session_state.coleta_log_file = log_file

                env = os.environ.copy()

                env["PYTHONUNBUFFERED"] = "1"

                cmd = [sys.executable, "-u", SCRIPTS["Coletar Gestos"], categoria, nome_teste]

                if serial_sel:

                    cmd += ["--serial", serial_sel]

                st.session_state.proc_coleta = subprocess.Popen(

                    cmd,

                    cwd=BASE_DIR,

                    stdout=log_file,

                    stderr=subprocess.STDOUT,

                    text=True,

                    env=env

                )

                st.success(f"Coleta iniciada para {categoria}/{nome_teste}")

            else:

                st.warning("Já existe uma coleta em andamento.")

        else:

            st.error("Preencha categoria e nome do teste antes de iniciar.")



with col2:
    if st.button("Finalizar Coleta", use_container_width=True):
        proc = st.session_state.proc_coleta

        if proc:

            try:

                with open(STOP_FLAG_PATH, "w") as f:

                    f.write("stop")

                st.warning("Toque na tela do rádio para capturar o print final...")

                # aguarda término e criação do acoes.json (pode levar um pouco)

                acoes_path = os.path.join(BASE_DIR, "Data", categoria, nome_teste, "json", "acoes.json")

                timeout_s = 60

                t0 = time.time()

                while time.time() - t0 < timeout_s:

                    if os.path.exists(acoes_path):

                        break

                    if proc.poll() is not None:

                        break

                    time.sleep(1)

                if os.path.exists(acoes_path):

                    st.success("Coleta finalizada com sucesso. Print final e ações salvos.")

                else:

                    proc.wait(timeout=10)

                    if os.path.exists(acoes_path):

                        st.success("Coleta finalizada com sucesso. Print final e ações salvos.")

                    else:

                        st.warning("Coleta finalizada, mas o acoes.json não apareceu. Verifique o log.")

            except subprocess.TimeoutExpired:

                proc.kill()

                st.warning("Coletor não respondeu, finalizado à força.")

            finally:

                if os.path.exists(STOP_FLAG_PATH):

                    os.remove(STOP_FLAG_PATH)

                if st.session_state.coleta_log_file:

                    try:

                        st.session_state.coleta_log_file.close()

                    except Exception:

                        pass

                    st.session_state.coleta_log_file = None

                st.session_state.proc_coleta = None

        else:

            st.info("Nenhuma coleta em andamento.")



# === RESULTADO ESPERADO (sem parar coleta) ===
with col3:
    if st.button("Salvar Resultado Esperado", use_container_width=True):
        if categoria and nome_teste:

            ok, msg = salvar_resultado_parcial(categoria, nome_teste, serial_sel)

            if ok:

                st.success(f"Resultado esperado salvo: {msg}")

            else:

                st.error(msg)

        else:

            st.error("Informe categoria e nome do teste antes de salvar o esperado.")


with col4:
    if st.button("Capturar Log do Radio", use_container_width=True):
        if not serial_sel:
            st.error("Selecione uma bancada conectada para capturar logs.")
        else:
            categoria_logs = (categoria or "").strip()
            nome_teste_logs = (nome_teste or "").strip()
            if not categoria_logs or not nome_teste_logs:
                categoria_logs, nome_teste_logs = _resolver_teste_por_serial(serial_sel)

            if not categoria_logs or not nome_teste_logs:
                st.error("Nao consegui resolver o teste desta bancada. Informe categoria/nome do teste ou rode um teste antes.")
            else:
                with st.spinner("Capturando logs do radio..."):
                    resultado = _capturar_logs_radio(categoria_logs, nome_teste_logs, serial_sel)
                status_captura = str(resultado.get("status", "") or "")
                pasta_logs = resultado.get("artifact_dir")
                erro_logs = resultado.get("error")
                if status_captura == "capturado":
                    st.success(f"Logs capturados em Data/{categoria_logs}/{nome_teste_logs}/{pasta_logs}")
                elif status_captura == "sem_artefatos":
                    st.warning(f"Nenhum log novo encontrado. Pasta gerada em Data/{categoria_logs}/{nome_teste_logs}/{pasta_logs}")
                else:
                    st.error(f"Falha ao capturar logs: {erro_logs or 'erro desconhecido'}")


with col5:
    if st.button("Abrir Pasta de Logs", use_container_width=True):
        if not serial_sel:
            st.error("Selecione uma bancada conectada para abrir os logs.")
        else:
            categoria_logs = (categoria or "").strip()
            nome_teste_logs = (nome_teste or "").strip()
            if not categoria_logs or not nome_teste_logs:
                categoria_logs, nome_teste_logs = _resolver_teste_por_serial(serial_sel)

            if not categoria_logs or not nome_teste_logs:
                st.error("Nao consegui resolver o teste desta bancada. Informe categoria/nome do teste ou rode um teste antes.")
            else:
                pasta_logs = _resolver_pasta_logs_teste(categoria_logs, nome_teste_logs, serial_sel)
                if not pasta_logs:
                    st.error("Nenhuma pasta de logs encontrada para este teste.")
                else:
                    ok_open, detalhe_open = _abrir_pasta_local(pasta_logs)
                    if ok_open:
                        st.success(f"Pasta de logs aberta: {pasta_logs}")
                    else:
                        st.error(f"Falha ao abrir a pasta de logs: {detalhe_open}")



# === LOGS DA COLETA (ao vivo) ===

log_path = st.session_state.coleta_log_path

proc = st.session_state.proc_coleta

if log_path and os.path.exists(log_path):

    st.markdown("**Logs da coleta (ao vivo)**" if proc is not None else "**Logs da ultima coleta**")

    if proc is not None and proc.poll() is None:

        st_autorefresh(interval=1000, limit=None, key="coleta_refresh")

    try:

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:

            lines = f.readlines()

        logs_txt = _clean_display_text("".join(lines[-200:]))

    except Exception:

        logs_txt = ""

    st.text_area("Toques e eventos", value=logs_txt, height=220)

    if proc is not None and proc.poll() is not None:

        st.warning(f"Coleta finalizada com codigo {proc.returncode}. Veja o log acima.")

        st.session_state.proc_coleta = None



# === DELETAR TESTE ===

st.divider()

st.subheader("Deletar Teste")

cat_del = st.text_input("Categoria do Teste a deletar", key="cat_del")

nome_del = st.text_input("Nome do Teste a deletar", key="nome_del")



if st.button("Deletar Teste", use_container_width=True):

    if cat_del and nome_del:

        teste_path = os.path.join(BASE_DIR, "Data", cat_del, nome_del)

        if os.path.exists(teste_path):

            try:

                shutil.rmtree(teste_path)

                st.success(f"Teste {cat_del}/{nome_del} deletado com sucesso.")

            except Exception as e:

                st.error(f"rro ao deletar: {e}")

        else:

            st.warning(f"Teste {cat_del}/{nome_del} não encontrado.")

    else:

        st.error("Informe categoria e nome do teste para deletar.")



# === PROCESSAR DATASET (manual) ===

st.divider()

st.subheader("Processar Dataset (opcional)")

categoria_ds = st.text_input("Categoria do Dataset", key="cat_dataset")

nome_teste_ds = st.text_input("Nome do Teste", key="nome_dataset")



if st.button("Processar Dataset", use_container_width=True):

    if categoria_ds and nome_teste_ds:

        with st.spinner(f"Processando dataset de {categoria_ds}/{nome_teste_ds}..."):

            proc_dataset = subprocess.run(

                [sys.executable, SCRIPTS["Processar Dataset"], categoria_ds, nome_teste_ds],

                cwd=BASE_DIR,

                capture_output=True,

                text=True

            )

        saida_dataset = _clean_display_text(

            "\n".join(

                parte for parte in [proc_dataset.stdout, proc_dataset.stderr] if parte and parte.strip()

            )

        )

        if proc_dataset.returncode == 0:

            st.success(f"Dataset de {categoria_ds}/{nome_teste_ds} processado com sucesso.")

            if saida_dataset:

                st.caption(saida_dataset)

        else:

            st.error(f"Falha ao processar dataset de {categoria_ds}/{nome_teste_ds}.")

            if saida_dataset:

                st.text_area("Detalhes do processamento", value=saida_dataset, height=180, disabled=True)

    else:

        st.error("Informe categoria e nome do teste.")



# === EXECUTAR TESTE ===

st.divider()

st.subheader("Executar Testes")



categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")

nome_teste_exec = st.text_input("Nome do Teste (deixe vazio para rodar todos)", key="nome_exec")


st.markdown("**Execucao paralela por bancada**")

execucoes_paralelas_config = []

if bancadas:

    colunas_paralelas = st.columns(2)

    for idx, serial_bancada in enumerate(bancadas, start=1):

        with colunas_paralelas[(idx - 1) % 2]:

            st.caption(f"Bancada {idx}")

            st.caption(f"Serial: {serial_bancada}")

            categoria_exec_b = st.text_input(f"Categoria Bancada {idx}", key=f"cat_exec_b{idx}")

            nome_teste_exec_b = st.text_input(f"Teste Bancada {idx}", key=f"nome_exec_b{idx}")

            if categoria_exec_b.strip() and nome_teste_exec_b.strip():

                execucoes_paralelas_config.append(

                    {

                        "categoria": categoria_exec_b.strip(),

                        "teste": nome_teste_exec_b.strip(),

                        "serial": serial_bancada,

                        "label": f"Bancada {idx}",

                    }

                )

else:

    st.info("Nenhuma bancada conectada para execucao paralela.")



st.markdown("<div class='exec-row'>", unsafe_allow_html=True)

col_a, col_b, col_c = st.columns([2, 2, 2])



with col_a:

    st.markdown("<div class='exec-card'>", unsafe_allow_html=True)

    st.markdown("<h4>Executar teste unico</h4>", unsafe_allow_html=True)

    btn_unico_col, btn_duplo_col = st.columns(2)

    with btn_unico_col:

        executar_teste_unico = st.button("Executar Teste Unico", use_container_width=True)

    with btn_duplo_col:

        executar_duplo = st.button("Rodar Testes em Paralelo", key="executar_teste_duplo", use_container_width=True)

    if executar_teste_unico:

        serial_exec = serial_sel or (bancadas[0] if bancadas else None)

        ok_exec, msg_exec, processos = _iniciar_execucoes_teste_unico(

            categoria_exec,

            nome_teste_exec,

            [serial_exec] if serial_exec else []

        )

        if ok_exec and processos:

            serial = processos[0]["serial"]

            st.success(f"Execucao iniciada para {categoria_exec}/{nome_teste_exec} (Bancada {serial})")

        else:

            st.error(msg_exec)

    if executar_duplo:

        if len(bancadas) < 2:

            st.error("Conecte pelo menos duas bancadas ADB para rodar em paralelo.")

        elif len(execucoes_paralelas_config) < 2:

            st.error("Preencha pelo menos duas bancadas com categoria e teste para executar em paralelo.")

        else:

            ok_exec, msg_exec, processos = _iniciar_execucoes_configuradas(

                execucoes_paralelas_config

            )

            if ok_exec:

                st.success("Execucoes iniciadas ao mesmo tempo nas bancadas configuradas.")

                for processo in processos:

                    st.caption(

                        f"{processo['label']}: {processo['categoria']}/{processo['teste']} em {processo['serial']}"

                    )

            else:

                st.error(msg_exec)

    st.markdown("</div>", unsafe_allow_html=True)



with col_b:

    st.markdown("<div class='exec-card secondary'>", unsafe_allow_html=True)

    st.markdown("<h4>Status</h4>", unsafe_allow_html=True)

    execucao_processos = st.session_state.get("execucao_unica_processos", [])

    status_msgs = []

    existe_execucao_ativa = False

    for item in execucao_processos:

        proc_exec = item.get("proc")

        if proc_exec is None:

            continue

        if proc_exec.poll() is None:

            payload = _carregar_status_execucao(item.get("categoria"), item.get("teste"), item.get("serial"))
            resumo = _formatar_resumo_execucao(payload)
            existe_execucao_ativa = True
            status_msgs.append(
                f"{item.get('label', 'Bancada')} ({item.get('serial', '-')}): {resumo.lower()}."
            )

            continue

        if not item.get("log_closed") and item.get("log_file") is not None:

            try:

                item["log_file"].close()

            except Exception:

                pass

            item["log_closed"] = True

        payload = _carregar_status_execucao(item.get("categoria"), item.get("teste"), item.get("serial"))
        resumo = _formatar_resumo_execucao(payload, fallback_returncode=proc_exec.returncode)
        status_msgs.append(
            f"{item.get('label', 'Bancada')} ({item.get('serial', '-')}): {resumo.lower()}."
        )

    if existe_execucao_ativa:

        st_autorefresh(interval=1500, limit=None, key="execucao_unica_refresh")

    st.session_state["teste_em_execucao"] = existe_execucao_ativa

    if not existe_execucao_ativa:

        st.session_state["proc_execucao_unica"] = None

        st.session_state["execucao_unica_status"] = ""

    status_msg = "<br>".join(status_msgs) if status_msgs else "Nenhum teste em execucao."

    st.markdown(f"<div class='status-box'>{status_msg}</div>", unsafe_allow_html=True)



    if "teste_em_execucao" in st.session_state and st.session_state["teste_em_execucao"]:

        if not st.session_state.get("teste_pausado", False):

            st.markdown("<div class='pause-btn'>", unsafe_allow_html=True)

            if st.button("Pausar Teste", key="pause_teste", use_container_width=True):

                with open(os.path.join(BASE_DIR, "pause.flag"), "w") as f:

                    f.write("pause")

                st.session_state["teste_pausado"] = True

                st.warning("Execucao pausada.")

            st.markdown("</div>", unsafe_allow_html=True)

        else:

            st.markdown("<div class='resume-btn'>", unsafe_allow_html=True)

            if st.button("Retomar Teste", key="resume_teste", use_container_width=True):

                pause_path = os.path.join(BASE_DIR, "pause.flag")

                if os.path.exists(pause_path):

                    os.remove(pause_path)

                st.session_state["teste_pausado"] = False

                st.success("Execucao retomada com sucesso.")

            st.markdown("</div>", unsafe_allow_html=True)

    else:

        st.caption("Sem teste em execucao.")



    st.markdown("</div>", unsafe_allow_html=True)



with col_c:



    st.markdown("<div class='exec-card secondary'>", unsafe_allow_html=True)

    st.markdown("<h4>Executar todos</h4>", unsafe_allow_html=True)
    btn_all_col, _btn_all_spacer = st.columns(2)

    with btn_all_col:
        executar_todos_categoria = st.button("Executar Todos da Categoria", use_container_width=True)

    if executar_todos_categoria:

        if categoria_exec:

            categoria_path = os.path.join(BASE_DIR, "Data", categoria_exec)

            if not os.path.isdir(categoria_path):

                st.error(f"Categoria {categoria_exec} nao encontrada em Data/")

            else:

                testes = [t for t in os.listdir(categoria_path) if os.path.isdir(os.path.join(categoria_path, t))]

                if not testes:

                    st.warning(f"Nenhum teste encontrado em Data/{categoria_exec}/")

                else:

                    st.success(f"Executando {len(testes)} testes da categoria {categoria_exec}...")

                    for t in testes:

                        dataset_path = os.path.join(categoria_path, t, "dataset.csv")

                        if not os.path.exists(dataset_path):

                            subprocess.run(

                                ["python", SCRIPTS["Processar Dataset"], categoria_exec, t],

                                cwd=BASE_DIR

                            )

                        log_path = os.path.join(BASE_DIR, "Data", "execucao_live.log")

                        st.session_state["execucao_log_path"] = log_path

                        log_file = open(log_path, "a", encoding="utf-8", errors="ignore", buffering=1)

                        subprocess.Popen(

                            ["python", SCRIPTS["Executar Teste"], categoria_exec, t],

                            cwd=BASE_DIR,

                            stdout=log_file,

                            stderr=subprocess.STDOUT,

                            text=True

                        )

        else:

            st.error("Informe a categoria para rodar todos os testes.")

    st.markdown("</div>", unsafe_allow_html=True)



st.markdown("</div>", unsafe_allow_html=True)



# === RELATÓRIOS DE FALHAS ===

st.divider()

execucao_processos = st.session_state.get("execucao_unica_processos", [])

if False and execucao_processos:

    st.subheader("Logs de Execucao")

    abas_logs = st.tabs(

        [

            f"{item.get('label', 'Bancada')} | {item.get('categoria', '-')}/{item.get('teste', '-')}"

            for item in execucao_processos

        ]

    )

    for aba_log, item in zip(abas_logs, execucao_processos):

        with aba_log:

            proc_exec = item.get("proc")

            payload = _carregar_status_execucao(item.get("categoria"), item.get("teste"), item.get("serial"))

            if proc_exec is not None and proc_exec.poll() is None:

                situacao = _formatar_resumo_execucao(payload)

            elif proc_exec is not None:

                situacao = _formatar_resumo_execucao(payload, fallback_returncode=proc_exec.returncode)

            else:

                situacao = "Sem processo"

            info_col_1, info_col_2, info_col_3 = st.columns([1.3, 2.2, 2.5])

            with info_col_1:

                st.caption("Status")

                st.write(situacao)

            with info_col_2:

                st.caption("Bancada / Serial")

                st.write(f"{item.get('label', 'Bancada')} - {item.get('serial', '-')}")

            with info_col_3:

                st.caption("Teste")

                st.write(f"{item.get('categoria', '-')}/{item.get('teste', '-')}")

            log_path = item.get("log_path")

            logs_txt = ""

            if log_path and os.path.exists(log_path):

                try:

                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:

                        lines = f.readlines()

                    logs_txt = _clean_display_text("".join(lines[-200:]))

                except Exception:

                    logs_txt = ""

            if not logs_txt:

                logs_txt = "Aguardando linhas de log..."

            st.text_area(

                "Saida da execucao",

                value=logs_txt,

                height=320,

                disabled=True,

                key=f"log_execucao_{item.get('serial', 'sem_serial')}_{item.get('categoria', '-')}_{item.get('teste', '-')}"

            )



st.subheader("Gerar Relatórios de Falhas")



if st.button("Gerar Relatórios de Falhas (execução_log.json)", use_container_width=True):

    gerar_falha_path = root_path("src", "vwait", "entrypoints", "cli", "generate_failure_reports.py")
    if not os.path.exists(gerar_falha_path):

        st.error("Arquivo generate_failure_reports.py não encontrado.")

    else:

        with st.spinner("Analisando execucao_log.json e gerando relatórios..."):

            try:

                result = subprocess.run(

                    [sys.executable, gerar_falha_path],
                    cwd=BASE_DIR,

                    capture_output=True,

                    text=True

                )

                st.text_area("Saída do Script", result.stdout, height=250)



                rel_dir = root_path("workspace", "reports", "failures")
                if os.path.isdir(rel_dir):
                    relatorios = sorted(
                        [
                            os.path.relpath(os.path.join(root, name), rel_dir)
                            for root, _, files in os.walk(rel_dir)
                            for name in files
                            if name.endswith((".json", ".md", ".csv"))
                        ],
                        reverse=True
                    )
                    if relatorios:

                        st.success(f"? {len(relatorios)} relatórios gerados!")

                        for r in relatorios[:10]:

                            st.markdown(f"- ?? **{r}**  `{os.path.join(rel_dir, r)}`")

                    else:

                        st.info("Nenhum relatório encontrado.")

                else:

                    st.warning("A pasta workspace/reports/failures ainda não existe.")
            except Exception as e:

                st.error(f"Erro ao executar generate_failure_reports.py: {e}")



# === DASHBOARD ===

st.divider()

st.markdown("<div class='tester-link-row'>", unsafe_allow_html=True)
link_col_1, link_col_2, link_col_3 = st.columns(3)

with link_col_1:
    if st.button("Abrir Dashboard", use_container_width=True):

        try:

            port = int(os.environ.get("VWAIT_DASHBOARD_PORT", "8504"))
            pronto = _garantir_painel_streamlit(SCRIPTS["Abrir Dashboard"], port)

            webbrowser.open_new_tab(f"http://localhost:{port}")
            if pronto:
                st.success(f"Dashboard pronto em http://localhost:{port}")
            else:
                st.warning(f"Dashboard ainda inicializando em http://localhost:{port}")

        except Exception as e:

            st.error(f"Falha ao abrir dashboard: {e}")

with link_col_2:
    if st.button("Abrir Painel de Logs", use_container_width=True):

        try:

            port = int(os.environ.get("VWAIT_LOGS_PANEL_PORT", "8505"))
            pronto = _garantir_painel_streamlit(SCRIPTS["Abrir Painel de Logs"], port)

            webbrowser.open_new_tab(f"http://localhost:{port}")
            if pronto:
                st.success(f"Painel de logs pronto em http://localhost:{port}")
            else:
                st.warning(f"Painel de logs ainda inicializando em http://localhost:{port}")

        except Exception as e:

            st.error(f"Falha ao abrir painel de logs: {e}")

with link_col_3:
    if st.button("Abrir Controle de Falhas", use_container_width=True):

        try:

            port = int(os.environ.get("VWAIT_FAILURE_CONTROL_PORT", "8506"))
            pronto = _garantir_painel_streamlit(SCRIPTS["Abrir Controle de Falhas"], port)

            webbrowser.open_new_tab(f"http://localhost:{port}")
            if pronto:
                st.success(f"Controle de falhas pronto em http://localhost:{port}")
            else:
                st.warning(f"Controle de falhas ainda inicializando em http://localhost:{port}")

        except Exception as e:

            st.error(f"Falha ao abrir controle de falhas: {e}")

st.markdown("</div>", unsafe_allow_html=True)
