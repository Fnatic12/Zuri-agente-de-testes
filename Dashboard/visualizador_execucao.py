import os
import json
from datetime import datetime, timedelta
import subprocess

import cv2
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from PIL import Image

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None


def titulo_painel(titulo: str, subtitulo: str = ""):
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"]  {{
            background: #0B0C10 !important;
            color: #E0E0E0 !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
        }}
        [data-testid="stHeader"] {{
            display: none !important;
            height: 0 !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        .main .block-container, .block-container {{
            background: transparent !important;
        }}
        .block-container {{
            padding-top: 1.15rem;
            max-width: 1180px;
        }}
        .main-title {{
            font-size: 2.05rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #8b5cf6 48%, #d946ef 76%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.15em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #9ca3af;
            font-size: 0.95rem;
            margin-bottom: 1.1em;
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{
            color: #e5e7eb;
        }}
        [data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label {{
            color: #a8b3c5 !important;
        }}
        [data-baseweb="select"] > div {{
            background: rgba(20, 24, 32, 0.9) !important;
            border-color: #334155 !important;
            color: #e5e7eb !important;
        }}
        input, textarea {{
            background: rgba(20, 24, 32, 0.9) !important;
            color: #e5e7eb !important;
            border-color: #334155 !important;
        }}
        .clean-card {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.55);
            border-radius: 14px;
            padding: 0.75rem 0.9rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 6px 18px rgba(2, 6, 23, 0.45);
        }}
        .card-kpi-label {{
            color: #94a3b8;
            font-size: 0.78rem;
            margin-bottom: 0.15rem;
        }}
        .card-kpi-value {{
            color: #f8fafc;
            font-weight: 700;
            font-size: 1.28rem;
            line-height: 1.1;
        }}
        div[data-testid="stMetric"] {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.45);
            border-radius: 12px;
            padding: 0.35rem 0.65rem;
        }}
        div[data-testid="stMetricLabel"] p {{
            color: #94a3b8 !important;
        }}
        div[data-testid="stMetricValue"] {{
            color: #f8fafc !important;
        }}
        .stExpander {{
            border: 1px solid rgba(71, 85, 105, 0.35) !important;
            border-radius: 10px !important;
            background: rgba(15, 23, 42, 0.5) !important;
        }}
        [data-testid="stExpander"] details {{
            background: rgba(15, 23, 42, 0.5) !important;
            border: 1px solid rgba(71, 85, 105, 0.35) !important;
            border-radius: 10px !important;
        }}
        [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {{
            color: #dbe4f0 !important;
        }}
        [data-testid="stMarkdownContainer"] code {{
            color: #bfdbfe !important;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


# === CONFIGURACOES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")
BANCADA_LABELS = {
    "2801761952320038": "Bancada 1",
    "2801780E52320038": "Bancada 2",
    "2801780c52320038": "Bancada 2",
    "2801839552320038": "Bancada 3",
}
BANCADA_LABELS_NORM = {str(k).lower(): v for k, v in BANCADA_LABELS.items()}


# === FUNCOES AUXILIARES ===
def carregar_logs(data_root=DATA_ROOT):
    """Lista execucoes disponiveis"""
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


def _tempo_formatado(segundos: float) -> str:
    segundos = max(0, int(segundos))
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m {segundos % 60}s"
    return f"{segundos // 3600}h {(segundos % 3600) // 60}m"


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _candidate_adb_commands() -> list[str]:
    candidates = []
    env_cmd = os.environ.get("ADB_PATH", "").strip()
    if env_cmd:
        candidates.append(env_cmd)
    if os.name == "nt":
        candidates.append(r"C:\Users\Automation01\platform-tools\adb.exe")
    candidates.append("adb")
    seen = set()
    ordered = []
    for cmd in candidates:
        norm = cmd.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(cmd)
    return ordered


def _listar_dispositivos_adb() -> set[str]:
    for adb_cmd in _candidate_adb_commands():
        try:
            out = subprocess.run(
                [adb_cmd, "devices"],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except Exception:
            continue

        if out.returncode != 0:
            continue

        seriais = set()
        for line in out.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                seriais.add(parts[0])
        return seriais
    return set()


def _extract_status_payload(serial: str, raw: dict) -> dict:
    payload = {}
    nested = raw.get(serial)
    if isinstance(nested, dict):
        payload.update(nested)
    for key in (
        "serial",
        "status",
        "teste",
        "acoes_totais",
        "acoes_executadas",
        "progresso",
        "tempo_decorrido_s",
        "inicio",
        "fim",
        "atualizado_em",
        "ultima_acao",
    ):
        if key in raw and raw.get(key) is not None:
            payload[key] = raw.get(key)
    payload["serial"] = serial
    return payload


def _carregar_status_bancadas(data_root=DATA_ROOT):
    latest = {}
    if not os.path.isdir(data_root):
        return latest

    for root, _, files in os.walk(data_root):
        for name in files:
            if not (name.startswith("status_") and name.endswith(".json")):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    continue
            except Exception:
                continue

            serial = str(raw.get("serial") or name[len("status_") : -5]).strip()
            if not serial:
                continue

            payload = _extract_status_payload(serial, raw)
            ts = (
                _parse_datetime(payload.get("atualizado_em"))
                or _parse_datetime(payload.get("inicio"))
                or _parse_datetime(payload.get("fim"))
                or datetime.fromtimestamp(os.path.getmtime(path))
            )

            prev = latest.get(serial)
            if prev is None or ts > prev.get("_timestamp_dt", datetime.min):
                payload["_timestamp_dt"] = ts
                payload["_status_path"] = path
                latest[serial] = payload
    return latest


def _status_human(status: str) -> str:
    normalized = str(status or "").strip().lower()
    mapping = {
        "executando": "Executando",
        "finalizado": "Finalizado",
        "erro": "Erro",
        "ociosa": "Ociosa",
    }
    return mapping.get(normalized, normalized.capitalize() if normalized else "Desconhecido")


def _status_chip_html(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "executando":
        color = "#f59e0b"
    elif normalized == "finalizado":
        color = "#22c55e"
    elif normalized == "erro":
        color = "#ef4444"
    else:
        color = "#94a3b8"
    return (
        "<span style='display:inline-block;padding:0.22rem 0.6rem;border-radius:999px;"
        f"font-size:0.76rem;font-weight:700;background:{color}20;color:{color};border:1px solid {color}66;'>"
        f"{_status_human(status)}</span>"
    )


def _estimativa_restante(info: dict) -> float | None:
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    tempo_decorrido = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
    if total <= 0 or executadas <= 0 or executadas >= total:
        return None
    por_acao = tempo_decorrido / float(executadas)
    return max(0.0, (total - executadas) * por_acao)


def _status_age_seconds(info: dict, now: datetime) -> float:
    ts = info.get("_timestamp_dt")
    if not isinstance(ts, datetime):
        return float("inf")
    return max(0.0, (now - ts).total_seconds())


def _is_live_status(info: dict, now: datetime) -> bool:
    status = str(info.get("status", "")).strip().lower()
    teste = str(info.get("teste", "")).strip()
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    age_s = _status_age_seconds(info, now)

    if status == "executando":
        return bool(teste) and total > 0 and executadas <= total and age_s <= 60.0
    if status == "finalizado":
        return bool(teste) and total > 0 and age_s <= 45.0
    if status == "erro":
        return bool(teste) and age_s <= 90.0
    return False


def _filtrar_bancadas_reais(status_map: dict, conectadas: set[str]) -> dict:
    now = datetime.now()
    conectadas_norm = {str(serial).lower() for serial in conectadas}
    filtered = {}
    for serial, info in status_map.items():
        if str(serial).lower() not in conectadas_norm:
            continue
        if not _is_live_status(info, now):
            continue
        filtered[serial] = info
    return filtered


def _nome_bancada(serial: str) -> str:
    return BANCADA_LABELS.get(serial) or BANCADA_LABELS_NORM.get(str(serial).lower()) or serial


def _resolver_diretorio_teste(info: dict) -> str | None:
    status_path = str(info.get("_status_path") or "").strip()
    if status_path:
        candidate = os.path.dirname(status_path)
        if os.path.isdir(candidate):
            return candidate

    teste = str(info.get("teste") or "").strip().replace("\\", "/")
    if "/" in teste:
        categoria, nome = teste.split("/", 1)
        candidate = os.path.join(DATA_ROOT, categoria, nome)
        if os.path.isdir(candidate):
            return candidate
    return None


def _ultima_screenshot_bancada(info: dict) -> str | None:
    test_dir = _resolver_diretorio_teste(info)
    if not test_dir:
        return None

    candidates: list[str] = []
    for folder in ("resultados", "frames"):
        img_dir = os.path.join(test_dir, folder)
        if not os.path.isdir(img_dir):
            continue
        for name in os.listdir(img_dir):
            ext = os.path.splitext(name)[1].lower()
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                candidates.append(os.path.join(img_dir, name))

    resultado_final = os.path.join(test_dir, "resultado_final.png")
    if os.path.exists(resultado_final):
        candidates.append(resultado_final)

    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def exibir_bancadas_tempo_real():
    st.subheader("Bancadas em tempo real")
    st.caption("Somente execucoes reais: bancada conectada + status recente.")

    if st_autorefresh is not None:
        st_autorefresh(interval=3000, limit=None, key="dash_realtime_refresh")

    conectadas = _listar_dispositivos_adb()
    status_raw = _carregar_status_bancadas(DATA_ROOT)
    bancadas = _filtrar_bancadas_reais(status_raw, conectadas)

    executando_rows = {s: v for s, v in bancadas.items() if str(v.get("status", "")).lower() == "executando"}
    finalizado_rows = {s: v for s, v in bancadas.items() if str(v.get("status", "")).lower() == "finalizado"}
    erro_rows = {s: v for s, v in bancadas.items() if str(v.get("status", "")).lower() == "erro"}

    restantes = [
        _estimativa_restante(v)
        for v in executando_rows.values()
        if str(v.get("status", "")).lower() == "executando"
    ]
    restantes = [value for value in restantes if value is not None]
    eta_global_s = max(restantes) if restantes else None
    final_previsto = (
        (datetime.now() + timedelta(seconds=float(eta_global_s))).strftime("%H:%M:%S")
        if eta_global_s is not None
        else "-"
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Bancadas conectadas", len(conectadas))
    c2.metric("Executando agora", len(executando_rows))
    c3.metric("Finalizadas (45s)", len(finalizado_rows))
    c4.metric("Erro (90s)", len(erro_rows))
    c5.metric("ETA global", _tempo_formatado(eta_global_s) if eta_global_s is not None else "-")
    st.caption(f"Previsao de termino global: {final_previsto}")

    if not conectadas:
        st.warning("Nenhuma bancada ADB conectada no momento.")
        return
    if not executando_rows:
        st.info("Nenhum teste em execucao neste momento.")
        return

    layout_mode = st.radio(
        "Layout dos cards",
        options=["2x2", "2x3"],
        horizontal=True,
        index=0,
        key="realtime_layout_mode",
    )
    cols_per_row = 2 if layout_mode == "2x2" else 3

    rows = sorted(
        executando_rows.items(),
        key=lambda item: (
            0 if str(item[1].get("status", "")).lower() == "executando" else 1,
            item[0],
        ),
    )

    for start in range(0, len(rows), cols_per_row):
        chunk = rows[start : start + cols_per_row]
        cols = st.columns(cols_per_row)
        for i, col in enumerate(cols):
            if i >= len(chunk):
                continue
            serial, info = chunk[i]
            nome = _nome_bancada(serial)
            teste = str(info.get("teste", "-"))
            status = str(info.get("status", ""))
            progresso = float(info.get("progresso", 0.0) or 0.0)
            total = int(info.get("acoes_totais", 0) or 0)
            executadas = int(info.get("acoes_executadas", 0) or 0)
            tempo = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
            restante = _estimativa_restante(info)
            atualizado = str(info.get("atualizado_em") or info.get("inicio") or "-")
            thumb = _ultima_screenshot_bancada(info)

            with col:
                st.markdown(
                    (
                        "<div class='clean-card'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:0.5rem;'>"
                        f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{nome}</div>"
                        f"{_status_chip_html(status)}"
                        "</div>"
                        f"<div style='margin-top:0.35rem;color:#a8b3c5;font-size:0.84rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                        f"Teste: {teste}"
                        "</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, max(0.0, progresso / 100.0)), text=f"{progresso:.1f}%")
                d1, d2 = st.columns(2)
                d1.metric("Acoes", f"{executadas}/{total}" if total > 0 else str(executadas))
                d2.metric("ETA", _tempo_formatado(restante) if restante is not None else "-")
                d3, d4 = st.columns(2)
                d3.metric("Tempo", _tempo_formatado(tempo))
                d4.metric("Atualizado", atualizado.split("T")[1][:8] if "T" in atualizado else atualizado)

                if thumb and os.path.exists(thumb):
                    st.image(thumb, caption=f"Ultima tela: {os.path.basename(thumb)}", use_container_width=True)
                else:
                    st.caption("Sem screenshot recente para esta bancada.")


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
            "resultado_final": "SEM DADOS",
        }

    acertos = sum(1 for a in execucao if "OK" in a.get("status", "").upper())
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", ""))
    tempo_total = sum(a.get("duracao", 1) for a in execucao)

    # Tolerante a ausencia de 'id' e/ou 'tela'
    telas_unicas = {(a.get("tela") or f"id{a.get('id', idx)}") for idx, a in enumerate(execucao)}
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
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO",
    }


def _kpi_card(label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='clean-card'>"
            f"<div class='card-kpi-label'>{label}</div>"
            f"<div class='card-kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _style_axes_clean(ax):
    ax.set_facecolor("#0f172a")
    ax.grid(axis="y", color="#1f2937", linewidth=0.9)
    ax.tick_params(colors="#cbd5e1", labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#334155")
        spine.set_linewidth(0.8)


# === DASHBOARD ===
def exibir_metricas(metricas):
    st.subheader("Resumo")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _kpi_card("Total de acoes", str(metricas["total_acoes"]))
    with col2:
        _kpi_card("Acertos", str(metricas["acertos"]))
    with col3:
        _kpi_card("Falhas", str(metricas["falhas"]))
    with col4:
        _kpi_card("Flakes", str(metricas["flakes"]))

    col5, col6, col7 = st.columns(3)
    with col5:
        _kpi_card("Precisao", f"{metricas['precisao_percentual']}%")
    with col6:
        _kpi_card("Cobertura de telas", f"{metricas['cobertura_telas']}%")
    with col7:
        _kpi_card("Tempo total", f"{metricas['tempo_total']}s")

    if metricas["resultado_final"] == "APROVADO":
        st.success("Resultado final: APROVADO")
    else:
        st.error("Resultado final: REPROVADO")

    st.markdown("##### Distribuicao de resultado")
    labels = ["Acertos", "Falhas"]
    sizes = [max(0, metricas["acertos"]), max(0, metricas["falhas"])]
    if sum(sizes) == 0:
        sizes = [1, 0]
    colors = ["#22c55e", "#ef4444"]

    fig, ax = plt.subplots(figsize=(3.35, 2.05), dpi=120)
    ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
        startangle=110,
        wedgeprops=dict(width=0.42, edgecolor="#0f172a", linewidth=1.2),
        textprops=dict(color="#e2e8f0", fontsize=8.2),
    )
    ax.text(0, 0, str(metricas["total_acoes"]), ha="center", va="center", fontsize=11, color="#f8fafc", weight="bold")
    ax.set(aspect="equal")
    fig.patch.set_facecolor("#070b12")
    fig.tight_layout(pad=0.5)
    st.pyplot(fig)
    plt.close(fig)


def exibir_timeline(execucao):
    st.subheader("Tempo por acao")
    if not execucao:
        st.info("Sem acoes para montar timeline.")
        return

    tempos = [a.get("duracao", 1) for a in execucao]
    ids = [a.get("id", idx + 1) for idx, a in enumerate(execucao)]
    status_colors = ["#16a34a" if "OK" in str(a.get("status", "")).upper() else "#dc2626" for a in execucao]

    fig, ax = plt.subplots(figsize=(5.6, 2.25), dpi=125)
    ax.bar(ids, tempos, color=status_colors, edgecolor="#0f172a", linewidth=0.65)
    _style_axes_clean(ax)
    ax.set_xlabel("Acao", color="#cbd5e1", fontsize=8.5)
    ax.set_ylabel("Duracao (s)", color="#cbd5e1", fontsize=8.5)
    ax.set_title("Timeline", color="#e5e7eb", fontsize=9.8, pad=6)
    fig.patch.set_facecolor("#070b12")
    fig.tight_layout(pad=0.6)
    st.pyplot(fig)
    plt.close(fig)


def exibir_acoes(execucao, base_dir):
    st.subheader("Detalhes das acoes")
    for acao in execucao:
        with st.expander(f"Acao {acao['id']} - {acao['acao'].upper()} | {acao['status']}"):
            col1, col2 = st.columns(2)

            frame_path = os.path.join(base_dir, acao["frame_esperado"])
            resultado_path = os.path.join(base_dir, acao["screenshot"])

            if os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {acao['frame_esperado']}", use_container_width=True)
            else:
                col1.warning("Frame esperado nao encontrado")

            if os.path.exists(resultado_path):
                col2.image(Image.open(resultado_path), caption=f"Obtido: {acao['screenshot']}", use_container_width=True)
            else:
                col2.warning("Screenshot nao encontrado")

            st.write(f"Similaridade: **{acao['similaridade']:.2f}**")
            st.write(f"Duracao: **{acao.get('duracao', 0)}s**")
            st.json(acao.get("coordenadas", {}))
            if "log" in acao:
                st.code(acao["log"], language="bash")


def _simples_similarity(img_a: Image.Image, img_b: Image.Image) -> float:
    """Similaridade simples baseada em diferenca media normalizada (0..1)."""
    a = img_a.convert("L")
    b = img_b.convert("L").resize(a.size)
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    diff = np.abs(arr_a - arr_b)
    score = 1.0 - (np.mean(diff) / 255.0)
    return float(max(0.0, min(1.0, score)))


def _apply_ignore_mask(mask: np.ndarray, ignore_regions):
    if not ignore_regions:
        return mask
    h, w = mask.shape[:2]
    for (x, y, bw, bh) in ignore_regions:
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(w, int(x + bw))
        y2 = min(h, int(y + bh))
        mask[y1:y2, x1:x2] = 0
    return mask


def _compute_diff_mask_cv(img_a: np.ndarray, img_b: np.ndarray, diff_threshold=25):
    lab_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2LAB)
    lab_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2LAB)
    diff = cv2.absdiff(lab_a, lab_b)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(diff_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if diff_threshold:
        _, hard = cv2.threshold(diff_gray, diff_threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_or(otsu, hard)
    else:
        mask = otsu
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def _find_bboxes(mask: np.ndarray, min_area=200, max_area=200000):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area or area > max_area:
            continue
        bboxes.append((x, y, w, h, float(area)))
    return bboxes


def _is_toggle_candidate(bbox, img_shape, aspect_min=1.7, aspect_max=5.5):
    x, y, w, h, _ = bbox
    if h <= 0:
        return False
    img_h, img_w = img_shape[:2]
    ratio = w / float(h)
    # Filtro geometrico: evita classificar texto pequeno/linhas como toggle.
    if not (aspect_min <= ratio <= aspect_max):
        return False
    if w < 28 or h < 12:
        return False
    if w > int(img_w * 0.35) or h > int(img_h * 0.12):
        return False
    return True


def _toggle_state_by_color(img_roi: np.ndarray):
    hsv = cv2.cvtColor(img_roi, cv2.COLOR_BGR2HSV)
    lower = np.array((90, 60, 60), dtype=np.uint8)
    upper = np.array((130, 255, 255), dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    if ratio >= 0.08:
        return "ON", min(1.0, ratio / 0.2)
    return "OFF", min(1.0, (0.08 - ratio) / 0.08)


def _toggle_state_by_knob(img_roi: np.ndarray):
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0
    roi_area = float(img_roi.shape[0] * img_roi.shape[1])
    best = None
    best_conf = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < 20:
            continue
        per = cv2.arcLength(c, True)
        if per <= 0:
            continue
        circularity = float((4.0 * np.pi * area) / (per * per))
        x, y, w, h = cv2.boundingRect(c)
        if h <= 0:
            continue
        wh_ratio = w / float(h)
        area_ratio = area / roi_area
        # Knob tipico: quase circular, area moderada dentro da ROI.
        if circularity < 0.55 or wh_ratio < 0.65 or wh_ratio > 1.45:
            continue
        if area_ratio < 0.02 or area_ratio > 0.40:
            continue
        conf = min(1.0, (circularity - 0.55) / 0.35 + 0.25)
        if conf > best_conf:
            cx = x + w / 2.0
            best = cx
            best_conf = conf
    if best is None:
        return None, 0.0
    state = "ON" if best > (img_roi.shape[1] / 2.0) else "OFF"
    return state, best_conf


def _compare_images_cv(img_a: np.ndarray, img_b: np.ndarray, ignore_regions=None):
    mask = _compute_diff_mask_cv(img_a, img_b, diff_threshold=25)
    mask = _apply_ignore_mask(mask, ignore_regions or [])
    bboxes = _find_bboxes(mask)

    diffs = []
    toggles = []
    overlay = img_a.copy()
    for bbox in bboxes:
        x, y, w, h, score = bbox
        roi_a = img_a[y : y + h, x : x + w]
        roi_b = img_b[y : y + h, x : x + w]
        dtype = "generic"
        if _is_toggle_candidate(bbox, img_a.shape):
            state_a_c, conf_a_c = _toggle_state_by_color(roi_a)
            state_b_c, conf_b_c = _toggle_state_by_color(roi_b)
            state_a_k, conf_a_k = _toggle_state_by_knob(roi_a)
            state_b_k, conf_b_k = _toggle_state_by_knob(roi_b)
            # So aceita toggle quando o knob e detectado nas duas imagens.
            if state_a_k is not None and state_b_k is not None:
                state_a = state_a_k
                state_b = state_b_k
                conf = (conf_a_k + conf_b_k + conf_a_c + conf_b_c) / 4.0
            else:
                state_a = state_a_c
                state_b = state_b_c
                conf = (conf_a_c + conf_b_c) / 2.0
            if state_a_k is not None and state_b_k is not None and state_a != state_b:
                dtype = "toggle"
                toggles.append(
                    {
                        "bbox": (x, y, w, h),
                        "stateA": state_a,
                        "stateB": state_b,
                        "confidence": round(conf, 3),
                    }
                )

        diffs.append({"bbox": (x, y, w, h), "score": score, "type": dtype})
        color = (0, 255, 0) if dtype == "toggle" else (0, 200, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, dtype, (x, max(0, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    return {
        "diffs": diffs,
        "toggle_changes": toggles,
        "diff_mask": mask,
        "overlay": overlay,
    }


def exibir_comparacao_esperados(base_dir):
    st.subheader("Comparacao com resultados esperados")
    esperados_dir = os.path.join(base_dir, "esperados")
    final_path = os.path.join(base_dir, "resultado_final.png")

    if not os.path.exists(final_path):
        st.warning("resultado_final.png nao encontrado para comparacao.")
        return

    if not os.path.isdir(esperados_dir):
        st.info("Nenhuma pasta 'esperados' encontrada para este teste.")
        return

    esperados = [f for f in os.listdir(esperados_dir) if f.lower().endswith(".png")]
    if not esperados:
        st.info("Nenhum esperado salvo para comparacao.")
        return

    try:
        img_final = Image.open(final_path)
    except Exception:
        st.error("Falha ao abrir resultado_final.png.")
        return

    # Regioes a ignorar (opcional)
    ignore_regions = []
    ignore_path = os.path.join(esperados_dir, "ignore.json")
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, "r", encoding="utf-8") as f:
                ignore_regions = json.load(f)
        except Exception:
            ignore_regions = []

    for nome in sorted(esperados):
        exp_path = os.path.join(esperados_dir, nome)
        try:
            img_exp = Image.open(exp_path)
            score = _simples_similarity(img_exp, img_final)
        except Exception:
            st.warning(f"Falha ao comparar {nome}.")
            continue

        st.markdown(f"**Comparacao:** `{nome}` x `resultado_final.png`")
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.image(img_exp, caption=f"Esperado: {nome}", use_container_width=True)
        col2.image(img_final, caption="Resultado final", use_container_width=True)
        col3.metric("Similaridade (global)", f"{score * 100:.1f}%")

        # Comparacao robusta automatica (differences + toggle)
        try:
            exp_bgr = cv2.cvtColor(np.array(img_exp), cv2.COLOR_RGB2BGR)
            fin_bgr = cv2.cvtColor(np.array(img_final), cv2.COLOR_RGB2BGR)
            if fin_bgr.shape[:2] != exp_bgr.shape[:2]:
                fin_bgr = cv2.resize(fin_bgr, (exp_bgr.shape[1], exp_bgr.shape[0]))
            diff_res = _compare_images_cv(exp_bgr, fin_bgr, ignore_regions=ignore_regions)

            # desenha caixas nas duas imagens separadamente (sem overlay combinado)
            exp_box = exp_bgr.copy()
            fin_box = fin_bgr.copy()
            for d in diff_res["diffs"]:
                x, y, w, h = d["bbox"]
                color = (0, 255, 0) if d["type"] == "toggle" else (0, 200, 255)
                cv2.rectangle(exp_box, (x, y), (x + w, y + h), color, 2)
                cv2.rectangle(fin_box, (x, y), (x + w, y + h), color, 2)

            st.markdown("### Comparacao de toggle")

            o1, o2, o3 = st.columns([2, 2, 2])
            o1.image(cv2.cvtColor(exp_box, cv2.COLOR_BGR2RGB), caption="Esperado (com boxes)", use_container_width=True)
            o2.image(cv2.cvtColor(fin_box, cv2.COLOR_BGR2RGB), caption="Final (com boxes)", use_container_width=True)
            o3.image(diff_res["diff_mask"], caption="Mascara de diferencas", use_container_width=True)

            with st.container():
                if diff_res["toggle_changes"]:
                    st.write("Toggles detectados (esperado -> final):")
                    for t in diff_res["toggle_changes"]:
                        st.write(f"- {t['stateA']} -> {t['stateB']} | conf={t['confidence']} | bbox={t['bbox']}")
                    st.error("Resultado reprovado: divergencia de toggle detectada.")
                else:
                    st.write("Nenhum toggle detectado automaticamente.")
                    st.success("Resultado aprovado: nenhum toggle divergente detectado.")
        except Exception:
            st.warning("Falha ao executar comparacao robusta (cv).")


def exibir_validacao_final(execucao, base_dir):
    st.subheader("Validacao final da tela")
    resultado_final_path = os.path.join(base_dir, "resultado_final.png")
    if not execucao:
        st.warning("Nenhuma acao registrada.")
        return

    ultima = execucao[-1]
    frame_esperado = ultima.get("frame_esperado")
    frame_path = os.path.join(base_dir, frame_esperado) if frame_esperado else ""

    col1, col2 = st.columns(2)
    if frame_path and os.path.exists(frame_path):
        col1.image(Image.open(frame_path), caption="Esperada (ultima acao)", use_container_width=True)
    else:
        col1.error("Frame esperado nao encontrado")

    if os.path.exists(resultado_final_path):
        col2.image(Image.open(resultado_final_path), caption="Resultado final", use_container_width=True)
    else:
        col2.error("resultado_final.png nao encontrado")

    sim = float(ultima.get("similaridade", 0.0))
    st.write(f"Similaridade final: {sim:.2f}")


def main():
    titulo_painel("Dashboard de Execucao de Testes - VWAIT", "")
    exibir_bancadas_tempo_real()
    st.markdown("---")
    st.subheader("Execucao detalhada por teste")

    if not os.path.isdir(DATA_ROOT):
        st.error(f"Pasta de dados nao encontrada: {DATA_ROOT}")
        return

    logs = carregar_logs()
    if not logs:
        st.info("Nenhum execucao_log.json encontrado em Data/*/*/.")
        return

    labels = [label for label, _ in logs]
    selected = st.selectbox("Selecione a execucao", labels)
    path_map = {label: path for label, path in logs}
    log_path = path_map.get(selected)
    if not log_path or not os.path.exists(log_path):
        st.error("Execucao selecionada nao encontrada.")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        st.error(f"Falha ao ler execucao_log.json: {e}")
        return

    execucao = data.get("execucao") if isinstance(data, dict) else data
    if not isinstance(execucao, list):
        st.error("Formato invalido de execucao_log.json (esperado lista ou {'execucao': []}).")
        return

    base_dir = os.path.dirname(log_path)
    metricas = calcular_metricas(execucao)

    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_comparacao_esperados(base_dir)
    exibir_validacao_final(execucao, base_dir)
    exibir_acoes(execucao, base_dir)


if __name__ == "__main__":
    main()

