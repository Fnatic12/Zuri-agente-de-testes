import os
import json
import time
import streamlit as st
from datetime import datetime, timedelta

# === CONFIGURAÇÕES GERAIS ===
st.set_page_config(
    page_title="ZURI - Painel de Bancadas",
    page_icon="🖥️",
    layout="wide"
)

STATUS_FILE = os.path.join("Data", "status_bancadas.json")

st.title("🖥️ Painel de Bancadas - Execuções em Tempo Real")
st.caption("Acompanhe em tempo real o progresso e o status de cada bancada ZURI.")

# === BOTÃO DE ATUALIZAÇÃO MANUAL ===
if st.button("🔄 Atualizar agora"):
    st.experimental_rerun()

# === FUNÇÃO AUXILIAR ===
def carregar_status(status_file=STATUS_FILE):
    """Carrega status das bancadas"""
    if not os.path.exists(status_file):
        return {}
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        st.error(f"Erro ao ler status_bancadas.json: {e}")
        return {}

def tempo_formatado(segundos):
    if segundos < 60:
        return f"{int(segundos)}s"
    elif segundos < 3600:
        return f"{int(segundos // 60)}m {int(segundos % 60)}s"
    else:
        horas = int(segundos // 3600)
        minutos = int((segundos % 3600) // 60)
        return f"{horas}h {minutos}m"

# === CARREGAMENTO DE STATUS ===
bancadas = carregar_status()
if not bancadas:
    st.warning("Nenhuma bancada encontrada ou arquivo 'status_bancadas.json' ausente.")
    st.stop()

# === INTERFACE ===
cols = st.columns(len(bancadas))

for i, (bancada, dados) in enumerate(bancadas.items()):
    with cols[i]:
        st.markdown(f"### 🧩 **{bancada.upper()}**")

        status = dados.get("status", "Ociosa")
        teste = dados.get("teste", "-")
        progresso = dados.get("progresso", 0)
        ultima_acao = dados.get("ultima_acao", "—")
        tempo_decorrido = dados.get("tempo_decorrido_s", 0)

        # === DEFINIR COR E TEXTO DO STATUS ===
        if status == "Executando":
            status_color = "🟢"
            status_label = f"{status_color} **Em execução**"
        elif status == "Ociosa":
            status_color = "⚪"
            status_label = f"{status_color} **Ociosa**"
        elif status == "Finalizado":
            status_color = "✅"
            status_label = f"{status_color} **Finalizado**"
        else:
            status_color = "🔴"
            status_label = f"{status_color} **Indefinido**"

        # === CARD VISUAL ===
        st.markdown(
            f"""
            <div style="
                background: #1E1E1E;
                border-radius: 16px;
                padding: 18px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.25);
                color: #E0E0E0;
                border: 1px solid rgba(255,255,255,0.1);
                ">
                <h4 style="margin-top:0;">🧪 {teste}</h4>
                <p style="font-size:14px; margin-bottom:8px;">{status_label}</p>

                <div style="margin-top:8px; margin-bottom:8px;">
                    <div style="
                        background:#333;
                        border-radius:8px;
                        overflow:hidden;
                        height:20px;
                        width:100%;
                        ">
                        <div style="
                            background:#4CAF50;
                            width:{progresso}%;
                            height:100%;
                            transition:width 0.5s;
                        "></div>
                    </div>
                    <p style="font-size:13px; text-align:right;">{progresso:.1f}% concluído</p>
                </div>

                <p style="font-size:13px;">⏱️ Tempo: {tempo_formatado(tempo_decorrido)}</p>
                <p style="font-size:13px;">🎯 Última ação: <b>{ultima_acao}</b></p>
            </div>
            """,
            unsafe_allow_html=True
        )

        # === BOTÃO DETALHES ===
        if status in ["Executando", "Finalizado"]:
            st.button(f"🔍 Ver Detalhes ({teste})", key=f"det_{bancada}")
        else:
            st.button("⏸️ Aguardando", disabled=True, key=f"aguardando_{bancada}")

st.divider()

# === RESUMO GERAL ===
st.markdown("## 📊 Resumo das Execuções")

executando = [b for b, d in bancadas.items() if d.get("status") == "Executando"]
finalizados = [b for b, d in bancadas.items() if d.get("status") == "Finalizado"]
ociosas = [b for b, d in bancadas.items() if d.get("status") == "Ociosa"]

col1, col2, col3 = st.columns(3)
col1.metric("🟢 Executando", len(executando))
col2.metric("✅ Finalizados", len(finalizados))
col3.metric("⚪ Ociosas", len(ociosas))

# === TABELA DETALHADA ===
st.markdown("### 📋 Detalhes por Bancada")
st.dataframe(
    [
        {
            "Bancada": b.upper(),
            "Teste": d.get("teste", "-"),
            "Status": d.get("status", "Ociosa"),
            "Progresso (%)": d.get("progresso", 0),
            "Última Ação": d.get("ultima_acao", "-"),
            "Tempo Decorrido": tempo_formatado(d.get("tempo_decorrido_s", 0))
        }
        for b, d in bancadas.items()
    ],
    hide_index=True,
    use_container_width=True
)

st.caption("Clique em 🔄 Atualizar para recarregar o status das bancadas.")
