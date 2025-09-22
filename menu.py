import streamlit as st
import subprocess
import os
import signal
import platform

# === CONFIG ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    "Coletar Gestos": os.path.join(BASE_DIR, "Scripts", "coletor_adb.py"),
    "Processar Dataset": os.path.join(BASE_DIR, "Pre_process", "processar_dataset.py"),
    "Executar Teste": os.path.join(BASE_DIR, "Run", "run_noia.py"),
    "Abrir Dashboard": os.path.join(BASE_DIR, "Dashboard", "visualizador_execucao.py"),
}

STOP_FLAG_PATH = os.path.join(BASE_DIR, "stop.flag")

# Guarda referência do processo da coleta
if "proc_coleta" not in st.session_state:
    st.session_state.proc_coleta = None

st.set_page_config(page_title="ZURI - Automação VW", page_icon="🚗", layout="centered")
st.image("https://upload.wikimedia.org/wikipedia/commons/6/6d/VW_logo_2019.png", width=120)
st.title("ZURI - Plataforma de Automação de Testes")
st.markdown("**Sistema de testes automatizados para Infotainment - Volkswagen**")
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
                # 1) Garante que não existe stop.flag esquecido
                if os.path.exists(STOP_FLAG_PATH):
                    try:
                        os.remove(STOP_FLAG_PATH)
                    except Exception:
                        pass

                # Inicia o coletor com os argumentos (categoria / nome)
                st.session_state.proc_coleta = subprocess.Popen(
                    ["python", SCRIPTS["Coletar Gestos"], categoria, nome_teste],
                    cwd=BASE_DIR
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
                if platform.system() == "Windows":
                    # 2) Windows: cria stop.flag para o coletor encerrar limpo
                    with open(STOP_FLAG_PATH, "w") as f:
                        f.write("stop")
                    st.info("📄 stop.flag criado. Aguardando a coleta finalizar...")

                    # Aguarda saída graciosa
                    proc.wait(timeout=10)
                else:
                    # 3) Linux/Mac: manda SIGINT (CTRL+C)
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=10)

                st.success("🛑 Coleta finalizada e print final salvo.")
            except subprocess.TimeoutExpired:
                proc.kill()
                st.warning("⚠️ Processo não respondeu, foi finalizado à força.")
            finally:
                # 4) Limpa flag (se existir) e reseta estado
                if os.path.exists(STOP_FLAG_PATH):
                    try:
                        os.remove(STOP_FLAG_PATH)
                    except Exception:
                        pass
                st.session_state.proc_coleta = None
        else:
            st.info("Nenhuma coleta em andamento.")

# === PROCESSAR DATASET ===
st.divider()
st.subheader("⚙️ Processar Dataset")
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
        st.error("⚠️ Informe categoria e nome do teste para processar o dataset.")

# === EXECUTAR TESTE ===
st.divider()
st.subheader("🚀 Executar Teste")
categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")
nome_teste_exec = st.text_input("Nome do Teste", key="nome_exec")

if st.button("▶️ Executar Teste"):
    if categoria_exec and nome_teste_exec:
        subprocess.Popen(
            ["python", SCRIPTS["Executar Teste"], categoria_exec, nome_teste_exec],
            cwd=BASE_DIR
        )
        st.info(f"▶️ Execução do teste iniciada para {categoria_exec}/{nome_teste_exec}...")
    else:
        st.error("⚠️ Informe categoria e nome do teste para executar o teste.")

# === DASHBOARD ===
st.divider()
if st.button("📊 Abrir Dashboard"):
    subprocess.Popen(["streamlit", "run", SCRIPTS["Abrir Dashboard"]], cwd=BASE_DIR)
    st.success("🌐 Dashboard aberto em nova aba do navegador.")
