import os

import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
from PIL import Image
from vwait.core.paths import tester_expected_final_path


def load_logs(*, data_root):
    logs = []
    if not os.path.isdir(data_root):
        return logs
    for category in os.listdir(data_root):
        category_path = os.path.join(data_root, category)
        if os.path.isdir(category_path):
            for test_name in os.listdir(category_path):
                test_path = os.path.join(category_path, test_name)
                if os.path.isdir(test_path):
                    file_path = os.path.join(test_path, "execucao_log.json")
                    if os.path.exists(file_path):
                        logs.append((f"{category}/{test_name}", file_path))
    return logs


def calculate_metrics(execution):
    total = len(execution)
    hits = sum(1 for action in execution if "OK" in action.get("status", "").upper())
    failures = total - hits
    flakes = sum(1 for action in execution if "FLAKE" in action.get("status", "")) if total > 0 else 0
    total_time = sum(action.get("duracao", 1) for action in execution)
    coverage = round((len({action.get("tela", f"id{action.get('id')}") for action in execution}) / total) * 100, 1) if total > 0 else 0
    precision = round((hits / total) * 100, 2) if total > 0 else 0
    return {
        "total_acoes": total,
        "acertos": hits,
        "falhas": failures,
        "flakes": flakes,
        "precisao_percentual": precision,
        "tempo_total": total_time,
        "cobertura_telas": coverage,
        "resultado_final": "APROVADO" if failures == 0 else "REPROVADO",
    }


def render_metrics(metrics):
    st.subheader("Metricas gerais")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de acoes", metrics["total_acoes"])
    col2.metric("Acertos", metrics["acertos"])
    col3.metric("Falhas", metrics["falhas"])
    col4, col5, col6 = st.columns(3)
    col4.metric("Precisao (%)", metrics["precisao_percentual"])
    col5.metric("Instabilidades", metrics["flakes"])
    col6.metric("Cobertura de Telas (%)", metrics["cobertura_telas"])
    st.caption("Instabilidades = acoes com status `FLAKE`, indicando falha intermitente ou comportamento inconsistente.")
    st.metric("Tempo total de execucao (s)", metrics["tempo_total"])
    if metrics["resultado_final"] == "APROVADO":
        st.success("APROVADO")
    else:
        st.error("REPROVADO")
    fig, ax = plt.subplots()
    labels = ["Acertos", "Falhas"]
    sizes = [metrics["acertos"], metrics["falhas"]]
    colors = ["#4CAF50", "#F44336"]
    explode = (0.05, 0)
    ax.pie(sizes, explode=explode, labels=labels, colors=colors, autopct="%1.1f%%", shadow=True, startangle=90)
    ax.axis("equal")
    st.pyplot(fig)


def render_timeline(execution):
    st.subheader("Timeline da execucao")
    durations = [int(float(action.get("duracao", 1))) for action in execution]
    ids = []
    for index, action in enumerate(execution):
        value = action.get("id", index + 1)
        try:
            ids.append(int(value))
        except (ValueError, TypeError):
            ids.append(index + 1)
    status = ["green" if "OK" in action.get("status", "").upper() else "red" for action in execution]
    fig, ax = plt.subplots()
    ax.bar(ids, durations, color=status)
    ax.set_xlabel("Acao")
    ax.set_ylabel("Duracao (s)")
    ax.set_title("Tempo por acao")
    st.pyplot(fig)


def render_actions(execution, base_dir):
    st.subheader("Detalhes das acoes")
    for action in execution:
        title = f"Acao {action.get('id')} - {str(action.get('acao', '')).upper()} | {action.get('status', '')}"
        with st.expander(title):
            col1, col2 = st.columns(2)
            frame_path = os.path.join(base_dir, action.get("frame_esperado", ""))
            result_path = os.path.join(base_dir, action.get("screenshot", ""))
            if frame_path and os.path.exists(frame_path):
                col1.image(Image.open(frame_path), caption=f"Esperado: {action.get('frame_esperado', '')}", use_container_width=True)
            else:
                col1.warning("Frame esperado nao encontrado")
            if result_path and os.path.exists(result_path):
                col2.image(Image.open(result_path), caption=f"Obtido: {action.get('screenshot', '')}", use_container_width=True)
            else:
                col2.warning("Screenshot nao encontrado")
            if "similaridade" in action:
                st.write(f"Similaridade: **{action['similaridade']:.2f}**")
            st.write(f"Duracao: **{action.get('duracao', 0)}s**")
            if "coordenadas" in action:
                st.json(action.get("coordenadas", {}))
            if "log" in action:
                st.code(action["log"], language="bash")


def render_heatmap(execution):
    st.subheader("Mapa de calor dos toques")
    xs = [action["coordenadas"]["x"] for action in execution if "coordenadas" in action and "x" in action["coordenadas"]]
    ys = [action["coordenadas"]["y"] for action in execution if "coordenadas" in action and "y" in action["coordenadas"]]
    if xs and ys:
        fig, ax = plt.subplots()
        sns.kdeplot(x=xs, y=ys, cmap="Reds", fill=True, ax=ax, thresh=0.05)
        ax.invert_yaxis()
        st.pyplot(fig)
    else:
        st.warning("Sem coordenadas para gerar mapa de calor.")


def render_final_validation(execution, base_dir):
    st.subheader("Validacao final da tela")
    test_ref = str(base_dir).replace("\\", "/").split("/Data/runs/tester/", 1)
    final_result_path = ""
    if len(test_ref) == 2:
        parts = test_ref[1].split("/", 3)
        if len(parts) >= 2:
            final_result_path = str(tester_expected_final_path(parts[0], parts[1]))
    col1, col2 = st.columns(2)
    if execution:
        last = execution[-1]
        frame_path = os.path.join(base_dir, last.get("frame_esperado", ""))
        if frame_path and os.path.exists(frame_path):
            col1.image(Image.open(frame_path), caption="Esperada (ultima acao)", use_container_width=True)
        else:
            col1.error("Frame esperado nao encontrado")
        if os.path.exists(final_result_path):
            col2.image(Image.open(final_result_path), caption="Obtida (Resultado Final)", use_container_width=True)
        else:
            col2.error("resultado_final.png nao encontrado")
        if "similaridade" in last:
            st.write(f"Similaridade final: **{last['similaridade']:.2f}**")
        if "OK" in last.get("status", "").upper():
            st.success("Tela final validada")
        else:
            st.error("Tela final divergente")
    else:
        st.warning("Nenhuma acao registrada")


def render_regressions(execution):
    st.subheader("Analise de regressoes")
    failures = [action for action in execution if "OK" not in action.get("status", "").upper()]
    if failures:
        st.write("Top falhas nesta execucao:")
        for failure in failures:
            similarity = failure.get("similaridade")
            similarity_str = f"{similarity:.2f}" if isinstance(similarity, (int, float)) else "N/A"
            st.write(f"- Acao {failure.get('id')} ({failure.get('acao', '')}): Similaridade {similarity_str}")
    else:
        st.success("Nenhuma falha registrada")
