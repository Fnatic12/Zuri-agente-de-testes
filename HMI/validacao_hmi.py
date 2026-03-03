import os
from typing import Dict, List, Optional, Tuple

import streamlit as st
from PIL import Image

from HMI.hmi_engine import ValidationConfig, collect_result_screens, validate_execution_images
from HMI.hmi_indexer import build_library_index, load_library_index
from HMI.hmi_report import get_validation_dir, load_validation_report, save_validation_report


def _title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <style>
        body {{ background-color: #0B0C10; color: #E0E0E0; }}
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
        .card {{
            background: rgba(30,30,30,0.95);
            border-radius: 18px;
            padding: 22px;
            border: 1px solid rgba(255,255,255,0.05);
            box-shadow: 0 8px 22px rgba(0,0,0,0.45);
            margin-bottom: 1rem;
        }}
        .hero {{
            background: linear-gradient(135deg, rgba(18,194,233,0.12), rgba(196,113,237,0.09), rgba(246,79,89,0.12));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 22px;
            padding: 24px;
            margin-bottom: 1rem;
        }}
        .stat-card {{
            background: rgba(18,18,18,0.92);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 16px 18px;
            min-height: 112px;
        }}
        .stat-label {{
            font-size: 0.82rem;
            color: #9CA3AF;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.35rem;
        }}
        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #F8FAFC;
            margin-bottom: 0.25rem;
        }}
        .stat-caption {{
            color: #94A3B8;
            font-size: 0.9rem;
        }}
        .status-chip {{
            display: inline-block;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            border: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 0.75rem;
        }}
        .status-pass {{
            background: rgba(16,185,129,0.16);
            color: #6EE7B7;
        }}
        .status-warn {{
            background: rgba(245,158,11,0.16);
            color: #FCD34D;
        }}
        .status-fail {{
            background: rgba(239,68,68,0.16);
            color: #FCA5A5;
        }}
        .section-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: #E5E7EB;
            margin-bottom: 0.75rem;
        }}
        .hint {{
            color: #94A3B8;
            font-size: 0.92rem;
            margin-top: 0.4rem;
        }}
        </style>
        <h1 class="main-title">{title}</h1>
        <p class="subtitle">{subtitle}</p>
        """,
        unsafe_allow_html=True,
    )


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "biblioteca"


def _list_tests(data_root: str) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    if not os.path.isdir(data_root):
        return rows
    for categoria in sorted(os.listdir(data_root)):
        cat_path = os.path.join(data_root, categoria)
        if not os.path.isdir(cat_path):
            continue
        for teste in sorted(os.listdir(cat_path)):
            test_path = os.path.join(cat_path, teste)
            if not os.path.isdir(test_path):
                continue
            if os.path.isdir(os.path.join(test_path, "resultados")):
                rows.append((f"{categoria}/{teste}", categoria, teste))
    return rows


def _load_index_if_exists(index_path: str) -> Optional[Dict]:
    if not index_path or not os.path.exists(index_path):
        return None
    try:
        return load_library_index(index_path)
    except Exception:
        return None


def _report_exists(test_dir: str) -> bool:
    return os.path.exists(os.path.join(get_validation_dir(test_dir), "resultado_hmi.json"))


def _status_chip(status: str) -> str:
    normalized = (status or "").upper()
    css = "status-fail"
    if normalized == "PASS":
        css = "status-pass"
    elif normalized == "PASS_WITH_WARNINGS":
        css = "status-warn"
    return f"<span class='status-chip {css}'>{normalized or 'N/A'}</span>"


def _stat_card(label: str, value: str, caption: str = "") -> None:
    st.markdown(
        (
            "<div class='stat-card'>"
            f"<div class='stat-label'>{label}</div>"
            f"<div class='stat-value'>{value}</div>"
            f"<div class='stat-caption'>{caption}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _show_summary(summary: Dict) -> None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        _stat_card("Telas", str(summary.get("total_screens", 0)), "Capturas avaliadas")
    with col2:
        _stat_card("Pass", str(summary.get("passed", 0)), "Sem divergencia critica")
    with col3:
        _stat_card("Warnings", str(summary.get("warnings", 0)), "Aderencia parcial")
    with col4:
        _stat_card("Fail", str(summary.get("failed", 0)), "Reprovadas")
    with col5:
        _stat_card("Score medio", f"{summary.get('average_score', 0.0) * 100:.1f}%", "Score composto")
    with col6:
        _stat_card("Pixel match", f"{summary.get('average_pixel_match', 0.0) * 100:.2f}%", "Media ponto a ponto")

    if summary.get("result") == "PASS":
        st.success("Validacao HMI aprovada.")
    else:
        st.error("Validacao HMI reprovada.")


def _show_item(item: Dict) -> None:
    title = f"{os.path.basename(item['screenshot_path'])} -> {item.get('screen_name') or 'sem match'}"
    with st.expander(title):
        st.markdown(_status_chip(item.get("status", "N/A")), unsafe_allow_html=True)
        st.caption(item.get("reason", ""))

        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        if os.path.exists(item["screenshot_path"]):
            col1.image(Image.open(item["screenshot_path"]), caption="Captura do radio", use_container_width=True)
        else:
            col1.warning("Screenshot nao encontrada.")

        ref_path = item.get("reference_path")
        if ref_path and os.path.exists(ref_path):
            col2.image(Image.open(ref_path), caption="Melhor match do Figma", use_container_width=True)
        else:
            col2.warning("Referencia do Figma nao encontrada.")

        artifacts = item.get("artifacts", {})
        overlay_path = artifacts.get("overlay_path")
        heatmap_path = artifacts.get("heatmap_path")
        if overlay_path and os.path.exists(overlay_path):
            col3.image(Image.open(overlay_path), caption="Overlay de divergencias", use_container_width=True)
        else:
            col3.info("Overlay indisponivel.")
        if heatmap_path and os.path.exists(heatmap_path):
            col4.image(Image.open(heatmap_path), caption="Heatmap de delta", use_container_width=True)
        else:
            col4.info("Heatmap indisponivel.")

        scores = item.get("scores", {})
        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("Final", f"{scores.get('final', 0.0) * 100:.2f}%")
        s2.metric("Pixel", f"{scores.get('pixel', 0.0) * 100:.2f}%")
        s3.metric("Grid min", f"{scores.get('grid_min', 0.0) * 100:.2f}%")
        s4.metric("Edge", f"{scores.get('edge', 0.0) * 100:.2f}%")
        s5.metric("Global", f"{scores.get('global', 0.0) * 100:.2f}%")
        s6.metric("Align", f"{scores.get('alignment', 0.0) * 100:.2f}%")

        diff_summary = item.get("diff_summary", {})
        st.markdown(
            (
                "<div class='card'>"
                "<div class='section-title'>Detalhamento tecnico</div>"
                f"<div>Divergencias em regioes: <b>{diff_summary.get('diff_count', 0)}</b></div>"
                f"<div>Toggle(s) divergentes: <b>{diff_summary.get('toggle_count', 0)}</b></div>"
                f"<div>Area divergente: <b>{diff_summary.get('diff_area_ratio', 0.0) * 100:.3f}%</b></div>"
                f"<div>Pixels alterados: <b>{diff_summary.get('changed_pixels', 0)}</b></div>"
                f"<div>Delta medio LAB: <b>{diff_summary.get('mean_delta', 0.0):.3f}</b></div>"
                f"<div>Delta p95 LAB: <b>{diff_summary.get('p95_delta', 0.0):.3f}</b></div>"
                f"<div>Pior celula: <b>{diff_summary.get('worst_cell_score', 0.0) * 100:.2f}%</b></div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        toggle_changes = item.get("toggle_changes", [])
        if toggle_changes:
            st.write("Toggles divergentes:")
            for toggle in toggle_changes:
                st.write(
                    f"- {toggle.get('stateA')} -> {toggle.get('stateB')} | "
                    f"conf={toggle.get('confidence')} | bbox={toggle.get('bbox')}"
                )

        critical_regions = item.get("critical_region_failures", [])
        if critical_regions:
            st.write("Regioes criticas divergentes:")
            for region in critical_regions:
                st.write(
                    f"- {region.get('name')} | match={region.get('match_ratio')} | "
                    f"min={region.get('min_match')} | bbox={region.get('bbox')}"
                )


def render_hmi_validation_page(base_dir: str, data_root: str) -> None:
    cache_root = os.path.join(data_root, "hmi_cache")
    os.makedirs(cache_root, exist_ok=True)

    if "hmi_figma_dir" not in st.session_state:
        st.session_state["hmi_figma_dir"] = ""
    if "hmi_index_path" not in st.session_state:
        st.session_state["hmi_index_path"] = ""

    _title(
        "Validacao HMI",
        "Comparacao precisa tela a tela entre capturas do radio e a biblioteca local de telas exportadas do Figma.",
    )

    current_index = _load_index_if_exists(st.session_state.get("hmi_index_path", ""))
    tests = _list_tests(data_root)
    reports_count = sum(1 for _, categoria, teste in tests if _report_exists(os.path.join(data_root, categoria, teste)))

    st.markdown("<div class='hero'>", unsafe_allow_html=True)
    hero1, hero2, hero3 = st.columns(3)
    with hero1:
        _stat_card(
            "Biblioteca ativa",
            str(current_index.get("screen_count", 0) if current_index else 0),
            os.path.basename(current_index.get("figma_dir", "")) if current_index else "Nenhuma biblioteca indexada",
        )
    with hero2:
        _stat_card("Execucoes com resultados", str(reports_count), "Relatorios HMI disponiveis")
    with hero3:
        _stat_card("Modo", "Estrito", "Comparacao ponto a ponto com alinhamento")
    st.markdown("</div>", unsafe_allow_html=True)

    tabs = st.tabs(["Biblioteca Figma", "Executar Validacao", "Resultados"])

    with tabs[0]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        left, right = st.columns([2, 1])
        with left:
            st.markdown("<div class='section-title'>Fonte oficial das telas HMI</div>", unsafe_allow_html=True)
            figma_dir = st.text_input(
                "Pasta local com exports do Figma",
                value=st.session_state.get("hmi_figma_dir", ""),
                placeholder=r"C:\projeto\figma_exports",
            )
            st.session_state["hmi_figma_dir"] = figma_dir.strip()
            suggested_name = _slugify(os.path.basename(figma_dir) or "biblioteca_hmi")
            index_name = st.text_input("Nome do indice local", value=suggested_name)
            st.markdown(
                "<div class='hint'>"
                "Cada PNG pode ter um arquivo lado a lado <code>.meta.json</code> com "
                "<code>critical_regions</code> e <code>ignore_regions</code>."
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("Indexar biblioteca", key="indexar_hmi"):
                if not figma_dir.strip():
                    st.error("Informe a pasta dos exports do Figma.")
                else:
                    index_path = os.path.join(cache_root, f"{_slugify(index_name)}.json")
                    try:
                        index = build_library_index(figma_dir.strip(), index_path)
                        st.session_state["hmi_index_path"] = index_path
                        st.success(f"Biblioteca indexada com {index['screen_count']} tela(s).")
                    except Exception as exc:
                        st.error(f"Falha ao indexar biblioteca: {exc}")
        with right:
            st.markdown("<div class='section-title'>Camadas da comparacao</div>", unsafe_allow_html=True)
            st.write("- alinhamento automatico")
            st.write("- analise pixel a pixel em LAB")
            st.write("- grade estrutural")
            st.write("- comparacao de bordas")
            st.write("- componentes e regioes criticas")
        st.markdown("</div>", unsafe_allow_html=True)

        current_index = _load_index_if_exists(st.session_state.get("hmi_index_path", ""))
        if current_index:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.write(f"Indice ativo: `{st.session_state['hmi_index_path']}`")
            col1, col2, col3 = st.columns(3)
            col1.metric("Telas", current_index.get("screen_count", 0))
            col2.metric("Gerado em", current_index.get("generated_at", "N/A"))
            col3.metric("Pasta Figma", os.path.basename(current_index.get("figma_dir", "")) or "-")

            preview_rows = [
                {
                    "screen_id": screen.get("screen_id"),
                    "arquivo": screen.get("relative_path"),
                    "resolucao": f"{screen.get('width')}x{screen.get('height')}",
                    "edge_density": screen.get("edge_density"),
                }
                for screen in current_index.get("screens", [])[:20]
            ]
            if preview_rows:
                st.dataframe(preview_rows, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

    label_map = {label: (categoria, teste) for label, categoria, teste in tests}

    with tabs[1]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if not tests:
            st.warning("Nenhuma execucao com pasta de resultados encontrada em Data/.")
        else:
            left, right = st.columns([1.6, 1])
            with left:
                st.markdown("<div class='section-title'>Selecao da execucao</div>", unsafe_allow_html=True)
                selected_label = st.selectbox("Execucao a validar", options=list(label_map.keys()), index=0)
            with right:
                st.markdown("<div class='section-title'>Perfil de comparacao</div>", unsafe_allow_html=True)
                mode = st.selectbox("Modo", ["Estrito", "Balanceado"], index=0)

            categoria, teste = label_map[selected_label]
            test_dir = os.path.join(data_root, categoria, teste)
            screens = collect_result_screens(test_dir)
            st.caption(f"Capturas encontradas: {len(screens)}")

            cfg_col1, cfg_col2, cfg_col3 = st.columns(3)
            default_top_k = 8 if mode == "Estrito" else 5
            default_pass = 0.93 if mode == "Estrito" else 0.88
            default_warn = 0.82 if mode == "Estrito" else 0.74
            top_k = cfg_col1.number_input("Top candidatos", min_value=1, max_value=20, value=default_top_k)
            pass_threshold = cfg_col2.slider("Threshold PASS", min_value=0.50, max_value=0.99, value=default_pass)
            warning_threshold = cfg_col3.slider("Threshold WARNING", min_value=0.30, max_value=0.95, value=default_warn)

            cfg_col4, cfg_col5, cfg_col6 = st.columns(3)
            point_tolerance = cfg_col4.slider("Tolerancia pixel", min_value=4, max_value=40, value=18 if mode == "Estrito" else 22)
            exact_match_ratio = cfg_col5.slider(
                "Pixel match minimo",
                min_value=0.900,
                max_value=0.999,
                value=0.985 if mode == "Estrito" else 0.965,
            )
            min_cell_score = cfg_col6.slider(
                "Pior celula minima",
                min_value=0.700,
                max_value=0.999,
                value=0.920 if mode == "Estrito" else 0.860,
            )

            if st.button("Validar execucao HMI", key="validar_hmi"):
                library_index = _load_index_if_exists(st.session_state.get("hmi_index_path", ""))
                if library_index is None:
                    st.error("Indexe uma biblioteca do Figma antes de validar.")
                elif not screens:
                    st.error("Nenhuma screenshot encontrada para esta execucao.")
                else:
                    cfg = ValidationConfig(
                        top_k=int(top_k),
                        pass_threshold=float(pass_threshold),
                        warning_threshold=float(warning_threshold),
                        point_tolerance=float(point_tolerance),
                        exact_match_ratio=float(exact_match_ratio),
                        min_cell_score=float(min_cell_score),
                    )
                    with st.spinner("Comparando telas capturadas com a biblioteca Figma..."):
                        result = validate_execution_images(screens, library_index, cfg)
                        report_path = save_validation_report(test_dir, library_index, result)
                    st.success(f"Validacao finalizada. Relatorio salvo em {report_path}")

        st.markdown("</div>", unsafe_allow_html=True)

    with tabs[2]:
        if not tests:
            st.info("Sem resultados HMI disponiveis.")
            return

        result_options = [label for label, categoria, teste in tests if _report_exists(os.path.join(data_root, categoria, teste))]
        if not result_options:
            st.info("Nenhum relatorio HMI gerado ainda.")
            return

        selected_report = st.selectbox("Execucao com relatorio HMI", options=result_options, index=0)
        categoria, teste = label_map[selected_report]
        test_dir = os.path.join(data_root, categoria, teste)
        try:
            report = load_validation_report(test_dir)
        except Exception as exc:
            st.error(f"Falha ao ler resultado HMI: {exc}")
            return

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        _show_summary(report.get("summary", {}))
        st.caption(f"Biblioteca usada: {report.get('figma_dir', '-')}")
        rows = []
        for item in report.get("items", []):
            diff_summary = item.get("diff_summary", {})
            scores = item.get("scores", {})
            rows.append(
                {
                    "arquivo": os.path.basename(item.get("screenshot_path", "")),
                    "status": item.get("status"),
                    "match_figma": item.get("screen_name"),
                    "score_final": f"{scores.get('final', 0.0) * 100:.2f}%",
                    "pixel_match": f"{diff_summary.get('pixel_match_ratio', 0.0) * 100:.2f}%",
                    "area_divergente": f"{diff_summary.get('diff_area_ratio', 0.0) * 100:.3f}%",
                }
            )
        if rows:
            st.dataframe(rows, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        for item in report.get("items", []):
            _show_item(item)


def main() -> None:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_root = os.path.join(base_dir, "Data")
    st.set_page_config(page_title="Validacao HMI", page_icon="", layout="wide")
    render_hmi_validation_page(base_dir, data_root)


if __name__ == "__main__":
    main()
