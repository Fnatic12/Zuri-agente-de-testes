from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable

import matplotlib.pyplot as plt
import streamlit as st
from PIL import Image, ImageChops
from vwait.core.paths import tester_recorded_frames_dir

from .helpers import (
    clean_display_text,
    estimativa_restante,
    nome_bancada,
    percent_text,
    quality_snapshot,
    saude_chip_html,
    saude_execucao,
    status_age_seconds,
    status_chip_html,
    status_normalized,
    tempo_formatado,
    velocidade_live,
)

LoadExecucaoFn = Callable[[dict[str, Any]], list[dict[str, Any]]]
LatestScreenshotFn = Callable[[dict[str, Any]], str | None]
ResolveTestDirFn = Callable[[dict[str, Any]], str | None]
CountImagesFn = Callable[[str | None], int]
ListAdbDevicesFn = Callable[[], set[str]]
LoadStatusMapFn = Callable[[], dict[str, Any]]
FilterRealBenchesFn = Callable[[dict[str, Any], set[str]], dict[str, Any]]

def _catalog_test_ref_from_run_dir(base_dir: str) -> tuple[str, str] | None:
    normalized = str(base_dir).replace("\\", "/")
    marker = "/Data/runs/tester/"
    if marker not in normalized:
        return None
    rel = normalized.split(marker, 1)[1]
    parts = rel.split("/", 3)
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _resolve_action_image_paths(base_dir: str, acao: dict[str, Any]) -> tuple[str | None, str | None]:
    frame_raw = str(acao.get("frame_esperado", "") or "").strip()
    resultado_raw = str(acao.get("screenshot", "") or "").strip()

    frame_path = None
    if frame_raw:
        candidate = frame_raw if os.path.isabs(frame_raw) else os.path.abspath(os.path.join(base_dir, frame_raw))
        if os.path.exists(candidate):
            frame_path = candidate
        else:
            test_ref = _catalog_test_ref_from_run_dir(base_dir)
            if test_ref:
                category, test_name = test_ref
                fallback = tester_recorded_frames_dir(category, test_name) / os.path.basename(frame_raw)
                if fallback.exists():
                    frame_path = str(fallback)

    resultado_path = None
    if resultado_raw:
        candidate = resultado_raw if os.path.isabs(resultado_raw) else os.path.abspath(os.path.join(base_dir, resultado_raw))
        if os.path.exists(candidate):
            resultado_path = candidate
        else:
            fallback = os.path.abspath(os.path.join(base_dir, "artifacts", "results", os.path.basename(resultado_raw)))
            if os.path.exists(fallback):
                resultado_path = fallback

    return frame_path, resultado_path


def _build_action_diff_image(frame_path: str, resultado_path: str) -> Image.Image | None:
    try:
        esperado = Image.open(frame_path).convert("RGB")
        obtido = Image.open(resultado_path).convert("RGB")
        if obtido.size != esperado.size:
            obtido = obtido.resize(esperado.size)
        return ImageChops.difference(esperado, obtido)
    except Exception:
        return None


def portfolio_live_summary(
    executando_rows: dict[str, Any],
    finalizado_rows: dict[str, Any],
    erro_rows: dict[str, Any],
    conectadas: set[str],
    *,
    load_execucao: LoadExecucaoFn,
) -> dict[str, Any]:
    now = datetime.now()
    quality_rows = []
    for serial, info in executando_rows.items():
        execucao = load_execucao(info)
        quality = quality_snapshot(info, execucao)
        saude = saude_execucao(info, now, quality)
        quality_rows.append((serial, info, quality, saude))

    progressos = [float(info.get("progresso", 0.0) or 0.0) for _, info, _, _ in quality_rows]
    velocidades = [value for _, info, _, _ in quality_rows if (value := velocidade_live(info)) is not None]
    ok_total = sum(int(quality.get("ok", 0) or 0) for _, _, quality, _ in quality_rows)
    divergente_total = sum(int(quality.get("divergente", 0) or 0) for _, _, quality, _ in quality_rows)
    amostra_total = sum(int(quality.get("amostra", 0) or 0) for _, _, quality, _ in quality_rows)
    aprovacao = (ok_total / amostra_total) * 100.0 if amostra_total > 0 else None
    criticos = [item for item in quality_rows if item[3].get("label") == "Critico"]
    atencao = [item for item in quality_rows if item[3].get("label") == "Atencao"]

    foco = None
    prioridades = {"Critico": 2, "Atencao": 1, "Saudavel": 0}
    if quality_rows:
        foco = max(
            quality_rows,
            key=lambda item: (
                prioridades.get(item[3].get("label"), 0),
                int(item[2].get("divergente", 0) or 0),
                float(estimativa_restante(item[1]) or 0.0),
            ),
        )

    return {
        "conectadas": len(conectadas),
        "executando": len(executando_rows),
        "finalizadas": len(finalizado_rows),
        "erros": len(erro_rows),
        "progresso_medio": (sum(progressos) / len(progressos)) if progressos else None,
        "aprovacao": aprovacao,
        "divergencias": divergente_total,
        "velocidade_total": sum(velocidades) if velocidades else None,
        "criticos": len(criticos),
        "atencao": len(atencao),
        "foco": foco,
    }


def render_realtime_dashboard(
    *,
    list_adb_devices: ListAdbDevicesFn,
    load_status_map: LoadStatusMapFn,
    filter_real_benches: FilterRealBenchesFn,
    load_execucao: LoadExecucaoFn,
    latest_screenshot: LatestScreenshotFn,
    resolve_test_dir: ResolveTestDirFn,
    count_images: CountImagesFn,
    autorefresh_available: bool,
) -> None:
    st.subheader("Bancadas em tempo real")
    st.caption("Somente execuções reais: bancada conectada + status recente.")

    if autorefresh_available:
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=3000, limit=None, key="dash_realtime_refresh")

    conectadas = list_adb_devices()
    status_raw = load_status_map()
    bancadas = filter_real_benches(status_raw, conectadas)

    executando_rows = {
        serial: info
        for serial, info in bancadas.items()
        if status_normalized(info.get("status", "")) in {"executando", "coletando_logs"}
    }
    finalizado_rows = {
        serial: info
        for serial, info in bancadas.items()
        if status_normalized(info.get("status", "")) == "finalizado"
    }
    erro_rows = {
        serial: info
        for serial, info in bancadas.items()
        if status_normalized(info.get("status", "")) == "erro"
    }

    restantes = [
        estimativa_restante(info)
        for info in executando_rows.values()
        if status_normalized(info.get("status", "")) == "executando"
    ]
    restantes = [value for value in restantes if value is not None]
    eta_global_s = max(restantes) if restantes else None
    final_previsto = (
        (datetime.now() + timedelta(seconds=float(eta_global_s))).strftime("%H:%M:%S")
        if eta_global_s is not None
        else "-"
    )

    summary = portfolio_live_summary(
        executando_rows,
        finalizado_rows,
        erro_rows,
        conectadas,
        load_execucao=load_execucao,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bancadas conectadas", len(conectadas))
    c2.metric("Executando agora", len(executando_rows))
    c3.metric("Progresso medio", percent_text(summary.get("progresso_medio")))
    c4.metric("Aprovacao parcial", percent_text(summary.get("aprovacao")))
    c5.metric("Divergencias abertas", str(summary.get("divergencias", 0)))
    c6.metric("ETA global", tempo_formatado(eta_global_s) if eta_global_s is not None else "-")
    st.caption(f"Previsao de termino global: {final_previsto}")

    if not conectadas:
        st.warning("Nenhuma bancada ADB conectada no momento.")
        return
    if not executando_rows:
        st.info("Nenhum teste em execucao neste momento.")
        return

    foco = summary.get("foco")
    if foco:
        serial_foco, info_foco, quality_foco, saude_foco = foco
        eta_foco = estimativa_restante(info_foco)
        texto_foco = (
            f"{nome_bancada(serial_foco)} em {clean_display_text(info_foco.get('teste', '-'))}: "
            f"{saude_foco.get('reason', '').lower()}, "
            f"{int(quality_foco.get('divergente', 0) or 0)} divergencias, "
            f"ETA {tempo_formatado(eta_foco or 0.0) if eta_foco is not None else '-'}."
        )
    else:
        texto_foco = "Nenhuma bancada ativa com dados suficientes para destaque."

    badges = []
    if summary.get("criticos", 0):
        badges.append(
            "<span class='signal-badge' style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            f"{summary.get('criticos', 0)} critico(s)</span>"
        )
    if summary.get("atencao", 0):
        badges.append(
            "<span class='signal-badge' style='background:#f59e0b20;border-color:#f59e0b66;color:#fde68a;'>"
            f"{summary.get('atencao', 0)} em atencao</span>"
        )
    if summary.get("finalizadas", 0):
        badges.append(
            "<span class='signal-badge' style='background:#22c55e20;border-color:#22c55e66;color:#bbf7d0;'>"
            f"{summary.get('finalizadas', 0)} finalizada(s) agora</span>"
        )
    if summary.get("erros", 0):
        badges.append(
            "<span class='signal-badge' style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            f"{summary.get('erros', 0)} erro(s) recentes</span>"
        )

    st.markdown(
        (
            "<div class='executive-banner'>"
            "<div class='executive-banner-title'>Leitura Executiva</div>"
            f"<div class='executive-banner-body'>{texto_foco}</div>"
            f"<div>{''.join(badges)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

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
            {"Critico": 0, "Atencao": 1, "Saudavel": 2}.get(
                str(saude_execucao(item[1], datetime.now(), quality_snapshot(item[1], load_execucao(item[1]))).get("label", "")),
                2,
            ),
            item[0],
        ),
    )

    for start in range(0, len(rows), cols_per_row):
        chunk = rows[start : start + cols_per_row]
        cols = st.columns(cols_per_row)
        for idx, col in enumerate(cols):
            if idx >= len(chunk):
                continue
            serial, info = chunk[idx]
            nome = nome_bancada(serial)
            teste = str(info.get("teste", "-"))
            status = str(info.get("status", ""))
            progresso = float(info.get("progresso", 0.0) or 0.0)
            total = int(info.get("acoes_totais", 0) or 0)
            executadas = int(info.get("acoes_executadas", 0) or 0)
            tempo = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
            restante = estimativa_restante(info)
            atualizado = str(info.get("atualizado_em") or info.get("inicio") or "-")
            thumb = latest_screenshot(info)
            execucao = load_execucao(info)
            quality = quality_snapshot(info, execucao)
            saude = saude_execucao(info, datetime.now(), quality)
            similaridade_media = info.get("similaridade_media")
            similaridade_media_txt = (
                f"{float(similaridade_media) * 100:.1f}%"
                if similaridade_media is not None and str(similaridade_media).strip() != ""
                else "-"
            )
            test_dir = resolve_test_dir(info)
            capturas = count_images(os.path.join(test_dir, "resultados")) if test_dir else 0

            with col:
                st.markdown(
                    (
                        "<div class='clean-card'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:0.5rem;'>"
                        f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{nome}</div>"
                        f"<div style='display:flex;gap:0.35rem;flex-wrap:wrap;justify-content:flex-end;'>"
                        f"{status_chip_html(status)}{saude_chip_html(saude)}"
                        "</div>"
                        "</div>"
                        f"<div style='margin-top:0.35rem;color:#a8b3c5;font-size:0.84rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                        f"Teste: {teste}"
                        "</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, max(0.0, progresso / 100.0)), text=f"{progresso:.1f}%")
                st.caption(saude.get("reason", "Sem leitura executiva"))
                d1, d2 = st.columns(2)
                d1.metric("Acoes", f"{executadas}/{total}" if total > 0 else str(executadas))
                d2.metric("ETA", tempo_formatado(restante) if restante is not None else "-")
                d4, d5 = st.columns(2)
                d4.metric("Aprovacao", percent_text(quality.get("aprovacao")))
                d5.metric("Divergencias", str(quality.get("divergente", 0)))
                d7, d8, d9 = st.columns(3)
                d7.metric("Tempo", tempo_formatado(tempo))
                d8.metric("Capturas", str(capturas))
                d9.metric("Similaridade media", similaridade_media_txt)
                st.caption(
                    f"Atualizado em {atualizado.split('T')[1][:8] if 'T' in atualizado else atualizado}"
                )
                if thumb and os.path.exists(thumb):
                    st.image(thumb, caption=f"Ultima tela: {os.path.basename(thumb)}", use_container_width=True)
                else:
                    st.caption("Sem screenshot recente para esta bancada.")


def calculate_metrics(execucao: list[dict[str, Any]]) -> dict[str, Any]:
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

    acertos = sum(1 for acao in execucao if "OK" in str(acao.get("status", "")).upper())
    falhas = total - acertos
    flakes = sum(1 for acao in execucao if "FLAKE" in str(acao.get("status", "")))
    tempo_total = sum(acao.get("duracao", 1) for acao in execucao)
    telas_unicas = {(acao.get("tela") or f"id{acao.get('id', idx)}") for idx, acao in enumerate(execucao)}
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


def _style_axes_clean(ax: Any) -> None:
    ax.set_facecolor("#0f172a")
    ax.grid(axis="y", color="#1f2937", linewidth=0.9)
    ax.tick_params(colors="#cbd5e1", labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#334155")
        spine.set_linewidth(0.8)


def render_metrics(metricas: dict[str, Any]) -> None:
    st.subheader("Resumo")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _kpi_card("Total de acoes", str(metricas["total_acoes"]))
    with col2:
        _kpi_card("Acertos", str(metricas["acertos"]))
    with col3:
        _kpi_card("Falhas", str(metricas["falhas"]))
    with col4:
        _kpi_card("Instabilidades", str(metricas["flakes"]))

    st.caption("Instabilidades = acoes marcadas com status `FLAKE`, ou seja, comportamento intermitente/não deterministico durante a execucao.")

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


def render_timeline(execucao: list[dict[str, Any]]) -> None:
    st.subheader("Tempo por acao")
    if not execucao:
        st.info("Sem acoes para montar timeline.")
        return

    tempos = [acao.get("duracao", 1) for acao in execucao]
    ids = [acao.get("id", idx + 1) for idx, acao in enumerate(execucao)]
    status_colors = [
        "#16a34a" if "OK" in str(acao.get("status", "")).upper() else "#dc2626"
        for acao in execucao
    ]

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


def render_actions(execucao: list[dict[str, Any]], base_dir: str) -> None:
    st.subheader("Detalhes das ações")
    if not execucao:
        st.info("Nenhuma ação encontrada.")
        return

    st.caption(f"{len(execucao)} ações carregadas.")
    resumo = []
    for idx, acao in enumerate(execucao, start=1):
        resumo.append(
            {
                "Acao": idx,
                "ID": acao.get("id", idx),
                "Tipo": str(acao.get("acao", "")).upper(),
                "Status": acao.get("status", "-"),
                "Similaridade": round(float(acao.get("similaridade", 0.0) or 0.0), 3),
                "Duracao (s)": round(float(acao.get("duracao", 0.0) or 0.0), 2),
            }
        )

    st.dataframe(resumo, use_container_width=True, hide_index=True)
    indice_acao = st.selectbox(
        "Selecione a acao para ver os detalhes",
        options=list(range(len(execucao))),
        format_func=lambda i: (
            f"Acao {i + 1} - {str(execucao[i].get('acao', '')).upper()} | {execucao[i].get('status', '-')}"
        ),
        key="dashboard_acao_detalhe",
    )

    acao = execucao[indice_acao]
    frame_path, resultado_path = _resolve_action_image_paths(base_dir, acao)

    col_meta_1, col_meta_2, col_meta_3 = st.columns(3)
    col_meta_1.metric("Status", acao.get("status", "-"))
    col_meta_2.metric("Similaridade", f"{float(acao.get('similaridade', 0.0) or 0.0):.2f}")
    col_meta_3.metric("Duracao", f"{float(acao.get('duracao', 0.0) or 0.0):.2f}s")

    st.markdown("**Frame coletado vs resultado da execucao**")

    col1, col2 = st.columns(2)
    if frame_path and os.path.exists(frame_path):
        col1.image(
            Image.open(frame_path),
            caption=f"Frame coletado: {os.path.basename(frame_path)}",
            use_container_width=True,
        )
    else:
        col1.warning("Frame coletado nao encontrado")

    if resultado_path and os.path.exists(resultado_path):
        col2.image(
            Image.open(resultado_path),
            caption=f"Resultado da execucao: {os.path.basename(resultado_path)}",
            use_container_width=True,
        )
    else:
        col2.warning("Resultado da execucao nao encontrado")

    if frame_path and resultado_path and os.path.exists(frame_path) and os.path.exists(resultado_path):
        diff_image = _build_action_diff_image(frame_path, resultado_path)
        if diff_image is not None:
            st.markdown("**Comparacao visual da acao**")
            diff_col1, diff_col2 = st.columns([1, 2])
            similarity = float(acao.get("similaridade", 0.0) or 0.0)
            status = str(acao.get("status", "-") or "-")
            if "OK" in status.upper():
                diff_col1.success(f"Acao consistente\n\nSimilaridade: {similarity:.3f}")
            else:
                diff_col1.error(f"Acao divergente\n\nSimilaridade: {similarity:.3f}")
            diff_col2.image(diff_image, caption="Mapa visual de diferencas", use_container_width=True)

    meta_col1, meta_col2 = st.columns(2)
    meta_col1.caption(f"Origem esperada: {acao.get('frame_esperado', '-')}")
    meta_col2.caption(f"Origem obtida: {acao.get('screenshot', '-')}")


__all__ = [
    "calculate_metrics",
    "portfolio_live_summary",
    "render_actions",
    "render_metrics",
    "render_realtime_dashboard",
    "render_timeline",
]
