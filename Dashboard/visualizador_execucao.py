# dashboard/visualizador_execucao.py

import streamlit as st
import json
import os
import pandas as pd
from PIL import Image
from io import BytesIO
from datetime import datetime

# === Configuração inicial ===
ROOT_DIR = "Data"
st.set_page_config(page_title="Dashboard de Execução", layout="wide")
st.title("📊 Dashboard de Execução Automatizada")

# === Funções auxiliares ===
def encontrar_logs(root):
    return [
        os.path.join(dirpath, file)
        for dirpath, _, filenames in os.walk(root)
        for file in filenames if file == "execucao_log.json"
    ]

def tempo_total(df):
    return (df['timestamp_fim'].max() - df['timestamp_inicio'].min()).total_seconds()

# === Seletor de log ===
logs = encontrar_logs(ROOT_DIR)
if not logs:
    st.warning("Nenhum log encontrado.")
    st.stop()

log_path = st.selectbox("📁 Escolha um log para visualizar:", logs)
with open(log_path, "r", encoding="utf-8") as f:
    registros = json.load(f)

df = pd.DataFrame(registros)
df['timestamp_inicio'] = pd.to_datetime(df['timestamp_inicio'])
df['timestamp_fim'] = pd.to_datetime(df['timestamp_fim'])
df['tempo_execucao'] = (df['timestamp_fim'] - df['timestamp_inicio']).dt.total_seconds()
df['resultado'] = df['erro'].apply(lambda x: "❌ Falha" if pd.notna(x) else "✅ Sucesso")

# === Filtros laterais ===
st.sidebar.header("🔎 Filtros")
filtro_resultado = st.sidebar.multiselect("Filtrar por resultado:", options=["✅ Sucesso", "❌ Falha"], default=["✅ Sucesso", "❌ Falha"])
df_filtrado = df[df['resultado'].isin(filtro_resultado)]

# === Exportação ===
st.sidebar.header("📤 Exportar relatório")
export_formato = st.sidebar.selectbox("Formato:", ["CSV", "Excel"])
nome_arquivo = f"relatorio_execucao_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if st.sidebar.button("📥 Baixar"):
    if export_formato == "CSV":
        csv_data = df_filtrado.to_csv(index=False).encode("utf-8")
        st.sidebar.download_button("⬇️ Baixar CSV", csv_data, file_name=f"{nome_arquivo}.csv", mime="text/csv")
    else:
        excel_io = BytesIO()
        with pd.ExcelWriter(excel_io, engine='xlsxwriter') as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name='Execucao')
        st.sidebar.download_button("⬇️ Baixar Excel", excel_io.getvalue(), file_name=f"{nome_arquivo}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# === Métricas gerais ===
col1, col2, col3, col4 = st.columns(4)
col1.metric("🔁 Total de Ações", len(df))
col2.metric("✅ Sucessos", df['resultado'].value_counts().get("✅ Sucesso", 0))
col3.metric("❌ Falhas", df['resultado'].value_counts().get("❌ Falha", 0))
col4.metric("⏱️ Tempo Total (s)", f"{tempo_total(df):.1f}")

# === Timeline de execução ===
st.markdown("### 🕒 Timeline de Execução")
df_timeline = df[['timestamp_inicio', 'tempo_execucao', 'resultado']].copy()
df_timeline['horário'] = df_timeline['timestamp_inicio'].dt.strftime('%H:%M:%S')
st.bar_chart(data=df_timeline, x='horário', y='tempo_execucao', color='resultado')

st.markdown("---")
st.subheader("📌 Detalhamento das Ações")

# === Loop de ações ===
for idx, r in df_filtrado.iterrows():
    with st.expander(f"Ação {r['indice']+1} — {r['resultado']} — Tempo: {r['tempo_execucao']:.2f}s"):
        col1, col2 = st.columns([1, 2])
        img_path = r.get("imagem_referencia")

        # Imagem de referência
        if img_path and os.path.exists(img_path):
            col1.image(Image.open(img_path), caption="Imagem Referência", use_column_width=True)
        else:
            col1.warning("Imagem não encontrada")

        # Dados relevantes
        dados = {
            "Tipo": r.get("tipo"),
            "Coordenadas": r.get("coordenadas"),
            "Similaridade final": round(r.get("similaridade_final", 0), 4),
            "Erro": r.get("erro", "Nenhum"),
            "Início": r.get("timestamp_inicio"),
            "Fim": r.get("timestamp_fim"),
        }
        col2.json(dados)

st.caption("🧠 Desenvolvido para validar execuções da IA no infotainment com precisão.")