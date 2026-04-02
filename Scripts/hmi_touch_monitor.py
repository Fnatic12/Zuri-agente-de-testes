import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional

from PIL import Image

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from HMI.hmi_engine import ValidationConfig, evaluate_single_screenshot
from HMI.hmi_indexer import load_library_index
from app.shared.adb_utils import resolve_adb_path


DEFAULT_DEV = "/dev/input/event2"
DEFAULT_RES = (1920, 1080)
SCREENSHOT_DELAY_S = 1.05
SCREEN_WATCH_INTERVAL_S = 0.9
SCREEN_CHANGE_HASH_THRESHOLD = 3
STOP_REQUESTED = False
HEX_VAL = re.compile(r"\s([0-9a-fA-F]{8})\s*$")
CREATE_FLAGS = 0
STARTUPINFO = None
USER32 = None
KERNEL32 = None
WINTYPES = None
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
VK_LBUTTON = 0x01
if os.name == "nt":
    import ctypes
    from ctypes import wintypes as WINTYPES

    CREATE_FLAGS = subprocess.CREATE_NO_WINDOW
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = 0
    USER32 = ctypes.windll.user32
    KERNEL32 = ctypes.windll.kernel32

    class POINT(ctypes.Structure):
        _fields_ = [("x", WINTYPES.LONG), ("y", WINTYPES.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", WINTYPES.LONG),
            ("top", WINTYPES.LONG),
            ("right", WINTYPES.LONG),
            ("bottom", WINTYPES.LONG),
        ]

else:
    POINT = None
    RECT = None


def _handle_stop(signum, frame):
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


signal.signal(signal.SIGTERM, _handle_stop)
signal.signal(signal.SIGINT, _handle_stop)


def adb_cmd(serial: str | None = None) -> list[str]:
    adb_path = resolve_adb_path()
    if serial:
        return [adb_path, "-s", serial]
    return [adb_path]


def _run_kwargs() -> dict:
    kwargs = {"creationflags": CREATE_FLAGS}
    if STARTUPINFO is not None:
        kwargs["startupinfo"] = STARTUPINFO
    return kwargs


def _kill_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **_run_kwargs(),
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def run_out(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, **_run_kwargs())
    return proc.stdout.strip()


def log_message(message: str) -> None:
    print(f"[hmi_touch_monitor] {message}", flush=True)


def _default_results_payload() -> dict[str, Any]:
    return {
        "processed": [],
        "history": [],
        "full_results": [],
    }


def _load_json_dict(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_json_dict(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe_payload: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) == "debug_images":
                safe_payload[str(key)] = {}
                continue
            safe_payload[str(key)] = _json_safe_value(item)
        return safe_payload
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
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


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    compacted = _json_safe_value(result)
    return compacted if isinstance(compacted, dict) else {}


def _result_to_history_row(result: dict[str, Any]) -> dict[str, Any]:
    scores = result.get("scores") or {}
    diff_summary = result.get("diff_summary") or {}
    screenshot_path = str(result.get("screenshot_path") or "")
    return {
        "capturado_em": os.path.basename(screenshot_path),
        "screenshot_path": screenshot_path,
        "screen_name": str(result.get("screen_name") or "-"),
        "feature_context": str(result.get("feature_context") or "-"),
        "status": str(result.get("status") or "-"),
        "similarity": float(scores.get("final", 0.0) or 0.0),
        "pixel_match": float(diff_summary.get("pixel_match_ratio", 0.0) or 0.0),
        "reference_path": str(result.get("reference_path") or ""),
        "processed_at": datetime.now().isoformat(),
    }


def _store_validation_result(results_path: str, file_name: str, result: dict[str, Any]) -> dict[str, Any]:
    payload = _load_json_dict(results_path) or _default_results_payload()
    processed = set(str(name) for name in payload.get("processed", []))
    history = list(payload.get("history", []))
    full_results = [item for item in payload.get("full_results", []) if isinstance(item, dict)]

    compact_result = _compact_result(result)
    if file_name not in processed:
        history.append(_result_to_history_row(compact_result))
        full_results.append(compact_result)
        processed.add(file_name)

    payload = {
        "processed": sorted(processed),
        "history": history[-50:],
        "full_results": full_results[-100:],
    }
    _save_json_dict(results_path, payload)
    return payload


def _build_lookup_cfg() -> ValidationConfig:
    return ValidationConfig(
        top_k=5,
        pass_threshold=0.93,
        warning_threshold=0.82,
        point_tolerance=18.0,
        exact_match_ratio=0.985,
        min_cell_score=0.92,
        enable_context_routing=False,
        context_top_k=5,
    )


def _hash_distance(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b:
        return 999
    return sum(left != right for left, right in zip(hash_a, hash_b))


def _average_hash_from_path(image_path: str, hash_size: int = 8) -> str:
    with Image.open(image_path) as img:
        gray = img.convert("L").resize((hash_size, hash_size))
        pixels = list(gray.getdata())
    if not pixels:
        return ""
    avg = sum(int(value) for value in pixels) / float(len(pixels))
    return "".join("1" if int(value) >= avg else "0" for value in pixels)


def _resize_image(local_path: str, target_size: tuple[int, int] | None) -> None:
    if not target_size:
        return
    width, height = int(target_size[0]), int(target_size[1])
    if width <= 0 or height <= 0:
        return
    try:
        with Image.open(local_path) as img:
            if img.size == (width, height):
                return
            resampling = getattr(Image, "Resampling", Image)
            resized = img.resize((width, height), resampling.LANCZOS)
            resized.save(local_path)
    except Exception as exc:
        log_message(f"falha ao redimensionar captura para {width}x{height}: {exc}")


def take_screenshot(local_path: str, serial: str | None = None, target_size: tuple[int, int] | None = None) -> str:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    cmd = adb_cmd(serial) + ["exec-out", "screencap", "-p"]
    with open(local_path, "wb") as fh:
        subprocess.run(cmd, stdout=fh, **_run_kwargs())
    _resize_image(local_path, target_size)
    return local_path


def get_resolution(serial: str | None = None) -> tuple[int, int]:
    out = run_out(adb_cmd(serial) + ["shell", "wm", "size"])
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
    if match:
        return int(match.group(1)), int(match.group(2))
    return DEFAULT_RES


def autodetect_touch_device(serial: str | None = None) -> str:
    out = run_out(adb_cmd(serial) + ["shell", "getevent", "-pl"])
    dev_touchscreen = None
    dev_touch = None
    current_block: list[str] = []

    for line in out.splitlines():
        if line.startswith("add device"):
            current_block = [line]
        else:
            current_block.append(line)

        if "name:" not in line.lower():
            continue
        name_line = line.lower()
        if "touchscreen" in name_line:
            match = re.search(r"add device \d+:\s+(/dev/input/event\d+)", current_block[0])
            if match:
                dev_touchscreen = match.group(1)
        elif "touch" in name_line:
            match = re.search(r"add device \d+:\s+(/dev/input/event\d+)", current_block[0])
            if match and dev_touch is None:
                dev_touch = match.group(1)

    return dev_touchscreen or dev_touch or DEFAULT_DEV


def get_abs_ranges_for_device(dev_path: str, serial: str | None = None) -> dict[str, dict[str, int | None]]:
    out = run_out(adb_cmd(serial) + ["shell", "getevent", "-pl", dev_path])
    ranges: dict[str, dict[str, int | None]] = {
        "ABS_X": {"min": 0, "max": None},
        "ABS_Y": {"min": 0, "max": None},
        "ABS_MT_POSITION_X": {"min": 0, "max": None},
        "ABS_MT_POSITION_Y": {"min": 0, "max": None},
    }
    for line in out.splitlines():
        for key in list(ranges.keys()):
            if key not in line:
                continue
            match = re.search(r"min\s+(\d+),\s*max\s+(\d+)", line)
            if match:
                ranges[key]["min"] = int(match.group(1))
                ranges[key]["max"] = int(match.group(2))
    return ranges


def scale_to_px(val: int, min_v: int, max_v: int | None, px_max: int) -> int:
    if max_v is None or max_v == min_v:
        return int(val)
    val = max(min_v, min(max_v, val))
    ratio = (val - min_v) / float(max_v - min_v)
    return int(round(ratio * (px_max - 1)))


def hex_last_int(line: str) -> int | None:
    match = HEX_VAL.search(line)
    return int(match.group(1), 16) if match else None


def _stop_flag_candidates(output_dir: str) -> list[str]:
    parent_dir = os.path.dirname(output_dir)
    return [
        os.path.join(output_dir, "stop.flag"),
        os.path.join(parent_dir, "stop.flag"),
    ]


def should_stop(output_dir: str) -> bool:
    if STOP_REQUESTED:
        return True
    return any(os.path.exists(path) for path in _stop_flag_candidates(output_dir))


def _touch_axis_range(abs_ranges: dict[str, dict[str, int | None]], axis: str) -> tuple[int, int | None]:
    if axis == "x":
        preferred = abs_ranges.get("ABS_MT_POSITION_X", {})
        fallback = abs_ranges.get("ABS_X", {})
    else:
        preferred = abs_ranges.get("ABS_MT_POSITION_Y", {})
        fallback = abs_ranges.get("ABS_Y", {})

    preferred_max = preferred.get("max")
    if preferred_max is not None:
        return int(preferred.get("min") or 0), int(preferred_max)

    fallback_max = fallback.get("max")
    return int(fallback.get("min") or 0), int(fallback_max) if fallback_max is not None else None


def is_touch_start_line(line: str) -> bool:
    if "EV_KEY" in line and "BTN_TOUCH" in line and "DOWN" in line:
        return True
    if "EV_ABS" in line and "ABS_MT_TRACKING_ID" in line:
        value = hex_last_int(line)
        return value is not None and value != 0xFFFFFFFF
    return False


def is_touch_end_line(line: str) -> bool:
    if "EV_KEY" in line and "BTN_TOUCH" in line and "UP" in line:
        return True
    if "EV_ABS" in line and "ABS_MT_TRACKING_ID" in line:
        value = hex_last_int(line)
        return value == 0xFFFFFFFF
    return False


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
    if not KERNEL32 or pid <= 0:
        return ""
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = WINTYPES.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if KERNEL32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.strip()
    except Exception:
        return ""
    finally:
        KERNEL32.CloseHandle(handle)
    return ""


def _foreground_window_info() -> dict[str, Any]:
    if not USER32:
        return {"hwnd": None, "title": "", "pid": 0, "process_name": "", "process_path": ""}
    hwnd = USER32.GetForegroundWindow()
    pid = WINTYPES.DWORD(0)
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_path = _query_process_image_name(int(pid.value))
    process_name = os.path.basename(process_path).lower() if process_path else ""
    return {
        "hwnd": hwnd,
        "title": _window_text(hwnd),
        "pid": int(pid.value),
        "process_name": process_name,
        "process_path": process_path,
    }


def _is_scrcpy_foreground(info: dict[str, Any]) -> bool:
    process_name = str(info.get("process_name") or "").lower()
    title = str(info.get("title") or "").lower()
    return "scrcpy" in process_name or "scrcpy" in title


def _pointer_position_in_window(hwnd: Any) -> tuple[int, int]:
    if not USER32 or not hwnd or POINT is None or RECT is None:
        return -1, -1
    point = POINT()
    rect = RECT()
    if not USER32.GetCursorPos(ctypes.byref(point)):
        return -1, -1
    if not USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return int(point.x), int(point.y)
    return int(point.x - rect.left), int(point.y - rect.top)


def append_manifest(output_dir: str, file_name: str, action_type: str, x: int, y: int) -> None:
    manifest_path = os.path.join(output_dir, "manifest.jsonl")
    payload = {
        "captured_at": datetime.now().isoformat(),
        "file": file_name,
        "action": action_type,
        "x": x,
        "y": y,
    }
    with open(manifest_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _capture_output_frame(
    output_dir: str,
    serial: str | None,
    action_type: str,
    x: int,
    y: int,
    target_size: tuple[int, int] | None,
) -> tuple[str, str]:
    file_name = f"touch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    file_path = os.path.join(output_dir, file_name)
    take_screenshot(file_path, serial, target_size=target_size)
    append_manifest(output_dir, file_name, action_type, x, y)
    return file_name, file_path


def _compare_capture_if_configured(
    file_name: str,
    file_path: str,
    results_path: str | None,
    library_index: Optional[dict[str, Any]],
    cfg: Optional[ValidationConfig],
) -> None:
    if not results_path or library_index is None or cfg is None:
        return
    try:
        result = evaluate_single_screenshot(file_path, library_index, cfg)
        _store_validation_result(results_path, file_name, result)
        log_message(
            "comparacao concluida "
            f"{file_name} -> {str(result.get('screen_name') or 'sem_match')} "
            f"[{str(result.get('status') or 'SEM_STATUS')}]"
        )
    except Exception as exc:
        log_message(f"falha ao comparar {file_name}: {exc}")


def _capture_screen_change_frame(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    previous_hash: str,
    min_hash_distance: int = SCREEN_CHANGE_HASH_THRESHOLD,
) -> tuple[str, Optional[str], Optional[str]]:
    with NamedTemporaryFile(prefix="hmi_watch_", suffix=".png", dir=output_dir, delete=False) as temp_file:
        temp_path = temp_file.name
    try:
        take_screenshot(temp_path, serial, target_size=target_size)
        frame_hash = _average_hash_from_path(temp_path)
        if previous_hash and _hash_distance(previous_hash, frame_hash) < max(1, int(min_hash_distance)):
            os.remove(temp_path)
            return previous_hash, None, None
        file_name = f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        file_path = os.path.join(output_dir, file_name)
        os.replace(temp_path, file_path)
        append_manifest(output_dir, file_name, "screen_change", -1, -1)
        return frame_hash, file_name, file_path
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def collect_screen_watch_screenshots(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
) -> None:
    last_saved_hash = ""
    log_message("monitorando mudancas reais de tela")
    while not should_stop(output_dir):
        try:
            frame_hash, file_name, file_path = _capture_screen_change_frame(
                output_dir,
                serial,
                target_size,
                last_saved_hash,
            )
        except Exception as exc:
            log_message(f"falha ao observar mudanca de tela: {exc}")
            time.sleep(SCREEN_WATCH_INTERVAL_S)
            continue

        if file_name and file_path:
            last_saved_hash = frame_hash
            log_message(f"capturado {file_name} apos mudanca visual de tela")
            _compare_capture_if_configured(file_name, file_path, results_path, library_index, cfg)

        time.sleep(SCREEN_WATCH_INTERVAL_S)


def collect_host_click_screenshots(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
) -> None:
    if not USER32:
        raise RuntimeError("modo host_click disponivel apenas no Windows")

    prev_left_down = False
    last_capture_at = 0.0
    log_message("monitorando cliques na janela do scrcpy")

    while not should_stop(output_dir):
        info = _foreground_window_info()
        left_down = bool(USER32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

        if _is_scrcpy_foreground(info) and left_down and not prev_left_down:
            now = time.time()
            if now - last_capture_at >= 0.35:
                click_x, click_y = _pointer_position_in_window(info.get("hwnd"))
                log_message(
                    f"clique detectado na janela scrcpy; aguardando {SCREENSHOT_DELAY_S:.2f}s para capturar "
                    f"(cursor={click_x},{click_y})"
                )
                time.sleep(SCREENSHOT_DELAY_S)
                if should_stop(output_dir):
                    break
                file_name, file_path = _capture_output_frame(
                    output_dir,
                    serial,
                    "host_click",
                    click_x,
                    click_y,
                    target_size,
                )
                last_capture_at = time.time()
                log_message(f"capturado {file_name} apos clique no scrcpy")
                _compare_capture_if_configured(file_name, file_path, results_path, library_index, cfg)

        prev_left_down = left_down
        time.sleep(0.03)


def collect_touch_screenshots(
    dev_path: str,
    output_dir: str,
    screen_res: tuple[int, int],
    abs_ranges: dict[str, dict[str, int | None]],
    serial: str | None,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
) -> None:
    x_min, x_max = _touch_axis_range(abs_ranges, "x")
    y_min, y_max = _touch_axis_range(abs_ranges, "y")
    while not STOP_REQUESTED:
        proc = subprocess.Popen(
            adb_cmd(serial) + ["shell", "getevent", "-lt", dev_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            **_run_kwargs(),
        )

        if proc.stdout is None:
            break

        in_touch = False
        sx_raw = sy_raw = None
        lx_raw = ly_raw = None
        t_start = None

        try:
            for raw_line in proc.stdout:
                line = raw_line.decode(errors="ignore").rstrip()
                if should_stop(output_dir):
                    break

                if not in_touch and is_touch_start_line(line):
                    in_touch = True
                    t_start = time.time()
                    sx_raw = sy_raw = lx_raw = ly_raw = None

                if "EV_ABS" in line:
                    if "ABS_MT_POSITION_X" in line or "ABS_X" in line:
                        value = hex_last_int(line)
                        if value is not None:
                            lx_raw = value
                            if sx_raw is None:
                                sx_raw = value
                    elif "ABS_MT_POSITION_Y" in line or "ABS_Y" in line:
                        value = hex_last_int(line)
                        if value is not None:
                            ly_raw = value
                            if sy_raw is None:
                                sy_raw = value

                end_touch = is_touch_end_line(line)

                if not in_touch or not end_touch or None in (sx_raw, sy_raw, lx_raw, ly_raw):
                    continue

                in_touch = False
                dur_s = (time.time() - t_start) if t_start else 0.0
                sx_px = scale_to_px(int(sx_raw), x_min, x_max, screen_res[0])
                sy_px = scale_to_px(int(sy_raw), y_min, y_max, screen_res[1])
                lx_px = scale_to_px(int(lx_raw), x_min, x_max, screen_res[0])
                ly_px = scale_to_px(int(ly_raw), y_min, y_max, screen_res[1])
                dist = math.hypot(lx_px - sx_px, ly_px - sy_px)
                action_type = "tap" if dist <= 25 else "swipe"
                if dist <= 25 and dur_s > 0.8:
                    action_type = "long_press"

                time.sleep(SCREENSHOT_DELAY_S)
                file_name, file_path = _capture_output_frame(
                    output_dir,
                    serial,
                    action_type,
                    sx_px,
                    sy_px,
                    target_size,
                )
                log_message(f"capturado {file_name} apos {action_type} em ({sx_px},{sy_px})")
                _compare_capture_if_configured(file_name, file_path, results_path, library_index, cfg)

        finally:
            try:
                _kill_process_tree(proc.pid)
            except Exception:
                pass

        if should_stop(output_dir):
            break
        log_message("stream getevent encerrado; tentando reconectar em 1s")
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--monitor-mode", choices=("auto", "device", "host_click", "screen_watch"), default="auto")
    parser.add_argument("--index-path", default="")
    parser.add_argument("--results-path", default="")
    parser.add_argument("--target-width", type=int, default=0)
    parser.add_argument("--target-height", type=int, default=0)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    screen_res = get_resolution(args.serial)
    dev_path = autodetect_touch_device(args.serial)
    abs_ranges = get_abs_ranges_for_device(dev_path, args.serial)
    target_size = None
    if int(args.target_width or 0) > 0 and int(args.target_height or 0) > 0:
        target_size = (int(args.target_width), int(args.target_height))
    results_path = str(args.results_path or "").strip() or os.path.join(os.path.dirname(args.output_dir), "results.json")
    library_index: Optional[dict[str, Any]] = None
    compare_cfg: Optional[ValidationConfig] = None
    if str(args.index_path or "").strip():
        try:
            library_index = load_library_index(str(args.index_path).strip())
            compare_cfg = _build_lookup_cfg()
            _save_json_dict(results_path, _load_json_dict(results_path) or _default_results_payload())
            log_message(f"comparacao automatica habilitada com biblioteca {args.index_path}")
        except Exception as exc:
            log_message(f"falha ao carregar biblioteca para comparacao automatica: {exc}")
            library_index = None
            compare_cfg = None
    log_message(
        f"iniciando monitor serial={args.serial or 'default'} dev={dev_path} "
        f"res={screen_res[0]}x{screen_res[1]} output={args.output_dir} "
        f"modo={args.monitor_mode} target={target_size or 'original'} "
        f"compare={'on' if library_index is not None and compare_cfg is not None else 'off'}"
    )
    if args.monitor_mode == "screen_watch":
        collect_screen_watch_screenshots(
            args.output_dir,
            args.serial,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=compare_cfg,
        )
    elif args.monitor_mode == "host_click":
        collect_host_click_screenshots(
            args.output_dir,
            args.serial,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=compare_cfg,
        )
    elif args.monitor_mode == "device":
        collect_touch_screenshots(
            dev_path,
            args.output_dir,
            screen_res,
            abs_ranges,
            args.serial,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=compare_cfg,
        )
    else:
        if os.name == "nt":
            try:
                collect_screen_watch_screenshots(
                    args.output_dir,
                    args.serial,
                    target_size,
                    results_path=results_path,
                    library_index=library_index,
                    cfg=compare_cfg,
                )
            except Exception as exc:
                log_message(f"falha no modo screen_watch; voltando para device: {exc}")
                collect_touch_screenshots(
                    dev_path,
                    args.output_dir,
                    screen_res,
                    abs_ranges,
                    args.serial,
                    target_size,
                    results_path=results_path,
                    library_index=library_index,
                    cfg=compare_cfg,
                )
        else:
            collect_touch_screenshots(
                dev_path,
                args.output_dir,
                screen_res,
                abs_ranges,
                args.serial,
                target_size,
                results_path=results_path,
                library_index=library_index,
                cfg=compare_cfg,
            )
    log_message("monitor finalizado")


if __name__ == "__main__":
    main()
