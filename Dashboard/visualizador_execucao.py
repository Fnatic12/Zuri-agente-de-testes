import os
import json
import streamlit as st
from PIL import Image
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import time

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

# === CONFIGURAÇÕES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
st.set_page_config(page_title="Dashboard - VWAIT", page_icon="📊", layout="wide")

# === FUNÇÕES AUXILIARES ===
def carregar_logs(data_root=DATA_ROOT):
    """Lista execuções disponíveis"""
    logs = []
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
    if total == 0:
        return {
            "total_acoes": 0,
            "acertos": 0,
            "falhas": 0,
            "flakes": 0,
            "precisao_percentual": 0,
            "tempo_total": 0,
            "cobertura_telas": 0,
            "resultado_final": "SEM DADOS"
        }

    acertos = sum(1 for a in execucao if "✅" in a.get("status", ""))
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", ""))
    tempo_total = sum(a.get("duracao", 1) for a in execucao)

    # TOLERANTE a ausência de 'id' e/ou 'tela'
    telas_unicas = {
        (a.get("tela") or f"id{a.get('id', idx)}")
        for idx, a in enumerate(execucao)
    }
    cobertura = round((len(telas_unicas) / total) * 100, 1)
    precisao = round((acertos / total) * 100, 2)

    return {
        "total_acoes": total,
        "acertos": acertos,
        "falhas": falhas,
        "flakes": flakes,
        "precisao_percentual": precisao,
        "tempo_total": tempo_total,
        "cobertura_telas": cobertura,
        "resultado_final": "✅ APROVADO" if falhas == 0 else "❌ REPROVADO"
    }

# === DASHBOARD ===
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

    # === GRÁFICO DE PIZZA ===
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
    tempos = [a.get("duracao", 1) for a in execucao]
    ids = [a["id"] for a in execucao]
    status = ["green" if "✅" in a["status"] else "red" for a in execucao]

    fig, ax = plt.subplots()
    ax.bar(ids, tempos, color=status)
    ax.set_xlabel("Ação")
    ax.set_ylabel("Duração (s)")
    ax.set_title("Tempo por Ação")
    st.pyplot(fig)

def exibir_acoes(execucao, base_dir):
    st.subheader("📋 Detalhes das Ações")
    for acao in execucao:
        with st.expander(f"Ação {acao['id']} - {acao['acao'].upper()} | {acao['status']}"):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao["frame_esperado"])
            resultado_path = os.path.join(base_dir, acao["screenshot"])

            if os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {acao['frame_esperado']}", use_container_width=True)
            else:
                col1.warning("Frame esperado não encontrado")

            if os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Obtido: {acao['screenshot']}", use_container_width=True)
            else:
                col2.warning("Screenshot não encontrado")

            st.write(f"🎯 Similaridade: **{acao['similaridade']:.2f}**")
            st.write(f"⏱️ Duração: **{acao.get('duracao', 0)}s**")
            st.json(acao.get("coordenadas", {}))
            if "log" in acao:
                st.code(acao["log"], language="bash")

def exibir_mapa_calor(execucao):
    st.subheader("🔥 Mapa de Calor dos Toques")
    xs = [a["coordenadas"]["x"] for a in execucao if "coordenadas" in a]
    ys = [a["coordenadas"]["y"] for a in execucao if "coordenadas" in a]

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
        frame_path = os.path.join(base_dir, ultima["frame_esperado"])

        if os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (Última Ação)", use_container_width=True)
        else:
            col1.error("Frame esperado não encontrado")

        if os.path.exists(resultado_final_path):
            col2.image(Image.open(resultado_final_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png não encontrado")

        st.write(f"🎯 Similaridade Final: **{ultima['similaridade']:.2f}**")
        if "✅" in ultima["status"]:
            st.success("✅ Tela final validada")
        else:
            st.error("❌ Tela final divergente")
    else:
        st.warning("Nenhuma ação registrada")

def exibir_regressoes(execucao):
    st.subheader("📉 Análise de Regressões")
    falhas = [a for a in execucao if "❌" in a["status"]]
    if falhas:
        st.write("Top falhas nesta execução:")
        for f in falhas:
            st.write(f"- Ação {f['id']} ({f['acao']}): Similaridade {f['similaridade']:.2f}")
    else:
        st.success("Nenhuma falha registrada")

titulo_painel("📋 Dashboard de Execução de Testes - VWAIT", "Veja <b>todos</b> os resultados dos testes")

logs = carregar_logs()
if not logs:
    st.error("Nenhum execucao_log.json encontrado em Data/*/*/")
    st.stop()

opcao = st.selectbox("Selecione a execução", [r[0] for r in logs])
log_path = dict(logs)[opcao]

with open(log_path, "r", encoding="utf-8") as f:
    execucao = json.load(f)

base_dir = os.path.dirname(log_path)

# === SEÇÕES DO DASHBOARD ===
metricas = calcular_metricas(execucao)
exibir_metricas(metricas)
exibir_timeline(execucao)
exibir_acoes(execucao, base_dir)
exibir_mapa_calor(execucao)
exibir_validacao_final(execucao, base_dir)
exibir_regressoes(execucao)

# === EXPORTAÇÃO ===
if st.button("📤 Exportar Relatório JSON"):
    st.download_button("Baixar JSON", data=json.dumps(execucao, indent=2), file_name="relatorio_execucao.json")
