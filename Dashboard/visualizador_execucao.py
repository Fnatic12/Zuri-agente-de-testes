import os
import json
import streamlit as st
from PIL import Image
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import time
import cv2

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

# === CONFIGURACOES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")

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

    acertos = sum(1 for a in execucao if "OK" in a.get("status", "").upper())
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", ""))
    tempo_total = sum(a.get("duracao", 1) for a in execucao)

    # Tolerante a ausencia de 'id' e/ou 'tela'
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
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO"
    }

# === DASHBOARD ===
def exibir_metricas(metricas):
    st.subheader("Metricas gerais")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de acoes", metricas["total_acoes"])
    col2.metric("Acertos", metricas["acertos"])
    col3.metric("Falhas", metricas["falhas"])

    col4, col5, col6 = st.columns(3)
    col4.metric("Precisao (%)", metricas["precisao_percentual"])
    col5.metric("Flakes", metricas["flakes"])
    col6.metric("Cobertura de Telas (%)", metricas["cobertura_telas"])

    st.metric("Tempo total de execucao (s)", metricas["tempo_total"])

    if metricas["resultado_final"] == "APROVADO":
        st.success("APROVADO")
    else:
        st.error("REPROVADO")

    # === GRAFICO DE PIZZA ===
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
    st.subheader("Timeline da execucao")
    tempos = [a.get("duracao", 1) for a in execucao]
    ids = [a["id"] for a in execucao]
    status = ["green" if "OK" in str(a.get("status", "")).upper() else "red" for a in execucao]

    fig, ax = plt.subplots()
    ax.bar(ids, tempos, color=status)
    ax.set_xlabel("Acao")
    ax.set_ylabel("Duracao (s)")
    ax.set_title("Tempo por acao")
    st.pyplot(fig)

def exibir_mapa_calor(execucao):
    st.subheader("Mapa de calor dos toques")
    xs = [a["coordenadas"]["x"] for a in execucao if "coordenadas" in a]
    ys = [a["coordenadas"]["y"] for a in execucao if "coordenadas" in a]

    if xs and ys:
        fig, ax = plt.subplots()
        sns.kdeplot(x=xs, y=ys, cmap="Reds", fill=True, ax=ax, thresh=0.05)
        ax.invert_yaxis()
        st.pyplot(fig)
    else:
        st.warning("Sem coordenadas para gerar mapa de calor.")

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
        roi_a = img_a[y:y+h, x:x+w]
        roi_b = img_b[y:y+h, x:x+w]
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
                toggles.append({
                    "bbox": (x, y, w, h),
                    "stateA": state_a,
                    "stateB": state_b,
                    "confidence": round(conf, 3),
                })

        diffs.append({
            "bbox": (x, y, w, h),
            "score": score,
            "type": dtype,
        })
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
        col3.metric("Similaridade (global)", f"{score*100:.1f}%")

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

            o1, o2, o3 = st.columns([2, 2, 2])
            o1.image(cv2.cvtColor(exp_box, cv2.COLOR_BGR2RGB), caption="Esperado (com boxes)", use_container_width=True)
            o2.image(cv2.cvtColor(fin_box, cv2.COLOR_BGR2RGB), caption="Final (com boxes)", use_container_width=True)
            o3.image(diff_res["diff_mask"], caption="Mascara de diferencas", use_container_width=True)

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


def exibir_regressoes(execucao):
    st.subheader("Analise de regressoes")
    falhas = [a for a in execucao if "status" in a and "OK" not in str(a["status"]).upper()]
    if not falhas:
        st.success("Nenhuma falha registrada.")
        return
    for f in falhas[:10]:
        st.write(
            f"- Acao {f.get('id', '?')} ({f.get('acao', '?')}): "
            f"similaridade {float(f.get('similaridade', 0.0)):.2f}"
        )


def main():
    titulo_painel("Dashboard de Execucao de Testes - VWAIT", "Veja todos os resultados dos testes")

    if not os.path.isdir(DATA_ROOT):
        st.error(f"Pasta de dados nao encontrada: {DATA_ROOT}")
        st.stop()

    logs = carregar_logs()
    if not logs:
        st.error("Nenhum execucao_log.json encontrado em Data/*/*/")
        st.stop()

    labels = [label for label, _ in logs]
    selected = st.selectbox("Selecione a execucao", labels)
    path_map = {label: path for label, path in logs}
    log_path = path_map.get(selected)
    if not log_path or not os.path.exists(log_path):
        st.error("Execucao selecionada nao encontrada.")
        st.stop()

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        st.error(f"Falha ao ler execucao_log.json: {e}")
        st.stop()

    execucao = data.get("execucao") if isinstance(data, dict) else data
    if not isinstance(execucao, list):
        st.error("Formato invalido de execucao_log.json (esperado lista ou {'execucao': []}).")
        st.stop()

    base_dir = os.path.dirname(log_path)
    metricas = calcular_metricas(execucao)

    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_mapa_calor(execucao)
    exibir_comparacao_esperados(base_dir)
    exibir_validacao_final(execucao, base_dir)
    exibir_regressoes(execucao)
    exibir_acoes(execucao, base_dir)


if __name__ == "__main__":
    main()


