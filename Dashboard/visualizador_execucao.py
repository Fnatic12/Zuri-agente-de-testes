import os
import json
import streamlit as st
from PIL import Image
import matplotlib.pyplot as plt

# === CONFIGURAÇÕES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

# === FUNÇÕES ===
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
    acertos = sum(1 for a in execucao if "✅" in a["status"])
    falhas = total - acertos
    precisao = round((acertos / total) * 100, 2) if total > 0 else 0
    return {
        "total_acoes": total,
        "acertos": acertos,
        "falhas": falhas,
        "precisao_percentual": precisao,
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO"
    }

def exibir_metricas(metricas):
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Ações", metricas["total_acoes"])
    col2.metric("Acertos", metricas["acertos"])
    col3.metric("Falhas", metricas["falhas"])
    st.metric("Precisão (%)", metricas["precisao_percentual"])

    # Corrigido para não retornar DeltaGenerator
    if metricas["resultado_final"] == "APROVADO":
        st.success("✅ APROVADO")
    else:
        st.error("❌ REPROVADO")

    # === GRÁFICO DE PIZZA ===
    fig, ax = plt.subplots()
    labels = ["Acertos", "Falhas"]
    sizes = [metricas["acertos"], metricas["falhas"]]
    colors = ["#4CAF50", "#F44336"]
    explode = (0.05, 0)  # destaca os acertos

    ax.pie(
        sizes,
        explode=explode,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        shadow=True,
        startangle=90
    )
    ax.axis("equal")
    st.pyplot(fig)

def exibir_acoes(execucao, base_dir):
    st.subheader("📋 Detalhes das Ações")
    for acao in execucao:
        with st.expander(f"Ação {acao['id']} - {acao['acao'].upper()} | {acao['status']}"):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao["frame_esperado"])
            resultado_path = os.path.join(base_dir, acao["screenshot"])

            if os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Frame Esperado ({acao['frame_esperado']})", use_container_width=True)
            else:
                col1.warning("Frame esperado não encontrado")

            if os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Screenshot Obtido ({acao['screenshot']})", use_container_width=True)
            else:
                col2.warning("Screenshot não encontrado")

            st.write(f"🎯 Similaridade: **{acao['similaridade']:.2f}**")
            st.json(acao["coordenadas"])

def exibir_validacao_final(execucao, base_dir):
    st.subheader("🖼️ Validação Final da Tela")

    # Caminho do resultado final (gerado pelo run_noia.py)
    resultado_final_path = os.path.join(base_dir, "resultado_final.png")

    col1, col2 = st.columns(2)

    # Frame esperado = última ação do log
    if execucao:
        ultima = execucao[-1]
        frame_path = os.path.join(base_dir, ultima["frame_esperado"])

        if os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (Última Ação)", use_container_width=True)
        else:
            col1.error("Frame esperado não encontrado")

        # Screenshot final: usa resultado_final.png se existir
        if os.path.exists(resultado_final_path):
            col2.image(Image.open(resultado_final_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png não encontrado")

        # Similaridade final
        st.write(f"🎯 Similaridade Final: **{ultima['similaridade']:.2f}**")
        if "✅" in ultima["status"]:
            st.success("✅ Tela final validada")
        else:
            st.error("❌ Tela final divergente")
    else:
        st.warning("Nenhuma ação registrada")

# === INTERFACE ===
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

# === MÉTRICAS ===
st.subheader("📈 Métricas Gerais")
metricas = calcular_metricas(execucao)
exibir_metricas(metricas)

# === AÇÕES DETALHADAS ===
exibir_acoes(execucao, base_dir)

# === VALIDAÇÃO FINAL ===
exibir_validacao_final(execucao, base_dir)
