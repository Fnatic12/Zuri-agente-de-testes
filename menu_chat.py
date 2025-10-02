import os
import re
import json
import shutil
import subprocess
import streamlit as st
from unicodedata import normalize
from PIL import Image
import matplotlib.pyplot as plt
import seaborn as sns

# === CONFIGURAÇÕES ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
RUN_SCRIPT = os.path.join(BASE_DIR, "Run", "run_noia.py")
COLETOR_SCRIPT = os.path.join(BASE_DIR, "Scripts", "coletor_adb.py")
PROCESSAR_SCRIPT = os.path.join(BASE_DIR, "Pre_process", "processar_dataset.py")

st.set_page_config(page_title="ZURI - Assistente Gerencial", page_icon="🤖", layout="wide")

# === SESSION STATE ===
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# =========================
# === SUPORTE A BANCADAS ===
# =========================
def _parse_adb_devices(raw_lines):
    """
    Converte a saída do 'adb devices' em lista de seriais válidos.
    Considera apenas linhas que terminam com 'device' (online).
    """
    seriais = []
    for ln in raw_lines[1:]:  # pula a primeira linha "List of devices attached"
        ln = ln.strip()
        # Ex: "R58M12345AB\tdevice"
        m = re.match(r"^(\S+)\s+device$", ln)
        if m:
            seriais.append(m.group(1))
    return seriais

def listar_bancadas():
    """Mapeia dispositivos adb em bancadas numeradas: {'1': serial1, '2': serial2, ...}"""
    try:
        result = subprocess.check_output(["adb", "devices"], text=True).strip().splitlines()
        devices = _parse_adb_devices(result)
        return {str(i + 1): dev for i, dev in enumerate(devices)}
    except Exception:
        return {}

def _formatar_bancadas_str(bancadas: dict) -> str:
    if not bancadas:
        return "📡 Nenhuma bancada conectada."
    linhas = ["📡 **Bancadas disponíveis:**"]
    for k, v in bancadas.items():
        linhas.append(f"{k} → `{v}`")
    return "\n".join(linhas)

# ===================================
# === FUNÇÕES DE SUPORTE (AÇÕES)  ===
# ===================================
def _resolver_teste(nome_ou_token: str):
    """
    Recebe algo como 'audio_1' e tenta localizar em Data/<categoria>/<teste>.
    Retorna (categoria, teste) ou (None, None) se não achar.
    """
    if not nome_ou_token:
        return None, None

    # Primeiro tenta encontrar exatamente um teste com esse nome em alguma categoria
    for cat in listar_categorias():
        if nome_ou_token in listar_testes(cat):
            return cat, nome_ou_token

    # Fallback: se vier "categoria_nome", tenta deduzir
    if "_" in nome_ou_token:
        cat_cand = nome_ou_token.split("_", 1)[0]
        if cat_cand in listar_categorias():
            # Se existir um teste com esse nome dentro da categoria, retorna
            if nome_ou_token in listar_testes(cat_cand):
                return cat_cand, nome_ou_token

    return None, None

def _selecionar_bancada(bancada: str | None, bancadas: dict):
    """
    Seleciona o serial a partir da 'bancada' informada.
    Regras:
      - 'todas' => retorna lista com todos os seriais (paralelo)
      - número válido => retorna lista com um serial
      - None => pega a primeira disponível (se houver)
    Retorna (lista_de_seriais, mensagem_erro_ou_None)
    """
    if not bancadas:
        return [], "❌ Nenhuma bancada conectada."

    if bancada is None or str(bancada).strip() == "":
        # primeira disponível
        return [bancadas[sorted(bancadas.keys(), key=int)[0]]], None

    txt = str(bancada).strip().lower()
    if txt in ("todas", "todas as bancadas", "todas-bancadas", "all"):
        return list(bancadas.values()), None

    if txt.isdigit() and txt in bancadas:
        return [bancadas[txt]], None

    return [], f"❌ Bancada '{bancada}' não encontrada. Use **listar bancadas**."

def _popen_host_python(cmd):
    """Wrapper para subprocess.Popen no host (sem adb shell)."""
    try:
        subprocess.Popen(cmd, cwd=BASE_DIR)
        return True, None
    except Exception as e:
        return False, f"Falha ao executar comando: {e}"

def executar_teste(categoria, nome_teste, bancada: str | None = None):
    """
    Executa teste no host, encaminhando o serial da bancada como parâmetro para o script.
    Obs.: espera que Run/run_noia.py aceite algo como '--serial <SERIAL>'.
    """
    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro

    respostas = []
    for serial in seriais:
        cmd = ["python", RUN_SCRIPT, categoria, nome_teste, "--serial", serial]
        ok, msg = _popen_host_python(cmd)
        if ok:
            respostas.append(f"▶️ Executando **{categoria}/{nome_teste}** na bancada `{serial}`...")
        else:
            respostas.append(f"❌ {msg}")
    return "\n".join(respostas)

def gravar_teste(categoria, nome_teste, bancada: str | None = None):
    """
    Grava teste no host, encaminhando o serial como parâmetro para o coletor.
    Obs.: espera que Scripts/coletor_adb.py aceite '--serial <SERIAL>'.
    """
    bancadas = listar_bancadas()
    seriais, erro = _selecionar_bancada(bancada, bancadas)
    if erro:
        return erro

    respostas = []
    for serial in seriais:
        cmd = ["python", COLETOR_SCRIPT, categoria, nome_teste, "--serial", serial]
        ok, msg = _popen_host_python(cmd)
        if ok:
            respostas.append(f"🎥 Gravando **{categoria}/{nome_teste}** na bancada `{serial}`...")
        else:
            respostas.append(f"❌ {msg}")
    return "\n".join(respostas)

def processar_teste(categoria, nome_teste):
    cmd = ["python", PROCESSAR_SCRIPT, categoria, nome_teste]
    ok, msg = _popen_host_python(cmd)
    if ok:
        return f"⚙️ Processando dataset de **{categoria}/{nome_teste}**..."
    return f"❌ {msg}"

def apagar_teste(categoria, nome_teste):
    caminho = os.path.join(DATA_ROOT, categoria, nome_teste)
    if os.path.exists(caminho):
        shutil.rmtree(caminho)
        return f"🗑️ Teste **{categoria}/{nome_teste}** apagado com sucesso."
    return f"❌ Teste {categoria}/{nome_teste} não encontrado."

def listar_categorias():
    if not os.path.isdir(DATA_ROOT):
        return []
    return [c for c in os.listdir(DATA_ROOT) if os.path.isdir(os.path.join(DATA_ROOT, c))]

def listar_testes(categoria):
    cat_path = os.path.join(DATA_ROOT, categoria)
    if os.path.isdir(cat_path):
        return [t for t in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, t))]
    return []

# ======================================
# === FUNÇÕES AUXILIARES DO DASHBOARD ===
# ======================================
def carregar_logs(data_root=DATA_ROOT):
    logs = []
    if not os.path.isdir(data_root):
        return logs
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
    acertos = sum(1 for a in execucao if "✅" in a.get("status", ""))
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", "")) if total > 0 else 0
    tempo_total = sum(a.get("duracao", 1) for a in execucao)
    cobertura = round((len({a.get("tela", f"id{a.get('id')}") for a in execucao}) / total) * 100, 1) if total > 0 else 0
    precisao = round((acertos / total) * 100, 2) if total > 0 else 0

    return {
        "total_acoes": total,
        "acertos": acertos,
        "falhas": falhas,
        "flakes": flakes,
        "precisao_percentual": precisao,
        "tempo_total": tempo_total,
        "cobertura_telas": cobertura,
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO"
    }

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
    ids = [a.get("id") for a in execucao]
    status = ["green" if "✅" in a.get("status", "") else "red" for a in execucao]

    fig, ax = plt.subplots()
    ax.bar(ids, tempos, color=status)
    ax.set_xlabel("Ação")
    ax.set_ylabel("Duração (s)")
    ax.set_title("Tempo por Ação")
    st.pyplot(fig)

def exibir_acoes(execucao, base_dir):
    st.subheader("📋 Detalhes das Ações")
    for acao in execucao:
        titulo = f"Ação {acao.get('id')} - {str(acao.get('acao','')).upper()} | {acao.get('status','')}"
        with st.expander(titulo):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao.get("frame_esperado",""))
            resultado_path = os.path.join(base_dir, acao.get("screenshot",""))

            if frame_path and os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {acao.get('frame_esperado','')}", use_container_width=True)
            else:
                col1.warning("Frame esperado não encontrado")

            if resultado_path and os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Obtido: {acao.get('screenshot','')}", use_container_width=True)
            else:
                col2.warning("Screenshot não encontrado")

            if "similaridade" in acao:
                st.write(f"🎯 Similaridade: **{acao['similaridade']:.2f}**")
            st.write(f"⏱️ Duração: **{acao.get('duracao', 0)}s**")
            if "coordenadas" in acao:
                st.json(acao.get("coordenadas", {}))
            if "log" in acao:
                st.code(acao["log"], language="bash")

def exibir_mapa_calor(execucao):
    st.subheader("🔥 Mapa de Calor dos Toques")
    xs = [a["coordenadas"]["x"] for a in execucao if "coordenadas" in a and "x" in a["coordenadas"]]
    ys = [a["coordenadas"]["y"] for a in execucao if "coordenadas" in a and "y" in a["coordenadas"]]

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
        frame_path = os.path.join(base_dir, ultima.get("frame_esperado",""))

        if frame_path and os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (Última Ação)", use_container_width=True)
        else:
            col1.error("Frame esperado não encontrado")

        if os.path.exists(resultado_final_path):
            col2.image(Image.open(resultado_final_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png não encontrado")

        if "similaridade" in ultima:
            st.write(f"🎯 Similaridade Final: **{ultima['similaridade']:.2f}**")
        if "✅" in ultima.get("status",""):
            st.success("✅ Tela final validada")
        else:
            st.error("❌ Tela final divergente")
    else:
        st.warning("Nenhuma ação registrada")

def exibir_regressoes(execucao):
    st.subheader("📉 Análise de Regressões")
    falhas = [a for a in execucao if "❌" in a.get("status","")]
    if falhas:
        st.write("Top falhas nesta execução:")
        for f in falhas:
            sim = f.get("similaridade")
            sim_str = f"{sim:.2f}" if isinstance(sim, (int, float)) else "N/A"
            st.write(f"- Ação {f.get('id')} ({f.get('acao','')}): Similaridade {sim_str}")
    else:
        st.success("Nenhuma falha registrada")

# ===========================
# === PARSER DE COMANDOS  ===
# ===========================
# Palavras-chave com variações comuns (sem acento e lower)
KW_EXECUTAR = ["executar", "execute", "rodar", "rode", "run"]
KW_GRAVAR   = ["gravar", "grave", "coletar", "colete", "capturar", "record"]
KW_PROCESS  = ["processar", "processa", "pre-processar", "preprocessar", "pré-processar", "pre"]
KW_APAGAR   = ["apagar", "apague", "deletar", "delete", "remover", "remova", "excluir", "exclua"]
KW_LISTAR   = ["listar", "liste", "mostrar", "mostre", "exibir", "exiba", "lista"]
KW_BANCADAS = ["bancada", "bancadas", "devices", "dispositivos"]
KW_AJUDA    = ["ajuda", "help", "comandos"]

def _norm(s: str) -> str:
    """Lower + remove acentos para matching robusto."""
    s = s.strip().lower()
    return normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")

def _has_any(texto_norm: str, termos: list[str]) -> bool:
    texto_norm = _norm(texto_norm)
    termos_norm = [_norm(t) for t in termos]
    return any(t in texto_norm for t in termos_norm)

def _extrair_bancada(texto: str) -> str | None:
    """
    Extrai a bancada do comando.
    Suporta: "na bancada 2", "bancada=2", "bancada2", "todas as bancadas".
    Retorna "2", "todas" ou None.
    """
    t = _norm(texto)

    # todas as bancadas
    if re.search(r"\btodas(\s+as\s+)?bancadas\b", t) or re.search(r"\ball\b", t):
        return "todas"

    m = re.search(r"bancada\s*=\s*(\d+)", t)
    if m:
        return m.group(1)

    m = re.search(r"\bbancada\s*(\d+)\b", t)
    if m:
        return m.group(1)

    return None

def _extrair_token_teste(texto: str) -> str | None:
    """
    Busca algo no padrão 'palavra_numero' ou 'palavra-palavra' como token de teste.
    Ex.: audio_1, bluetooth_3, tela-home_2 etc.
    """
    t = _norm(texto)
    m = re.search(r"\b([a-z0-9]+[_-][a-z0-9]+)\b", t)
    return m.group(1) if m else None

def _extrair_categoria(texto: str) -> str | None:
    """
    Se o usuário pedir 'testes de <categoria>' ou mencionar explicitamente uma categoria existente.
    """
    t = _norm(texto)
    # padrão 'de <categoria>'
    m = re.search(r"\bde\s+([a-z0-9_-]+)\b", t)
    if m and m.group(1) in listar_categorias():
        return m.group(1)
    # ou se o nome da categoria aparecer diretamente no texto
    for cat in listar_categorias():
        if _norm(cat) in t:
            return cat
    return None

def interpretar_comando(comando: str):
    texto = comando.strip()
    texto_norm = _norm(texto)

    # 1) AJUDA
    if _has_any(texto_norm, KW_AJUDA):
        return (
            "🧭 **Comandos suportados**\n"
            "- **executar/rodar** `<teste>` [na bancada N|todas]\n"
            "- **gravar/coletar** `<teste>` [na bancada N|todas]\n"
            "- **processar** `<teste>`\n"
            "- **apagar/deletar/remover** `<teste>`\n"
            "- **listar/mostrar** categorias | testes [de <categoria>]\n"
            "- **listar bancadas**\n"
            "Ex.: `execute o teste audio_1 na bancada 2`"
        )

    # 2) LISTAR BANCADAS
    if _has_any(texto_norm, ["listar bancadas", "mostrar bancadas", "listar devices", "mostrar devices"]) \
       or (_has_any(texto_norm, KW_LISTAR) and any(k in texto_norm for k in ["bancada", "bancadas", "devices", "dispositivos"])):
        return _formatar_bancadas_str(listar_bancadas())

    # 3) EXECUTAR (rodar testes)
    if _has_any(texto_norm, KW_EXECUTAR):
        # Caso especial: "todos os testes da categoria X"
        if re.search(r"todos\s+os\s+testes\s+da\s+categoria", texto_norm):
            cat = _extrair_categoria(texto)
            if not cat:
                return "⚠️ Especifique a categoria (ex: rodar todos os testes da categoria audio)."

            testes = listar_testes(cat)
            if not testes:
                return f"📂 A categoria **{cat}** não possui testes."

            bancada = _extrair_bancada(texto)
            respostas = [f"▶️ Rodando todos os testes da categoria **{cat}** na bancada {bancada or '(padrão)'}..."]

            for t in testes:
                respostas.append(executar_teste(cat, t, bancada))

            return "\n".join(respostas)

    # 4) GRAVAR / COLETAR (NÃO depende de resolver)
    if _has_any(texto_norm, KW_GRAVAR):
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
            else:
                return "⚠️ Use o formato categoria_nome (ex: audio_3)."

            bancada = _extrair_bancada(texto)
            return gravar_teste(cat, token, bancada)

        return "⚠️ Especifique o teste (ex: `gravar audio_1 na bancada 1`)."

    # 5) PROCESSAR (gera dataset de algo que já foi gravado)
    if _has_any(texto_norm, KW_PROCESS):
        token = _extrair_token_teste(texto)
        if token:
            if "_" in token:
                cat, nome = token.split("_", 1)
                return processar_teste(cat, token)
            return "⚠️ Use o formato categoria_nome (ex: audio_3)."
        return "⚠️ Especifique o teste (ex: `processar audio_1`)."

    # 6) APAGAR / DELETAR / REMOVER (precisa existir em Data/*/*)
    if _has_any(texto_norm, KW_APAGAR):
        token = _extrair_token_teste(texto)
        if token:
            cat, teste = _resolver_teste(token)
            if cat and teste:
                return apagar_teste(cat, teste)
            return f"❌ Não encontrei o teste **{token}** em `Data/*/`."
        return "⚠️ Especifique o teste (ex: `apagar audio_1`)."

    # 7) LISTAR / MOSTRAR
    if _has_any(texto_norm, KW_LISTAR):
        cat = _extrair_categoria(texto)
        if cat:
            testes = listar_testes(cat)
            if testes:
                return f"📝 Testes em **{cat}**:\n- " + "\n- ".join(testes)
            return f"📂 A categoria **{cat}** não possui testes."
        cats = listar_categorias()
        if cats:
            return "📂 Categorias disponíveis:\n- " + "\n- ".join(cats)
        return "📂 Nenhuma categoria encontrada em `Data/`."

    return "❌ Não entendi o comando. Digite **ajuda** para ver exemplos."

# ==================
# === UI LATERAL  ===
# ==================
st.sidebar.title("☰ ZURI - Menu")
pagina = st.sidebar.radio("Navegação", ["💬 Chat", "📊 Dashboard"])

# Side info: bancadas
with st.sidebar.expander("📡 Bancadas (ADB)"):
    st.markdown(_formatar_bancadas_str(listar_bancadas()))
    if st.button("🔄 Atualizar lista de bancadas"):
        st.rerun()

# ============
# === CHAT ===
# ============
if pagina == "💬 Chat":
    st.title("💬 ZURI - Agente de Testes")
    st.markdown("Digite **ajuda** para ver exemplos de comandos.")
    st.markdown("---")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

    user_input = st.chat_input("Digite seu comando...")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        resposta = interpretar_comando(user_input)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta})
        st.rerun()

# =================
# === DASHBOARD ===
# =================
elif pagina == "📊 Dashboard":
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

    metricas = calcular_metricas(execucao)
    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_acoes(execucao, base_dir)
    exibir_mapa_calor(execucao)
    exibir_validacao_final(execucao, base_dir)
    exibir_regressoes(execucao)

    if st.button("📤 Exportar Relatório JSON"):
        st.download_button("Baixar JSON", data=json.dumps(execucao, indent=2), file_name="relatorio_execucao.json")
