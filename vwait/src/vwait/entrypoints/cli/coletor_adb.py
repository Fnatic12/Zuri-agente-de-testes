import os
import re
import json
import math
import time
import queue
import sys
import platform
import shutil
import select
import pyfiglet
import signal
import shlex
import threading
import colorama
from colorama import Fore, Style
from termcolor import colored
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.core.paths import PROJECT_ROOT as PROJECT_ROOT_PATH
from vwait.core.paths import ensure_tester_catalog, tester_actions_path, tester_expected_final_path, tester_recorded_dir, tester_recorded_frames_dir, tester_test_metadata_path
from vwait.platform.scrcpy_events import (
    ScrcpyGestureAssembler,
    ensure_persistent_scrcpy_session,
    iter_scrcpy_touch_events,
    iter_scrcpy_touch_events_from_log,
    save_events_json,
)

PROJECT_ROOT = str(PROJECT_ROOT_PATH)

from vwait.platform.adb import resolve_adb_path
colorama.init()

# =========================
# CONFIG
# =========================
BUILD_TAG = "ZURI Coletor v2 (event2)"
ADB_PATH = resolve_adb_path()

REMOTE_TMP = "/sdcard/tmp_shot.png"
MOV_THRESH_PX = 25            # distância p/ classificar SWIPE (senão é TAP)
DEFAULT_RES = (1920, 1080)    # fallback
DEFAULT_DEV = "/dev/input/event2"
SCREENSHOT_DELAY_S = 1.1      # atraso antes de capturar o frame (aguarda transicao de tela)
stop_requested = False

def handle_sigterm(signum, frame):
    global stop_requested
    stop_requested = True
signal.signal(signal.SIGTERM, handle_sigterm)

def printc(msg, color="white"):
    colors = {
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "red": Fore.RED,
        "white": Style.RESET_ALL,
        "cyan": Fore.CYAN,
        "blue": Fore.BLUE
    }
    print(f"{colors.get(color,'')}{msg}{Style.RESET_ALL}", flush=True)

def adb_cmd(serial=None):
    if serial:
        return [ADB_PATH, "-s", serial]
    return [ADB_PATH]

def run_out(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip()

def has_cmd(name: str) -> bool:
    return bool(shutil.which(name))

def scrcpy_running():
    try:
        if os.name == "nt":
            output = run_out(["tasklist"])
            return "scrcpy.exe" in output.lower()
        if shutil.which("pgrep"):
            return subprocess.run(["pgrep", "-x", "scrcpy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if shutil.which("pidof"):
            return subprocess.run(["pidof", "scrcpy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False
    return False

def probe_getevent_activity(dev_path, serial=None, timeout_s=2.0):
    """
    Verifica se há atividade no getevent por um curto intervalo.
    Retorna True se algum evento for lido.
    """
    proc = subprocess.Popen(
        adb_cmd(serial) + ["shell", "getevent", "-lt", dev_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    if proc.stdout is None:
        return False
    try:
        start = time.time()
        while time.time() - start < timeout_s:
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if ready:
                data = proc.stdout.read1(512)
                if data:
                    return True
    except Exception:
        return False
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            pass
    return False

def take_screenshot(local_path, serial=None):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    cmd = adb_cmd(serial) + ["exec-out", "screencap", "-p"]
    with open(local_path, "wb") as f:
        subprocess.run(cmd, stdout=f)
    return local_path

def _resolve_scrcpy_window_id(title_hint=None):
    if not has_cmd("xdotool"):
        return None
    candidates = []
    for pattern in [title_hint, "scrcpy"]:
        if not pattern:
            continue
        try:
            result = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", pattern],
                text=True,
            )
            ids = [line.strip() for line in result.splitlines() if line.strip()]
            candidates.extend(ids)
        except Exception:
            continue
    return candidates[0] if candidates else None


def _get_window_geometry(window_id):
    if not window_id:
        return None
    try:
        raw = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", window_id], text=True)
    except Exception:
        return None
    geom = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            geom[key.strip()] = int(value.strip())
    if all(k in geom for k in ("X", "Y", "WIDTH", "HEIGHT")):
        return geom
    return None


def _get_mouse_location():
    if not has_cmd("xdotool"):
        return None
    try:
        raw = subprocess.check_output(["xdotool", "getmouselocation", "--shell"], text=True)
    except Exception:
        return None
    data = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = int(value.strip())
    if "X" in data and "Y" in data:
        return data["X"], data["Y"]
    return None


_CACHED_XINPUT_POINTER = None


def _resolve_xinput_pointer():
    global _CACHED_XINPUT_POINTER
    if _CACHED_XINPUT_POINTER:
        return _CACHED_XINPUT_POINTER
    if not has_cmd("xinput"):
        return None
    try:
        raw = subprocess.check_output(["xinput", "list", "--short"], text=True)
    except Exception:
        return None
    candidates = []
    for line in raw.splitlines():
        line_clean = line.strip()
        if "pointer" not in line_clean.lower():
            continue
        if "virtual core keyboard" in line_clean.lower():
            continue
        m = re.search(r"id=(\\d+)", line_clean)
        if not m:
            continue
        pointer_id = m.group(1)
        candidates.append(pointer_id)
        if "virtual core pointer" in line_clean.lower():
            _CACHED_XINPUT_POINTER = pointer_id
            return _CACHED_XINPUT_POINTER
    if candidates:
        _CACHED_XINPUT_POINTER = candidates[0]
    return _CACHED_XINPUT_POINTER


def _mouse_button1_down():
    if not has_cmd("xinput"):
        return False
    pointer_id = _resolve_xinput_pointer()
    if not pointer_id:
        return False
    raw = ""
    try:
        raw = subprocess.check_output(["xinput", "query-state", pointer_id], text=True)
    except Exception:
        try:
            raw = subprocess.check_output(["xinput", "query-state", "Virtual core pointer"], text=True)
        except Exception:
            return False
    for line in raw.splitlines():
        if "button[1]" in line:
            return "down" in line.lower()
    return False


def _is_button1_down_with_xinput_test():
    if not has_cmd("xinput"):
        return False
    pointer_id = _resolve_xinput_pointer()
    if not pointer_id:
        return False
    try:
        raw = subprocess.check_output(["xinput", "test", pointer_id], text=True, timeout=0.2)
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
    except Exception:
        return False
    for line in str(raw).splitlines():
        if "button press" in line and "1" in line:
            return True
    return False


def collect_host_mouse_loop(frames_dir, screen_res, serial=None, title_hint=None, *, persist_action=None):
    if not has_cmd("xdotool") or not has_cmd("xinput"):
        printc("Erro: xdotool/xinput nao encontrados. Instale para capturar cliques do scrcpy no host.", "red")
        return []

    window_id = _resolve_scrcpy_window_id(title_hint)
    if not window_id:
        printc("Erro: janela do scrcpy nao encontrada (xdotool).", "red")
        return []

    actions = []
    idx = 1
    in_touch = False
    t_start = None
    sx = sy = None
    lx = ly = None
    last_geom_refresh = 0.0
    geom = None

    while True:
        if stop_requested or os.path.exists(os.path.join(PROJECT_ROOT, "stop.flag")):
            break

        if time.time() - last_geom_refresh > 1.0:
            geom = _get_window_geometry(window_id)
            last_geom_refresh = time.time()

        mouse = _get_mouse_location()
        if not geom or not mouse:
            time.sleep(0.05)
            continue

        mx, my = mouse
        inside = geom["X"] <= mx <= geom["X"] + geom["WIDTH"] and geom["Y"] <= my <= geom["Y"] + geom["HEIGHT"]
        btn_down = _mouse_button1_down() or _is_button1_down_with_xinput_test()

        if btn_down and inside and not in_touch:
            in_touch = True
            t_start = time.time()
            sx = mx
            sy = my
            lx = mx
            ly = my

        if in_touch and btn_down and inside:
            lx = mx
            ly = my

        if in_touch and not btn_down:
            in_touch = False
            if None in (sx, sy, lx, ly) or not geom:
                time.sleep(0.05)
                continue

            action_timestamp = datetime.now().isoformat()
            dur_ms = int((time.time() - t_start) * 1000) if t_start else 0
            dur_s = dur_ms / 1000.0
            sx_rel = max(0, min(geom["WIDTH"] - 1, sx - geom["X"]))
            sy_rel = max(0, min(geom["HEIGHT"] - 1, sy - geom["Y"]))
            lx_rel = max(0, min(geom["WIDTH"] - 1, lx - geom["X"]))
            ly_rel = max(0, min(geom["HEIGHT"] - 1, ly - geom["Y"]))

            sx_px = int(round(sx_rel / max(1, geom["WIDTH"] - 1) * (screen_res[0] - 1)))
            sy_px = int(round(sy_rel / max(1, geom["HEIGHT"] - 1) * (screen_res[1] - 1)))
            lx_px = int(round(lx_rel / max(1, geom["WIDTH"] - 1) * (screen_res[0] - 1)))
            ly_px = int(round(ly_rel / max(1, geom["HEIGHT"] - 1) * (screen_res[1] - 1)))

            dist = math.hypot(lx_px - sx_px, ly_px - sy_px)
            if dist <= MOV_THRESH_PX and dur_s > 0.8:
                action = {"tipo": "long_press", "x": sx_px, "y": sy_px, "duracao_s": round(dur_s, 2)}
            elif dist <= MOV_THRESH_PX:
                action = {"tipo": "tap", "x": sx_px, "y": sy_px, "duracao_s": round(dur_s, 2)}
            else:
                action = {"tipo": "swipe", "x1": sx_px, "y1": sy_px, "x2": lx_px, "y2": ly_px, "duracao_ms": dur_ms}

            time.sleep(SCREENSHOT_DELAY_S)
            img_name = f"frame_{idx:02d}.png"
            img_path = os.path.join(frames_dir, img_name)
            shot_path = take_screenshot(img_path, serial)
            screenshot_timestamp = datetime.now().isoformat()

            actions.append(
                {
                    "id": idx,
                    "timestamp": action_timestamp,
                    "action_timestamp": action_timestamp,
                    "screenshot_timestamp": screenshot_timestamp,
                    "imagem": img_name,
                    "acao": action,
                    "source": "scrcpy_host",
                }
            )
            if callable(persist_action):
                persist_action(actions)

            if action.get("tipo") == "tap":
                printc(f"TAP {idx}: ({sx_px},{sy_px})", "green")
            elif action.get("tipo") == "swipe":
                printc(f"SWIPE {idx}: ({sx_px},{sy_px})->({lx_px},{ly_px})", "green")
            elif action.get("tipo") == "long_press":
                printc(f"LONG_PRESS {idx}: ({sx_px},{sy_px})", "green")

            captured_ok = bool(shot_path) and os.path.exists(shot_path) and os.path.getsize(shot_path) > 0
            if captured_ok:
                printc(f"IMG {idx}: OK ({img_name})", "cyan")
            else:
                printc(f"IMG {idx}: FALHA ({img_name})", "red")

            idx += 1

        time.sleep(0.05)

    return actions


def collect_scrcpy_verbose_loop(
    frames_dir,
    screen_res,
    serial=None,
    stop_flag_path=None,
    *,
    categoria,
    nome_teste,
    actions_path,
    events_path,
):
    extra_args = []
    env_args = os.environ.get("SCRCPY_ARGS")
    if env_args:
        try:
            extra_args = shlex.split(env_args)
        except Exception:
            extra_args = []

    session_meta, created = ensure_persistent_scrcpy_session(serial=serial, extra_args=extra_args)
    events = []
    actions = []
    assembler = ScrcpyGestureAssembler(screen_res[0], screen_res[1])
    idx = 1
    action_queue = queue.Queue()
    actions_lock = threading.Lock()
    verbose_log_path = os.path.join(frames_dir, "..", "scrcpy_verbose.log")
    verbose_log_path = os.path.abspath(verbose_log_path)
    os.makedirs(os.path.dirname(verbose_log_path), exist_ok=True)

    def append_raw_line(line: str):
        with open(verbose_log_path, "a", encoding="utf-8", errors="ignore") as handle:
            handle.write(f"{line}\n")

    def screenshot_worker():
        while True:
            job = action_queue.get()
            if job is None:
                action_queue.task_done()
                break

            try:
                action_id = job["id"]
                action_payload = job["acao"]
                action_timestamp = job["timestamp"]
                action_source = job["source"]
                target_ts = datetime.fromisoformat(action_timestamp).timestamp() + SCREENSHOT_DELAY_S
                wait_s = max(0.0, target_ts - time.time())
                if wait_s > 0:
                    time.sleep(wait_s)

                img_name = f"frame_{action_id:02d}.png"
                img_path = os.path.join(frames_dir, img_name)
                shot_path = take_screenshot(img_path, serial)
                screenshot_timestamp = datetime.now().isoformat()

                record = {
                    "id": action_id,
                    "timestamp": action_timestamp,
                    "action_timestamp": action_timestamp,
                    "screenshot_timestamp": screenshot_timestamp,
                    "imagem": img_name,
                    "acao": action_payload,
                    "source": action_source,
                }
                with actions_lock:
                    actions.append(record)
                    ordered_actions = sorted(actions, key=lambda item: int(item.get("id", 0)))
                    persist_actions_payload(
                        actions_path,
                        categoria=categoria,
                        nome_teste=nome_teste,
                        source="scrcpy",
                        actions=ordered_actions,
                        include_scrcpy_events=True,
                    )

                if action_payload.get("tipo") == "tap":
                    printc(f"TAP {action_id}: ({action_payload.get('x')},{action_payload.get('y')})", "green")
                elif action_payload.get("tipo") == "swipe":
                    printc(
                        f"SWIPE {action_id}: ({action_payload.get('x1')},{action_payload.get('y1')})->({action_payload.get('x2')},{action_payload.get('y2')})",
                        "green",
                    )
                elif action_payload.get("tipo") == "long_press":
                    printc(f"LONG_PRESS {action_id}: ({action_payload.get('x')},{action_payload.get('y')})", "green")

                captured_ok = bool(shot_path) and os.path.exists(shot_path) and os.path.getsize(shot_path) > 0
                if captured_ok:
                    printc(f"IMG {action_id}: OK ({img_name})", "cyan")
                else:
                    printc(f"IMG {action_id}: FALHA ({img_name})", "red")
            finally:
                action_queue.task_done()

    managed_title = str(session_meta.get("window_title") or os.environ.get("SCRCPY_WINDOW_TITLE") or "VWAIT_DEVICE")
    session_log_path = str(session_meta.get("log_path") or "")
    start_offset = os.path.getsize(session_log_path) if (session_log_path and os.path.exists(session_log_path)) else 0
    if created:
        printc(f"Scrcpy gerenciado iniciado. Use a janela com titulo: {managed_title}", "cyan")
    else:
        printc(f"Reutilizando scrcpy persistente: {managed_title}", "cyan")
    printc(f"Log verbose bruto: {verbose_log_path}", "cyan")

    worker = threading.Thread(target=screenshot_worker, daemon=True)
    worker.start()

    try:
        for event in iter_scrcpy_touch_events_from_log(
            session_log_path,
            start_offset=start_offset,
            stop_flag_path=stop_flag_path,
            stop_grace_s=1.5,
            raw_line_handler=append_raw_line,
        ):
            events.append(event)
            save_events_json(events, events_path)
            printc(
                f"EVENT {event.event_type.upper()}: ({event.x},{event.y}) pressure={event.pressure:.2f}",
                "blue",
            )
            action = assembler.feed(event)
            if not action:
                continue

            action_queue.put(
                {
                    "id": idx,
                    "timestamp": event.timestamp,
                    "acao": action,
                    "source": "scrcpy",
                }
            )
            idx += 1
    finally:
        action_queue.put(None)
        action_queue.join()
        worker.join(timeout=2)

    with actions_lock:
        ordered_actions = sorted(actions, key=lambda item: int(item.get("id", 0)))
    return ordered_actions, events

def get_resolution(serial=None):
    out = run_out(adb_cmd(serial) + ["shell", "wm", "size"])
    m = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
    if m:
        return int(m.group(1)), int(m.group(2))
    return DEFAULT_RES

def autodetect_touch_device(serial=None, prefer_injected=False):
    """
    Procura o device de touch via `adb shell getevent -pl`.
    Se prefer_injected=True, prioriza dispositivos uinput/virtuais (scrcpy).
    """
    out = run_out(adb_cmd(serial) + ["shell", "getevent", "-pl"])
    devices = []

    def finalize_device(path, name, has_mt):
        if path:
            devices.append({"path": path, "name": name or "", "has_mt": has_mt})

    current_path = None
    current_name = ""
    current_has_mt = False

    for line in out.splitlines():
        if line.startswith("add device"):
            finalize_device(current_path, current_name, current_has_mt)
            m = re.search(r"add device \d+:\s+(/dev/input/event\\d+)", line)
            current_path = m.group(1) if m else None
            current_name = ""
            current_has_mt = False
            continue

        lower = line.lower()
        if "name:" in lower:
            m = re.search(r'name:\\s*\"([^\"]+)\"', line)
            current_name = m.group(1) if m else line.split("name:", 1)[-1].strip()
        if "ABS_MT_POSITION_X" in line or "ABS_MT_POSITION_Y" in line:
            current_has_mt = True

    finalize_device(current_path, current_name, current_has_mt)

    if devices:
        if prefer_injected:
            injected_keywords = ("scrcpy", "uinput", "virtual", "vinput", "inject", "remote")
            for item in devices:
                name_lower = (item.get("name") or "").lower()
                if item.get("has_mt") and any(k in name_lower for k in injected_keywords):
                    return item["path"]

        for item in devices:
            name_lower = (item.get("name") or "").lower()
            if item.get("has_mt") and "touchscreen" in name_lower:
                return item["path"]
        for item in devices:
            name_lower = (item.get("name") or "").lower()
            if item.get("has_mt") and "touch" in name_lower:
                return item["path"]

        for item in devices:
            if item.get("has_mt"):
                return item["path"]

    return DEFAULT_DEV

def get_abs_ranges_for_device(dev_path, serial=None):
    """
    Lê os ranges de ABS_X/ABS_Y e ABS_MT_POSITION_X/Y do device para escalar a pixels.
    Retorna dict com max/min.
    """
    out = run_out(adb_cmd(serial) + ["shell", "getevent", "-pl", dev_path])
    ranges = {
        "ABS_X": {"min": 0, "max": None},
        "ABS_Y": {"min": 0, "max": None},
        "ABS_MT_POSITION_X": {"min": 0, "max": None},
        "ABS_MT_POSITION_Y": {"min": 0, "max": None},
    }
    for line in out.splitlines():
        for key in list(ranges.keys()):
            if key in line:
                m = re.search(r"min\s+(\d+),\s*max\s+(\d+)", line)
                if m:
                    ranges[key]["min"] = int(m.group(1))
                    ranges[key]["max"] = int(m.group(2))
    return ranges

def scale_to_px(val, min_v, max_v, px_max):
    """Mapeia valor [min_v, max_v] -> [0, px_max-1]"""
    if max_v is None or max_v == min_v:
        return int(val)
    val = max(min_v, min(max_v, val))
    ratio = (val - min_v) / float(max_v - min_v)
    return int(round(ratio * (px_max - 1)))

# =========================
# COLETA DE GESTOS
# =========================
HEX_VAL = re.compile(r"\s([0-9a-fA-F]{8})\s*$")

def hex_last_int(line):
    m = HEX_VAL.search(line)
    return int(m.group(1), 16) if m else None


def persist_actions_payload(
    actions_path,
    *,
    categoria,
    nome_teste,
    source,
    actions,
    include_scrcpy_events=False,
):
    payload = {
        "teste": nome_teste,
        "categoria": categoria,
        "fonte": source,
        "acoes": actions,
        "resultado_esperado": "expected/final.png",
    }
    if include_scrcpy_events:
        payload["scrcpy_events"] = "recorded/scrcpy_events.json"
    with open(actions_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)



def collect_gestures_loop(dev_path, frames_dir, screen_res, abs_ranges, serial=None, source="adb", *, persist_action=None):
    actions = []
    idx = 1
    in_touch = False
    sx_raw = sy_raw = None
    lx_raw = ly_raw = None
    t_start = None

    while True:
        proc = subprocess.Popen(
            adb_cmd(serial) + ["shell", "getevent", "-lt", dev_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        if proc.stdout is None:
            break

        try:
            for raw_line in proc.stdout:
                line = raw_line.decode(errors="ignore").rstrip()

                if stop_requested or os.path.exists(os.path.join(PROJECT_ROOT, "stop.flag")):
                    break

                # Inicio do toque (BTN_TOUCH ou TRACKING_ID valido)
                if "EV_KEY" in line and "BTN_TOUCH" in line and "DOWN" in line:
                    in_touch = True
                    t_start = time.time()
                    sx_raw = sy_raw = lx_raw = ly_raw = None
                if "ABS_MT_TRACKING_ID" in line:
                    val = hex_last_int(line)
                    if val is not None and val != 0xFFFFFFFF and not in_touch:
                        in_touch = True
                        t_start = time.time()
                        sx_raw = sy_raw = lx_raw = ly_raw = None

                # Captura das coordenadas
                if "EV_ABS" in line:
                    if "ABS_MT_POSITION_X" in line or "ABS_X" in line:
                        val = hex_last_int(line)
                        if val is not None:
                            lx_raw = val
                            if sx_raw is None:
                                sx_raw = val
                    elif "ABS_MT_POSITION_Y" in line or "ABS_Y" in line:
                        val = hex_last_int(line)
                        if val is not None:
                            ly_raw = val
                            if sy_raw is None:
                                sy_raw = val

                # Final do toque
                end_touch = False
                if "EV_KEY" in line and "BTN_TOUCH" in line and "UP" in line:
                    end_touch = True
                if "EV_ABS" in line and "ABS_MT_TRACKING_ID" in line:
                    if "ffffffff" in line:
                        end_touch = True

                if in_touch and end_touch:
                    in_touch = False
                    action_timestamp = datetime.now().isoformat()
                    dur_ms = int((time.time() - t_start) * 1000)
                    if None in (sx_raw, sy_raw, lx_raw, ly_raw):
                        continue

                    sx_px = scale_to_px(sx_raw, abs_ranges["ABS_MT_POSITION_X"]["min"], abs_ranges["ABS_MT_POSITION_X"]["max"], screen_res[0])
                    sy_px = scale_to_px(sy_raw, abs_ranges["ABS_MT_POSITION_Y"]["min"], abs_ranges["ABS_MT_POSITION_Y"]["max"], screen_res[1])
                    lx_px = scale_to_px(lx_raw, abs_ranges["ABS_MT_POSITION_X"]["min"], abs_ranges["ABS_MT_POSITION_X"]["max"], screen_res[0])
                    ly_px = scale_to_px(ly_raw, abs_ranges["ABS_MT_POSITION_Y"]["min"], abs_ranges["ABS_MT_POSITION_Y"]["max"], screen_res[1])

                    dist = math.hypot(lx_px - sx_px, ly_px - sy_px)
                    dur_s = dur_ms / 1000.0

                    if dist <= MOV_THRESH_PX and dur_s > 0.8:
                        action = {"tipo": "long_press", "x": sx_px, "y": sy_px, "duracao_s": round(dur_s, 2)}
                    elif dist <= MOV_THRESH_PX:
                        action = {"tipo": "tap", "x": sx_px, "y": sy_px, "duracao_s": round(dur_s, 2)}
                    else:
                        action = {"tipo": "swipe", "x1": sx_px, "y1": sy_px, "x2": lx_px, "y2": ly_px, "duracao_ms": dur_ms}

                    # Captura rapida do frame
                    time.sleep(SCREENSHOT_DELAY_S)
                    img_name = f"frame_{idx:02d}.png"
                    img_path = os.path.join(frames_dir, img_name)
                    shot_path = take_screenshot(img_path, serial)
                    screenshot_timestamp = datetime.now().isoformat()

                    actions.append(
                        {
                            "id": idx,
                            "timestamp": action_timestamp,
                            "action_timestamp": action_timestamp,
                            "screenshot_timestamp": screenshot_timestamp,
                            "imagem": img_name,
                            "acao": action,
                            "source": source,
                        }
                    )
                    if callable(persist_action):
                        persist_action(actions)

                    if action.get("tipo") == "tap":
                        printc(f"TAP {idx}: ({sx_px},{sy_px})", "green")
                    elif action.get("tipo") == "swipe":
                        printc(f"SWIPE {idx}: ({sx_px},{sy_px})->({lx_px},{ly_px})", "green")
                    elif action.get("tipo") == "long_press":
                        printc(f"LONG_PRESS {idx}: ({sx_px},{sy_px})", "green")

                    captured_ok = bool(shot_path) and os.path.exists(shot_path) and os.path.getsize(shot_path) > 0
                    if captured_ok:
                        printc(f"IMG {idx}: OK ({img_name})", "cyan")
                    else:
                        printc(f"IMG {idx}: FALHA ({img_name})", "red")

                    idx += 1

        except KeyboardInterrupt:
            pass
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                pass

        if stop_requested or os.path.exists(os.path.join(PROJECT_ROOT, "stop.flag")):
            break

        # Se getevent encerrou sem stop, tenta reconectar
        time.sleep(1)

    return actions



# =========================
# MAIN
# =========================
def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    categoria = sys.argv[1].strip().lower().replace(" ", "_")
    nome_teste = sys.argv[2].strip().lower().replace(" ", "_")

    serial = None
    if "--serial" in sys.argv:
        idx = sys.argv.index("--serial")
        if idx + 1 < len(sys.argv):
            serial = sys.argv[idx + 1]

    input_source = "adb"
    scrcpy_title = os.environ.get("SCRCPY_WINDOW_TITLE", "")
    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        if idx + 1 < len(sys.argv):
            input_source = sys.argv[idx + 1].strip().lower() or "adb"
    if "--input-source" in sys.argv:
        idx = sys.argv.index("--input-source")
        if idx + 1 < len(sys.argv):
            input_source = sys.argv[idx + 1].strip().lower() or input_source
    if "--scrcpy" in sys.argv:
        input_source = "scrcpy"
    if "--scrcpy-host" in sys.argv:
        input_source = "scrcpy_host"
    if "--scrcpy-title" in sys.argv:
        idx = sys.argv.index("--scrcpy-title")
        if idx + 1 < len(sys.argv):
            scrcpy_title = sys.argv[idx + 1].strip()
    if input_source not in {"adb", "scrcpy", "scrcpy_host"}:
        input_source = "adb"

    ensure_tester_catalog(categoria, nome_teste)
    base_dir = str(ensure_tester_catalog(categoria, nome_teste))
    recorded_dir = str(tester_recorded_dir(categoria, nome_teste))
    frames_dir = str(tester_recorded_frames_dir(categoria, nome_teste))
    os.makedirs(frames_dir, exist_ok=True)

    if input_source == "scrcpy_host":
        printc("Fonte de coleta: scrcpy_host (cliques no host)", "cyan")
    else:
        printc(f"Fonte de coleta: {input_source}", "cyan")
    if input_source == "scrcpy_host" and not scrcpy_running():
        printc("Aviso: scrcpy nao detectado em execucao. A coleta pode falhar.", "yellow")

    screen_res = get_resolution(serial)
    initial_state_path = os.path.join(recorded_dir, "initial_state.png")
    try:
        take_screenshot(initial_state_path, serial)
        if os.path.exists(initial_state_path) and os.path.getsize(initial_state_path) > 0:
            printc(f"ESTADO INICIAL: OK ({os.path.basename(initial_state_path)})", "cyan")
    except Exception:
        pass

    source = input_source
    raw_events = []
    actions_path = str(tester_actions_path(categoria, nome_teste))
    events_path = os.path.join(str(tester_recorded_dir(categoria, nome_teste)), "scrcpy_events.json")

    def persist_current_actions(current_actions):
        persist_actions_payload(
            actions_path,
            categoria=categoria,
            nome_teste=nome_teste,
            source=source,
            actions=current_actions,
            include_scrcpy_events=source == "scrcpy",
        )

    if source == "scrcpy":
        stop_flag_path = os.path.join(PROJECT_ROOT, "stop.flag")
        actions, raw_events = collect_scrcpy_verbose_loop(
            frames_dir,
            screen_res,
            serial,
            stop_flag_path=stop_flag_path,
            categoria=categoria,
            nome_teste=nome_teste,
            actions_path=actions_path,
            events_path=events_path,
        )
    elif source == "scrcpy_host":
        dev = autodetect_touch_device(serial, prefer_injected=False)
        printc(f"Dispositivo de toque: {dev}", "cyan")
        actions = collect_host_mouse_loop(
            frames_dir,
            screen_res,
            serial,
            title_hint=scrcpy_title or "scrcpy",
            persist_action=persist_current_actions,
        )
    else:
        dev = autodetect_touch_device(serial, prefer_injected=False)
        printc(f"Dispositivo de toque: {dev}", "cyan")
        abs_ranges = get_abs_ranges_for_device(dev, serial)
        actions = collect_gestures_loop(
            dev,
            frames_dir,
            screen_res,
            abs_ranges,
            serial,
            source=source,
            persist_action=persist_current_actions,
        )
    final_img = take_screenshot(str(tester_expected_final_path(categoria, nome_teste)), serial)

    saida = {
        "teste": nome_teste,
        "categoria": categoria,
        "fonte": source,
        "acoes": actions,
        "resultado_esperado": "expected/final.png",
    }
    if raw_events:
        try:
            save_events_json(raw_events, events_path)
            saida["scrcpy_events"] = "recorded/scrcpy_events.json"
        except Exception:
            pass
    acoes_path = tester_actions_path(categoria, nome_teste)
    with open(acoes_path, "w", encoding="utf-8") as f:
        json.dump(saida, f, indent=4, ensure_ascii=False)
    tester_test_metadata_path(categoria, nome_teste).write_text(
        json.dumps(
            {
                "feature": "tester",
                "suite": categoria,
                "test_id": nome_teste,
                "latest_run_id": None,
                "input_source": input_source,
                "recorded_at": datetime.now().isoformat(),
                "initial_state": "recorded/initial_state.png" if os.path.exists(initial_state_path) else None,
                "expected_final": "expected/final.png" if final_img else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    main()
