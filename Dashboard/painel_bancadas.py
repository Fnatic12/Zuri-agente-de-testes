import os
import json
import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import tempfile
import pandas as pd
import statistics
from app.shared.ui_theme import apply_dark_background

# ============ CONFIG ============ #
st.set_page_config(page_title="Painel de Bancadas VWAIT", page_icon="", layout="wide")
apply_dark_background(hide_header=True)

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data")

# ============ ESTILO GLOBAL ============ #
st.markdown("""
<style>
body { background-color: #0B0C10; color: #E0E0E0; font-family: 'Inter', sans-serif; }

.main-title {
    font-size: 2.6rem;
    text-align: center;
    background: linear-gradient(90deg, #12c2e9, #c471ed, #f64f59);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin-bottom: 0.3em;
}
.subtitle {
    text-align: center;
    color: #AAAAAA;
    font-size: 1rem;
    margin-bottom: 2em;
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
    transform: translateY(-4px);
    box-shadow: 0 10px 24px rgba(0,0,0,0.55);
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
st.markdown("<h1 class='main-title'>Painel de ExecuÃ§Ã£o VWAIT</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Monitoramento em tempo real das bancadas Android conectadas</p>", unsafe_allow_html=True)

st_autorefresh(interval=3000, limit=None, key="refresh_status")

# ============ FUNÃ‡Ã•ES AUXILIARES ============ #
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
    """Coleta status_<serial>.json em Data/<categoria>/<teste>/."""
    if not os.path.isdir(DATA_ROOT):
        return {}
    latest = {}
    for root, _, files in os.walk(DATA_ROOT):
        for name in files:
            if not (name.startswith("status_") and name.endswith(".json")):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            serial = data.get("serial") or name[len("status_"):-5]
            ts = data.get("atualizado_em") or data.get("inicio") or os.path.getmtime(path)
            prev = latest.get(serial)
            if prev is None or str(ts) > str(prev.get("_ts", "")):
                data["_ts"] = ts
                latest[serial] = data
    for v in latest.values():
        if "status" in v and isinstance(v["status"], str):
            v["status"] = v["status"].lower()
    return latest

def extrair_kpis(serial, info):
    """Busca execucao_log.json do teste associado e extrai metricas basicas."""
    teste = str(info.get("teste", ""))
    if "/" not in teste:
        return None
    cat, nome = teste.split("/", 1)
    logs_dir = os.path.join(DATA_ROOT, cat, nome)
    exec_log = os.path.join(logs_dir, "execucao_log.json")
    if not os.path.exists(exec_log):
        return None

    try:
        with open(exec_log, "r", encoding="utf-8") as f:
            dados = json.load(f)
        total = len(dados)
        acertos = sum(1 for a in dados if "OK" in a.get("status", "").upper())
        falhas = total - acertos
        similaridades = [a.get("similaridade", 0) for a in dados if "similaridade" in a]
        media_sim = sum(similaridades) / len(similaridades) if similaridades else 0
        precisao = round((acertos / total) * 100, 1) if total else 0

        return {
            "total": total,
            "acertos": acertos,
            "falhas": falhas,
            "precisao": precisao,
            "similaridade": round(media_sim, 2)
        }
    except Exception:
        return None

# ============ MAPA DE NOMES FIXOS ============ #
MAPEAMENTO_BANCADAS = {
    "2801761952320038": "Bancada 1",
    "2801780E52320038": "Bancada 2",
    "2801839552320038": "Bancada 3"
}

# ============ LEITURA DO STATUS ============ #
bancadas = carregar_status_higienizado()
if not bancadas:
    st.info("ðŸ”Œ Nenhuma bancada ativa no momento. Aguardando execuÃ§Ã£o...")
    st.stop()

# ============ RESUMO GERAL ============ #
st.markdown("---")
st.markdown("## ðŸ“Š Resumo das Bancadas")

executando = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "executando"]
finalizados = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "finalizado"]
ociosas = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "ociosa"]
erros = [b for b, d in bancadas.items() if str(d.get("status","")).lower() == "erro"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("âš™ï¸ Em ExecuÃ§Ã£o", len(executando))
col2.metric("âœ… Finalizados", len(finalizados))
col3.metric("ðŸ’¤ Ociosas", len(ociosas))
col4.metric("âŒ Com Erros", len(erros))

st.caption("Atualizacao automatica a cada 3 segundos.")

# ============ TABELA DETALHADA ============ #
st.markdown("---")
st.markdown("## ðŸ§  Detalhamento TÃ©cnico das Bancadas")

dados_tabela = []
for bancada, info in bancadas.items():
    total = int(info.get("acoes_totais", 0))
    execs = int(info.get("acoes_executadas", 0))
    progresso = float(info.get("progresso", 0))
    tipo_exec = "Teste Automatizado"
    if "coleta" in str(info.get("teste", "")).lower():
        tipo_exec = "Coleta de Dados"
    elif "valida" in str(info.get("teste", "")).lower():
        tipo_exec = "ValidaÃ§Ã£o"
    elif "treino" in str(info.get("teste", "")).lower():
        tipo_exec = "Treinamento IA"

    dados_tabela.append({
        "ðŸ’» Bancada": MAPEAMENTO_BANCADAS.get(bancada, bancada),
        "ðŸ§© Teste": info.get("teste", "-"),
        "âš™ï¸ Status": info.get("status", "-").capitalize(),
        "â±ï¸ Tempo Decorrido": tempo_formatado(float(info.get("tempo_decorrido_s", 0))),
        "ðŸ ConclusÃ£o (%)": f"{progresso:.1f}",
        "ðŸ‘† Taps Executados": f"{execs}/{total}" if total > 0 else "-",
        "ðŸ§  Tipo ExecuÃ§Ã£o": tipo_exec
    })

df = pd.DataFrame(dados_tabela)

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
    .map(highlight_status, subset=["âš™ï¸ Status"])
    .set_table_styles([
        {'selector': 'thead th', 'props': [
            ('background-color', '#242424'),
            ('color', '#f0f0f0'),
            ('font-size', '14px'),
            ('font-weight', 'bold'),
            ('border-bottom', '2px solid #444')
        ]},
        {'selector': 'tbody td', 'props': [
            ('background-color', '#1c1c1c'),
            ('color', '#e0e0e0'),
            ('border-color', '#333'),
            ('font-size', '14px'),
            ('text-align', 'center')
        ]}
    ]),
    use_container_width=True,
    hide_index=True,
)



