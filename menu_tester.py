import streamlit as st
import subprocess
import os
import platform
import shutil

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

# Guarda referência do processo da coleta
if "proc_coleta" not in st.session_state:
    st.session_state.proc_coleta = None

st.set_page_config(page_title="Menu Tester", page_icon="🚗", layout="centered")
titulo_painel("🧠 Painel de Automação de Testes", "Plataforma <b>para</b> coletar e processamento de testes")
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
st.subheader("🚀 Executar Testes")

categoria_exec = st.text_input("Categoria do Teste", key="cat_exec")
nome_teste_exec = st.text_input("Nome do Teste (deixe vazio para rodar todos)", key="nome_exec")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ Executar Teste Único"):
        if categoria_exec and nome_teste_exec:
            teste_path = os.path.join(BASE_DIR, "Data", categoria_exec, nome_teste_exec)
            dataset_path = os.path.join(teste_path, "dataset.csv")

            # Se não existir dataset, processa antes
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

            subprocess.Popen(
                ["python", SCRIPTS["Executar Teste"], categoria_exec, nome_teste_exec],
                cwd=BASE_DIR
            )
            st.session_state["teste_em_execucao"] = True
            st.session_state["teste_pausado"] = False
            st.info(f"▶️ Execução iniciada para {categoria_exec}/{nome_teste_exec}")
        else:
            st.error("⚠️ Informe categoria e nome do teste.")

with col2:
    # Botão de pausa/retomada
    if "teste_em_execucao" in st.session_state and st.session_state["teste_em_execucao"]:
        if not st.session_state.get("teste_pausado", False):
            if st.button("⏸️ Pausar Teste"):
                with open(os.path.join(BASE_DIR, "pause.flag"), "w") as f:
                    f.write("pause")
                st.session_state["teste_pausado"] = True
                st.warning("⏸️ Execução pausada. Aguarde para retomar.")
        else:
            if st.button("▶️ Retomar Teste"):
                pause_path = os.path.join(BASE_DIR, "pause.flag")
                if os.path.exists(pause_path):
                    os.remove(pause_path)
                st.session_state["teste_pausado"] = False
                st.success("✅ Execução retomada com sucesso.")
    else:
        st.info("⚙️ Nenhum teste em execução.")

with col3:
    if st.button("📂 Executar Todos da Categoria"):
        if categoria_exec:
            categoria_path = os.path.join(BASE_DIR, "Data", categoria_exec)
            if not os.path.isdir(categoria_path):
                st.error(f"❌ Categoria {categoria_exec} não encontrada em Data/")
            else:
                testes = [t for t in os.listdir(categoria_path) if os.path.isdir(os.path.join(categoria_path, t))]
                if not testes:
                    st.warning(f"⚠️ Nenhum teste encontrado em Data/{categoria_exec}/")
                else:
                    st.success(f"▶️ Executando {len(testes)} testes da categoria {categoria_exec}...")
                    for t in testes:
                        dataset_path = os.path.join(categoria_path, t, "dataset.csv")
                        if not os.path.exists(dataset_path):
                            subprocess.run(
                                ["python", SCRIPTS["Processar Dataset"], categoria_exec, t],
                                cwd=BASE_DIR
                            )
                        subprocess.Popen(
                            ["python", SCRIPTS["Executar Teste"], categoria_exec, t],
                            cwd=BASE_DIR    
                        )
        else:
            st.error("⚠️ Informe a categoria para rodar todos os testes.")

# === RELATÓRIOS DE FALHAS ===
st.divider()
st.subheader("🧩 Gerar Relatórios de Falhas")

if st.button("📄 Gerar Relatórios de Falhas (execução_log.json)"):
    gerar_falha_path = os.path.join(BASE_DIR, "gerar_falha.py")
    if not os.path.exists(gerar_falha_path):
        st.error("❌ Arquivo gerar_falha.py não encontrado na raiz do projeto.")
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

                # Listar relatórios recém-criados
                rel_dir = os.path.join(BASE_DIR, "Relatorios_Falhas")
                if os.path.isdir(rel_dir):
                    relatorios = sorted(
                        [f for f in os.listdir(rel_dir) if f.endswith((".md", ".csv"))],
                        reverse=True
                    )
                    if relatorios:
                        st.success(f"✅ {len(relatorios)} relatórios gerados!")
                        for r in relatorios[:10]:  # mostra os 10 mais recentes
                            st.markdown(f"- 📁 **{r}** — `{os.path.join(rel_dir, r)}`")
                    else:
                        st.info("Nenhum relatório foi encontrado em /Relatorios_Falhas.")
                else:
                    st.warning("A pasta Relatorios_Falhas ainda não existe.")
            except Exception as e:
                st.error(f"❌ Erro ao executar gerar_falha.py: {e}")

# === DASHBOARD ===
st.divider()
if st.button("📊 Abrir Dashboard"):
    subprocess.Popen(["streamlit", "run", SCRIPTS["Abrir Dashboard"]], cwd=BASE_DIR)
    st.success("🌐 Dashboard aberto em nova aba do navegador.")
