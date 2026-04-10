import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional

from PIL import Image

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from vwait.features.hmi.application import ValidationConfig, evaluate_single_screenshot, load_library_index
from app.shared.adb_utils import resolve_adb_path
from app.shared.win_window_capture import capture_window_client_image


DEFAULT_DEV = "/dev/input/event2"
DEFAULT_RES = (1920, 1080)
SCREENSHOT_DELAY_S = 1.05
HOST_CLICK_CAPTURE_DELAY_S = 0.25
SCREEN_WATCH_INTERVAL_S = 0.25
SCREEN_CHANGE_HASH_THRESHOLD = 1
STOP_REQUESTED = False
COMPARE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hmi_compare")
HEX_VAL = re.compile(r"\s([0-9a-fA-F]{8})\s*$")
CREATE_FLAGS = 0
STARTUPINFO = None
USER32 = None
KERNEL32 = None
WINTYPES = None
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
VK_LBUTTON = 0x01
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = -1
SCRCPY_PID_CACHE: dict[str, Any] = {"at": 0.0, "pids": set()}
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

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", WINTYPES.DWORD),
            ("cntUsage", WINTYPES.DWORD),
            ("th32ProcessID", WINTYPES.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", WINTYPES.DWORD),
            ("cntThreads", WINTYPES.DWORD),
            ("th32ParentProcessID", WINTYPES.DWORD),
            ("pcPriClassBase", WINTYPES.LONG),
            ("dwFlags", WINTYPES.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

else:
    POINT = None
    RECT = None
    PROCESSENTRY32W = None


def _scrcpy_target_window_title() -> str:
    return str(os.getenv("SCRCPY_TARGET_WINDOW_TITLE", "malagueta") or "malagueta").strip().lower()


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


def _json_safe_value(value: Any, seen: Optional[set[int]] = None) -> Any:
    if seen is None:
        seen = set()
    value_id = id(value)
    if value_id in seen:
        return "[recursive]"
    if isinstance(value, dict):
        seen.add(value_id)
        safe_payload: dict[str, Any] = {}
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
        "capture_source": str(result.get("capture_source") or "-"),
        "reference_path": str(result.get("reference_path") or ""),
        "processed_at": datetime.now().isoformat(),
    }


def _store_validation_result(
    results_path: str,
    file_name: str,
    result: dict[str, Any],
    capture_source: str = "",
) -> dict[str, Any]:
    payload = _load_json_dict(results_path) or _default_results_payload()
    processed = set(str(name) for name in payload.get("processed", []))
    history = list(payload.get("history", []))
    full_results = [item for item in payload.get("full_results", []) if isinstance(item, dict)]

    result_payload = dict(result)
    if capture_source:
        result_payload["capture_source"] = capture_source
    compact_result = _compact_result(result_payload)
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
        subprocess.run(cmd, stdout=fh, check=True, timeout=8, **_run_kwargs())
    _resize_image(local_path, target_size)
    return local_path


def _capture_native_screenshot(local_path: str, serial: str | None = None) -> str:
    return take_screenshot(local_path, serial, target_size=None)


def _finalize_capture_from_native(native_path: str, final_path: str, target_size: tuple[int, int] | None) -> None:
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    if not target_size:
        os.replace(native_path, final_path)
        return
    shutil.copyfile(native_path, final_path)
    _resize_image(final_path, target_size)
    try:
        os.remove(native_path)
    except OSError:
        pass


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


def _preview_output_path(output_dir: str) -> str:
    return os.path.join(os.path.dirname(output_dir), "preview_latest.png")


def _refresh_preview_image(source_path: str, output_dir: str) -> None:
    if not source_path or not os.path.exists(source_path):
        return
    preview_path = _preview_output_path(output_dir)
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)
    temp_preview = f"{preview_path}.tmp"
    shutil.copyfile(source_path, temp_preview)
    os.replace(temp_preview, preview_path)


def _refresh_preview_from_scrcpy_window(output_dir: str) -> bool:
    if os.name != "nt" or USER32 is None:
        return False
    window_info = _find_scrcpy_window_info()
    hwnd = window_info.get("hwnd")
    if not hwnd:
        return False
    image = capture_window_client_image(hwnd)
    if image is None:
        return False
    preview_path = _preview_output_path(output_dir)
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)
    temp_preview = f"{preview_path}.tmp"
    try:
        image.save(temp_preview, format="PNG")
        os.replace(temp_preview, preview_path)
        return True
    except Exception:
        try:
            if os.path.exists(temp_preview):
                os.remove(temp_preview)
        except OSError:
            pass
        return False


def _hmi_teste_output_dir() -> str:
    return os.path.join(PROJECT_ROOT, "Data", "HMI_TESTE")


def _save_hmi_teste_capture(image: Image.Image, file_name: str, action_type: str, x: int, y: int) -> str:
    output_dir = _hmi_teste_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, file_name)
    temp_path = f"{file_path}.tmp"
    image.save(temp_path, format="PNG")
    os.replace(temp_path, file_path)
    append_manifest(output_dir, file_name, action_type, x, y)
    return file_path


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


def _scrcpy_process_ids() -> set[int]:
    if os.name != "nt" or not KERNEL32 or PROCESSENTRY32W is None:
        return set()
    now = time.time()
    cached_at = float(SCRCPY_PID_CACHE.get("at", 0.0) or 0.0)
    if now - cached_at <= 2.0:
        return set(SCRCPY_PID_CACHE.get("pids", set()))

    pids: set[int] = set()
    snapshot = KERNEL32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(INVALID_HANDLE_VALUE).value
    if not snapshot or snapshot == invalid_handle:
        SCRCPY_PID_CACHE.update({"at": now, "pids": pids})
        return pids

    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        has_entry = KERNEL32.Process32FirstW(snapshot, ctypes.byref(entry))
        while has_entry:
            if str(entry.szExeFile or "").strip().lower() == "scrcpy.exe":
                pids.add(int(entry.th32ProcessID))
            has_entry = KERNEL32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        KERNEL32.CloseHandle(snapshot)

    SCRCPY_PID_CACHE.update({"at": now, "pids": pids})
    return pids


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
    pid = int(info.get("pid", 0) or 0)
    target_title = _scrcpy_target_window_title()
    return (
        "scrcpy" in process_name
        or "scrcpy" in title
        or bool(target_title and target_title in title)
        or pid in _scrcpy_process_ids()
    )


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


def _find_scrcpy_window_info() -> dict[str, Any]:
    if not USER32:
        return {"hwnd": None, "title": "", "pid": 0, "process_name": "", "process_path": ""}

    matches: list[dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(WINTYPES.BOOL, WINTYPES.HWND, WINTYPES.LPARAM)
    def enum_windows(hwnd, _lparam):
        try:
            if not USER32.IsWindowVisible(hwnd):
                return True
            title = _window_text(hwnd)
            pid = WINTYPES.DWORD(0)
            USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_path = _query_process_image_name(int(pid.value))
            process_name = os.path.basename(process_path).lower() if process_path else ""
            candidate = {
                "hwnd": hwnd,
                "title": title,
                "pid": int(pid.value),
                "process_name": process_name,
                "process_path": process_path,
                "is_iconic": bool(USER32.IsIconic(hwnd)),
            }
            if _is_scrcpy_foreground(candidate):
                matches.append(candidate)
        except Exception:
            return True
        return True

    USER32.EnumWindows(enum_windows, 0)
    if not matches:
        return {"hwnd": None, "title": "", "pid": 0, "process_name": "", "process_path": ""}

    target_title = _scrcpy_target_window_title()
    foreground = _foreground_window_info()
    foreground_hwnd = foreground.get("hwnd")

    def _window_rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
        bbox = _window_client_bbox(item.get("hwnd"))
        area = 0
        if bbox:
            area = max(0, int(bbox[2] - bbox[0])) * max(0, int(bbox[3] - bbox[1]))
        title = str(item.get("title") or "").strip().lower()
        is_iconic = bool(item.get("is_iconic"))
        not_iconic = 1 if not is_iconic else 0
        has_client_bbox = 1 if bbox else 0
        exact_target = 1 if target_title and title == target_title and not is_iconic else 0
        titled_device = 1 if title and title != "scrcpy" and not is_iconic else 0
        is_foreground = 1 if foreground_hwnd and item.get("hwnd") == foreground_hwnd else 0
        return (not_iconic, has_client_bbox, exact_target, titled_device, is_foreground, area)

    return max(matches, key=_window_rank)


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


def _pointer_position_in_client(hwnd: Any) -> tuple[int, int] | None:
    if not USER32 or not hwnd or POINT is None:
        return None
    bbox = _window_client_bbox(hwnd)
    if not bbox:
        return None
    point = POINT()
    if not USER32.GetCursorPos(ctypes.byref(point)):
        return None
    left, top, right, bottom = bbox
    if int(point.x) < left or int(point.x) > right or int(point.y) < top or int(point.y) > bottom:
        return None
    return int(point.x - left), int(point.y - top)


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
    refresh_preview: bool = True,
) -> tuple[str, str]:
    file_name = f"touch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    file_path = os.path.join(output_dir, file_name)
    with NamedTemporaryFile(prefix="touch_native_", suffix=".png", dir=output_dir, delete=False) as temp_file:
        native_path = temp_file.name
    try:
        _capture_native_screenshot(native_path, serial)
        if refresh_preview:
            _refresh_preview_image(native_path, output_dir)
        _finalize_capture_from_native(native_path, file_path, target_size)
        try:
            with Image.open(native_path) as image:
                hmi_teste_path = _save_hmi_teste_capture(image.copy(), file_name, action_type, x, y)
            log_message(f"captura ADB salva em {hmi_teste_path}")
        except Exception as exc:
            log_message(f"falha ao salvar captura ADB em HMI_TESTE: {exc}")
    except Exception:
        try:
            if os.path.exists(native_path):
                os.remove(native_path)
        except OSError:
            pass
        raise
    append_manifest(output_dir, file_name, action_type, x, y)
    return file_name, file_path


def _capture_and_compare(
    output_dir: str,
    serial: str | None,
    action_type: str,
    x: int,
    y: int,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
    refresh_preview: bool = True,
) -> tuple[str, str, str]:
    file_name, file_path = _capture_output_frame(
        output_dir,
        serial,
        action_type,
        x,
        y,
        target_size,
        refresh_preview=refresh_preview,
    )
    frame_hash = _average_hash_from_path(file_path)
    _queue_compare_capture_if_configured(
        file_name,
        file_path,
        results_path,
        library_index,
        cfg,
        capture_source=action_type,
    )
    return file_name, file_path, frame_hash


def _compare_capture_if_configured(
    file_name: str,
    file_path: str,
    results_path: str | None,
    library_index: Optional[dict[str, Any]],
    cfg: Optional[ValidationConfig],
    capture_source: str = "",
) -> None:
    if not results_path or library_index is None or cfg is None:
        return
    try:
        result = evaluate_single_screenshot(file_path, library_index, cfg)
        _store_validation_result(results_path, file_name, result, capture_source=capture_source)
        log_message(
            "comparacao concluida "
            f"{file_name} -> {str(result.get('screen_name') or 'sem_match')} "
            f"[{str(result.get('status') or 'SEM_STATUS')}] "
            f"origem={capture_source or 'desconhecida'}"
        )
    except Exception as exc:
        log_message(f"falha ao comparar {file_name}: {exc}")


def _queue_compare_capture_if_configured(
    file_name: str,
    file_path: str,
    results_path: str | None,
    library_index: Optional[dict[str, Any]],
    cfg: Optional[ValidationConfig],
    capture_source: str = "",
) -> None:
    if not results_path or library_index is None or cfg is None:
        return
    COMPARE_EXECUTOR.submit(
        _compare_capture_if_configured,
        file_name,
        file_path,
        results_path,
        library_index,
        cfg,
        capture_source,
    )
    log_message(f"comparacao enfileirada para {file_name}")


def _capture_screen_change_frame(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    previous_hash: str,
    min_hash_distance: int = SCREEN_CHANGE_HASH_THRESHOLD,
) -> tuple[str, Optional[str], Optional[str]]:
    with NamedTemporaryFile(prefix="hmi_watch_native_", suffix=".png", dir=output_dir, delete=False) as temp_file:
        native_path = temp_file.name
    try:
        _capture_native_screenshot(native_path, serial)
        _refresh_preview_image(native_path, output_dir)
        frame_hash = _average_hash_from_path(native_path)
        if previous_hash and _hash_distance(previous_hash, frame_hash) < max(1, int(min_hash_distance)):
            os.remove(native_path)
            return previous_hash, None, None
        file_name = f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        file_path = os.path.join(output_dir, file_name)
        _finalize_capture_from_native(native_path, file_path, target_size)
        append_manifest(output_dir, file_name, "screen_change", -1, -1)
        return frame_hash, file_name, file_path
    except Exception:
        try:
            if os.path.exists(native_path):
                os.remove(native_path)
        except OSError:
            pass
        raise


def _capture_scrcpy_window_frame(
    output_dir: str,
    target_size: tuple[int, int] | None,
    previous_hash: str,
    min_hash_distance: int = SCREEN_CHANGE_HASH_THRESHOLD,
) -> tuple[str, Optional[str], Optional[str]]:
    if os.name != "nt" or USER32 is None:
        return previous_hash, None, None
    window_info = _find_scrcpy_window_info()
    hwnd = window_info.get("hwnd")
    bbox = _window_client_bbox(hwnd)
    if not hwnd or not bbox:
        return previous_hash, None, None

    with NamedTemporaryFile(prefix="scrcpy_watch_", suffix=".png", dir=output_dir, delete=False) as temp_file:
        temp_path = temp_file.name
    try:
        image = capture_window_client_image(hwnd)
        if image is None:
            return previous_hash, None, None
        image.save(temp_path)
        _refresh_preview_image(temp_path, output_dir)
        frame_hash = _average_hash_from_path(temp_path)
        if previous_hash and _hash_distance(previous_hash, frame_hash) < max(1, int(min_hash_distance)):
            os.remove(temp_path)
            return previous_hash, None, None
        title_slug = re.sub(r"[^a-z0-9]+", "_", str(window_info.get("title") or "").strip().lower()).strip("_") or "scrcpy"
        file_name = f"{title_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        file_path = os.path.join(output_dir, file_name)
        os.replace(temp_path, file_path)
        append_manifest(output_dir, file_name, "scrcpy_window", -1, -1)
        return frame_hash, file_name, file_path
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def _capture_scrcpy_window_output(
    output_dir: str,
    action_type: str,
    x: int,
    y: int,
    target_size: tuple[int, int] | None = None,
    window_info: Optional[dict[str, Any]] = None,
) -> tuple[str, str, str]:
    if os.name != "nt" or USER32 is None:
        raise RuntimeError("captura direta do scrcpy disponivel apenas no Windows")
    window_info = window_info if isinstance(window_info, dict) and window_info.get("hwnd") else _find_scrcpy_window_info()
    hwnd = window_info.get("hwnd")
    if not hwnd:
        scrcpy_pids = sorted(_scrcpy_process_ids())
        raise RuntimeError(
            "janela do scrcpy nao encontrada"
            + (f" (scrcpy.exe ativo em pid(s) {scrcpy_pids})" if scrcpy_pids else "")
        )
    if bool(USER32.IsIconic(hwnd)):
        raise RuntimeError("janela do scrcpy esta minimizada")
    title_slug = re.sub(r"[^a-z0-9]+", "_", str(window_info.get("title") or "").strip().lower()).strip("_") or "scrcpy"
    file_name = f"{title_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    file_path = os.path.join(output_dir, file_name)
    image = capture_window_client_image(hwnd)
    if image is None:
        raise RuntimeError("falha ao capturar a janela do scrcpy via PrintWindow")
    preview_path = _preview_output_path(output_dir)
    os.makedirs(os.path.dirname(preview_path), exist_ok=True)
    temp_preview = f"{preview_path}.tmp"
    image.save(temp_preview, format="PNG")
    os.replace(temp_preview, preview_path)
    hmi_teste_path = _save_hmi_teste_capture(image, file_name, action_type, x, y)
    if target_size:
        width, height = int(target_size[0]), int(target_size[1])
        if width > 0 and height > 0 and image.size != (width, height):
            resampling = getattr(Image, "Resampling", Image)
            image = image.resize((width, height), resampling.LANCZOS)
    image.save(file_path)
    append_manifest(output_dir, file_name, action_type, x, y)
    log_message(f"captura malagueta salva em {hmi_teste_path}")
    frame_hash = _average_hash_from_path(file_path)
    return file_name, file_path, frame_hash


def _scrcpy_window_available() -> bool:
    if os.name != "nt" or USER32 is None:
        return False
    info = _find_scrcpy_window_info()
    return bool(info.get("hwnd")) and not bool(info.get("is_iconic"))


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
            _queue_compare_capture_if_configured(
                file_name,
                file_path,
                results_path,
                library_index,
                cfg,
                capture_source="screen_change",
            )

        time.sleep(SCREEN_WATCH_INTERVAL_S)


def collect_hybrid_screenshots(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
) -> None:
    last_saved_hash = ""
    prev_left_down = False
    pending_click: dict[str, Any] | None = None
    next_visual_scan_at = 0.0
    log_message("monitorando em modo hibrido: cliques do scrcpy + mudancas visuais do radio via ADB")

    try:
        file_name, _file_path, last_saved_hash = _capture_and_compare(
            output_dir,
            serial,
            "initial_state",
            -1,
            -1,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=cfg,
        )
        _refresh_preview_from_scrcpy_window(output_dir)
        log_message(f"capturado {file_name} no estado inicial via ADB")
    except Exception as exc:
        log_message(f"falha ao capturar estado inicial: {exc}")

    while not should_stop(output_dir):
        now = time.time()

        if USER32:
            info = _foreground_window_info()
            left_down = bool(USER32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if _is_scrcpy_foreground(info) and left_down and not prev_left_down:
                click_x, click_y = _pointer_position_in_window(info.get("hwnd"))
                pending_click = {
                    "capture_at": now + HOST_CLICK_CAPTURE_DELAY_S,
                    "x": click_x,
                    "y": click_y,
                }
                log_message(
                    f"atividade scrcpy detectada; captura agendada em {HOST_CLICK_CAPTURE_DELAY_S:.2f}s "
                    f"(cursor={click_x},{click_y})"
                )
            prev_left_down = left_down

        if pending_click and now >= float(pending_click.get("capture_at", 0.0) or 0.0):
            try:
                preview_from_window = _refresh_preview_from_scrcpy_window(output_dir)
                file_name, _file_path, last_saved_hash = _capture_and_compare(
                    output_dir,
                    serial,
                    "host_click",
                    int(pending_click.get("x", -1) or -1),
                    int(pending_click.get("y", -1) or -1),
                    target_size,
                    results_path=results_path,
                    library_index=library_index,
                    cfg=cfg,
                    refresh_preview=not preview_from_window,
                )
                log_message(f"capturado {file_name} apos interacao detectada no scrcpy via ADB")
            except Exception as exc:
                log_message(f"falha ao capturar interacao do scrcpy: {exc}")
            pending_click = None

        if now >= next_visual_scan_at:
            next_visual_scan_at = now + SCREEN_WATCH_INTERVAL_S
            try:
                frame_hash, file_name, file_path = _capture_screen_change_frame(
                    output_dir,
                    serial,
                    target_size,
                    last_saved_hash,
                )
            except Exception as exc:
                log_message(f"falha ao observar mudanca de tela no modo hibrido: {exc}")
                time.sleep(0.12)
                continue

            if file_name and file_path:
                last_saved_hash = frame_hash
                log_message(f"capturado {file_name} apos mudanca visual detectada")
                _queue_compare_capture_if_configured(
                    file_name,
                    file_path,
                    results_path,
                    library_index,
                    cfg,
                    capture_source="screen_change",
                )

        time.sleep(0.08 if pending_click else 0.12)


def collect_host_click_screenshots(
    output_dir: str,
    serial: str | None,
    target_size: tuple[int, int] | None,
    results_path: str | None = None,
    library_index: Optional[dict[str, Any]] = None,
    cfg: Optional[ValidationConfig] = None,
    dev_path: str | None = None,
    screen_res: tuple[int, int] | None = None,
    abs_ranges: Optional[dict[str, dict[str, int | None]]] = None,
) -> None:
    if not USER32:
        raise RuntimeError("modo host_click disponivel apenas no Windows")

    prev_left_down = False
    last_capture_at = 0.0
    target_title = _scrcpy_target_window_title()
    log_message(f"monitorando cliques dentro da janela '{target_title}' do scrcpy")

    initial_info = _find_scrcpy_window_info()
    if not initial_info.get("hwnd"):
        scrcpy_pids = sorted(_scrcpy_process_ids())
        pid_text = f" pid(s) scrcpy={scrcpy_pids};" if scrcpy_pids else ""
        log_message(
            f"janela '{target_title}' nao encontrada;{pid_text} "
            "alternando para monitoramento visual via ADB para acompanhar as mudancas do scrcpy"
        )
        collect_hybrid_screenshots(
            output_dir,
            serial,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=cfg,
        )
        return

    try:
        file_name, file_path, _frame_hash = _capture_scrcpy_window_output(
            output_dir,
            "initial_state",
            -1,
            -1,
            target_size=target_size,
            window_info=initial_info,
        )
        _queue_compare_capture_if_configured(
            file_name,
            file_path,
            results_path,
            library_index,
            cfg,
            capture_source="scrcpy_window",
        )
        log_message(f"capturado {file_name} no estado inicial da janela '{target_title}'")
    except Exception as exc:
        log_message(f"falha ao capturar estado inicial da janela '{target_title}': {exc}")

    while not should_stop(output_dir):
        info = _find_scrcpy_window_info()
        hwnd = info.get("hwnd")
        client_pointer = _pointer_position_in_client(hwnd)
        left_down = bool(USER32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

        if hwnd and client_pointer and left_down and not prev_left_down:
            now = time.time()
            if now - last_capture_at >= 0.35:
                click_x, click_y = client_pointer
                log_message(
                    f"clique detectado dentro da janela '{str(info.get('title') or target_title)}'; "
                    f"aguardando {HOST_CLICK_CAPTURE_DELAY_S:.2f}s para capturar (cursor={click_x},{click_y})"
                )
                time.sleep(HOST_CLICK_CAPTURE_DELAY_S)
                if should_stop(output_dir):
                    break
                file_name, file_path, _frame_hash = _capture_scrcpy_window_output(
                    output_dir,
                    "host_click",
                    click_x,
                    click_y,
                    target_size=target_size,
                    window_info=info,
                )
                last_capture_at = time.time()
                log_message(f"capturado {file_name} apos clique dentro da janela '{str(info.get('title') or target_title)}'")
                _queue_compare_capture_if_configured(
                    file_name,
                    file_path,
                    results_path,
                    library_index,
                    cfg,
                    capture_source="host_click",
                )

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

    try:
        file_name, _file_path, _frame_hash = _capture_and_compare(
            output_dir,
            serial,
            "initial_state",
            -1,
            -1,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=cfg,
        )
        log_message(f"capturado {file_name} no estado inicial via ADB")
    except Exception as exc:
        log_message(f"falha ao capturar estado inicial na bancada: {exc}")

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
                _queue_compare_capture_if_configured(
                    file_name,
                    file_path,
                    results_path,
                    library_index,
                    cfg,
                    capture_source=action_type,
                )

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
    parser.add_argument("--monitor-mode", choices=("auto", "hybrid", "device", "host_click", "screen_watch"), default="auto")
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
    if target_size and tuple(target_size) != tuple(screen_res):
        log_message(
            f"normalizando capturas de {screen_res[0]}x{screen_res[1]} "
            f"para {int(target_size[0])}x{int(target_size[1])}"
        )
    if args.monitor_mode == "hybrid":
        collect_hybrid_screenshots(
            args.output_dir,
            args.serial,
            target_size,
            results_path=results_path,
            library_index=library_index,
            cfg=compare_cfg,
        )
    elif args.monitor_mode == "screen_watch":
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
            dev_path=dev_path,
            screen_res=screen_res,
            abs_ranges=abs_ranges,
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
        if os.name == "nt" and _scrcpy_window_available():
            log_message("modo automatico: janela do scrcpy detectada; monitorando cliques no scrcpy")
            collect_host_click_screenshots(
                args.output_dir,
                args.serial,
                target_size,
                results_path=results_path,
                library_index=library_index,
                cfg=compare_cfg,
                dev_path=dev_path,
                screen_res=screen_res,
                abs_ranges=abs_ranges,
            )
        else:
            log_message("modo automatico: monitorando toques da bancada via ADB/getevent")
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
