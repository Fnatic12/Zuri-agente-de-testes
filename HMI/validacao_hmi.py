import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import streamlit as st
from PIL import Image
from app.shared.adb_utils import resolve_adb_path
from app.shared.project_paths import root_path
from app.shared.ui_theme import apply_dark_background

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


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
    from HMI.hmi_ai import get_backend_status
    from HMI.hmi_engine import ValidationConfig, collect_result_screens, evaluate_single_screenshot, validate_execution_images
    from HMI.hmi_indexer import build_library_index, load_library_index
    from HMI.hmi_report import get_validation_dir, load_validation_report, save_validation_report

    return {
        "get_backend_status": get_backend_status,
        "ValidationConfig": ValidationConfig,
        "collect_result_screens": collect_result_screens,
        "evaluate_single_screenshot": evaluate_single_screenshot,
        "validate_execution_images": validate_execution_images,
        "build_library_index": build_library_index,
        "load_library_index": load_library_index,
        "get_validation_dir": get_validation_dir,
        "load_validation_report": load_validation_report,
        "save_validation_report": save_validation_report,
    }


def _load_visual_qa_modules() -> Dict[str, Any]:
    from visual_qa.application.use_cases.build_vector_index import BuildVectorIndex
    from visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
    from visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
    from visual_qa.config import VisualQaConfig, load_config
    from visual_qa.infrastructure.embeddings.factory import build_embedding_provider
    from visual_qa.infrastructure.llm.factory import build_report_generator
    from visual_qa.infrastructure.llm.null_report_generator import NullReportGenerator
    from visual_qa.infrastructure.pixel_compare.existing_pixel_adapter import ExistingPixelAdapter
    from visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore
    from visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository

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


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "biblioteca"


def _list_tests(data_root: str):
    rows = []
    if not os.path.isdir(data_root):
        return rows
    for categoria in sorted(os.listdir(data_root)):
        cat_path = os.path.join(data_root, categoria)
        if not os.path.isdir(cat_path):
            continue
        for teste in sorted(os.listdir(cat_path)):
            test_path = os.path.join(cat_path, teste)
            has_results = os.path.isdir(os.path.join(test_path, "resultados"))
            has_frames = os.path.isdir(os.path.join(test_path, "frames"))
            if has_results or has_frames:
                rows.append((f"{categoria}/{teste}", categoria, teste))
    return rows


def _safe_show_image(path: Optional[str], caption: str, empty_message: str) -> None:
    if path and os.path.exists(path):
        try:
            st.image(Image.open(path), caption=caption, use_container_width=True)
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

    bottom_img_cols = st.columns(2)
    with bottom_img_cols[0]:
        with st.container(border=True):
            st.markdown("**Overlay de divergencias**")
            _show_image_payload((result.get("debug_images") or {}).get("overlay"), "Overlay", "Overlay indisponivel")
    with bottom_img_cols[1]:
        with st.container(border=True):
            st.markdown("**Heatmap**")
            _show_image_payload((result.get("debug_images") or {}).get("heatmap"), "Heatmap", "Heatmap indisponivel")

    rows = _candidate_rows(result)
    if rows:
        st.markdown("#### Top correspondencias")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    for idx, candidate in enumerate((result.get("candidate_results") or [])[:5], start=1):
        candidate_scores = candidate.get("scores") or {}
        candidate_diff = candidate.get("diff_summary") or {}
        with st.expander(
            f"Top {idx}: {_safe_str(candidate.get('screen_name'), '-')} | {_safe_str(candidate.get('status'), '-')}"
        ):
            detail_cols = st.columns(3)
            with detail_cols[0]:
                with st.container(border=True):
                    st.markdown("**Screenshot real**")
                    _show_image_payload(result.get("screenshot_path"), "Screenshot real", "Screenshot indisponivel")
            with detail_cols[1]:
                with st.container(border=True):
                    st.markdown("**Referencia candidata**")
                    _show_image_payload(candidate.get("reference_path"), "Referencia", "Referencia indisponivel")
            with detail_cols[2]:
                with st.container(border=True):
                    st.markdown("**Overlay da candidata**")
                    _show_image_payload((candidate.get("debug_images") or {}).get("overlay"), "Overlay", "Overlay indisponivel")

            stats_cols = st.columns(4)
            stats_cols[0].metric("Similaridade", f"{float(candidate_scores.get('final', 0.0) or 0.0):.1%}")
            stats_cols[1].metric("Pixel match", f"{float(candidate_diff.get('pixel_match_ratio', 0.0) or 0.0):.1%}")
            stats_cols[2].metric("Contexto", _safe_str(candidate.get("feature_context"), "-"))
            stats_cols[3].metric("Status", _safe_str(candidate.get("status"), "-"))


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


def _safe_serial_name(serial: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(serial or "sem_serial")) or "sem_serial"


def _live_lookup_root(cache_root: str, serial: str) -> str:
    return os.path.join(cache_root, "live_lookup", _safe_serial_name(serial))


def _live_lookup_shots_dir(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "screenshots")


def _live_lookup_results_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "results.json")


def _live_lookup_monitor_state_path(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "monitor_state.json")


def _live_lookup_stop_flag(cache_root: str, serial: str) -> str:
    return os.path.join(_live_lookup_root(cache_root, serial), "stop.flag")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
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
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _load_live_monitor_state(cache_root: str, serial: str) -> Dict[str, Any]:
    return _load_json(_live_lookup_monitor_state_path(cache_root, serial)) or {}


def _live_monitor_running(cache_root: str, serial: str) -> bool:
    live_pids = _list_live_monitor_pids(serial)
    if live_pids:
        return True
    state = _load_live_monitor_state(cache_root, serial)
    pid = int(state.get("pid", 0) or 0)
    return _pid_is_running(pid)


def _start_live_monitor(cache_root: str, serial: str) -> str:
    root_dir = _live_lookup_root(cache_root, serial)
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    os.makedirs(shots_dir, exist_ok=True)
    stop_flag = _live_lookup_stop_flag(cache_root, serial)
    if os.path.exists(stop_flag):
        os.remove(stop_flag)
    if _live_monitor_running(cache_root, serial):
        return "Monitor automatico ja esta ativo."

    state = _load_live_monitor_state(cache_root, serial)
    previous_pid = int(state.get("pid", 0) or 0)
    if previous_pid > 0:
        _kill_process_tree(previous_pid)
    for pid in _list_live_monitor_pids(serial):
        _kill_process_tree(pid)

    script_path = root_path("Scripts", "hmi_touch_monitor.py")
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
    with open(log_path, "a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [python_exec, script_path, "--serial", serial, "--output-dir", shots_dir],
            cwd=root_path(),
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
            "output_dir": shots_dir,
        },
    )
    return f"Monitor automatico iniciado para {serial}."


def _stop_live_monitor(cache_root: str, serial: str) -> str:
    stop_flag = _live_lookup_stop_flag(cache_root, serial)
    os.makedirs(os.path.dirname(stop_flag), exist_ok=True)
    Path(stop_flag).write_text("stop", encoding="utf-8")
    state = _load_live_monitor_state(cache_root, serial)
    pid = int(state.get("pid", 0) or 0)
    if pid > 0 and _pid_is_running(pid):
        _kill_process_tree(pid)
    for live_pid in _list_live_monitor_pids(serial):
        _kill_process_tree(live_pid)
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
        "reference_path": _safe_str(result.get("reference_path"), ""),
        "processed_at": datetime.now().isoformat(),
    }


def _process_live_lookup_queue(
    hmi: Dict[str, Any],
    cache_root: str,
    serial: str,
    library_index: Dict[str, Any],
) -> Dict[str, Any]:
    shots_dir = _live_lookup_shots_dir(cache_root, serial)
    state_path = _live_lookup_results_path(cache_root, serial)
    payload = _load_json(state_path) or {"processed": [], "history": []}
    processed = set(str(name) for name in payload.get("processed", []))
    history = list(payload.get("history", []))
    latest_bundle = st.session_state.get("hmi_lookup_result")
    latest_result = latest_bundle.get("result") if isinstance(latest_bundle, dict) else None
    latest_path = _safe_str(latest_result.get("screenshot_path")) if isinstance(latest_result, dict) else ""
    cfg = _default_lookup_cfg(hmi)

    if not os.path.isdir(shots_dir):
        return {"new_count": 0, "history": history, "latest_bundle": latest_bundle}

    files = []
    for name in sorted(os.listdir(shots_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            files.append(name)

    new_count = 0
    latest_file_path = ""
    for name in files:
        file_path = os.path.join(shots_dir, name)
        latest_file_path = file_path
        if name in processed:
            continue
        result = hmi["evaluate_single_screenshot"](file_path, library_index, cfg)
        history.append(_result_to_history_row(result))
        processed.add(name)
        latest_bundle = {"lookup_dir": _live_lookup_root(cache_root, serial), "actual_path": file_path, "result": result}
        st.session_state["hmi_lookup_result"] = latest_bundle
        new_count += 1

    if not latest_bundle and latest_file_path:
        result = hmi["evaluate_single_screenshot"](latest_file_path, library_index, cfg)
        latest_bundle = {"lookup_dir": _live_lookup_root(cache_root, serial), "actual_path": latest_file_path, "result": result}
        st.session_state["hmi_lookup_result"] = latest_bundle

    history = history[-50:]
    _save_json(state_path, {"processed": sorted(processed), "history": history})
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
    cache_root = os.path.join(data_root, "hmi_cache")
    os.makedirs(cache_root, exist_ok=True)

    st.session_state.setdefault("hmi_figma_dir", "")
    st.session_state.setdefault("hmi_index_path", "")
    st.session_state.setdefault("hmi_index_name_value", "biblioteca_hmi")
    st.session_state.setdefault("hmi_capture_source", "auto")
    st.session_state.setdefault("hmi_enable_context_routing", True)
    st.session_state.setdefault("hmi_context_top_k", 12)
    st.session_state.setdefault("vqa_reference_dir", "")
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

    tab_lookup, tab_validate, tab_demo = st.tabs(["Comparacao ao Vivo", "Execucoes Salvas", "Teste Visual"])

    with tab_lookup:
        st.markdown("### Comparacao ao vivo com a biblioteca")
        st.caption("Compare manualmente um screenshot real ou deixe a bancada conectada gerar screenshots automaticamente a cada toque.")

        with st.container(border=True):
            lookup_dir = st.text_input(
                "Pasta da biblioteca de telas",
                value=_safe_str(st.session_state.get("hmi_figma_dir")),
                key="hmi_lookup_figma_dir",
            )
            st.session_state["hmi_figma_dir"] = lookup_dir.strip()
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
            st.markdown("### Comparacao automatica da bancada")
            st.caption("Quando ativa, cada toque detectado no radio gera um screenshot que e comparado automaticamente com a biblioteca.")

            selected_serial = st.selectbox(
                "Bancada conectada",
                options=connected_devices,
                key="hmi_live_selected_serial",
            )
            live_running = _live_monitor_running(cache_root, selected_serial)

            live_action_cols = st.columns([1, 1])
            with live_action_cols[0]:
                if not live_running:
                    if st.button("Ativar comparacao automatica", use_container_width=True, key="hmi_live_start_btn"):
                        if not lookup_dir.strip():
                            st.error("Informe a pasta da biblioteca antes de ativar o modo automatico.")
                        else:
                            msg = _start_live_monitor(cache_root, selected_serial)
                            st.success(msg)
                            st.rerun()
                else:
                    if st.button("Parar comparacao automatica", use_container_width=True, key="hmi_live_stop_btn"):
                        msg = _stop_live_monitor(cache_root, selected_serial)
                        st.info(msg)
                        st.rerun()
            with live_action_cols[1]:
                st.metric("Modo automatico", "ATIVO" if live_running else "PARADO")

            if live_running and lookup_dir.strip():
                index_path, live_library_index = _resolve_hmi_library(
                    hmi,
                    cache_root,
                    lookup_dir.strip(),
                    _safe_str(st.session_state.get("hmi_index_name_value"), "biblioteca_hmi"),
                )
                if live_library_index is not None:
                    st.session_state["hmi_index_path"] = _safe_str(index_path)
                    if st_autorefresh is not None:
                        st_autorefresh(interval=1800, limit=None, key=f"hmi_live_refresh_{selected_serial}")
                    live_payload = _process_live_lookup_queue(hmi, cache_root, selected_serial, live_library_index)
                    if live_payload.get("new_count", 0):
                        st.success(f"{int(live_payload['new_count'])} screenshot(s) novo(s) comparado(s) automaticamente.")
                    history_rows = live_payload.get("history") or []
                    if history_rows:
                        st.markdown("#### Historico automatico")
                        st.dataframe(
                            [
                                {
                                    "capturado_em": row.get("capturado_em"),
                                    "tela": row.get("screen_name"),
                                    "similaridade": f"{float(row.get('similarity', 0.0) or 0.0):.1%}",
                                    "pixel_match": f"{float(row.get('pixel_match', 0.0) or 0.0):.1%}",
                                    "status": row.get("status"),
                                }
                                for row in reversed(history_rows[-15:])
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
            elif connected_devices and not lookup_dir.strip():
                st.info("Informe a pasta da biblioteca para habilitar a comparacao automatica da bancada.")
        else:
            st.info("Nenhuma bancada ADB conectada no momento. O modo automatico aparece quando o radio estiver conectado.")

        _render_library_lookup_result(st.session_state.get("hmi_lookup_result"))

    with tab_validate:
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
        st.markdown("### Execucoes salvas e validacao em lote")
        st.caption("Use esta area para rodar validacao HMI em execucoes gravadas no Data/ e inspecionar resultados tecnicos.")

        with st.container(border=True):
            st.markdown("#### Biblioteca")
            config_col1, config_col2, config_col3 = st.columns([2, 1, 1])
            with config_col1:
                figma_dir = st.text_input(
                    "Pasta GEI_SCREENS / exports Figma",
                    value=_safe_str(st.session_state.get("hmi_figma_dir")),
                    key="hmi_unified_figma_dir",
                )
                st.session_state["hmi_figma_dir"] = figma_dir.strip()
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
                    pass_threshold = st.slider("Threshold PASS", min_value=0.5, max_value=0.99, value=0.93, key="hmi_unified_pass")
                with advanced_cols[3]:
                    warning_threshold = st.slider("Threshold WARNING", min_value=0.3, max_value=0.95, value=0.82, key="hmi_unified_warning")

                advanced_cols_2 = st.columns(4)
                with advanced_cols_2[0]:
                    top_k = st.number_input("Top candidatos", min_value=1, max_value=20, value=8, key="hmi_unified_top_k")
                with advanced_cols_2[1]:
                    point_tolerance = st.slider("Tolerancia pixel", min_value=4, max_value=40, value=18, key="hmi_unified_tolerance")
                with advanced_cols_2[2]:
                    exact_match_ratio = st.slider("Pixel match minimo", min_value=0.9, max_value=0.999, value=0.985, key="hmi_unified_exact")
                with advanced_cols_2[3]:
                    min_cell_score = st.slider("Pior celula minima", min_value=0.7, max_value=0.999, value=0.92, key="hmi_unified_min_cell")

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
                test_dir = os.path.join(data_root, categoria, teste)
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
            test_dir = os.path.join(data_root, categoria, teste)
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
                    test_dir = os.path.join(data_root, categoria, teste)
                    report = hmi["load_validation_report"](test_dir)
                    summary = report.get("summary", {})
                    st.write(summary)
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
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                _safe_show_image(item.get("screenshot_path"), "Captura", "Imagem nao encontrada")
                            with c2:
                                _safe_show_image(item.get("reference_path"), "Referencia", "Imagem nao encontrada")
                            with c3:
                                _safe_show_image((item.get("artifacts") or {}).get("overlay_path"), "Overlay", "Overlay indisponivel")

        with result_col2:
            with st.container(border=True):
                st.markdown("#### Visual QA")
                vqa_available = []
                for label, categoria, teste in tests:
                    test_dir = os.path.join(data_root, categoria, teste)
                    if _load_vqa_runs(_vqa_runs_dir(test_dir)):
                        vqa_available.append(label)
                if not vqa_available:
                    st.info("Nenhum resultado Visual QA disponivel.")
                else:
                    selected = st.selectbox("Resultado Visual QA", options=vqa_available, key="vqa_result_select")
                    categoria, teste = label_map[selected]
                    test_dir = os.path.join(data_root, categoria, teste)
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
            demo_pass_threshold = st.slider("Threshold PASS", min_value=0.5, max_value=0.99, value=0.93, key="hmi_demo_pass")
            demo_warning_threshold = st.slider("Threshold WARNING", min_value=0.3, max_value=0.95, value=0.82, key="hmi_demo_warning")
            demo_point_tolerance = st.slider("Tolerancia pixel", min_value=4, max_value=40, value=18, key="hmi_demo_tolerance")
            demo_exact_match = st.slider("Pixel match minimo", min_value=0.9, max_value=0.999, value=0.985, key="hmi_demo_exact")
            demo_min_cell = st.slider("Pior celula minima", min_value=0.7, max_value=0.999, value=0.92, key="hmi_demo_min_cell")

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

            img_cols = st.columns(4)
            with img_cols[0]:
                _safe_show_image(item.get("screenshot_path"), "Imagem real", "Imagem real indisponivel")
            with img_cols[1]:
                _safe_show_image(item.get("reference_path"), "Imagem prevista", "Imagem prevista indisponivel")
            with img_cols[2]:
                _safe_show_image(artifacts.get("overlay_path"), "Overlay", "Overlay indisponivel")
            with img_cols[3]:
                _safe_show_image(artifacts.get("heatmap_path"), "Heatmap", "Heatmap indisponivel")

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
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_root = os.path.join(base_dir, "Data")
    st.set_page_config(page_title="Validacao HMI", page_icon="", layout="wide")
    apply_dark_background(hide_header=True)
    render_hmi_validation_page(base_dir, data_root)


if __name__ == "__main__":
    main()
