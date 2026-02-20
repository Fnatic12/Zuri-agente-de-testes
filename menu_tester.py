import streamlit as st
import subprocess
import os
import platform
import sys
import shutil
from streamlit_autorefresh import st_autorefresh

# === Caminho do ADB ===
if platform.system() == "Windows":
    ADB_PATH = r"C:\Users\Automation01\platform-tools\adb.exe"
else:
    ADB_PATH = "adb"

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

# === CONFIG ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


SCRIPTS = {
    "Coletar Gestos": os.path.join(BASE_DIR, "Scripts", "coletor_adb.py"),
    "Processar Dataset": os.path.join(BASE_DIR, "Pre_process", "processar_dataset.py"),
    "Executar Teste": os.path.join(BASE_DIR, "Run", "run_noia.py"),
    "Abrir Dashboard": os.path.join(BASE_DIR, "Dashboard", "visualizador_execucao.py"),
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



st.set_page_config(page_title="Menu Tester", page_icon="🚗", layout="centered")
titulo_painel("🧠 Painel de Automação de Testes", "Plataforma <b>para</b> Coletar e Processar Testes")
st.divider() 

# === COLETA ===
st.subheader("🎥 Coletar Gestos")
categoria = st.text_input("Categoria do Teste (ex: audio, video, bluetooth)", key="cat_coleta")
nome_teste = st.text_input("Nome do Teste (ex: audio_1, bt_pareamento)", key="nome_coleta")

col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ Iniciar Coleta"):
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
                st.session_state.proc_coleta = subprocess.Popen(
                    [sys.executable, "-u", SCRIPTS["Coletar Gestos"], categoria, nome_teste],
                    cwd=BASE_DIR,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env
                )
                st.success(f"✅ Coleta iniciada para {categoria}/{nome_teste}")
            else:
                st.warning("⚠️ Já existe uma coleta em andamento.")
        else:
            st.error("Preencha categoria e nome do teste antes de iniciar.")

    if st.button("🛑 Finalizar Coleta"):
        proc = st.session_state.proc_coleta
        if proc:
            try:
                with open(STOP_FLAG_PATH, "w") as f:
                    f.write("stop")
                st.warning("👉 Toque na tela do rádio para capturar o print final...")
                proc.wait(timeout=15)
                st.success("🛑 Coleta finalizada com sucesso. Print final e ações salvos.")
            except subprocess.TimeoutExpired:
                proc.kill()
                st.warning("⚠️ Coletor não respondeu, finalizado à força.")
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
        logs_txt = "".join(lines[-200:])
    except Exception:
        logs_txt = ""
    st.text_area("Toques e eventos", value=logs_txt, height=220)
    if proc is not None and proc.poll() is not None:
        st.warning(f"Coleta finalizada com codigo {proc.returncode}. Veja o log acima.")
        st.session_state.proc_coleta = None

# === DELETAR TESTE ===
st.divider()
st.subheader("🗑️ Deletar Teste")
cat_del = st.text_input("Categoria do Teste a deletar", key="cat_del")
nome_del = st.text_input("Nome do Teste a deletar", key="nome_del")

if st.button("❌ Deletar Teste"):
    if cat_del and nome_del:
        teste_path = os.path.join(BASE_DIR, "Data", cat_del, nome_del)
        if os.path.exists(teste_path):
            try:
                shutil.rmtree(teste_path)
                st.success(f"🗑️ Teste {cat_del}/{nome_del} deletado com sucesso.")
            except Exception as e:
                st.error(f"❌ Erro ao deletar: {e}")
        else:
            st.warning(f"⚠️ Teste {cat_del}/{nome_del} não encontrado.")
    else:
        st.error("⚠️ Informe categoria e nome do teste para deletar.")

# === PROCESSAR DATASET (manual) ===
st.divider()
st.subheader("⚙️ Processar Dataset (opcional)")
categoria_ds = st.text_input("Categoria do Dataset", key="cat_dataset")
nome_teste_ds = st.text_input("Nome do Teste", key="nome_dataset")

if st.button("📂 Processar Dataset"):
    if categoria_ds and nome_teste_ds:
        subprocess.Popen(
            ["python", SCRIPTS["Processar Dataset"], categoria_ds, nome_teste_ds],
            cwd=BASE_DIR
        )
        st.info(f"🔄 Processando dataset de {categoria_ds}/{nome_teste_ds}...")
    else:
        st.error("⚠️ Informe categoria e nome do teste.")

# === EXECUTAR TESTE ===
st.divider()
st.subheader("Executar Testes")

categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")
nome_teste_exec = st.text_input("Nome do Teste (deixe vazio para rodar todos)", key="nome_exec")

st.markdown("<div class='exec-row'>", unsafe_allow_html=True)
col_a, col_b, col_c = st.columns([2, 2, 2])

with col_a:
    st.markdown("<div class='exec-card'>", unsafe_allow_html=True)
    st.markdown("<h4>Executar teste unico</h4>", unsafe_allow_html=True)
    if st.button("Executar Teste Unico"):
        if categoria_exec and nome_teste_exec:
            teste_path = os.path.join(BASE_DIR, "Data", categoria_exec, nome_teste_exec)
            dataset_path = os.path.join(teste_path, "dataset.csv")

            if not os.path.exists(dataset_path):
                st.warning("Dataset nao encontrado. Gerando automaticamente...")
                proc = subprocess.run(
                    ["python", SCRIPTS["Processar Dataset"], categoria_exec, nome_teste_exec],
                    cwd=BASE_DIR
                )
                if proc.returncode == 0:
                    st.success("Dataset processado com sucesso.")
                else:
                    st.error("Falha ao processar dataset.")
                    st.stop()

            try:
                result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, timeout=5)
                lines = result.stdout.strip().split("\n")[1:]
                dispositivos = [l.split("\t")[0] for l in lines if "\tdevice" in l]

                if not dispositivos:
                    st.error("Nenhum dispositivo ADB conectado.")
                    st.stop()

                serial = dispositivos[0]

                log_path = os.path.join(BASE_DIR, "Data", "execucao_live.log")
                st.session_state["execucao_log_path"] = log_path
                log_file = open(log_path, "w", encoding="utf-8", errors="ignore", buffering=1)
                proc_exec = subprocess.Popen(
                    ["python", SCRIPTS["Executar Teste"], categoria_exec, nome_teste_exec, "--serial", serial],
                    cwd=BASE_DIR,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                st.session_state["proc_execucao_unica"] = proc_exec
                st.session_state["execucao_unica_status"] = f"Executando {categoria_exec}/{nome_teste_exec} na bancada {serial}..."
                st.session_state["teste_em_execucao"] = True
                st.session_state["teste_pausado"] = False
                st.success(f"Execucao iniciada para {categoria_exec}/{nome_teste_exec} (Bancada {serial})")

            except Exception as e:
                st.error(f"Falha ao iniciar execucao: {e}")
        else:
            st.error("Informe categoria e nome do teste.")
    st.markdown("</div>", unsafe_allow_html=True)

# Logs de execucao (ao vivo)
log_path = st.session_state.get("execucao_log_path")
if log_path and os.path.exists(log_path):
    st.markdown("**Logs de execucao**")
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        logs_txt = "".join(lines[-200:])
    except Exception:
        logs_txt = ""
    st.markdown(f"<div class='log-box'><pre>{logs_txt}</pre></div>", unsafe_allow_html=True)

with col_b:
    st.markdown("<div class='exec-card secondary'>", unsafe_allow_html=True)
    st.markdown("<h4>Status</h4>", unsafe_allow_html=True)
    proc_exec = st.session_state.get("proc_execucao_unica")
    if proc_exec is not None and proc_exec.poll() is None:
        st_autorefresh(interval=1500, limit=None, key="execucao_unica_refresh")
        status_msg = st.session_state.get("execucao_unica_status", "Executando teste...")
    elif proc_exec is not None:
        if proc_exec.returncode == 0:
            status_msg = "Execucao do teste unico finalizada com sucesso."
        else:
            status_msg = f"Execucao do teste unico finalizou com erro (codigo {proc_exec.returncode})."
        st.session_state["proc_execucao_unica"] = None
        st.session_state["execucao_unica_status"] = ""
        st.session_state["teste_em_execucao"] = False
    else:
        status_msg = "Nenhum teste em execucao."
    st.markdown(f"<div class='status-box'>{status_msg}</div>", unsafe_allow_html=True)

    if "teste_em_execucao" in st.session_state and st.session_state["teste_em_execucao"]:
        if not st.session_state.get("teste_pausado", False):
            st.markdown("<div class='pause-btn'>", unsafe_allow_html=True)
            if st.button("Pausar Teste", key="pause_teste"):
                with open(os.path.join(BASE_DIR, "pause.flag"), "w") as f:
                    f.write("pause")
                st.session_state["teste_pausado"] = True
                st.warning("Execucao pausada.")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='resume-btn'>", unsafe_allow_html=True)
            if st.button("Retomar Teste", key="resume_teste"):
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
    if st.button("Executar Todos da Categoria"):
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
st.subheader("🧩 Gerar Relatórios de Falhas")

if st.button("📄 Gerar Relatórios de Falhas (execução_log.json)"):
    gerar_falha_path = os.path.join(BASE_DIR, "gerar_falha.py")
    if not os.path.exists(gerar_falha_path):
        st.error("❌ Arquivo gerar_falha.py não encontrado.")
    else:
        with st.spinner("🔍 Analisando execucao_log.json e gerando relatórios..."):
            try:
                result = subprocess.run(
                    ["python", gerar_falha_path],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True
                )
                st.text_area("📜 Saída do Script", result.stdout, height=250)

                rel_dir = os.path.join(BASE_DIR, "Relatorios_Falhas")
                if os.path.isdir(rel_dir):
                    relatorios = sorted(
                        [f for f in os.listdir(rel_dir) if f.endswith((".md", ".csv"))],
                        reverse=True
                    )
                    if relatorios:
                        st.success(f"✅ {len(relatorios)} relatórios gerados!")
                        for r in relatorios[:10]:
                            st.markdown(f"- 📁 **{r}** — `{os.path.join(rel_dir, r)}`")
                    else:
                        st.info("Nenhum relatório encontrado.")
                else:
                    st.warning("A pasta Relatorios_Falhas ainda não existe.")
            except Exception as e:
                st.error(f"❌ Erro ao executar gerar_falha.py: {e}")

# === DASHBOARD ===
st.divider()
if st.button("📊 Abrir Dashboard"):
    subprocess.Popen(["streamlit", "run", SCRIPTS["Abrir Dashboard"]], cwd=BASE_DIR)
    st.success("🌐 Dashboard aberto em nova aba do navegador.")
