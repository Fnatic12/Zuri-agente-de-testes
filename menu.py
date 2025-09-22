import streamlit as st
import subprocess
import os
import platform
import shutil

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
st.title("Plataforma de Automação de Testes")
st.markdown("**Sistema de testes automatizados para GEI - BTEE4**")
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
                # Cria stop.flag para sinalizar ao coletor
                with open(STOP_FLAG_PATH, "w") as f:
                    f.write("stop")

                st.warning("👉 Toque uma vez na tela do rádio para capturar o print final...")

                proc.wait(timeout=15)  # espera o coletor encerrar sozinho
                st.success("🛑 Coleta finalizada com sucesso. Print final e ações salvos.")
            except subprocess.TimeoutExpired:
                proc.kill()
                st.warning("⚠️ Coletor não respondeu, processo finalizado à força (sem print final).")
            finally:
                if os.path.exists(STOP_FLAG_PATH):
                    os.remove(STOP_FLAG_PATH)
                st.session_state.proc_coleta = None
        else:
            st.info("Nenhuma coleta em andamento.")

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

# === PROCESSAR DATASET (manual, opcional) ===
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
        st.error("⚠️ Informe categoria e nome do teste para processar o dataset.")

# === EXECUTAR TESTE ===
st.divider()
st.subheader("🚀 Executar Teste")
categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")
nome_teste_exec = st.text_input("Nome do Teste", key="nome_exec")

if st.button("▶️ Executar Teste"):
    if categoria_exec and nome_teste_exec:
        teste_path = os.path.join(BASE_DIR, "Data", categoria_exec, nome_teste_exec)
        dataset_path = os.path.join(teste_path, "dataset.csv")

        # Se não existir dataset, processa antes de executar
        if not os.path.exists(dataset_path):
            st.warning("⚠️ Dataset não encontrado. Gerando automaticamente...")
            proc = subprocess.run(
                ["python", SCRIPTS["Processar Dataset"], categoria_exec, nome_teste_exec],
                cwd=BASE_DIR
            )
            if proc.returncode == 0:
                st.success("✅ Dataset processado com sucesso.")
            else:
                st.error("❌ Falha ao processar dataset. Verifique o JSON de ações.")
                st.stop()

        # Agora executa o teste
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
