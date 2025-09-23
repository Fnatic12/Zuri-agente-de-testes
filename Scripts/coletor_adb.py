import os
import re
import json
import math
import time
import sys
import platform
import pyfiglet
import signal
import colorama
from colorama import Fore, Style
from termcolor import colored
import subprocess
from datetime import datetime
colorama.init()

# =========================
# CONFIG
# =========================
BUILD_TAG = "ZURI Coletor v2 (event2)"
if platform.system() == "Windows":
    ADB_PATH = r"C:\Users\Automation01\platform-tools\adb.exe"
else:
    ADB_PATH = "adb"

REMOTE_TMP = "/sdcard/tmp_shot.png"
MOV_THRESH_PX = 25            # distância p/ classificar SWIPE (senão é TAP)
DEFAULT_RES = (1920, 1080)    # fallback
DEFAULT_DEV = "/dev/input/event2"
stop_requested = False

def handle_sigterm(signum, frame):
    global stop_requested
    stop_requested = True
    printc("\n🛑 Finalizando coleta (SIGTERM recebido)...", "yellow")

signal.signal(signal.SIGTERM, handle_sigterm)

# Caminho absoluto para a raiz do projeto (um nível acima da pasta Scripts/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

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

def take_screenshot(local_path, serial=None):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    subprocess.run(adb_cmd(serial) + ["shell", "screencap", "-p", REMOTE_TMP])
    subprocess.run(adb_cmd(serial) + ["pull", REMOTE_TMP, local_path])
    subprocess.run(adb_cmd(serial) + ["shell", "rm", REMOTE_TMP])
    return local_path

def get_resolution(serial=None):
    out = run_out(adb_cmd(serial) + ["shell", "wm", "size"])
    m = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
    if m:
        return int(m.group(1)), int(m.group(2))
    return DEFAULT_RES

def autodetect_touch_device(serial=None):
    """
    Procura o device de touchscreen via `adb shell getevent -pl`.
    Dá prioridade para 'touchscreen'. Se não achar, cai para qualquer 'touch'.
    """
    out = run_out(adb_cmd(serial) + ["shell", "getevent", "-pl"])
    dev_touchscreen = None
    dev_touch = None
    current_block = []

    for line in out.splitlines():
        if line.startswith("add device"):
            current_block = [line]
        else:
            current_block.append(line)

        if "name:" in line.lower():
            name_line = line.lower()
            # prioridade: touchscreen
            if "touchscreen" in name_line:
                m = re.search(r"add device \d+:\s+(/dev/input/event\d+)", current_block[0])
                if m:
                    dev_touchscreen = m.group(1)
            # fallback: qualquer touch
            elif "touch" in name_line:
                m = re.search(r"add device \d+:\s+(/dev/input/event\d+)", current_block[0])
                if m and dev_touch is None:
                    dev_touch = m.group(1)

    return dev_touchscreen or dev_touch or DEFAULT_DEV

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

def collect_gestures_loop(dev_path, frames_dir, screen_res, abs_ranges, serial=None):
    printc(f"\n▶️ Escutando touchscreen em {dev_path}", "cyan")
    printc("Toque/arraste na tela do rádio. Para finalizar, pressione CTRL+C.\n", "yellow")

    cmd = adb_cmd(serial) + ["shell", "getevent", "-lt", dev_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, universal_newlines=True)

    actions = []
    idx = 1

    in_touch = False
    sx_raw = sy_raw = None
    lx_raw = ly_raw = None
    t_start = None

    try:
        for line in proc.stdout:
            line = line.rstrip()

            if os.path.exists(os.path.join(PROJECT_ROOT, "stop.flag")):
                printc("\n🛑 Finalização solicitada via arquivo stop.flag", "yellow")
                break

            if "EV_KEY" in line and "BTN_TOUCH" in line and "DOWN" in line:
                in_touch = True
                t_start = time.time()
                sx_raw = sy_raw = None
                lx_raw = ly_raw = None

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

            end_touch = False
            if "EV_KEY" in line and "BTN_TOUCH" in line and "UP" in line:
                end_touch = True
            if "EV_ABS" in line and "ABS_MT_TRACKING_ID" in line and "ffffffff" in line:
                end_touch = True

            if in_touch and end_touch:
                in_touch = False
                dur_ms = int((time.time() - t_start) * 1000)

                if sx_raw is None or sy_raw is None or lx_raw is None or ly_raw is None:
                    printc("⚠️  Gesto ignorado: sem coordenadas completas", "yellow")
                    continue

                sx_px = scale_to_px(
                    sx_raw,
                    abs_ranges["ABS_MT_POSITION_X"]["min"] if abs_ranges["ABS_MT_POSITION_X"]["max"] is not None else abs_ranges["ABS_X"]["min"],
                    abs_ranges["ABS_MT_POSITION_X"]["max"] if abs_ranges["ABS_MT_POSITION_X"]["max"] is not None else abs_ranges["ABS_X"]["max"],
                    screen_res[0]
                )
                sy_px = scale_to_px(
                    sy_raw,
                    abs_ranges["ABS_MT_POSITION_Y"]["min"] if abs_ranges["ABS_MT_POSITION_Y"]["max"] is not None else abs_ranges["ABS_Y"]["min"],
                    abs_ranges["ABS_MT_POSITION_Y"]["max"] if abs_ranges["ABS_MT_POSITION_Y"]["max"] is not None else abs_ranges["ABS_Y"]["max"],
                    screen_res[1]
                )
                lx_px = scale_to_px(
                    lx_raw,
                    abs_ranges["ABS_MT_POSITION_X"]["min"] if abs_ranges["ABS_MT_POSITION_X"]["max"] is not None else abs_ranges["ABS_X"]["min"],
                    abs_ranges["ABS_MT_POSITION_X"]["max"] if abs_ranges["ABS_MT_POSITION_X"]["max"] is not None else abs_ranges["ABS_X"]["max"],
                    screen_res[0]
                )
                ly_px = scale_to_px(
                    ly_raw,
                    abs_ranges["ABS_MT_POSITION_Y"]["min"] if abs_ranges["ABS_MT_POSITION_Y"]["max"] is not None else abs_ranges["ABS_Y"]["min"],
                    abs_ranges["ABS_MT_POSITION_Y"]["max"] if abs_ranges["ABS_MT_POSITION_Y"]["max"] is not None else abs_ranges["ABS_Y"]["max"],
                    screen_res[1]
                )

                dist = math.hypot(lx_px - sx_px, ly_px - sy_px)
                if dist <= MOV_THRESH_PX:
                    action = {
                        "tipo": "tap",
                        "x": int(sx_px),
                        "y": int(sy_px),
                        "resolucao": {"largura": screen_res[0], "altura": screen_res[1]}
                    }
                    label = f"TAP ({action['x']},{action['y']})"
                else:
                    action = {
                        "tipo": "swipe",
                        "x1": int(sx_px),
                        "y1": int(sy_px),
                        "x2": int(lx_px),
                        "y2": int(ly_px),
                        "duracao_ms": max(dur_ms, 1),
                        "resolucao": {"largura": screen_res[0], "altura": screen_res[1]}
                    }
                    label = f"SWIPE ({action['x1']},{action['y1']})→({action['x2']},{action['y2']}) {dur_ms}ms"

                img_name = f"frame_{idx:02d}.png"
                take_screenshot(os.path.join(frames_dir, img_name), serial)

                actions.append({
                    "id": idx,
                    "timestamp": datetime.now().isoformat(),
                    "imagem": img_name,
                    "acao": action
                })

                printc(f"✅ Ação {idx}: {label} | frame: {img_name}", "green")
                idx += 1

    except KeyboardInterrupt:
        printc("\n⏹️ Coleta encerrada pelo usuário.", "yellow")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            pass

    return actions

def print_banner():
    banner = pyfiglet.figlet_format("ZURI Coletor")
    print(colored(banner, "blue"))
    print(colored("v2 - Coleta Automática de Ações no Rádio via ADB", "blue"))
    print(colored("="*55, "blue"))
    print(colored("         VWAIT   -   BTEE   -   ZURI", "blue"))
    print(colored("="*55, "blue"))

# =========================
# MAIN
# =========================
def main():
    print_banner()

    if len(sys.argv) < 3:
        printc("❌ Uso correto: python coletor_adb.py <categoria> <nome_teste> [--serial <serial>]", "red")
        sys.exit(1)

    categoria = sys.argv[1].strip().lower().replace(" ", "_")
    nome_teste = sys.argv[2].strip().lower().replace(" ", "_")

    serial = None
    if "--serial" in sys.argv:
        idx = sys.argv.index("--serial")
        if idx + 1 < len(sys.argv):
            serial = sys.argv[idx + 1]

    printc(f"📦 {BUILD_TAG}", "cyan")
    print("📁 Coleta Automática de Ações no Rádio via ADB")

    base_dir = os.path.join(PROJECT_ROOT, "Data", categoria, nome_teste)
    json_dir = os.path.join(base_dir, "json")
    frames_dir = os.path.join(base_dir, "frames")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)

    screen_res = get_resolution(serial)
    printc(f"🖥️ Resolução detectada: {screen_res[0]}x{screen_res[1]}", "cyan")

    dev = autodetect_touch_device(serial)
    printc(f"📟 Device de touch: {dev}", "cyan")

    abs_ranges = get_abs_ranges_for_device(dev, serial)
    printc(f"🔎 Ranges capturados (ABS): {abs_ranges}", "white")

    actions = collect_gestures_loop(dev, frames_dir, screen_res, abs_ranges, serial)

    printc("\n📸 Capturando screenshot final do teste...", "yellow")
    final_img = take_screenshot(os.path.join(base_dir, "resultado_final.png"), serial)

    saida = {
        "teste": nome_teste,
        "categoria": categoria,
        "acoes": actions,
        "resultado_esperado": "resultado_final.png"
    }
    acoes_path = os.path.join(json_dir, "acoes.json")
    with open(acoes_path, "w", encoding="utf-8") as f:
        json.dump(saida, f, indent=4, ensure_ascii=False)

    printc(f"\n✅ Coleta finalizada.", "green")
    printc(f"📄 Ações salvas em: {acoes_path}", "green")
    printc(f"🖼️ Screenshot final: {final_img}", "green")

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    main()
