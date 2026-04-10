from __future__ import annotations

import json
import os
from typing import Any, Callable

import cv2
import numpy as np
import streamlit as st
from PIL import Image

from .helpers import clean_display_text


OpenFolderFn = Callable[[str], tuple[bool, str]]
LoadFailureReportFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]
ResolveExistingPathFn = Callable[[str, Any, str], str | None]


def simple_similarity(img_a: Image.Image, img_b: Image.Image) -> float:
    a = img_a.convert("L")
    b = img_b.convert("L").resize(a.size)
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    diff = np.abs(arr_a - arr_b)
    score = 1.0 - (np.mean(diff) / 255.0)
    return float(max(0.0, min(1.0, score)))


def apply_ignore_mask(mask: np.ndarray, ignore_regions: list | None) -> np.ndarray:
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


def compute_diff_mask_cv(img_a: np.ndarray, img_b: np.ndarray, diff_threshold: int = 25) -> np.ndarray:
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


def find_bboxes(mask: np.ndarray, min_area: int = 200, max_area: int = 200000) -> list[tuple[int, int, int, int, float]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: list[tuple[int, int, int, int, float]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area or area > max_area:
            continue
        bboxes.append((x, y, w, h, float(area)))
    return bboxes


def is_toggle_candidate(
    bbox: tuple[int, int, int, int, float],
    img_shape: tuple[int, ...],
    aspect_min: float = 1.7,
    aspect_max: float = 5.5,
) -> bool:
    x, y, w, h, _ = bbox
    if h <= 0:
        return False
    img_h, img_w = img_shape[:2]
    ratio = w / float(h)
    if not (aspect_min <= ratio <= aspect_max):
        return False
    if w < 28 or h < 12:
        return False
    if w > int(img_w * 0.35) or h > int(img_h * 0.12):
        return False
    return True


def toggle_state_by_color(img_roi: np.ndarray) -> tuple[str, float]:
    hsv = cv2.cvtColor(img_roi, cv2.COLOR_BGR2HSV)
    lower = np.array((90, 60, 60), dtype=np.uint8)
    upper = np.array((130, 255, 255), dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    if ratio >= 0.08:
        return "ON", min(1.0, ratio / 0.2)
    return "OFF", min(1.0, (0.08 - ratio) / 0.08)


def toggle_state_by_knob(img_roi: np.ndarray) -> tuple[str | None, float]:
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0
    roi_area = float(img_roi.shape[0] * img_roi.shape[1])
    best = None
    best_conf = 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 20:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = float((4.0 * np.pi * area) / (perimeter * perimeter))
        x, y, w, h = cv2.boundingRect(contour)
        if h <= 0:
            continue
        wh_ratio = w / float(h)
        area_ratio = area / roi_area
        if circularity < 0.55 or wh_ratio < 0.65 or wh_ratio > 1.45:
            continue
        if area_ratio < 0.02 or area_ratio > 0.40:
            continue
        conf = min(1.0, (circularity - 0.55) / 0.35 + 0.25)
        if conf > best_conf:
            best = x + w / 2.0
            best_conf = conf
    if best is None:
        return None, 0.0
    state = "ON" if best > (img_roi.shape[1] / 2.0) else "OFF"
    return state, best_conf


def compare_images_cv(
    img_a: np.ndarray,
    img_b: np.ndarray,
    ignore_regions: list | None = None,
) -> dict[str, Any]:
    mask = compute_diff_mask_cv(img_a, img_b, diff_threshold=25)
    mask = apply_ignore_mask(mask, ignore_regions or [])
    bboxes = find_bboxes(mask)

    diffs = []
    toggles = []
    overlay = img_a.copy()
    for bbox in bboxes:
        x, y, w, h, score = bbox
        roi_a = img_a[y : y + h, x : x + w]
        roi_b = img_b[y : y + h, x : x + w]
        dtype = "generic"
        if is_toggle_candidate(bbox, img_a.shape):
            state_a_c, conf_a_c = toggle_state_by_color(roi_a)
            state_b_c, conf_b_c = toggle_state_by_color(roi_b)
            state_a_k, conf_a_k = toggle_state_by_knob(roi_a)
            state_b_k, conf_b_k = toggle_state_by_knob(roi_b)
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


def load_ignore_regions(esperados_dir: str) -> list:
    ignore_path = os.path.join(esperados_dir, "ignore.json")
    if not os.path.exists(ignore_path):
        return []
    try:
        with open(ignore_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, list) else []
    except Exception:
        return []


def compare_expected_with_final(
    expected_path: str,
    final_path: str,
    ignore_regions: list | None = None,
) -> dict[str, Any]:
    img_expected = Image.open(expected_path)
    img_final = Image.open(final_path)
    score = simple_similarity(img_expected, img_final)

    expected_bgr = cv2.cvtColor(np.array(img_expected), cv2.COLOR_RGB2BGR)
    final_bgr = cv2.cvtColor(np.array(img_final), cv2.COLOR_RGB2BGR)
    if final_bgr.shape[:2] != expected_bgr.shape[:2]:
        final_bgr = cv2.resize(final_bgr, (expected_bgr.shape[1], expected_bgr.shape[0]))

    diff_res = compare_images_cv(expected_bgr, final_bgr, ignore_regions=ignore_regions or [])
    expected_box = expected_bgr.copy()
    final_box = final_bgr.copy()
    for diff in diff_res["diffs"]:
        x, y, w, h = diff["bbox"]
        color = (0, 255, 0) if diff["type"] == "toggle" else (0, 200, 255)
        cv2.rectangle(expected_box, (x, y), (x + w, y + h), color, 2)
        cv2.rectangle(final_box, (x, y), (x + w, y + h), color, 2)

    return {
        "nome": os.path.basename(expected_path),
        "score": score,
        "img_exp": img_expected,
        "img_final": img_final,
        "diff_res": diff_res,
        "exp_box": cv2.cvtColor(expected_box, cv2.COLOR_BGR2RGB),
        "fin_box": cv2.cvtColor(final_box, cv2.COLOR_BGR2RGB),
    }


def render_expected_comparison(base_dir: str) -> None:
    st.subheader("Comparacao com resultados esperados")
    esperados_dir = os.path.join(base_dir, "esperados")
    final_path = os.path.join(base_dir, "resultado_final.png")

    if not os.path.exists(final_path):
        st.warning("resultado_final.png nao encontrado para comparacao.")
        return
    if not os.path.isdir(esperados_dir):
        st.info("Nenhuma pasta 'esperados' encontrada para este teste.")
        return

    esperados = [name for name in os.listdir(esperados_dir) if name.lower().endswith(".png")]
    if not esperados:
        st.info("Nenhum esperado salvo para comparacao.")
        return

    try:
        Image.open(final_path)
    except Exception:
        st.error("Falha ao abrir resultado_final.png.")
        return

    ignore_regions = load_ignore_regions(esperados_dir)
    for nome in sorted(esperados):
        expected_path = os.path.join(esperados_dir, nome)
        try:
            comp = compare_expected_with_final(expected_path, final_path, ignore_regions=ignore_regions)
        except Exception:
            st.warning(f"Falha ao comparar {nome}.")
            continue

        st.markdown(f"**Comparacao:** `{nome}` x `resultado_final.png`")
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.image(comp["img_exp"], caption=f"Esperado: {nome}", use_container_width=True)
        col2.image(comp["img_final"], caption="Resultado final", use_container_width=True)
        col3.metric("Similaridade (global)", f"{comp['score'] * 100:.1f}%")


def render_toggle_comparison(base_dir: str) -> None:
    st.subheader("Comparacao de toggles")
    esperados_dir = os.path.join(base_dir, "esperados")
    final_path = os.path.join(base_dir, "resultado_final.png")

    if not os.path.exists(final_path):
        st.info("resultado_final.png nao encontrado para comparacao de toggles.")
        return
    if not os.path.isdir(esperados_dir):
        st.info("Nenhuma pasta 'esperados' encontrada para avaliar toggles.")
        return

    esperados = sorted(name for name in os.listdir(esperados_dir) if name.lower().endswith(".png"))
    if not esperados:
        st.info("Nenhuma imagem esperada disponivel para comparar toggles.")
        return

    ignore_regions = load_ignore_regions(esperados_dir)
    resultados = []
    for nome in esperados:
        expected_path = os.path.join(esperados_dir, nome)
        try:
            resultados.append(compare_expected_with_final(expected_path, final_path, ignore_regions=ignore_regions))
        except Exception:
            st.warning(f"Falha ao avaliar toggles em {nome}.")

    if not resultados:
        st.info("Nao foi possivel gerar a comparacao de toggles desta execucao.")
        return

    total_toggles = sum(len(item["diff_res"]["toggle_changes"]) for item in resultados)
    com_divergencia = sum(1 for item in resultados if item["diff_res"]["toggle_changes"])
    sem_divergencia = len(resultados) - com_divergencia

    if total_toggles > 0:
        resumo = (
            f"Foram detectados {total_toggles} toggle(s) divergente(s) em "
            f"{com_divergencia} comparacao(oes) desta execucao. "
            "Revise os cards abaixo antes de aprovar o resultado."
        )
        badge = (
            "<span class='signal-badge' "
            "style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            "Toggle divergente detectado"
            "</span>"
        )
        banner_style = (
            "background:linear-gradient(135deg, rgba(127, 29, 29, 0.92), rgba(69, 10, 10, 0.88));"
            "border:1px solid rgba(248, 113, 113, 0.45);"
        )
    else:
        resumo = (
            f"As {len(resultados)} comparacao(oes) avaliadas nao apresentaram divergencia de toggle. "
            "O comportamento visual desta execucao permaneceu consistente."
        )
        badge = (
            "<span class='signal-badge' "
            "style='background:#22c55e20;border-color:#22c55e66;color:#bbf7d0;'>"
            "Sem divergencia de toggle"
            "</span>"
        )
        banner_style = (
            "background:linear-gradient(135deg, rgba(6, 78, 59, 0.92), rgba(2, 44, 34, 0.88));"
            "border:1px solid rgba(74, 222, 128, 0.35);"
        )

    st.markdown(
        (
            f"<div class='executive-banner' style='{banner_style}'>"
            "<div class='executive-banner-title'>Resumo Executivo dos Toggles</div>"
            f"<div class='executive-banner-body'>{resumo}</div>"
            f"{badge}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Esperados analisados", str(len(resultados)))
    m2.metric("Comparacoes sem divergencia", str(sem_divergencia))
    m3.metric("Comparacoes com divergencia", str(com_divergencia))
    m4.metric("Toggles divergentes", str(total_toggles))

    for item in resultados:
        nome = item["nome"]
        diff_res = item["diff_res"]
        toggle_count = len(diff_res["toggle_changes"])
        status = "Divergencia detectada" if toggle_count else "Sem divergencia"
        status_prefix = "error" if toggle_count else "success"
        with st.expander(f"{nome} | {status} | similaridade {item['score'] * 100:.1f}%"):
            c1, c2, c3 = st.columns(3)
            c1.image(item["exp_box"], caption="Esperado (com boxes)", use_container_width=True)
            c2.image(item["fin_box"], caption="Resultado final (com boxes)", use_container_width=True)
            c3.image(diff_res["diff_mask"], caption="Mascara de diferencas", use_container_width=True)

            if toggle_count:
                getattr(st, status_prefix)(
                    f"{toggle_count} toggle(s) divergente(s) detectado(s) nesta comparacao."
                )
                for toggle in diff_res["toggle_changes"]:
                    st.write(
                        f"- {toggle['stateA']} -> {toggle['stateB']} | "
                        f"conf={toggle['confidence']} | bbox={toggle['bbox']}"
                    )
            else:
                getattr(st, status_prefix)("Nenhum toggle divergente detectado.")


def render_final_validation(execucao: list[dict[str, Any]], base_dir: str) -> None:
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


def _render_text_block(text: Any, fallback: str = "-") -> None:
    cleaned = clean_display_text(text)
    if not cleaned:
        st.caption(fallback)
        return
    st.markdown(cleaned.replace("\n", "  \n"))


def render_failure_report(
    base_dir: str,
    selected: str,
    status_payload: dict[str, Any],
    *,
    load_failure_report: LoadFailureReportFn,
    open_folder: OpenFolderFn,
    resolve_existing_path: ResolveExistingPathFn,
) -> None:
    st.subheader("Relatorio estruturado da falha")
    bundle = load_failure_report(base_dir, status_payload)
    report = bundle.get("report") or {}
    resultado_final = clean_display_text(status_payload.get("resultado_final")).lower()

    if not report:
        if resultado_final == "reprovado":
            detalhe = bundle.get("error") or "Execucao reprovada sem artefato estruturado disponivel."
            st.warning(detalhe)
        else:
            st.info("Nenhum relatorio de falha disponivel para esta execucao.")
        return

    dashboard_summary = report.get("dashboard_summary") or {}
    radio_log = report.get("radio_log") or {}

    st.error(bundle.get("short_text") or report.get("short_text") or "Falha detectada nesta execucao.")
    if bundle.get("generated_at"):
        st.caption(f"Relatorio gerado em {bundle['generated_at']}")

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("Abrir pasta do relatorio", key=f"open_failure_report_{selected}"):
            report_dir = bundle.get("report_dir")
            if not report_dir:
                st.error("Pasta do relatorio nao encontrada.")
            else:
                ok_open, detalhe_open = open_folder(str(report_dir))
                if ok_open:
                    st.success(f"Pasta aberta: {report_dir}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")
    with action_col2:
        if st.button("Abrir logs do radio da falha", key=f"open_failure_radio_logs_{selected}"):
            radio_dir = resolve_existing_path(
                base_dir,
                radio_log.get("capture_dir") or radio_log.get("capture_dir_relative") or status_payload.get("log_capture_dir"),
                "dir",
            )
            if not radio_dir:
                st.error("Pasta de logs do radio nao encontrada.")
            else:
                ok_open, detalhe_open = open_folder(str(radio_dir))
                if ok_open:
                    st.success(f"Pasta aberta: {radio_dir}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Resultado", str(dashboard_summary.get("resultado_final") or "REPROVADO").upper())
    m2.metric("Divergencias", str(dashboard_summary.get("failed_actions") or report.get("summary", {}).get("failed_actions") or 0))
    m3.metric("Acoes avaliadas", str(dashboard_summary.get("total_actions") or report.get("summary", {}).get("total_actions") or 0))
    avg_similarity = float(dashboard_summary.get("average_similarity", 0.0) or 0.0)
    m4.metric("Similaridade media", f"{avg_similarity:.3f}")

    st.markdown("##### Pre-condicao")
    _render_text_block(report.get("precondition"))

    st.markdown("##### Acoes executadas")
    operation_steps = report.get("operation_steps") or []
    if operation_steps:
        with st.expander("Ver sequencia executada", expanded=True):
            for idx, step in enumerate(operation_steps, start=1):
                st.write(f"{idx}. {clean_display_text(step)}")
    else:
        st.caption("Nenhuma acao consolidada no relatorio.")

    col_result_1, col_result_2 = st.columns(2)
    with col_result_1:
        st.markdown("##### Resultado do teste")
        _render_text_block(report.get("test_result"))
    with col_result_2:
        st.markdown("##### Resultado esperado")
        _render_text_block(report.get("expected_result"))

    st.markdown("##### Resultado obtido")
    _render_text_block(report.get("actual_results"))

    st.markdown("##### Log do radio")
    _render_text_block(radio_log.get("summary"))
    if radio_log.get("metadata"):
        with st.expander("Metadados da captura de logs"):
            st.json(radio_log["metadata"])
    if radio_log.get("files"):
        with st.expander("Arquivos indexados da falha"):
            for item in radio_log["files"]:
                st.write(clean_display_text(item))

    path_lines = []
    if bundle.get("json_path"):
        path_lines.append(f"JSON: {bundle['json_path']}")
    if bundle.get("markdown_path"):
        path_lines.append(f"Markdown: {bundle['markdown_path']}")
    if bundle.get("csv_path"):
        path_lines.append(f"CSV: {bundle['csv_path']}")
    if path_lines:
        st.caption(" | ".join(path_lines))


__all__ = [
    "compare_expected_with_final",
    "compare_images_cv",
    "find_bboxes",
    "render_expected_comparison",
    "render_failure_report",
    "render_final_validation",
    "render_toggle_comparison",
    "simple_similarity",
]
