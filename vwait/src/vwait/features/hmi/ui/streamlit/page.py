import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageChops
from vwait.core.paths import TESTER_RUNS_ROOT, hmi_cache_dir, resolve_tester_run_dir
from vwait.platform.adb import resolve_adb_path
from vwait.core.config.ui_theme import apply_dark_background

DEFAULT_HMI_LIBRARY_DIR = "/home/victor-milani/GEI - IMGs"
PROJECT_ROOT = Path(__file__).resolve().parents[6]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    USER32 = ctypes.windll.user32
    KERNEL32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

else:
    ctypes = None
    wintypes = None
    USER32 = None
    KERNEL32 = None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    POINT = None
    RECT = None

def _subprocess_windowless_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _load_hmi_modules() -> Dict[str, Any]:
    from vwait.features.hmi.application import (
        ValidationConfig,
        build_validation_dimension_rows,
        build_validation_dimension_workbook,
        build_library_index,
        collect_result_screens,
        evaluate_single_screenshot,
        get_backend_status,
        get_validation_dir,
        load_library_index,
        load_validation_report,
        save_validation_report,
        validate_execution_images,
    )

    return {
        "get_backend_status": get_backend_status,
        "ValidationConfig": ValidationConfig,
        "collect_result_screens": collect_result_screens,
        "evaluate_single_screenshot": evaluate_single_screenshot,
        "validate_execution_images": validate_execution_images,
        "build_library_index": build_library_index,
        "load_library_index": load_library_index,
        "build_validation_dimension_rows": build_validation_dimension_rows,
        "build_validation_dimension_workbook": build_validation_dimension_workbook,
        "get_validation_dir": get_validation_dir,
        "load_validation_report": load_validation_report,
        "save_validation_report": save_validation_report,
    }


def _load_visual_qa_modules() -> Dict[str, Any]:
    from vwait.features.visual_qa.application.use_cases.build_vector_index import BuildVectorIndex
    from vwait.features.visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
    from vwait.features.visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
    from vwait.features.visual_qa.config import VisualQaConfig, load_config
    from vwait.features.visual_qa.infrastructure.embeddings.factory import build_embedding_provider
    from vwait.features.visual_qa.infrastructure.llm.factory import build_report_generator
    from vwait.features.visual_qa.infrastructure.llm.null_report_generator import NullReportGenerator
    from vwait.features.visual_qa.infrastructure.pixel_compare.existing_pixel_adapter import ExistingPixelAdapter
    from vwait.features.visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore
    from vwait.features.visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository

    return {
        "BuildVectorIndex": BuildVectorIndex,
        "ClassifyScreenshot": ClassifyScreenshot,
        "ValidateScreenshot": ValidateScreenshot,
        "VisualQaConfig": VisualQaConfig,
        "load_config": load_config,
        "build_embedding_provider": build_embedding_provider,
        "build_report_generator": build_report_generator,
        "NullReportGenerator": NullReportGenerator,
        "ExistingPixelAdapter": ExistingPixelAdapter,
        "LocalArtifactStore": LocalArtifactStore,
        "FaissVectorIndexRepository": FaissVectorIndexRepository,
    }


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _scrcpy_target_window_title() -> str:
    return _safe_str(os.getenv("SCRCPY_TARGET_WINDOW_TITLE"), "malagueta").strip().lower() or "malagueta"


def _window_text(hwnd: Any) -> str:
    if not USER32 or not hwnd:
        return ""
    length = USER32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    USER32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _query_process_image_name(pid: int) -> str:
    if not KERNEL32 or not pid:
        return ""
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if KERNEL32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.strip()
    except Exception:
        return ""
    finally:
        KERNEL32.CloseHandle(handle)
    return ""


def _window_client_bbox(hwnd: Any) -> tuple[int, int, int, int] | None:
    if not USER32 or not hwnd or RECT is None or POINT is None:
        return None
    rect = RECT()
    if not USER32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    top_left = POINT(0, 0)
    bottom_right = POINT(rect.right, rect.bottom)
    if not USER32.ClientToScreen(hwnd, ctypes.byref(top_left)):
        return None
    if not USER32.ClientToScreen(hwnd, ctypes.byref(bottom_right)):
        return None
    left = int(top_left.x)
    top = int(top_left.y)
    right = int(bottom_right.x)
    bottom = int(bottom_right.y)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _find_scrcpy_window_info() -> Dict[str, Any]:
    if not USER32:
        return {}
    matches: list[Dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_windows(hwnd, _lparam):
        try:
            if not USER32.IsWindowVisible(hwnd):
                return True
            title = _window_text(hwnd)
            pid = wintypes.DWORD(0)
            USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_path = _query_process_image_name(int(pid.value))
            process_name = os.path.basename(process_path).lower() if process_path else ""
            title_norm = title.strip().lower()
            if "scrcpy" not in process_name and "scrcpy" not in title_norm:
                return True
            matches.append(
                {
                    "hwnd": hwnd,
                    "title": title,
                    "pid": int(pid.value),
                    "process_name": process_name,
                    "process_path": process_path,
                    "is_iconic": bool(USER32.IsIconic(hwnd)),
                }
            )
        except Exception:
            return True
        return True

    USER32.EnumWindows(enum_windows, 0)
    if not matches:
        return {}

    target_title = _scrcpy_target_window_title()

    def _window_rank(item: Dict[str, Any]) -> tuple[int, int, int, int, int]:
        bbox = _window_client_bbox(item.get("hwnd"))
        area = 0
        if bbox:
            area = max(0, int(bbox[2] - bbox[0])) * max(0, int(bbox[3] - bbox[1]))
        title = _safe_str(item.get("title")).strip().lower()
        is_iconic = bool(item.get("is_iconic"))
        not_iconic = 1 if not is_iconic else 0
        has_client_bbox = 1 if bbox else 0
        exact_target = 1 if target_title and title == target_title and not is_iconic else 0
        titled_device = 1 if title and title != "scrcpy" and not is_iconic else 0
        return (not_iconic, has_client_bbox, exact_target, titled_device, area)

    return max(matches, key=_window_rank)


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "biblioteca"


def _list_tests(data_root: str):
    rows = []
    runs_root = str(TESTER_RUNS_ROOT)
    if not os.path.isdir(runs_root):
        return rows
    for categoria in sorted(os.listdir(runs_root)):
        cat_path = os.path.join(runs_root, categoria)
        if not os.path.isdir(cat_path):
            continue
        for teste in sorted(os.listdir(cat_path)):
            test_path = resolve_tester_run_dir(categoria, teste)
            if test_path and os.path.isdir(test_path):
                rows.append((f"{categoria}/{teste}", categoria, teste))
    return rows


def _safe_show_image(path: Optional[str], caption: str, empty_message: str) -> None:
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as image_file:
                image_bytes = image_file.read()
            if image_bytes:
                st.image(image_bytes, caption=caption, use_container_width=True)
                return
            with Image.open(path) as image:
                st.image(image.copy(), caption=caption, use_container_width=True)
            return
        except Exception:
            pass
    st.info(empty_message)


def _show_image_payload(payload: Any, caption: str, empty_message: str) -> None:
    if isinstance(payload, str):
        _safe_show_image(payload, caption, empty_message)
        return
    if isinstance(payload, np.ndarray):
        try:
            st.image(payload, caption=caption, use_container_width=True)
            return
        except Exception:
            pass
    st.info(empty_message)


def _build_visual_diff_image(actual_path: Any, reference_path: Any) -> Image.Image | None:
    if not isinstance(actual_path, str) or not isinstance(reference_path, str):
        return None
    if not os.path.exists(actual_path) or not os.path.exists(reference_path):
        return None
    try:
        actual = Image.open(actual_path).convert("RGB")
        reference = Image.open(reference_path).convert("RGB")
        if actual.size != reference.size:
            actual = actual.resize(reference.size)
        return ImageChops.difference(reference, actual)
    except Exception:
        return None


def _load_rgb_image(path: Any) -> np.ndarray | None:
    if not isinstance(path, str) or not os.path.exists(path):
        return None
    try:
        with Image.open(path) as image:
            return np.array(image.convert("RGB"))
    except Exception:
        return None


def _estimate_visual_shift_px(actual_path: Any, reference_path: Any) -> tuple[float, float] | None:
    actual = _load_rgb_image(actual_path)
    reference = _load_rgb_image(reference_path)
    if actual is None or reference is None:
        return None
    if actual.shape[:2] != reference.shape[:2]:
        actual = cv2.resize(actual, (reference.shape[1], reference.shape[0]))
    try:
        actual_gray = cv2.cvtColor(actual, cv2.COLOR_RGB2GRAY).astype(np.float32)
        reference_gray = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY).astype(np.float32)
        shift, _response = cv2.phaseCorrelate(reference_gray, actual_gray)
        return float(shift[0]), float(shift[1])
    except Exception:
        return None


def _visual_diff_regions(result: Dict[str, Any], limit: int = 12) -> list[Dict[str, Any]]:
    debug_images = result.get("debug_images") or {}
    mask = debug_images.get("diff_mask")
    if not isinstance(mask, np.ndarray):
        actual = _load_rgb_image(result.get("screenshot_path"))
        reference = _load_rgb_image(result.get("reference_path"))
        if actual is None or reference is None:
            return []
        if actual.shape[:2] != reference.shape[:2]:
            actual = cv2.resize(actual, (reference.shape[1], reference.shape[0]))
        diff = cv2.absdiff(reference, actual)
        gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
        _, mask = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
    mask = np.where(mask > 0, 255, 0).astype(np.uint8)
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: list[Dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area <= 4:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        regions.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "area_px": int(area),
                "center_x": int(x + w / 2),
                "center_y": int(y + h / 2),
            }
        )
    return sorted(regions, key=lambda item: item["area_px"], reverse=True)[:limit]


def _difference_severity_label(diff_area_ratio: float, toggle_count: int, critical_count: int) -> str:
    if critical_count > 0:
        return "Região crítica alterada"
    if toggle_count > 0:
        return "Componente/toggle alterado"
    if diff_area_ratio >= 0.08:
        return "Diferença visual alta"
    if diff_area_ratio >= 0.02:
        return "Diferença visual moderada"
    if diff_area_ratio > 0:
        return "Diferença visual baixa"
    return "Sem diferença relevante"


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value or 0.0):.2%}"
    except Exception:
        return "-"


def _render_hmi_difference_details(result: Dict[str, Any]) -> None:
    screenshot_path = result.get("screenshot_path")
    reference_path = result.get("reference_path")
    diff_summary = result.get("diff_summary") or {}
    toggle_changes = result.get("toggle_changes") or []
    critical_failures = result.get("critical_region_failures") or []
    diff_image = _build_visual_diff_image(screenshot_path, reference_path)
    debug_images = result.get("debug_images") or {}
    regions = _visual_diff_regions(result)
    visual_shift = _estimate_visual_shift_px(screenshot_path, reference_path)

    if not diff_summary and diff_image is None:
        return

    status = _safe_str(result.get("status"), "SEM_STATUS").upper()
    similarity = float((result.get("scores") or {}).get("final", 0.0) or 0.0)
    changed_pixels = int(diff_summary.get("changed_pixels", 0) or 0)
    diff_count = int(diff_summary.get("diff_count", 0) or 0)
    toggle_count = int(diff_summary.get("toggle_count", 0) or 0)
    critical_count = len(critical_failures)
    diff_area_ratio = float(diff_summary.get("diff_area_ratio", 0.0) or 0.0)
    severity = _difference_severity_label(diff_area_ratio, toggle_count, critical_count)

    st.markdown("#### O que mudou entre as telas")
    if status == "PASS":
        st.success(f"{severity}. Similaridade final: {similarity:.3f}")
    elif "WARNING" in status:
        st.warning(f"{severity}. Similaridade final: {similarity:.3f}")
    else:
        st.error(f"{severity}. Similaridade final: {similarity:.3f}")

    metric_cols = st.columns(6)
    metric_cols[0].metric("Área divergente", _format_percent(diff_area_ratio))
    metric_cols[1].metric("Pixel match", _format_percent(diff_summary.get("pixel_match_ratio")))
    metric_cols[2].metric("Pixels alterados", f"{changed_pixels:,}".replace(",", "."))
    metric_cols[3].metric("Regiões visuais", str(len(regions) or diff_count))
    metric_cols[4].metric("Toggles/componentes", str(toggle_count))
    if visual_shift:
        metric_cols[5].metric("Deslocamento", f"x {visual_shift[0]:+.1f}px | y {visual_shift[1]:+.1f}px")
    else:
        metric_cols[5].metric("Deslocamento", "-")

    image_tabs = st.tabs(["Mapa de diferenças", "Overlay anotado", "Heatmap"])
    with image_tabs[0]:
        if diff_image is not None:
            st.image(diff_image, caption="Diferença pixel a pixel entre referência e captura real", use_container_width=True)
        else:
            st.info("Mapa visual de diferenças indisponível para este resultado.")
    with image_tabs[1]:
        overlay = debug_images.get("overlay")
        if overlay is not None:
            _show_image_payload(overlay, "Overlay com regiões divergentes e pior célula", "Overlay indisponível")
        else:
            st.info("Overlay anotado indisponível para este resultado.")
    with image_tabs[2]:
        heatmap = debug_images.get("heatmap")
        if heatmap is None:
            heatmap = debug_images.get("diff_mask")
        if heatmap is not None:
            _show_image_payload(heatmap, "Mapa de calor das diferenças", "Heatmap indisponível")
        else:
            st.info("Heatmap indisponível para este resultado.")

    if critical_failures:
        st.markdown("##### Regiões críticas alteradas")
        for idx, region in enumerate(critical_failures, start=1):
            st.caption(
                f"Região crítica {idx}: {region.get('name', 'critical_region')} em bbox={region.get('bbox')}, "
                f"match={_format_percent(region.get('match_ratio'))}, mínimo={_format_percent(region.get('min_match'))}."
            )


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _save_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _save_uploaded_image(uploaded_file: Any, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(uploaded_file.getbuffer())


def _run_demo_compare(
    hmi: Dict[str, Any],
    cache_root: str,
    expected_upload: Any,
    actual_upload: Any,
    feature_context: str,
    screen_name: str,
    cfg: Any,
) -> Dict[str, Any]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    demo_dir = os.path.join(cache_root, "demo_compare", run_id)
    reference_dir = os.path.join(demo_dir, "reference")

    expected_ext = os.path.splitext(_safe_str(getattr(expected_upload, "name", "")))[1].lower() or ".png"
    actual_ext = os.path.splitext(_safe_str(getattr(actual_upload, "name", "")))[1].lower() or ".png"
    expected_path = os.path.join(reference_dir, f"expected{expected_ext}")
    actual_path = os.path.join(demo_dir, f"actual{actual_ext}")

    _save_uploaded_image(expected_upload, expected_path)
    _save_uploaded_image(actual_upload, actual_path)

    _save_json(
        os.path.splitext(expected_path)[0] + ".meta.json",
        {
            "screen_id": "demo/expected",
            "name": screen_name or "Tela esperada",
            "feature_context": feature_context or "demo",
            "tags": ["demo", feature_context or "demo"],
        },
    )

    index_path = os.path.join(demo_dir, "demo_library.json")
    library_index = hmi["build_library_index"](reference_dir, index_path, enable_semantic=True, enable_ocr=True)
    validation_result = hmi["validate_execution_images"]([actual_path], library_index, cfg)
    report_path = hmi["save_validation_report"](demo_dir, library_index, validation_result)
    report = hmi["load_validation_report"](demo_dir)
    return {
        "demo_dir": demo_dir,
        "report_path": report_path,
        "report": report,
        "index_path": index_path,
    }


def _resolve_hmi_library(
    hmi: Dict[str, Any],
    cache_root: str,
    figma_dir: str,
    index_name: str,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    index_path = os.path.join(cache_root, f"{_slugify(index_name)}.json")
    if os.path.exists(index_path):
        try:
            cached = hmi["load_library_index"](index_path)
            cached_root = _safe_str(cached.get("figma_dir"))
            if figma_dir and os.path.abspath(cached_root) == os.path.abspath(figma_dir):
                return index_path, cached
        except Exception:
            pass
    if not figma_dir or not os.path.isdir(figma_dir):
        return None, None
    index = hmi["build_library_index"](figma_dir, index_path, enable_semantic=True, enable_ocr=True)
    return index_path, index


def _load_live_runtime_library(
    hmi: Dict[str, Any],
    cache_root: str,
    serial: str,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    state = _load_live_monitor_state(cache_root, serial)
    index_path = _safe_str(state.get("index_path") or st.session_state.get("hmi_index_path"))
    if not index_path or not os.path.exists(index_path):
        return None, None
    try:
        return index_path, hmi["load_library_index"](index_path)
    except Exception:
        return None, None


def _live_ui_session_token() -> str:
    token = _safe_str(st.session_state.get("hmi_live_ui_session_token"))
    if token:
        return token
    token = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    st.session_state["hmi_live_ui_session_token"] = token
    return token


def _run_demo_context_discovery(
    hmi: Dict[str, Any],
    cache_root: str,
    actual_upload: Any,
    library_index: Dict[str, Any],
    cfg: Any,
) -> Dict[str, Any]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    demo_dir = os.path.join(cache_root, "demo_context", run_id)
    actual_ext = os.path.splitext(_safe_str(getattr(actual_upload, "name", "")))[1].lower() or ".png"
    actual_path = os.path.join(demo_dir, f"actual{actual_ext}")
    _save_uploaded_image(actual_upload, actual_path)
    validation_result = hmi["validate_execution_images"]([actual_path], library_index, cfg)
    report_path = hmi["save_validation_report"](demo_dir, library_index, validation_result)
    report = hmi["load_validation_report"](demo_dir)
    return {
        "demo_dir": demo_dir,
        "report_path": report_path,
        "report": report,
        "index_path": _safe_str(library_index.get("figma_dir")),
    }


def _run_library_similarity_lookup(
    hmi: Dict[str, Any],
    cache_root: str,
    actual_upload: Any,
    library_index: Dict[str, Any],
    cfg: Any,
) -> Dict[str, Any]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    lookup_dir = os.path.join(cache_root, "library_lookup", run_id)
    actual_ext = os.path.splitext(_safe_str(getattr(actual_upload, "name", "")))[1].lower() or ".png"
    actual_path = os.path.join(lookup_dir, f"actual{actual_ext}")
    _save_uploaded_image(actual_upload, actual_path)
    result = hmi["evaluate_single_screenshot"](actual_path, library_index, cfg)
    return {
        "lookup_dir": lookup_dir,
        "actual_path": actual_path,
        "result": result,
    }


def _build_validation_summary(items: list[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(items)
    passed = sum(1 for item in items if _safe_str(item.get("status")).upper() == "PASS")
    warnings = sum(1 for item in items if _safe_str(item.get("status")).upper() == "PASS_WITH_WARNINGS")
    failed = max(0, total - passed - warnings)
    average_score = (
        sum(float((item.get("scores") or {}).get("final", 0.0) or 0.0) for item in items) / float(max(total, 1))
    )
    average_pixel_match = (
        sum(float((item.get("diff_summary") or {}).get("pixel_match_ratio", 0.0) or 0.0) for item in items)
        / float(max(total, 1))
    )
    semantic_scores = [
        float((item.get("diff_summary") or {}).get("semantic_score"))
        for item in items
        if (item.get("diff_summary") or {}).get("semantic_score") is not None
    ]
    critical_failures = sum(len(item.get("critical_region_failures") or []) for item in items)
    component_failures = sum(
        1 for item in items if _safe_str(item.get("status")).upper() == "FAIL_COMPONENT_STATE"
    )
    context_confidence = [
        float((item.get("stage1") or {}).get("context_confidence", 0.0) or 0.0)
        for item in items
        if item.get("stage1") is not None
    ]
    contexts_detected: Dict[str, int] = {}
    for item in items:
        stage1 = item.get("stage1") or {}
        context = _safe_str(stage1.get("predicted_screen_type") or item.get("feature_context") or "unknown", "unknown")
        contexts_detected[context] = contexts_detected.get(context, 0) + 1

    return {
        "total_screens": total,
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "average_score": round(average_score, 4),
        "average_pixel_match": round(average_pixel_match, 4),
        "average_semantic": round(sum(semantic_scores) / float(max(len(semantic_scores), 1)), 4),
        "critical_failures": critical_failures,
        "component_failures": component_failures,
        "average_context_confidence": round(sum(context_confidence) / float(max(len(context_confidence), 1)), 4),
        "contexts_detected": contexts_detected,
        "result": "PASS" if failed == 0 else "FAIL",
    }


def _build_validation_report_payload(
    items: list[Dict[str, Any]],
    library_index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    clean_items = [item for item in items if isinstance(item, dict)]
    return {
        "generated_at": datetime.now().isoformat(),
        "figma_dir": _safe_str((library_index or {}).get("figma_dir")),
        "library_generated_at": (library_index or {}).get("generated_at"),
        "summary": _build_validation_summary(clean_items),
        "items": clean_items,
    }


def _render_lookup_results_export(
    hmi: Dict[str, Any],
    report: Optional[Dict[str, Any]],
    export_slug: str,
    caption: str,
) -> None:
    if not report:
        return
    items = report.get("items") or []
    if not items:
        return

    structured_rows = hmi["build_validation_dimension_rows"](report)
    if not structured_rows:
        return

    summary = report.get("summary") or _build_validation_summary(items)
    export_filename = f"hmi_lookup_{_slugify(export_slug)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    st.markdown("#### Resultados")
    st.caption(caption)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Screens analisadas", str(int(summary.get("total_screens", len(items)) or len(items))))
    metric_cols[1].metric("Aprovadas", str(int(summary.get("passed", 0) or 0)))
    metric_cols[2].metric("Ressalvas", str(int(summary.get("warnings", 0) or 0)))
    metric_cols[3].metric("Falhas", str(int(summary.get("failed", 0) or 0)))
    metric_cols[4].metric("Score medio", f"{float(summary.get('average_score', 0.0) or 0.0):.1%}")

    st.download_button(
        "Extrair report",
        data=hmi["build_validation_dimension_workbook"](structured_rows),
        file_name=export_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"hmi_lookup_dimension_report_{_slugify(export_slug)}",
    )
    st.dataframe(structured_rows, use_container_width=True, hide_index=True)


def _candidate_rows(result: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for idx, candidate in enumerate(result.get("candidate_results") or [], start=1):
        scores = candidate.get("scores") or {}
        diff_summary = candidate.get("diff_summary") or {}
        rows.append(
            {
                "rank": idx,
                "tela": _safe_str(candidate.get("screen_name"), "-"),
                "contexto": _safe_str(candidate.get("feature_context"), "-"),
                "similaridade": f"{float(scores.get('final', 0.0) or 0.0):.1%}",
                "pixel_match": f"{float(diff_summary.get('pixel_match_ratio', 0.0) or 0.0):.1%}",
                "status": _safe_str(candidate.get("status"), "-"),
                "arquivo": os.path.basename(_safe_str(candidate.get("reference_path"), "")),
            }
        )
    return rows


def _render_library_lookup_result(bundle: Optional[Dict[str, Any]]) -> None:
    if not bundle:
        return
    result = bundle.get("result") or {}
    if not result:
        return

    st.markdown(
        """
        <style>
        .lookup-summary-card {
            padding: 18px 20px;
            border-radius: 18px;
            border: 1px solid rgba(116, 183, 255, 0.18);
            background: linear-gradient(135deg, rgba(8, 20, 46, 0.96), rgba(6, 11, 22, 0.92));
            box-shadow: 0 18px 36px rgba(0, 0, 0, 0.24);
            margin: 0.6rem 0 1rem 0;
        }
        .lookup-strip {
            padding: 14px 18px;
            border-radius: 16px;
            background: linear-gradient(90deg, rgba(18, 90, 62, 0.92), rgba(26, 76, 53, 0.78));
            border: 1px solid rgba(117, 255, 181, 0.14);
            margin-bottom: 1rem;
            color: #eafff2;
            font-weight: 700;
        }
        .lookup-subtitle {
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: rgba(176, 215, 255, 0.72);
            margin-bottom: 0.35rem;
        }
        .lookup-title {
            font-size: 1.55rem;
            font-weight: 800;
            color: #f5f9ff;
            line-height: 1.15;
            margin-bottom: 0.4rem;
        }
        .lookup-copy {
            color: rgba(229, 238, 255, 0.82);
            font-size: 0.98rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    scores = result.get("scores") or {}
    diff_summary = result.get("diff_summary") or {}
    stage1 = result.get("stage1") or {}
    status = _safe_str(result.get("status"), "SEM_STATUS")
    best_name = _safe_str(result.get("screen_name"), "Sem correspondencia")
    similarity = float(scores.get("final", 0.0) or 0.0)
    pixel_match = float(diff_summary.get("pixel_match_ratio", 0.0) or 0.0)
    predicted_context = _safe_str(stage1.get("predicted_screen_type"), "desconhecido")

    if status == "PASS":
        st.success(f"Melhor correspondencia encontrada: {best_name} ({similarity:.1%})")
    elif "WARNING" in status:
        st.warning(f"Correspondencia com ressalvas: {best_name} ({similarity:.1%})")
    elif result.get("reference_path"):
        st.error(f"Correspondencia fraca: {best_name} ({similarity:.1%})")
    else:
        st.error("Nenhuma imagem valida da biblioteca foi aprovada para comparacao.")

    st.markdown(
        f"""
        <div class="lookup-summary-card">
            <div class="lookup-subtitle">Resultado principal</div>
            <div class="lookup-title">{best_name}</div>
            <div class="lookup-copy">
                Similaridade final <strong>{similarity:.1%}</strong> |
                Pixel match <strong>{pixel_match:.1%}</strong> |
                Status <strong>{status}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Melhor match", best_name)
    metric_cols[1].metric("Similaridade final", f"{similarity:.1%}")
    metric_cols[2].metric("Pixel match", f"{pixel_match:.1%}")
    metric_cols[3].metric("Contexto sugerido", predicted_context)

    st.caption(
        f"Status: {status} | Arquivo de referencia: {os.path.basename(_safe_str(result.get('reference_path'), '-'))}"
    )
    st.info(_context_narrative(result))

    st.markdown('<div class="lookup-strip">Comparativo visual</div>', unsafe_allow_html=True)
    top_img_cols = st.columns(2)
    with top_img_cols[0]:
        with st.container(border=True):
            st.markdown("**Screenshot real**")
            _show_image_payload(result.get("screenshot_path"), "Screenshot real", "Screenshot indisponivel")
    with top_img_cols[1]:
        with st.container(border=True):
            st.markdown("**Melhor referencia**")
            _show_image_payload(result.get("reference_path"), "Melhor referencia", "Referencia indisponivel")

    _render_hmi_difference_details(result)


def _context_narrative(item: Dict[str, Any]) -> str:
    stage1 = item.get("stage1") or {}
    predicted = _safe_str(stage1.get("predicted_screen_type"), "desconhecido")
    confidence = float(stage1.get("context_confidence", 0.0) or 0.0)
    screen_name = _safe_str(item.get("screen_name"), "sem match")
    status = _safe_str(item.get("status"), "SEM_STATUS")
    top_contexts = stage1.get("top_contexts") or []
    alternatives = [str(row.get("context")) for row in top_contexts[1:3] if row.get("context")]
    alt_text = f" Alternativas proximas: {', '.join(alternatives)}." if alternatives else ""
    if predicted in {"", "unknown", "desconhecido"}:
        return "O motor nao conseguiu definir um contexto confiavel para esta tela."
    return (
        f"Contexto mais provavel: {predicted} com confianca de {confidence:.1%}. "
        f"A melhor referencia encontrada foi '{screen_name}' e o resultado final ficou em {status}.{alt_text}"
    )


def _vqa_runs_dir(test_dir: str) -> str:
    return os.path.join(test_dir, "hmi_validation", "visual_qa_runs")


def _vqa_summary_path(test_dir: str) -> str:
    return os.path.join(test_dir, "hmi_validation", "visual_qa_summary.json")


def _vqa_index_stats(index_dir: str) -> Dict[str, Any]:
    metadata = _load_json(os.path.join(index_dir, "metadata.json")) or {}
    count = len(metadata) if isinstance(metadata, dict) else 0
    return {
        "ready": os.path.exists(os.path.join(index_dir, "index.faiss")) and os.path.exists(os.path.join(index_dir, "metadata.json")),
        "count": count,
    }


def _default_lookup_cfg(hmi: Dict[str, Any]) -> Any:
    return hmi["ValidationConfig"](
        top_k=5,
        pass_threshold=0.93,
        warning_threshold=0.82,
        point_tolerance=18.0,
        exact_match_ratio=0.985,
        min_cell_score=0.92,
        enable_context_routing=False,
        context_top_k=5,
    )


def _parse_adb_devices(raw_lines: list[str]) -> list[str]:
    devices: list[str] = []
    for line in raw_lines[1:]:
        line = str(line).strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def _list_connected_adb_devices() -> list[str]:
    adb_path = resolve_adb_path()
    try:
        raw = subprocess.check_output(
            [adb_path, "devices"],
            text=True,
            timeout=8,
            **_subprocess_windowless_kwargs(),
        ).strip().splitlines()
        return _parse_adb_devices(raw)
    except Exception:
        return []


def _get_connected_device_resolution(serial: str) -> tuple[int, int]:
    if not serial:
        return (0, 0)
    adb_path = resolve_adb_path()
    try:
        raw = subprocess.check_output(
            [adb_path, "-s", serial, "shell", "wm", "size"],
            text=True,
            timeout=8,
            **_subprocess_windowless_kwargs(),
        )
    except Exception:
        return (0, 0)
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", str(raw or ""))
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def _safe_serial_name(serial: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(serial or "sem_serial")) or "sem_serial"


DEFAULT_LIVE_CAPTURE_SIZE = (1600, 900)


def _preferred_live_capture_size(library_index: Optional[Dict[str, Any]]) -> tuple[int, int]:
    if not isinstance(library_index, dict):
        return DEFAULT_LIVE_CAPTURE_SIZE
    counts: Dict[tuple[int, int], int] = {}
    for entry in library_index.get("screens", []):
        try:
            width = int(entry.get("width", 0) or 0)
            height = int(entry.get("height", 0) or 0)
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue
        key = (width, height)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return DEFAULT_LIVE_CAPTURE_SIZE
    return max(counts.items(), key=lambda item: (item[1], item[0][0] * item[0][1]))[0]


def _latest_live_screenshot_path(cache_root: str, serial: str) -> str:
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    if not os.path.isdir(shots_dir):
        return ""
    files = [
        os.path.join(shots_dir, name)
        for name in os.listdir(shots_dir)
        if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        and not name.startswith(("hmi_watch_", "scrcpy_watch_"))
    ]
    if not files:
        return ""
    return max(files, key=os.path.getmtime)


def _live_activity_state_key(serial: str) -> str:
    return f"hmi_live_activity::{_safe_serial_name(serial)}"


def _get_live_activity_state(serial: str) -> Dict[str, Any]:
    payload = st.session_state.get(_live_activity_state_key(serial))
    if isinstance(payload, dict):
        return payload
    return {
        "phase": "idle",
        "message": "Aguardando inicio da validacao automatica.",
        "progress": 0.0,
        "started_at": time.time(),
        "updated_at": time.time(),
        "preview_path": "",
        "resolution": DEFAULT_LIVE_CAPTURE_SIZE,
    }


def _update_live_activity_state(
    serial: str,
    phase: str,
    message: str,
    progress: float,
    preview_path: str = "",
    resolution: tuple[int, int] | None = None,
) -> Dict[str, Any]:
    current = _get_live_activity_state(serial)
    now = time.time()
    payload = {
        "phase": str(phase or "idle"),
        "message": str(message or "").strip() or current.get("message") or "Aguardando atualizacao.",
        "progress": max(0.0, min(1.0, float(progress or 0.0))),
        "started_at": current.get("started_at", now) if current.get("phase") == phase else now,
        "updated_at": now,
        "preview_path": preview_path or current.get("preview_path", ""),
        "resolution": resolution or current.get("resolution") or DEFAULT_LIVE_CAPTURE_SIZE,
    }
    st.session_state[_live_activity_state_key(serial)] = payload
    return payload


def _live_lookup_root(cache_root: str, serial: str) -> str:
    return os.path.join(cache_root, "live_lookup", _safe_serial_name(serial))


def _live_lookup_shots_dir(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "screenshots")


def _live_lookup_preview_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "preview_latest.png")


def _live_lookup_results_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "results.json")


def _empty_live_lookup_results() -> Dict[str, Any]:
    return {
        "processed": [],
        "history": [],
        "full_results": [],
    }


def _load_live_lookup_results(cache_root: str, serial: str) -> Dict[str, Any]:
    return _load_json(_live_lookup_results_path(cache_root, serial)) or _empty_live_lookup_results()


def _live_lookup_full_results(payload: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [item for item in payload.get("full_results", []) if isinstance(item, dict)]


def _latest_live_result_bundle(
    cache_root: str,
    serial: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    payload = payload or _load_live_lookup_results(cache_root, serial)
    full_results = _live_lookup_full_results(payload)
    if not full_results:
        return None
    latest_result = full_results[-1]
    screenshot_path = _safe_str(latest_result.get("screenshot_path"))
    actual_path = screenshot_path if screenshot_path and os.path.exists(screenshot_path) else screenshot_path
    return {
        "lookup_dir": _live_lookup_root(cache_root, serial),
        "actual_path": actual_path,
        "result": latest_result,
    }


def _file_age_seconds(path: str) -> Optional[float]:
    if not path or not os.path.exists(path):
        return None
    try:
        return max(0.0, time.time() - float(os.path.getmtime(path)))
    except OSError:
        return None


def _refresh_scrcpy_preview(cache_root: str, serial: str) -> tuple[str, tuple[int, int] | None]:
    if not serial:
        return "", None
    adb_path = resolve_adb_path()
    preview_path = _live_lookup_preview_path(cache_root, serial)
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)
    temp_path = f"{preview_path}.tmp.png"
    try:
        with open(temp_path, "wb") as image_file:
            subprocess.run(
                [adb_path, "-s", serial, "exec-out", "screencap", "-p"],
                stdout=image_file,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=8,
                **_subprocess_windowless_kwargs(),
            )
        with Image.open(temp_path) as image:
            native_size = tuple(int(v) for v in image.size)
        os.replace(temp_path, preview_path)
        return preview_path, native_size
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        if os.path.exists(preview_path):
            try:
                with Image.open(preview_path) as image:
                    return preview_path, tuple(int(v) for v in image.size)
            except Exception:
                return preview_path, None
        return "", None


def _json_safe_value(value: Any, seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()
    value_id = id(value)
    if value_id in seen:
        return "[recursive]"
    if isinstance(value, dict):
        seen.add(value_id)
        safe_payload: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key) == "debug_images":
                safe_payload[str(key)] = {}
                continue
            safe_payload[str(key)] = _json_safe_value(item, seen)
        seen.discard(value_id)
        return safe_payload
    if isinstance(value, (list, tuple, set)):
        seen.add(value_id)
        safe_items = [_json_safe_value(item, seen) for item in value]
        seen.discard(value_id)
        return safe_items
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _compact_live_result(result: Dict[str, Any]) -> Dict[str, Any]:
    compacted = _json_safe_value(result)
    return compacted if isinstance(compacted, dict) else {}


def _live_lookup_monitor_state_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "monitor_state.json")


def _live_lookup_stop_flag(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "stop.flag")


def _live_lookup_shots_stop_flag(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_shots_dir(cache_root, serial), "stop.flag")


def _live_monitor_log_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "monitor.log")


def _reset_live_lookup_session(cache_root: str, serial: str) -> None:
    root_dir = _live_lookup_root(cache_root, serial)
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    os.makedirs(shots_dir, exist_ok=True)

    removable_names = {"manifest.jsonl", "stop.flag"}
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    for name in os.listdir(shots_dir):
        file_path = os.path.join(shots_dir, name)
        if not os.path.isfile(file_path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in image_exts or name.lower() in removable_names:
            try:
                os.remove(file_path)
            except OSError:
                pass

    for path in (
        _live_lookup_preview_path(cache_root, serial),
        _live_lookup_results_path(cache_root, serial),
        _live_lookup_monitor_state_path(cache_root, serial),
        _live_lookup_stop_flag(cache_root, serial),
        _live_lookup_shots_stop_flag(cache_root, serial),
        _live_monitor_log_path(cache_root, serial),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    os.makedirs(root_dir, exist_ok=True)


def _clear_live_lookup_outputs(cache_root: str, serial: str) -> None:
    root_dir = _live_lookup_root(cache_root, serial)
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    if os.path.isdir(shots_dir):
        for name in os.listdir(shots_dir):
            file_path = os.path.join(shots_dir, name)
            if not os.path.isfile(file_path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in image_exts or name.lower() == "manifest.jsonl":
                try:
                    os.remove(file_path)
                except OSError:
                    pass

    for path in (
        _live_lookup_preview_path(cache_root, serial),
        _live_lookup_results_path(cache_root, serial),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    os.makedirs(root_dir, exist_ok=True)
    os.makedirs(shots_dir, exist_ok=True)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _kill_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _list_live_monitor_pids(serial: str) -> list[int]:
    if not serial or os.name != "nt":
        return []
    script_name = "hmi_touch_monitor.py"
    escaped_serial = str(serial).replace("'", "''")
    ps_script = (
        "$items = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*"
        + script_name
        + "*' -and $_.CommandLine -like '*--serial "
        + escaped_serial
        + "*' }; "
        "$items | ForEach-Object { $_.ProcessId }"
    )
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in raw.splitlines():
        text = line.strip()
        if text.isdigit():
            pids.append(int(text))
    return sorted(set(pids))


def _load_live_monitor_state(cache_root: str, serial: str) -> Dict[str, Any]:
    return _load_json(_live_lookup_monitor_state_path(cache_root, serial)) or {}


def _live_monitor_belongs_to_session(state: Optional[Dict[str, Any]], session_token: str) -> bool:
    if not session_token:
        return True
    payload = state if isinstance(state, dict) else {}
    return _safe_str(payload.get("session_token")) == session_token


def _clear_live_monitor_runtime_state(cache_root: str, serial: str) -> None:
    for path in (
        _live_lookup_monitor_state_path(cache_root, serial),
        _live_lookup_stop_flag(cache_root, serial),
        _live_lookup_shots_stop_flag(cache_root, serial),
    ):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _ensure_live_monitor_session(cache_root: str, serial: str, session_token: str) -> None:
    state = _load_live_monitor_state(cache_root, serial)
    pid = int(state.get("pid", 0) or 0)
    live_pids = _list_live_monitor_pids(serial)
    monitor_alive = bool(live_pids) or _pid_is_running(pid)
    if monitor_alive and not _live_monitor_belongs_to_session(state, session_token):
        if pid > 0:
            _kill_process_tree(pid)
        for live_pid in live_pids:
            _kill_process_tree(live_pid)
        _clear_live_monitor_runtime_state(cache_root, serial)
        _update_live_activity_state(
            serial,
            "idle",
            "Aguardando inicio manual da validacao automatica.",
            0.0,
            preview_path="",
        )
        return
    if not monitor_alive and state:
        _clear_live_monitor_runtime_state(cache_root, serial)
        _update_live_activity_state(
            serial,
            "idle",
            "Aguardando inicio manual da validacao automatica.",
            0.0,
            preview_path=_latest_live_screenshot_path(cache_root, serial),
        )


def _live_monitor_running(cache_root: str, serial: str, session_token: str = "") -> bool:
    state = _load_live_monitor_state(cache_root, serial)
    if session_token and not _live_monitor_belongs_to_session(state, session_token):
        return False
    pid = int(state.get("pid", 0) or 0)
    if _pid_is_running(pid):
        return True
    live_pids = _list_live_monitor_pids(serial)
    if live_pids:
        return True
    return False


def _start_live_monitor(
    cache_root: str,
    serial: str,
    index_path: Optional[str] = None,
    monitor_mode: str = "auto",
    target_size: tuple[int, int] | None = None,
    session_token: str = "",
) -> str:
    root_dir = _live_lookup_root(cache_root, serial)
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    if _live_monitor_running(cache_root, serial, session_token=session_token):
        return "Monitor automatico ja esta ativo."

    state = _load_live_monitor_state(cache_root, serial)
    previous_pid = int(state.get("pid", 0) or 0)
    if previous_pid > 0:
        _kill_process_tree(previous_pid)
    for pid in _list_live_monitor_pids(serial):
        _kill_process_tree(pid)

    native_size = _get_connected_device_resolution(serial)
    _reset_live_lookup_session(cache_root, serial)
    os.makedirs(shots_dir, exist_ok=True)

    script_path = str(PROJECT_ROOT / "src" / "vwait" / "entrypoints" / "cli" / "hmi_touch_monitor.py")
    log_path = os.path.join(root_dir, "monitor.log")
    python_exec = sys.executable
    if os.name == "nt":
        pythonw_exec = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw_exec):
            python_exec = pythonw_exec
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    cmd = [python_exec, script_path, "--serial", serial, "--output-dir", shots_dir, "--monitor-mode", monitor_mode]
    if index_path:
        cmd.extend(["--index-path", str(index_path), "--results-path", _live_lookup_results_path(cache_root, serial)])
    if target_size:
        cmd.extend(["--target-width", str(int(target_size[0])), "--target-height", str(int(target_size[1]))])
    with open(log_path, "a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=log_file,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    _save_json(
        _live_lookup_monitor_state_path(cache_root, serial),
        {
            "pid": proc.pid,
            "serial": serial,
            "started_at": datetime.now().isoformat(),
            "session_token": session_token,
            "output_dir": shots_dir,
            "index_path": index_path,
            "monitor_mode": monitor_mode,
            "target_width": int(target_size[0]) if target_size else None,
            "target_height": int(target_size[1]) if target_size else None,
            "native_width": int(native_size[0]) if native_size and native_size[0] > 0 else None,
            "native_height": int(native_size[1]) if native_size and native_size[1] > 0 else None,
        },
    )
    return (
        f"Validacao automatica iniciada para {serial}"
        + (f" em {int(target_size[0])}x{int(target_size[1])}." if target_size else ".")
    )


def _stop_live_monitor(cache_root: str, serial: str, hmi: Dict[str, Any]) -> str:
    stop_flag = _live_lookup_stop_flag(cache_root, serial)
    os.makedirs(os.path.dirname(stop_flag), exist_ok=True)
    Path(stop_flag).write_text("stop", encoding="utf-8")
    state = _load_live_monitor_state(cache_root, serial)
    pid = int(state.get("pid", 0) or 0)
    if pid > 0 and _pid_is_running(pid):
        _kill_process_tree(pid)
    for live_pid in _list_live_monitor_pids(serial):
        _kill_process_tree(live_pid)
    _update_live_activity_state(
        serial,
        "stopped",
        "Validacao automatica parada.",
        0.0,
        preview_path=_latest_live_screenshot_path(cache_root, serial),
    )
    # Generate report after stopping
    index_path = state.get("index_path")
    if index_path and os.path.exists(index_path):
        library_index = hmi["load_library_index"](index_path)
        payload = _load_live_lookup_results(cache_root, serial)
        full_results = _live_lookup_full_results(payload)
        if not full_results:
            try:
                _process_live_lookup_queue(hmi, cache_root, serial, library_index)
            except Exception:
                pass
            payload = _load_live_lookup_results(cache_root, serial)
            full_results = _live_lookup_full_results(payload)
        if full_results:
            result = _build_validation_report_payload(full_results, library_index)
            test_dir = _live_lookup_root(cache_root, serial)
            report_path = hmi["save_validation_report"](test_dir, library_index, result)
            _clear_live_monitor_runtime_state(cache_root, serial)
            return f"Monitor automatico sinalizado para parar em {serial}. Relatorio gerado em {report_path}."
    _clear_live_monitor_runtime_state(cache_root, serial)
    return f"Monitor automatico sinalizado para parar em {serial}."


def _result_to_history_row(result: Dict[str, Any]) -> Dict[str, Any]:
    scores = result.get("scores") or {}
    diff_summary = result.get("diff_summary") or {}
    screenshot_path = _safe_str(result.get("screenshot_path"))
    return {
        "capturado_em": os.path.basename(screenshot_path),
        "screenshot_path": screenshot_path,
        "screen_name": _safe_str(result.get("screen_name"), "-"),
        "feature_context": _safe_str(result.get("feature_context"), "-"),
        "status": _safe_str(result.get("status"), "-"),
        "similarity": float(scores.get("final", 0.0) or 0.0),
        "pixel_match": float(diff_summary.get("pixel_match_ratio", 0.0) or 0.0),
        "capture_source": _safe_str(result.get("capture_source"), "-"),
        "reference_path": _safe_str(result.get("reference_path"), ""),
        "processed_at": datetime.now().isoformat(),
    }


def _is_stable_image_file(path: str, min_size_bytes: int = 512) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        size_before = os.path.getsize(path)
    except OSError:
        return False
    if size_before < min_size_bytes:
        return False
    time.sleep(0.15)
    try:
        size_after = os.path.getsize(path)
    except OSError:
        return False
    return size_before == size_after


def _process_live_lookup_queue(
    hmi: Dict[str, Any],
    cache_root: str,
    serial: str,
    library_index: Dict[str, Any],
    status_hook=None,
) -> Dict[str, Any]:
    if status_hook is None:
        status_hook = lambda _phase, _message, _progress, _preview_path="": None
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    state_path = _live_lookup_results_path(cache_root, serial)
    payload = _load_live_lookup_results(cache_root, serial)
    processed = set(str(name) for name in payload.get("processed", []))
    history = list(payload.get("history", []))
    full_results = [item for item in payload.get("full_results", []) if isinstance(item, dict)]
    latest_bundle = st.session_state.get("hmi_lookup_result")
    latest_result = latest_bundle.get("result") if isinstance(latest_bundle, dict) else None
    latest_path = _safe_str(latest_result.get("screenshot_path")) if isinstance(latest_result, dict) else ""
    stored_latest = full_results[-1] if full_results else None
    stored_latest_path = _safe_str(stored_latest.get("screenshot_path")) if isinstance(stored_latest, dict) else ""
    cfg = _default_lookup_cfg(hmi)

    if not os.path.isdir(shots_dir):
        status_hook("waiting", "Aguardando a primeira captura da bancada ou do scrcpy.", 0.02, "")
        return {"new_count": 0, "history": history, "latest_bundle": latest_bundle}

    files = []
    for name in sorted(os.listdir(shots_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            files.append(name)

    new_count = 0
    latest_file_path = ""
    if stored_latest_path and stored_latest_path != latest_path and os.path.exists(stored_latest_path):
        try:
            status_hook(
                "comparing",
                f"Sincronizando a ultima comparacao salva ({os.path.basename(stored_latest_path)})...",
                0.55,
                stored_latest_path,
            )
            synced_result = hmi["evaluate_single_screenshot"](stored_latest_path, library_index, cfg)
            latest_bundle = {
                "lookup_dir": _live_lookup_root(cache_root, serial),
                "actual_path": stored_latest_path,
                "result": synced_result,
            }
        except Exception:
            latest_bundle = {
                "lookup_dir": _live_lookup_root(cache_root, serial),
                "actual_path": stored_latest_path,
                "result": stored_latest,
            }
        st.session_state["hmi_lookup_result"] = latest_bundle
        latest_result = latest_bundle.get("result") if isinstance(latest_bundle, dict) else None
        latest_path = _safe_str(latest_result.get("screenshot_path")) if isinstance(latest_result, dict) else ""

    status_hook("scanning", "Procurando novas capturas na pasta monitorada...", 0.08, "")
    for name in files:
        file_path = os.path.join(shots_dir, name)
        latest_file_path = file_path
        if name in processed:
            continue
        status_hook("capturing", f"Preparando a captura {name} para comparacao...", 0.2, file_path)
        if not _is_stable_image_file(file_path):
            continue
        try:
            status_hook("comparing", f"Comparando {name} com a biblioteca...", 0.6, file_path)
            result = hmi["evaluate_single_screenshot"](file_path, library_index, cfg)
        except Exception:
            status_hook("comparing", f"Falha ao comparar {name}; tentando novamente no proximo ciclo.", 0.6, file_path)
            continue
        compact_result = _compact_live_result(result)
        history.append(_result_to_history_row(compact_result))
        full_results.append(compact_result)
        processed.add(name)
        latest_bundle = {"lookup_dir": _live_lookup_root(cache_root, serial), "actual_path": file_path, "result": result}
        st.session_state["hmi_lookup_result"] = latest_bundle
        new_count += 1
        status_hook("done", f"Comparacao concluida para {name}.", 1.0, file_path)

    if not latest_bundle and latest_file_path:
        result = hmi["evaluate_single_screenshot"](latest_file_path, library_index, cfg)
        latest_bundle = {"lookup_dir": _live_lookup_root(cache_root, serial), "actual_path": latest_file_path, "result": result}
        st.session_state["hmi_lookup_result"] = latest_bundle

    history = history[-50:]
    full_results = full_results[-100:]  # Keep last 100 full results for report generation
    _save_json(state_path, {"processed": sorted(processed), "history": history, "full_results": full_results})
    if new_count == 0:
        status_hook(
            "waiting",
            "Aguardando nova tela da bancada ou do scrcpy para capturar e comparar.",
            0.05,
            latest_file_path,
        )
    return {"new_count": new_count, "history": history, "latest_bundle": latest_bundle}


def _load_vqa_runs(runs_dir: str) -> list[Dict[str, Any]]:
    if not os.path.isdir(runs_dir):
        return []
    rows = []
    for name in sorted(os.listdir(runs_dir), reverse=True):
        run_path = os.path.join(runs_dir, name, "run_result.json")
        payload = _load_json(run_path)
        if payload:
            payload["__run_result_path"] = run_path
            rows.append(payload)
    return rows


def _live_monitor_mode_options() -> list[tuple[str, str]]:
    if os.name == "nt":
        return [
            ("host_click", "Janela malagueta: capturar ao clicar no scrcpy"),
            ("device", "Bancada/ADB por toque"),
            ("screen_watch", "Mudanca visual da tela"),
            ("hybrid", "Avancado: scrcpy + mudanca visual da bancada"),
        ]
    return [
        ("screen_watch", "Scrcpy/ADB: capturar cada mudança visual"),
        ("device", "Bancada/ADB por toque físico"),
    ]


def _live_monitor_mode_label(mode: str) -> str:
    labels = dict(_live_monitor_mode_options())
    return labels.get(mode, mode or "-")


def _capture_source_label(source: str) -> str:
    mapping = {
        "initial_state": "Estado inicial",
        "scrcpy_window": "Janela do scrcpy",
        "screen_change": "Mudanca visual",
        "host_click": "Clique na malagueta",
        "tap": "Toque na bancada",
        "swipe": "Swipe na bancada",
        "long_press": "Pressao longa na bancada",
    }
    return mapping.get(_safe_str(source), _safe_str(source, "-"))


def _render_live_capture_dashboard(
    hmi: Dict[str, Any],
    cache_root: str,
    selected_serial: str,
    live_running: bool,
    live_state: Dict[str, Any],
    native_live_size: tuple[int, int],
) -> None:
    live_results_payload = _load_live_lookup_results(cache_root, selected_serial)
    live_latest_bundle = _latest_live_result_bundle(cache_root, selected_serial, live_results_payload)
    live_latest_result = live_latest_bundle.get("result") if isinstance(live_latest_bundle, dict) else None
    history_rows = [item for item in live_results_payload.get("history", []) if isinstance(item, dict)]
    live_activity = _get_live_activity_state(selected_serial)
    live_preview_path = (
        _live_lookup_preview_path(cache_root, selected_serial)
        if os.path.exists(_live_lookup_preview_path(cache_root, selected_serial))
        else ""
    ) or _latest_live_screenshot_path(cache_root, selected_serial) or _safe_str(live_activity.get("preview_path"))

    live_target_size = (
        int(live_state.get("target_width", 0) or 0),
        int(live_state.get("target_height", 0) or 0),
    )
    if live_target_size[0] <= 0 or live_target_size[1] <= 0:
        live_target_size = tuple(live_activity.get("resolution") or DEFAULT_LIVE_CAPTURE_SIZE)

    if live_running:
        if isinstance(live_latest_result, dict):
            _update_live_activity_state(
                selected_serial,
                "monitoring",
                "Monitor ativo. Resultado recebido do processo automatico.",
                0.72,
                preview_path=live_preview_path or _safe_str(live_latest_result.get("screenshot_path")),
                resolution=live_target_size,
            )
        elif live_preview_path:
            _update_live_activity_state(
                selected_serial,
                "capturing",
                "Monitor ativo. Captura recebida; aguardando a comparacao automatica.",
                0.34,
                preview_path=live_preview_path,
                resolution=live_target_size,
            )
        else:
            _update_live_activity_state(
                selected_serial,
                "waiting",
                "Monitor ativo. Aguardando a primeira tela da bancada ou do scrcpy...",
                0.08,
                resolution=live_target_size,
            )
        live_activity = _get_live_activity_state(selected_serial)

    elapsed_s = max(0.0, time.time() - float(live_activity.get("started_at", time.time()) or time.time()))
    capture_caption = f"Comparacao alinhada a biblioteca em {int(live_target_size[0])}x{int(live_target_size[1])}."
    if native_live_size[0] > 0 and native_live_size[1] > 0:
        capture_caption = (
            f"Preview nativo do scrcpy/radio em {int(native_live_size[0])}x{int(native_live_size[1])}. "
            f"Comparacao alinhada a biblioteca em {int(live_target_size[0])}x{int(live_target_size[1])}."
        )

    with st.container(border=True):
        st.markdown("#### Acompanhamento da captura")
        st.markdown(
            """
            <style>
            [class*="st-key-hmi_live_export_"] div[data-testid="stDownloadButton"] button,
            [class*="st-key-hmi_live_clear_"] div[data-testid="stButton"] button {
                min-height: 3.25rem !important;
                border-radius: 14px !important;
                border: 1px solid rgba(129, 140, 248, 0.55) !important;
                background: linear-gradient(135deg, rgba(49, 46, 129, 0.96), rgba(99, 102, 241, 0.72)) !important;
                color: #f5f6ff !important;
                font-weight: 700 !important;
                box-shadow: 0 14px 28px rgba(99, 102, 241, 0.16) !important;
            }
            [class*="st-key-hmi_live_export_"] div[data-testid="stDownloadButton"] button:hover,
            [class*="st-key-hmi_live_clear_"] div[data-testid="stButton"] button:hover {
                transform: translateY(-1px);
                filter: brightness(1.08);
            }
            [class*="st-key-hmi_live_export_"] div[data-testid="stDownloadButton"] button:disabled {
                opacity: 0.45 !important;
                filter: grayscale(0.35);
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        action_col1, action_col2, action_col3 = st.columns([1, 1, 2])
        live_full_results = _live_lookup_full_results(live_results_payload)
        if live_full_results:
            live_report = _build_validation_report_payload(live_full_results)
            live_rows = hmi["build_validation_dimension_rows"](live_report)
        else:
            live_rows = []
        export_name = (
            f"hmi_live_{_safe_serial_name(selected_serial)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        with action_col1:
            st.download_button(
                "Exportar relatório",
                data=hmi["build_validation_dimension_workbook"](live_rows) if live_rows else b"",
                file_name=export_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=not bool(live_rows),
                key=f"hmi_live_export_{_safe_serial_name(selected_serial)}",
            )
        with action_col2:
            if st.button("Limpar", use_container_width=True, key=f"hmi_live_clear_{_safe_serial_name(selected_serial)}"):
                _clear_live_lookup_outputs(cache_root, selected_serial)
                st.session_state["hmi_lookup_result"] = None
                _update_live_activity_state(
                    selected_serial,
                    "waiting" if live_running else "idle",
                    "Capturas e análises limpas. Aguardando nova tela.",
                    0.08 if live_running else 0.0,
                    preview_path="",
                    resolution=live_target_size,
                )
                st.success("Últimas capturas, imagens e análises foram limpas.")
                st.rerun()
        with action_col3:
            st.caption("Exporte o histórico atual ou limpe as capturas/análises para começar uma nova leitura visual.")

        st.progress(float(live_activity.get("progress", 0.0) or 0.0))
        st.caption(
            f"{_safe_str(live_activity.get('message'), 'Aguardando captura.')} | "
            f"Tempo nesta etapa: {elapsed_s:.1f}s"
        )
        st.caption(capture_caption)
        st.markdown("**Ultima tela capturada**")
        if live_preview_path:
            _safe_show_image(
                live_preview_path,
                f"Captura {os.path.basename(live_preview_path)}",
                "Nao foi possivel abrir a captura mais recente.",
            )
        else:
            st.info("Nenhuma captura ainda. Inicie a validacao automatica e interaja pela bancada ou pelo scrcpy.")
        if history_rows:
            st.markdown("#### Historico automatico")
            st.dataframe(
                [
                    {
                        "capturado_em": row.get("capturado_em"),
                        "tela": row.get("screen_name"),
                        "origem": _capture_source_label(_safe_str(row.get("capture_source"))),
                        "similaridade": f"{float(row.get('similarity', 0.0) or 0.0):.1%}",
                        "pixel_match": f"{float(row.get('pixel_match', 0.0) or 0.0):.1%}",
                        "status": row.get("status"),
                    }
                    for row in reversed(history_rows[-10:])
                ],
                use_container_width=True,
                hide_index=True,
            )
        if isinstance(live_latest_bundle, dict):
            st.markdown("#### Última comparação automática")
            _render_library_lookup_result(live_latest_bundle)
        monitor_log_path = _live_monitor_log_path(cache_root, selected_serial)
        if os.path.exists(monitor_log_path):
            with st.expander("Log do monitor automatico"):
                try:
                    with open(monitor_log_path, "r", encoding="utf-8", errors="ignore") as handle:
                        log_lines = handle.readlines()[-20:]
                    st.code("".join(log_lines) or "(sem linhas ainda)", language="text")
                except Exception:
                    st.info("Nao foi possivel ler o monitor.log.")


def _hmi_context_stats(library_index: Optional[Dict[str, Any]]) -> Dict[str, int]:
    stats: Dict[str, int] = {}
    if not isinstance(library_index, dict):
        return stats
    for entry in library_index.get("screens", []):
        context = _safe_str(entry.get("feature_context"), "geral") or "geral"
        stats[context] = stats.get(context, 0) + 1
    return dict(sorted(stats.items(), key=lambda item: item[0]))


def _make_vqa_config(vqa: Dict[str, Any], reference_dir: str, index_dir: str, runs_dir: str) -> Any:
    base = vqa["load_config"](None)
    VisualQaConfig = vqa["VisualQaConfig"]
    return VisualQaConfig(
        reference_dir=Path(reference_dir).resolve(),
        index_dir=Path(index_dir).resolve(),
        runs_dir=Path(runs_dir).resolve(),
        top_k=max(1, int(st.session_state.get("vqa_top_k", 5))),
        classification_threshold=float(st.session_state.get("vqa_threshold", 0.35)),
        embedding_provider=_safe_str(st.session_state.get("vqa_embedding_provider", "auto")),
        mobileclip_model=base.mobileclip_model,
        openclip_model=base.openclip_model,
        openclip_pretrained=base.openclip_pretrained,
        use_faiss=True,
        report_mode="ollama" if bool(st.session_state.get("vqa_use_llm", False)) else "null",
        ollama_base_url=_safe_str(st.session_state.get("vqa_ollama_base_url", base.ollama_base_url)),
        ollama_model=_safe_str(st.session_state.get("vqa_ollama_model", base.ollama_model)),
        ollama_timeout_s=base.ollama_timeout_s,
        config_path=None,
    )


def _make_vqa_use_cases(vqa: Dict[str, Any], cfg: Any) -> Dict[str, Any]:
    embedding = vqa["build_embedding_provider"](cfg)
    build_repo = vqa["FaissVectorIndexRepository"](index_dir=str(cfg.index_dir), embedding_provider=embedding, use_faiss=True)
    query_repo = vqa["FaissVectorIndexRepository"](index_dir=str(cfg.index_dir), use_faiss=True)
    report_generator = vqa["build_report_generator"](cfg) if cfg.report_mode == "ollama" else vqa["NullReportGenerator"]()
    return {
        "build_index": vqa["BuildVectorIndex"](embedding_provider=embedding, vector_repo=build_repo),
        "validate": vqa["ValidateScreenshot"](
            classifier=vqa["ClassifyScreenshot"](embedding_provider=embedding, vector_repo=query_repo),
            pixel_comparator=vqa["ExistingPixelAdapter"](),
            report_generator=report_generator,
            artifact_store=vqa["LocalArtifactStore"](runs_dir=str(cfg.runs_dir)),
        ),
    }


def render_hmi_validation_page(base_dir: str, data_root: str) -> None:
    del base_dir
    hmi = _load_hmi_modules()
    cache_root = str(hmi_cache_dir())
    os.makedirs(cache_root, exist_ok=True)

    st.session_state.setdefault("hmi_figma_dir", DEFAULT_HMI_LIBRARY_DIR)
    st.session_state.setdefault("hmi_index_path", "")
    st.session_state.setdefault("hmi_index_name_value", "biblioteca_hmi")
    st.session_state.setdefault("hmi_capture_source", "auto")
    st.session_state.setdefault("hmi_live_monitor_mode", "host_click" if os.name == "nt" else "screen_watch")
    st.session_state.setdefault("hmi_enable_context_routing", True)
    st.session_state.setdefault("hmi_context_top_k", 12)
    st.session_state.setdefault("vqa_reference_dir", DEFAULT_HMI_LIBRARY_DIR)
    st.session_state.setdefault("vqa_index_dir", os.path.join(cache_root, "visual_qa_index"))
    st.session_state.setdefault("vqa_embedding_provider", "auto")
    st.session_state.setdefault("vqa_top_k", 5)
    st.session_state.setdefault("vqa_threshold", 0.35)
    st.session_state.setdefault("vqa_strategy", "best")
    st.session_state.setdefault("vqa_use_llm", False)
    st.session_state.setdefault("vqa_ollama_base_url", "http://127.0.0.1:11434")
    st.session_state.setdefault("vqa_ollama_model", "llama3.1:8b")
    st.session_state.setdefault("hmi_demo_result", None)
    st.session_state.setdefault("hmi_lookup_result", None)
    st.session_state.setdefault("hmi_live_selected_serial", "")
    st.session_state.setdefault("hmi_lookup_top_k", 5)
    st.session_state.setdefault("hmi_lookup_enable_context_routing", False)
    st.session_state.setdefault("hmi_lookup_pass", 0.93)
    st.session_state.setdefault("hmi_lookup_warning", 0.82)
    st.session_state.setdefault("hmi_lookup_tolerance", 18)
    st.session_state.setdefault("hmi_lookup_exact", 0.985)
    st.session_state.setdefault("hmi_lookup_min_cell", 0.92)
    st.session_state.setdefault("hmi_last_hmi_summary", None)
    st.session_state.setdefault("hmi_last_vqa_summary", None)
    st.session_state["hmi_figma_dir"] = DEFAULT_HMI_LIBRARY_DIR
    st.session_state["vqa_reference_dir"] = DEFAULT_HMI_LIBRARY_DIR
    st.session_state["hmi_lookup_figma_dir"] = DEFAULT_HMI_LIBRARY_DIR
    st.session_state["hmi_unified_figma_dir"] = DEFAULT_HMI_LIBRARY_DIR

    st.title("Validação HMI")
    st.caption("Biblioteca de telas do radio + screenshot real -> melhor correspondencia por similaridade visual.")

    current_index = None
    if st.session_state.get("hmi_index_path") and os.path.exists(st.session_state["hmi_index_path"]):
        current_index = hmi["load_library_index"](st.session_state["hmi_index_path"])
    backend_status = hmi["get_backend_status"]()
    vqa_stats = _vqa_index_stats(_safe_str(st.session_state.get("vqa_index_dir")))
    context_stats = _hmi_context_stats(current_index)
    tests = _list_tests(data_root)
    label_map = {label: (categoria, teste) for label, categoria, teste in tests}
    connected_devices = _list_connected_adb_devices()
    if connected_devices and st.session_state.get("hmi_live_selected_serial") not in connected_devices:
        st.session_state["hmi_live_selected_serial"] = connected_devices[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Biblioteca HMI", current_index.get("screen_count", 0) if current_index else 0)
    c2.metric("OCR", "ON" if backend_status.ocr_available else "OFF")
    c3.metric("Features GEI", len(context_stats))
    c4.metric("Visual QA pronto", "SIM" if vqa_stats["ready"] else "NAO")

    tab_lookup, tab_demo = st.tabs(["Comparação ao Vivo", "Teste Visual"])

    with tab_lookup:
        st.markdown("### Comparação ao vivo com a biblioteca")
        st.caption(
            "Compare manualmente um screenshot real ou deixe a bancada conectada gerar screenshots "
            "automaticamente a cada mudanca de tela."
        )

        with st.container(border=True):
            lookup_dir = st.text_input(
                "Pasta da biblioteca de telas",
                value=DEFAULT_HMI_LIBRARY_DIR,
                key="hmi_lookup_figma_dir",
                disabled=True,
                help="Caminho fixo da biblioteca GEI usada pela Validação HMI.",
            )
            st.session_state["hmi_figma_dir"] = DEFAULT_HMI_LIBRARY_DIR
            if lookup_dir.strip() and not st.session_state.get("vqa_reference_dir"):
                st.session_state["vqa_reference_dir"] = lookup_dir.strip()

            lookup_upload = st.file_uploader(
                "Screenshot real",
                type=["png", "jpg", "jpeg", "bmp", "webp"],
                key="hmi_lookup_upload",
            )

            if st.button("Comparar", type="primary", use_container_width=True, key="hmi_lookup_run_btn"):
                if not lookup_dir.strip():
                    st.error("Informe a pasta da biblioteca.")
                elif lookup_upload is None:
                    st.error("Envie o screenshot real para comparar.")
                else:
                    try:
                        with st.spinner("Carregando a biblioteca HMI da pasta base..."):
                            index_path, library_index = _resolve_hmi_library(
                                hmi,
                                cache_root,
                                lookup_dir.strip(),
                                _safe_str(st.session_state.get("hmi_index_name_value"), "biblioteca_hmi"),
                            )
                        if library_index is None:
                            raise RuntimeError("Nao foi possivel carregar a biblioteca.")
                        st.session_state["hmi_index_path"] = _safe_str(index_path)
                        cfg = hmi["ValidationConfig"](
                            top_k=5,
                            pass_threshold=0.93,
                            warning_threshold=0.82,
                            point_tolerance=18.0,
                            exact_match_ratio=0.985,
                            min_cell_score=0.92,
                            enable_context_routing=False,
                            context_top_k=5,
                        )
                        st.session_state["hmi_lookup_result"] = _run_library_similarity_lookup(
                            hmi,
                            cache_root,
                            lookup_upload,
                            library_index,
                            cfg,
                        )
                        st.success("Comparacao concluida.")
                    except Exception as exc:
                        st.error(f"Falha ao comparar screenshot com a biblioteca: {exc}")

        if connected_devices:
            st.markdown("### Comparação automatica da bancada")
            st.caption(
                "Quando ativa, cada mudanca de tela detectada na bancada ou no scrcpy gera um screenshot "
                "que e comparado automaticamente com a biblioteca."
            )

            selected_serial = st.selectbox(
                "Bancada conectada",
                options=connected_devices,
                key="hmi_live_selected_serial",
            )
            session_token = _live_ui_session_token()
            _ensure_live_monitor_session(cache_root, selected_serial, session_token)
            live_state = _load_live_monitor_state(cache_root, selected_serial)
            live_running = _live_monitor_running(cache_root, selected_serial, session_token=session_token)
            st.session_state["hmi_live_is_running"] = bool(live_running)
            live_results_payload = _load_live_lookup_results(cache_root, selected_serial)
            live_latest_bundle = _latest_live_result_bundle(cache_root, selected_serial, live_results_payload)
            live_latest_result = live_latest_bundle.get("result") if isinstance(live_latest_bundle, dict) else None
            history_rows = [item for item in live_results_payload.get("history", []) if isinstance(item, dict)]
            native_live_size = (
                int(live_state.get("native_width", 0) or 0),
                int(live_state.get("native_height", 0) or 0),
            )
            if native_live_size[0] <= 0 or native_live_size[1] <= 0:
                native_live_size = _get_connected_device_resolution(selected_serial)

            mode_options = _live_monitor_mode_options()
            mode_values = [value for value, _label in mode_options]
            if os.name != "nt" and not live_running and _safe_str(st.session_state.get("hmi_live_monitor_mode")) == "device":
                st.session_state["hmi_live_monitor_mode"] = "screen_watch"
            if _safe_str(st.session_state.get("hmi_live_monitor_mode")) not in mode_values:
                st.session_state["hmi_live_monitor_mode"] = mode_values[0]
            selected_mode = st.selectbox(
                "Fonte de captura automatica",
                options=mode_values,
                format_func=_live_monitor_mode_label,
                key="hmi_live_monitor_mode",
                disabled=live_running,
            )
            if live_running:
                st.caption(
                    "Modo ativo: "
                    f"{_live_monitor_mode_label(_safe_str(live_state.get('monitor_mode'), selected_mode))}. "
                    "Para trocar a forma de captura, pare e inicie novamente."
                )
            else:
                st.caption(
                    "A validacao sempre comeca inativa. O dashboard apenas exibe a ultima captura salva pelo monitor."
                )

            live_action_cols = st.columns([1, 1])
            with live_action_cols[0]:
                if not live_running:
                    if st.button("Iniciar validacao automatica", use_container_width=True, key="hmi_live_start_btn"):
                        if not lookup_dir.strip():
                            st.error("Informe a pasta da biblioteca antes de ativar o modo automatico.")
                        else:
                            try:
                                with st.spinner("Preparando a biblioteca HMI para a validacao automatica..."):
                                    index_path, live_library_index = _resolve_hmi_library(
                                        hmi,
                                        cache_root,
                                        lookup_dir.strip(),
                                        _safe_str(st.session_state.get("hmi_index_name_value"), "biblioteca_hmi"),
                                    )
                                if live_library_index is None or not index_path:
                                    raise RuntimeError("Nao foi possivel carregar a biblioteca para o modo automatico.")
                                live_target_size = _preferred_live_capture_size(live_library_index)
                                st.session_state["hmi_index_path"] = _safe_str(index_path)
                                st.session_state["hmi_lookup_result"] = None
                                _update_live_activity_state(
                                    selected_serial,
                                    "starting",
                                    f"Iniciando a validacao automatica em {live_target_size[0]}x{live_target_size[1]}...",
                                    0.03,
                                    resolution=live_target_size,
                                )
                                msg = _start_live_monitor(
                                    cache_root,
                                    selected_serial,
                                    index_path,
                                    monitor_mode=selected_mode,
                                    target_size=live_target_size,
                                    session_token=session_token,
                                )
                                st.success(msg)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Falha ao iniciar comparacao automatica: {exc}")
                else:
                    if st.button("Parar validacao automatica", use_container_width=True, key="hmi_live_stop_btn"):
                        msg = _stop_live_monitor(cache_root, selected_serial, hmi)
                        st.info(msg)
                        st.rerun()
            with live_action_cols[1]:
                st.metric("Modo automatico", "ATIVO" if live_running else "PARADO")
                live_activity = _get_live_activity_state(selected_serial)
                live_target_size = (
                    int(live_state.get("target_width", 0) or 0),
                    int(live_state.get("target_height", 0) or 0),
                )
                if live_target_size[0] <= 0 or live_target_size[1] <= 0:
                    live_target_size = tuple(live_activity.get("resolution") or DEFAULT_LIVE_CAPTURE_SIZE)
                st.caption(f"Resolucao alvo: {int(live_target_size[0])}x{int(live_target_size[1])}")
                if native_live_size[0] > 0 and native_live_size[1] > 0:
                    st.caption(f"Captura nativa: {int(native_live_size[0])}x{int(native_live_size[1])}")
                    if tuple(native_live_size) != tuple(live_target_size):
                        st.caption(
                            f"Normalizacao automatica: {int(native_live_size[0])}x{int(native_live_size[1])} "
                            f"-> {int(live_target_size[0])}x{int(live_target_size[1])}"
                        )
                state_mode = _safe_str(live_state.get("monitor_mode"), selected_mode)
                st.caption(f"Captura: {_live_monitor_mode_label(state_mode)}")

            if live_running:
                index_path = _safe_str(live_state.get("index_path"))
                st.session_state["hmi_index_path"] = index_path or _safe_str(st.session_state.get("hmi_index_path"))
                if lookup_dir.strip() and index_path and _safe_str(st.session_state.get("hmi_index_path")) and not os.path.exists(index_path):
                    st.warning(
                        "Nao foi possivel localizar a biblioteca ativa da validacao automatica. "
                        "Pare e inicie novamente para recarregar a pasta base."
                    )
            elif connected_devices and not lookup_dir.strip():
                st.info("Informe a pasta da biblioteca para habilitar a comparacao automatica da bancada.")

            def _live_capture_panel() -> None:
                _render_live_capture_dashboard(hmi, cache_root, selected_serial, live_running, live_state, native_live_size)

            if live_running and hasattr(st, "fragment"):
                st.fragment(run_every=0.5)(_live_capture_panel)()
            else:
                _live_capture_panel()
        else:
            st.session_state["hmi_live_is_running"] = False
            st.info("Nenhuma bancada ADB conectada no momento. O modo automatico aparece quando o radio estiver conectado.")

        live_report: Optional[Dict[str, Any]] = None
        live_report_caption = ""
        manual_bundle = st.session_state.get("hmi_lookup_result")
        current_bundle = manual_bundle
        current_result = current_bundle.get("result") if isinstance(current_bundle, dict) else None
        current_lookup_dir = _safe_str(current_bundle.get("lookup_dir")) if isinstance(current_bundle, dict) else ""
        active_serial = _safe_str(st.session_state.get("hmi_live_selected_serial"))
        live_payload = {}
        live_full_results: list[Dict[str, Any]] = []
        live_root = ""
        live_latest_bundle = None
        if active_serial:
            live_payload = _load_live_lookup_results(cache_root, active_serial)
            live_full_results = _live_lookup_full_results(live_payload)
            live_root = _live_lookup_root(cache_root, active_serial)
            live_latest_bundle = _latest_live_result_bundle(cache_root, active_serial, live_payload)

        should_use_live_results = bool(live_full_results) and (
            not isinstance(current_result, dict)
            or (current_lookup_dir and os.path.abspath(current_lookup_dir) == os.path.abspath(live_root))
        )
        if should_use_live_results:
            live_report = _build_validation_report_payload(live_full_results)
            live_report_caption = f"Extracao consolidada do historico automatico da bancada `{active_serial}`."
        elif isinstance(current_result, dict):
            live_report = _build_validation_report_payload([current_result])
            live_report_caption = "Extracao do resultado atual da comparacao ao vivo."
        elif live_full_results:
            live_report = _build_validation_report_payload(live_full_results)
            live_report_caption = f"Extracao consolidada do historico automatico da bancada `{active_serial}`."

        active_live_running = bool(st.session_state.get("hmi_live_is_running"))
        if active_live_running:
            st.caption(
                "A cada nova tela capturada pelo monitor, o resultado abaixo é atualizado automaticamente "
                "com a correspondência mais próxima da biblioteca."
            )
        else:
            _render_lookup_results_export(
                hmi,
                live_report,
                export_slug=active_serial or "manual",
                caption=live_report_caption,
            )
            _render_library_lookup_result(live_latest_bundle or manual_bundle)

    if False:
        st.markdown(
            """
            <style>
            .hmi-summary-card {
                padding: 18px 20px;
                border-radius: 18px;
                border: 1px solid rgba(116, 183, 255, 0.22);
                background: linear-gradient(135deg, rgba(8, 18, 42, 0.96), rgba(8, 12, 24, 0.92));
                box-shadow: 0 18px 40px rgba(0, 0, 0, 0.26);
                margin-bottom: 1rem;
            }
            .hmi-summary-title {
                font-size: 0.82rem;
                text-transform: uppercase;
                letter-spacing: 0.12em;
                color: rgba(170, 205, 255, 0.72);
                margin-bottom: 0.35rem;
            }
            .hmi-summary-status {
                font-size: 1.7rem;
                font-weight: 800;
                line-height: 1.1;
                margin-bottom: 0.45rem;
                color: #f4f8ff;
            }
            .hmi-summary-copy {
                color: rgba(228, 237, 255, 0.82);
                font-size: 0.98rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("### Execuçõoes salvas e validacao em lote")
        st.caption(
            "Use esta area para rodar validacao HMI em execucoes gravadas no Data/runs/tester/ e inspecionar resultados tecnicos."
        )

        with st.container(border=True):
            st.markdown("#### Biblioteca")
            config_col1, config_col2, config_col3 = st.columns([2, 1, 1])
            with config_col1:
                figma_dir = st.text_input(
                    "Pasta GEI_SCREENS / exports Figma",
                    value=DEFAULT_HMI_LIBRARY_DIR,
                    key="hmi_unified_figma_dir",
                    disabled=True,
                    help="Caminho fixo da biblioteca GEI usada para indexar e comparar as telas.",
                )
                st.session_state["hmi_figma_dir"] = DEFAULT_HMI_LIBRARY_DIR
                if figma_dir.strip() and not st.session_state.get("vqa_reference_dir"):
                    st.session_state["vqa_reference_dir"] = figma_dir.strip()
            with config_col2:
                unified_index_name = st.text_input(
                    "Nome indice HMI",
                    value=_safe_str(st.session_state.get("hmi_index_name_value"), "biblioteca_hmi"),
                    key="hmi_unified_index_name",
                )
                st.session_state["hmi_index_name_value"] = unified_index_name.strip() or "biblioteca_hmi"
            with config_col3:
                st.selectbox(
                    "Fonte screenshots",
                    options=["auto", "resultados", "frames", "both"],
                    key="hmi_capture_source",
                    help="auto: usa resultados e cai para frames se nao existir.",
                )

            with st.expander("Parametros avancados", expanded=False):
                advanced_cols = st.columns(4)
                with advanced_cols[0]:
                    st.checkbox("Roteamento por contexto", key="hmi_enable_context_routing")
                with advanced_cols[1]:
                    st.number_input("Contexto Top-K", min_value=1, max_value=30, key="hmi_context_top_k")
                with advanced_cols[2]:
                    pass_threshold = st.slider("Threshold PASS", min_value=0.5, max_value=0.99, value=0.93, step=0.01, key="hmi_unified_pass")
                with advanced_cols[3]:
                    warning_threshold = st.slider("Threshold WARNING", min_value=0.3, max_value=0.95, value=0.82, step=0.01, key="hmi_unified_warning")

                advanced_cols_2 = st.columns(4)
                with advanced_cols_2[0]:
                    top_k = st.number_input("Top candidatos", min_value=1, max_value=20, value=8, key="hmi_unified_top_k")
                with advanced_cols_2[1]:
                    point_tolerance = st.slider("Tolerancia pixel", min_value=4, max_value=40, value=18, key="hmi_unified_tolerance")
                with advanced_cols_2[2]:
                    exact_match_ratio = st.slider("Pixel match minimo", min_value=0.9, max_value=0.999, value=0.985, step=0.001, key="hmi_unified_exact")
                with advanced_cols_2[3]:
                    min_cell_score = st.slider("Pior celula minima", min_value=0.7, max_value=0.999, value=0.92, step=0.001, key="hmi_unified_min_cell")

            if context_stats:
                with st.expander("Features no indice atual", expanded=False):
                    st.json(context_stats)

            action_col1, action_col2 = st.columns([1, 1])
            with action_col1:
                if st.button("Indexar biblioteca HMI", use_container_width=True):
                    if not figma_dir.strip():
                        st.error("Informe a pasta dos exports do Figma.")
                    else:
                        try:
                            index_path, index = _resolve_hmi_library(
                                hmi,
                                cache_root,
                                figma_dir.strip(),
                                _safe_str(st.session_state["hmi_index_name_value"]),
                            )
                            st.session_state["hmi_index_path"] = _safe_str(index_path)
                            st.success(f"Biblioteca HMI indexada com {index['screen_count']} telas.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Falha ao indexar: {exc}")
            with action_col2:
                st.caption("Use a mesma biblioteca para HMI contextual e Visual QA.")

        st.divider()
        st.markdown("### Rodar lote em execucao salva")

        if not tests:
            st.warning("Nenhuma execucao encontrada em Data.")
        else:
            with st.container(border=True):
                st.markdown("#### Execucao")
                selected = st.selectbox("Execucao", options=list(label_map.keys()), key="hmi_unified_exec_select")
                categoria, teste = label_map[selected]
                test_dir = str(resolve_tester_run_dir(categoria, teste) or "")
                screens = hmi["collect_result_screens"](test_dir, source=_safe_str(st.session_state.get("hmi_capture_source"), "auto"))
                mini_stats = st.columns(3)
                mini_stats[0].metric("Execucao", selected)
                mini_stats[1].metric("Screenshots", len(screens))
                mini_stats[2].metric("Indice HMI", "Pronto" if st.session_state.get("hmi_index_path") and os.path.exists(st.session_state["hmi_index_path"]) else "Pendente")

                exec_col1, exec_col2 = st.columns([1.1, 0.9])
                with exec_col1:
                    st.markdown("##### Acao principal")
                    if st.button("Executar validacao HMI", type="primary", use_container_width=True):
                        library_index = None
                        if st.session_state.get("hmi_index_path") and os.path.exists(st.session_state["hmi_index_path"]):
                            library_index = hmi["load_library_index"](st.session_state["hmi_index_path"])
                        elif figma_dir.strip():
                            try:
                                index_path, library_index = _resolve_hmi_library(
                                    hmi,
                                    cache_root,
                                    figma_dir.strip(),
                                    _safe_str(st.session_state["hmi_index_name_value"]),
                                )
                                st.session_state["hmi_index_path"] = _safe_str(index_path)
                            except Exception as exc:
                                st.error(f"Falha ao preparar indice HMI: {exc}")
                        if library_index is None:
                            st.error("Indexe a biblioteca HMI antes.")
                        elif not screens:
                            st.error("Nenhuma screenshot encontrada.")
                        else:
                            try:
                                cfg = hmi["ValidationConfig"](
                                    top_k=int(top_k),
                                    pass_threshold=float(pass_threshold),
                                    warning_threshold=float(warning_threshold),
                                    point_tolerance=float(point_tolerance),
                                    exact_match_ratio=float(exact_match_ratio),
                                    min_cell_score=float(min_cell_score),
                                    enable_context_routing=bool(st.session_state.get("hmi_enable_context_routing", True)),
                                    context_top_k=int(st.session_state.get("hmi_context_top_k", 12)),
                                )
                                result = hmi["validate_execution_images"](screens, library_index, cfg)
                                report_path = hmi["save_validation_report"](test_dir, library_index, result)
                                summary = result.get("summary", {})
                                st.session_state["hmi_last_hmi_summary"] = {
                                    "execution": selected,
                                    "report_path": report_path,
                                    "summary": summary,
                                }
                                st.success(f"Relatorio HMI salvo em {report_path}")
                            except Exception as exc:
                                st.error(f"Falha na validacao HMI: {exc}")
                    st.caption("Este e o fluxo principal: contexto da tela, roteamento por feature e comparacao robusta.")
                with exec_col2:
                    with st.expander("Visual QA complementar", expanded=False):
                        st.text_input("Referencia Visual QA", key="vqa_reference_dir")
                        st.text_input("Indice Visual QA", key="vqa_index_dir")
                        st.selectbox("Embedding provider", ["auto", "mobileclip", "openclip", "local"], key="vqa_embedding_provider")
                        st.number_input("Top K", min_value=1, max_value=20, key="vqa_top_k")
                        st.slider("Threshold", min_value=0.05, max_value=0.99, step=0.01, key="vqa_threshold")
                        st.selectbox("Estrategia", ["best", "vote"], key="vqa_strategy")
                        st.checkbox("Usar LLM no report", key="vqa_use_llm")
                        if st.session_state.get("vqa_use_llm"):
                            st.text_input("OLLAMA base URL", key="vqa_ollama_base_url")
                            st.text_input("OLLAMA model", key="vqa_ollama_model")

                        qa_btn_col1, qa_btn_col2 = st.columns(2)
                        with qa_btn_col1:
                            if st.button("Construir indice Visual QA", use_container_width=True):
                                reference_dir = _safe_str(st.session_state.get("vqa_reference_dir")).strip()
                                index_dir = _safe_str(st.session_state.get("vqa_index_dir")).strip()
                                if not reference_dir or not index_dir:
                                    st.error("Informe referencia e indice do Visual QA.")
                                else:
                                    try:
                                        vqa = _load_visual_qa_modules()
                                        cfg = _make_vqa_config(vqa, reference_dir, index_dir, os.path.join(cache_root, "visual_qa_runs"))
                                        use_cases = _make_vqa_use_cases(vqa, cfg)
                                        summary = use_cases["build_index"].execute(str(cfg.reference_dir), str(cfg.index_dir))
                                        st.success(f"Indice Visual QA pronto com {summary.get('images_indexed', 0)} imagens.")
                                    except Exception as exc:
                                        st.error(f"Falha no indice Visual QA: {exc}")
                        with qa_btn_col2:
                            if st.button("Executar Visual QA nesta execucao", use_container_width=True):
                                reference_dir = _safe_str(st.session_state.get("vqa_reference_dir")).strip()
                                index_dir = _safe_str(st.session_state.get("vqa_index_dir")).strip()
                                stats = _vqa_index_stats(index_dir)
                                if not reference_dir:
                                    st.error("Configure a referencia Visual QA.")
                                elif not stats["ready"]:
                                    st.error("Indice Visual QA nao encontrado. Construa o indice antes.")
                                elif not screens:
                                    st.error("Nenhuma screenshot para validar.")
                                else:
                                    try:
                                        vqa = _load_visual_qa_modules()
                                        cfg = _make_vqa_config(vqa, reference_dir, index_dir, _vqa_runs_dir(test_dir))
                                        use_cases = _make_vqa_use_cases(vqa, cfg)
                                        validate = use_cases["validate"]
                                        progress = st.progress(0.0)
                                        rows = []
                                        for i, screenshot in enumerate(screens, start=1):
                                            progress.progress((i - 1) / max(len(screens), 1))
                                            run = validate.execute(
                                                screenshot_path=screenshot,
                                                index_dir=str(cfg.index_dir),
                                                top_k=int(cfg.top_k),
                                                threshold=float(cfg.classification_threshold),
                                                strategy=_safe_str(st.session_state.get("vqa_strategy"), "best"),
                                                output_dir=None,
                                                config_snapshot=cfg.snapshot(),
                                            )
                                            rows.append(
                                                {
                                                    "run_id": run.run_id,
                                                    "screenshot_path": run.screenshot_path,
                                                    "predicted_screen_type": run.predicted_screen_type,
                                                    "pixel_status": run.pixel_result.status if run.pixel_result else "NO_PIXEL",
                                                    "result_json": str(run.json_path) if run.json_path else None,
                                                    "report_path": str(run.report_path) if run.report_path else None,
                                                }
                                            )
                                        progress.progress(1.0)
                                        _save_json(_vqa_summary_path(test_dir), {"total": len(rows), "rows": rows})
                                        st.session_state["hmi_last_vqa_summary"] = {"execution": selected, "total": len(rows)}
                                        st.success(f"Visual QA executado para {len(rows)} screenshot(s).")
                                    except Exception as exc:
                                        st.error(f"Falha no Visual QA: {exc}")

        st.divider()
        st.markdown("### Resultados")

        last_summary = st.session_state.get("hmi_last_hmi_summary") or {}
        summary_payload = last_summary.get("summary") or {}
        if summary_payload:
            result_label = _safe_str(summary_payload.get("result"), "SEM_RESULTADO")
            pass_rate = 0.0
            total_screens = int(summary_payload.get("total_screens", 0) or 0)
            if total_screens > 0:
                pass_rate = float(summary_payload.get("passed", 0) or 0) / float(total_screens)
            st.markdown(
                f"""
                <div class="hmi-summary-card">
                    <div class="hmi-summary-title">Resumo final da ultima execucao</div>
                    <div class="hmi-summary-status">{result_label}</div>
                    <div class="hmi-summary-copy">
                        Execucao: <strong>{_safe_str(last_summary.get("execution"), "-")}</strong>
                        <br/>
                        Pass rate: <strong>{pass_rate:.1%}</strong> |
                        Score medio: <strong>{float(summary_payload.get("average_score", 0.0)):.2%}</strong> |
                        Pixel medio: <strong>{float(summary_payload.get("average_pixel_match", 0.0)):.2%}</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        available = []
        for label, categoria, teste in tests:
            test_dir = str(resolve_tester_run_dir(categoria, teste) or "")
            if os.path.exists(os.path.join(hmi["get_validation_dir"](test_dir), "resultado_hmi.json")):
                available.append(label)

        result_col1, result_col2 = st.columns([1, 1])
        with result_col1:
            with st.container(border=True):
                st.markdown("#### HMI contextual")
                if not available:
                    st.info("Nenhum relatorio HMI gerado.")
                else:
                    selected = st.selectbox("Resultado HMI", options=available, key="hmi_result_select")
                    categoria, teste = label_map[selected]
                    test_dir = str(resolve_tester_run_dir(categoria, teste) or "")
                    report = hmi["load_validation_report"](test_dir)
                    summary = report.get("summary", {})
                    structured_rows = hmi["build_validation_dimension_rows"](report)
                    st.write(summary)
                    if structured_rows:
                        export_filename = (
                            f"hmi_report_{_slugify(selected)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                        )
                        st.markdown("##### Report de validacao HMI")
                        st.caption(
                            "Colunas sintetizadas por tela a partir da validacao automatica de layout, tipografia, icones, espacamento, cores e status final."
                        )
                        st.download_button(
                            "Extrair report",
                            data=hmi["build_validation_dimension_workbook"](structured_rows),
                            file_name=export_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key=f"hmi_dimension_report_{_slugify(selected)}",
                        )
                        st.dataframe(structured_rows, use_container_width=True, hide_index=True)
                    rows = []
                    for item in report.get("items", []):
                        stage1 = item.get("stage1") or {}
                        rows.append(
                            {
                                "arquivo": os.path.basename(_safe_str(item.get("screenshot_path"))),
                                "contexto": stage1.get("predicted_screen_type"),
                                "contexto_conf": stage1.get("context_confidence"),
                                "status": item.get("status"),
                                "match_figma": item.get("screen_name"),
                                "score_final": item.get("scores", {}).get("final"),
                            }
                        )
                    if rows:
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                    for item in report.get("items", []):
                        stage1 = item.get("stage1") or {}
                        with st.expander(f"{os.path.basename(_safe_str(item.get('screenshot_path')))} -> {item.get('screen_name')}"):
                            st.info(_context_narrative(item))
                            st.write(item.get("reason"))
                            st.write(
                                {
                                    "contexto_previsto": stage1.get("predicted_screen_type"),
                                    "contexto_confianca": stage1.get("context_confidence"),
                                    "contexto_estrategia": stage1.get("strategy"),
                                }
                            )
                            if stage1.get("top_contexts"):
                                st.dataframe(stage1.get("top_contexts"), use_container_width=True, hide_index=True)
                            if stage1.get("top_matches"):
                                st.dataframe(stage1.get("top_matches"), use_container_width=True, hide_index=True)
                            c1, c2 = st.columns(2)
                            with c1:
                                _safe_show_image(item.get("screenshot_path"), "Captura", "Imagem nao encontrada")
                            with c2:
                                _safe_show_image(item.get("reference_path"), "Referencia", "Imagem nao encontrada")

        with result_col2:
            with st.container(border=True):
                st.markdown("#### Visual QA")
                vqa_available = []
                for label, categoria, teste in tests:
                    test_dir = str(resolve_tester_run_dir(categoria, teste) or "")
                    if _load_vqa_runs(_vqa_runs_dir(test_dir)):
                        vqa_available.append(label)
                if not vqa_available:
                    st.info("Nenhum resultado Visual QA disponivel.")
                else:
                    selected = st.selectbox("Resultado Visual QA", options=vqa_available, key="vqa_result_select")
                    categoria, teste = label_map[selected]
                    test_dir = str(resolve_tester_run_dir(categoria, teste) or "")
                    runs = _load_vqa_runs(_vqa_runs_dir(test_dir))
                    st.write(f"Runs encontrados: {len(runs)}")
                    table = []
                    for payload in runs:
                        run = payload.get("run") or {}
                        cls = payload.get("classification") or {}
                        pixel = payload.get("pixel_result") or {}
                        table.append(
                            {
                                "arquivo": os.path.basename(_safe_str(run.get("screenshot_path"))),
                                "predicted": cls.get("predicted_screen_type"),
                                "similarity": cls.get("winning_score"),
                                "pixel_status": pixel.get("status"),
                                "diff_percent": pixel.get("difference_percent"),
                                "ssim": pixel.get("ssim_score"),
                            }
                        )
                    if table:
                        st.dataframe(table, use_container_width=True, hide_index=True)
                    for payload in runs:
                        run = payload.get("run") or {}
                        cls = payload.get("classification") or {}
                        pixel = payload.get("pixel_result") or {}
                        with st.expander(f"{os.path.basename(_safe_str(run.get('screenshot_path')))} -> {cls.get('predicted_screen_type')}"):
                            st.write(f"Run ID: {run.get('run_id')}")
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                _safe_show_image(run.get("screenshot_path"), "Screenshot", "Nao encontrada")
                            with c2:
                                _safe_show_image(cls.get("selected_baseline_image"), "Baseline", "Nao encontrada")
                            with c3:
                                _safe_show_image(pixel.get("diff_image_path") if pixel else None, "Diff", "Indisponivel")
                            if cls.get("top_k"):
                                st.dataframe(cls.get("top_k"), use_container_width=True, hide_index=True)
                            report_path = _safe_str((payload.get("report") or {}).get("report_path"))
                            if report_path and os.path.exists(report_path):
                                st.markdown("**Report**")
                                try:
                                    with open(report_path, "r", encoding="utf-8") as fh:
                                        st.markdown(fh.read())
                                except Exception:
                                    st.info(f"Nao foi possivel ler report: {report_path}")


    with tab_demo:
        st.markdown("### Teste Visual 1x1")
        st.caption("Use comparacao direta ou descoberta automatica de contexto com a biblioteca completa do radio.")

        demo_mode = st.radio(
            "Modo",
            options=["Descobrir contexto automaticamente", "Comparacao direta"],
            horizontal=True,
            key="hmi_demo_mode",
        )

        if demo_mode == "Comparacao direta":
            upload_real_col, upload_ref_col = st.columns(2)
            with upload_real_col:
                actual_upload = st.file_uploader(
                    "Imagem real",
                    type=["png", "jpg", "jpeg", "bmp", "webp"],
                    key="hmi_demo_actual_upload",
                )
            with upload_ref_col:
                expected_upload = st.file_uploader(
                    "Imagem prevista",
                    type=["png", "jpg", "jpeg", "bmp", "webp"],
                    key="hmi_demo_expected_upload",
                )

            meta_col1, meta_col2 = st.columns([1, 2])
            with meta_col1:
                feature_context = st.text_input("Contexto", value="demo", key="hmi_demo_context")
            with meta_col2:
                screen_name = st.text_input("Nome da tela esperada", value="Tela esperada", key="hmi_demo_screen_name")
        else:
            actual_upload = st.file_uploader(
                "Imagem real",
                type=["png", "jpg", "jpeg", "bmp", "webp"],
                key="hmi_demo_actual_upload_context",
            )
            expected_upload = None
            feature_context = ""
            screen_name = ""
            st.info("Neste modo, a imagem real eh comparada contra toda a biblioteca HMI para descobrir o contexto e a tela mais provavel.")

        with st.expander("Ajustes avancados", expanded=False):
            demo_enable_context = st.checkbox("Roteamento por contexto", value=True, key="hmi_demo_enable_context")
            demo_allow_alignment = st.checkbox("Alinhamento automatico", value=True, key="hmi_demo_allow_alignment")
            demo_pass_threshold = st.slider("Threshold PASS", min_value=0.5, max_value=0.99, value=0.93, step=0.01, key="hmi_demo_pass")
            demo_warning_threshold = st.slider("Threshold WARNING", min_value=0.3, max_value=0.95, value=0.82, step=0.01, key="hmi_demo_warning")
            demo_point_tolerance = st.slider("Tolerancia pixel", min_value=4, max_value=40, value=18, key="hmi_demo_tolerance")
            demo_exact_match = st.slider("Pixel match minimo", min_value=0.9, max_value=0.999, value=0.985, step=0.001, key="hmi_demo_exact")
            demo_min_cell = st.slider("Pior celula minima", min_value=0.7, max_value=0.999, value=0.92, step=0.001, key="hmi_demo_min_cell")

        button_label = "Analisar contexto e comparar" if demo_mode != "Comparacao direta" else "Comparar imagens"
        if st.button(button_label, type="primary", key="hmi_demo_compare_btn"):
            if actual_upload is None:
                st.error("Envie a imagem real.")
            elif demo_mode == "Comparacao direta" and expected_upload is None:
                st.error("Envie a imagem prevista.")
            else:
                try:
                    cfg = hmi["ValidationConfig"](
                        top_k=5 if demo_mode != "Comparacao direta" else 1,
                        pass_threshold=float(demo_pass_threshold),
                        warning_threshold=float(demo_warning_threshold),
                        point_tolerance=float(demo_point_tolerance),
                        exact_match_ratio=float(demo_exact_match),
                        min_cell_score=float(demo_min_cell),
                        allow_alignment=bool(demo_allow_alignment),
                        enable_context_routing=bool(demo_enable_context),
                        context_top_k=8 if demo_mode != "Comparacao direta" else 3,
                    )
                    if demo_mode == "Comparacao direta":
                        st.session_state["hmi_demo_result"] = _run_demo_compare(
                            hmi=hmi,
                            cache_root=cache_root,
                            expected_upload=expected_upload,
                            actual_upload=actual_upload,
                            feature_context=feature_context.strip() or "demo",
                            screen_name=screen_name.strip() or "Tela esperada",
                            cfg=cfg,
                        )
                    else:
                        index_path, library_index = _resolve_hmi_library(
                            hmi,
                            cache_root,
                            _safe_str(st.session_state.get("hmi_figma_dir")).strip(),
                            _safe_str(st.session_state.get("hmi_index_name_value"), "biblioteca_hmi"),
                        )
                        if library_index is None:
                            raise RuntimeError("Indexe ou configure a biblioteca HMI antes de usar a descoberta automatica de contexto.")
                        st.session_state["hmi_index_path"] = _safe_str(index_path)
                        st.session_state["hmi_demo_result"] = _run_demo_context_discovery(
                            hmi=hmi,
                            cache_root=cache_root,
                            actual_upload=actual_upload,
                            library_index=library_index,
                            cfg=cfg,
                        )
                    st.success("Analise concluida.")
                except Exception as exc:
                    st.error(f"Falha ao comparar imagens: {exc}")

        demo_result = st.session_state.get("hmi_demo_result")
        if demo_result:
            report = demo_result.get("report") or {}
            summary = report.get("summary") or {}
            item = ((report.get("items") or [None])[0]) or {}
            scores = item.get("scores") or {}
            diff_summary = item.get("diff_summary") or {}
            stage1 = item.get("stage1") or {}
            artifacts = item.get("artifacts") or {}
            status = _safe_str(item.get("status"), "SEM_STATUS")

            if status == "PASS":
                st.success(f"Resultado: {status}")
            elif "WARNING" in status:
                st.warning(f"Resultado: {status}")
            else:
                st.error(f"Resultado: {status}")

            st.info(_context_narrative(item))

            top_metrics = st.columns(5)
            top_metrics[0].metric("Score final", f"{float(scores.get('final', 0.0)):.2%}")
            top_metrics[1].metric("Pixel match", f"{float(diff_summary.get('pixel_match_ratio', 0.0)):.2%}")
            top_metrics[2].metric("SSIM/global", f"{float(scores.get('global', 0.0)):.2%}")
            top_metrics[3].metric("Contexto", _safe_str(stage1.get("predicted_screen_type"), "demo"))
            top_metrics[4].metric("Tela encontrada", _safe_str(item.get("screen_name"), "-"))

            st.caption(
                f"Conf. contexto: {float(stage1.get('context_confidence', 0.0)):.2%} | "
                f"Area divergente: {float(diff_summary.get('diff_area_ratio', 0.0)):.2%} | "
                f"Componentes alterados: {int(diff_summary.get('toggle_count', 0))}"
            )

            score_rows = [
                {"metrica": "Global", "score": float(scores.get("global", 0.0))},
                {"metrica": "Pixel", "score": float(scores.get("pixel", 0.0))},
                {"metrica": "Edge", "score": float(scores.get("edge", 0.0))},
                {"metrica": "Grid medio", "score": float(scores.get("grid_avg", 0.0))},
                {"metrica": "Grid pior celula", "score": float(scores.get("grid_min", 0.0))},
                {"metrica": "Estrutura", "score": float(scores.get("structure", 0.0))},
                {"metrica": "Componente", "score": float(scores.get("component", 0.0))},
                {"metrica": "Semantico", "score": float(scores.get("semantic", 0.0))},
                {"metrica": "Texto OCR", "score": float(scores.get("text", 0.0))},
                {"metrica": "Alinhamento", "score": float(scores.get("alignment", 0.0))},
            ]
            st.dataframe(score_rows, use_container_width=True, hide_index=True)
            if stage1.get("top_contexts"):
                st.markdown("**Top contextos detectados**")
                st.dataframe(stage1.get("top_contexts"), use_container_width=True, hide_index=True)
            if stage1.get("top_matches"):
                st.markdown("**Top telas candidatas**")
                st.dataframe(stage1.get("top_matches"), use_container_width=True, hide_index=True)

            img_cols = st.columns(2)
            with img_cols[0]:
                _safe_show_image(item.get("screenshot_path"), "Imagem real", "Imagem real indisponivel")
            with img_cols[1]:
                _safe_show_image(item.get("reference_path"), "Imagem prevista", "Imagem prevista indisponivel")

            tech_cols = st.columns(2)
            with tech_cols[0]:
                _safe_show_image(artifacts.get("aligned_path"), "Alinhada", "Imagem alinhada indisponivel")
            with tech_cols[1]:
                _safe_show_image(artifacts.get("diff_mask_path"), "Mascara diff", "Mascara diff indisponivel")

            with st.expander("Detalhes tecnicos", expanded=False):
                st.write(item.get("reason"))
                st.write(
                    {
                        "report_path": demo_result.get("report_path"),
                        "index_path": demo_result.get("index_path"),
                        "summary": summary,
                        "stage1": stage1,
                        "diff_summary": diff_summary,
                    }
                )


def main() -> None:
    base_dir = str(PROJECT_ROOT)
    data_root = str(PROJECT_ROOT / "Data")
    st.set_page_config(page_title="Validacao HMI", page_icon="", layout="wide")
    apply_dark_background(hide_header=True)
    render_hmi_validation_page(base_dir, data_root)


if __name__ == "__main__":
    main()


__all__ = [
    "_build_validation_report_payload",
    "_compact_live_result",
    "_live_monitor_belongs_to_session",
    "_preferred_live_capture_size",
    "main",
    "render_hmi_validation_page",
]
