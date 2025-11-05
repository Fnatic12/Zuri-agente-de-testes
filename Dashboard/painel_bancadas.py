import os
import json
import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import tempfile

# ============ CONFIG ============ #
st.set_page_config(page_title="ZURI - Painel de Bancadas", page_icon="🧠", layout="wide")

STATUS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data", "status_bancadas.json")

# ============ ESTILO GLOBAL ============ #
st.markdown("""
<style>
body { background-color: #0B0C10; color: #E0E0E0; font-family: 'Inter', sans-serif; }

.main-title {
    font-size: 2.5rem;
    text-align: center;
    background: linear-gradient(90deg, #12c2e9, #c471ed, #f64f59);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 0.3em;
}
.subtitle {
    text-align: center;
    color: #AAAAAA;
    font-size: 1rem;
    margin-bottom: 1.8em;
}

.card {
    background: rgba(30,30,30,0.95);
    border-radius: 18px;
    padding: 22px;
    border: 1px solid rgba(255,255,255,0.05);
    box-shadow: 0 8px 22px rgba(0,0,0,0.45);
    transition: all 0.3s ease-in-out;
}
.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 25px rgba(0,0,0,0.6);
}

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 8px;
}

.badge.executando { background: linear-gradient(90deg,#f6d365,#fda085); animation: pulse 1.5s infinite; }
.badge.finalizado { background: linear-gradient(90deg,#56ab2f,#a8e063); }
.badge.ociosa { background: linear-gradient(90deg,#bdc3c7,#2c3e50); }
.badge.erro { background: linear-gradient(90deg,#ff416c,#ff4b2b); }

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(253,160,133, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(253,160,133, 0); }
  100% { box-shadow: 0 0 0 0 rgba(253,160,133, 0); }
}

.progress-container {
    background: #2a2a2a;
    border-radius: 10px;
    height: 16px;
    overflow: hidden;
    margin-top: 12px;
}
.progress-bar {
    height: 100%;
    transition: width 0.8s ease-in-out;
}
.metric-label { font-size: 13px; color: #B0B0B0; margin-top: 6px; margin-bottom: 2px; }
</style>
""", unsafe_allow_html=True)

# ============ HEADER ============ #
st.markdown("<h1 class='main-title'>🧠 Painel de Execução ZURI</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Monitoramento em tempo real das bancadas Android conectadas</p>", unsafe_allow_html=True)

st_autorefresh(interval=3000, limit=None, key="refresh_status")

# ============ FUNÇÕES AUXILIARES ============ #
def tempo_formatado(segundos):
    if segundos < 60:
        return f"{int(segundos)}s"
    if segundos < 3600:
        return f"{int(segundos // 60)}m {int(segundos % 60)}s"
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    return f"{h}h {m}m"

def _atomic_overwrite(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=os.path.dirname(path)) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)

def carregar_status_higienizado():
    if not os.path.exists(STATUS_PATH):
        return {}
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    cleaned = {}
    for k, v in raw.items():
        serial = k.replace("bancada_", "")
        cleaned[serial] = v
        if "status" in v and isinstance(v["status"], str):
            v["status"] = v["status"].lower()

    if cleaned != raw:
        _atomic_overwrite(STATUS_PATH, cleaned)

    return cleaned

# ============ LEITURA E EXIBIÇÃO ============ #
bancadas = carregar_status_higienizado()

if not bancadas:
    st.info("🔌 Nenhuma bancada ativa no momento. Aguardando execução...")
    st.stop()

# Distribui dinamicamente os cards
cols_per_row = 3 if len(bancadas) >= 3 else len(bancadas)
rows = [list(bancadas.items())[i:i+cols_per_row] for i in range(0, len(bancadas), cols_per_row)]

for row in rows:
    cols = st.columns(len(row))
    for col, (bancada, dados) in zip(cols, row):
        with col:
            status = str(dados.get("status", "ociosa")).lower()
            teste = dados.get("teste", "-")
            progresso = float(dados.get("progresso", 0))
            ultima_acao = dados.get("ultima_acao", "—")
            tempo_decorrido = float(dados.get("tempo_decorrido_s", 0))

            if status == "executando":
                badge_class, grad = "executando", "linear-gradient(90deg,#f6d365,#fda085)"
                emoji = "⚙️"
            elif status == "finalizado":
                badge_class, grad = "finalizado", "linear-gradient(90deg,#56ab2f,#a8e063)"
                emoji = "✅"
            elif status == "ociosa":
                badge_class, grad = "ociosa", "linear-gradient(90deg,#bdc3c7,#2c3e50)"
                emoji = "💤"
            else:
                badge_class, grad = "erro", "linear-gradient(90deg,#ff416c,#ff4b2b)"
                emoji = "❌"

            nome_card = bancada if bancada != "BANCADA_SEM_SERIAL" else "Bancada Genérica"

            st.markdown(f"""
            <div class="card">
                <div class="badge {badge_class}">{emoji} {status.capitalize()}</div>
                <h3 style="color:#fff; margin-bottom:4px;">{nome_card.upper()}</h3>
                <p style="color:#aaa; font-size:14px;">🧩 <b>Teste:</b> {teste}</p>

                <div class="progress-container">
                    <div class="progress-bar" style="width:{progresso}%; background:{grad};"></div>
                </div>
                <p class="metric-label" style="text-align:right;">{progresso:.1f}% concluído</p>

                <p class="metric-label">⏱️ <b>Tempo:</b> {tempo_formatado(tempo_decorrido)}</p>
                <p class="metric-label">🎯 <b>Última ação:</b> {ultima_acao}</p>
            </div>
            """, unsafe_allow_html=True)

# ============ RESUMO ============ #
st.markdown("---")
st.markdown("## 📊 Resumo das Bancadas")

executando = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "executando"]
finalizados = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "finalizado"]
ociosas = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "ociosa"]
erros = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "erro"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("⚙️ Em Execução", len(executando))
col2.metric("✅ Finalizados", len(finalizados))
col3.metric("💤 Ociosas", len(ociosas))
col4.metric("❌ Com Erros", len(erros))

st.caption("🕒 Atualização automática a cada 3 segundos — dados provenientes de 'status_bancadas.json'")

# ============ TABELA DE DETALHES ============ #
import pandas as pd

st.markdown("---")
st.markdown("## 🧠 Detalhamento Técnico das Bancadas")

dados_tabela = []

for bancada, info in bancadas.items():
    total = int(info.get("acoes_totais", 0))
    execs = int(info.get("acoes_executadas", 0))
    progresso = float(info.get("progresso", 0))
    tipo_exec = "Teste Automatizado"
    if "coleta" in str(info.get("teste", "")).lower():
        tipo_exec = "Coleta de Dados"
    elif "valida" in str(info.get("teste", "")).lower():
        tipo_exec = "Validação"
    elif "treino" in str(info.get("teste", "")).lower():
        tipo_exec = "Treinamento IA"

    dados_tabela.append({
        "💻 Bancada": bancada,
        "🧩 Teste": info.get("teste", "-"),
        "⚙️ Status": info.get("status", "-").capitalize(),
        "⏱️ Tempo Decorrido": tempo_formatado(float(info.get("tempo_decorrido_s", 0))),
        "🏁 Conclusão (%)": f"{progresso:.1f}",
        "👆 Taps Executados": f"{execs}/{total}" if total > 0 else "-",
        "🧠 Tipo Execução": tipo_exec
    })

df = pd.DataFrame(dados_tabela)

# Cores personalizadas por status
def highlight_status(val):
    v = str(val).lower()
    if "executando" in v:
        color = "#f6ad55"
    elif "finalizado" in v:
        color = "#68d391"
    elif "ociosa" in v:
        color = "#a0aec0"
    elif "erro" in v:
        color = "#f56565"
    else:
        color = "#e2e8f0"
    return f"color: {color}; font-weight: 600;"

st.dataframe(
    df.style
    .applymap(highlight_status, subset=["⚙️ Status"])
    .set_properties(**{
        "background-color": "#1c1c1c",
        "color": "#e0e0e0",
        "border-color": "#333",
        "font-size": "14px",
        "text-align": "center"
    })
    .set_table_styles([
        {'selector': 'thead th', 'props': [
            ('background-color', '#242424'),
            ('color', '#f0f0f0'),
            ('font-size', '14px'),
            ('font-weight', 'bold'),
            ('border-bottom', '2px solid #444')
        ]}
    ]),
    use_container_width=True,
    hide_index=True,
)
