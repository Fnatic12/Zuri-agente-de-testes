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

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.shared.adb_utils import resolve_adb_path


ADB_PATH = resolve_adb_path()
DEFAULT_DEV = "/dev/input/event2"
DEFAULT_RES = (1920, 1080)
SCREENSHOT_DELAY_S = 1.05
STOP_REQUESTED = False
HEX_VAL = re.compile(r"\s([0-9a-fA-F]{8})\s*$")


def _handle_stop(signum, frame):
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True


signal.signal(signal.SIGTERM, _handle_stop)
signal.signal(signal.SIGINT, _handle_stop)


def adb_cmd(serial: str | None = None) -> list[str]:
    if serial:
        return [ADB_PATH, "-s", serial]
    return [ADB_PATH]


def run_out(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.stdout.strip()


def take_screenshot(local_path: str, serial: str | None = None) -> str:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    cmd = adb_cmd(serial) + ["exec-out", "screencap", "-p"]
    with open(local_path, "wb") as fh:
        subprocess.run(cmd, stdout=fh)
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


def collect_touch_screenshots(dev_path: str, output_dir: str, screen_res: tuple[int, int], abs_ranges: dict[str, dict[str, int | None]], serial: str | None) -> None:
    while not STOP_REQUESTED:
        proc = subprocess.Popen(
            adb_cmd(serial) + ["shell", "getevent", "-lt", dev_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
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
                if STOP_REQUESTED or os.path.exists(os.path.join(output_dir, "stop.flag")):
                    break

                if "EV_KEY" in line and "BTN_TOUCH" in line and "DOWN" in line:
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

                end_touch = False
                if "EV_KEY" in line and "BTN_TOUCH" in line and "UP" in line:
                    end_touch = True
                if "EV_ABS" in line and "ABS_MT_TRACKING_ID" in line and "ffffffff" in line:
                    end_touch = True

                if not in_touch or not end_touch or None in (sx_raw, sy_raw, lx_raw, ly_raw):
                    continue

                in_touch = False
                dur_s = (time.time() - t_start) if t_start else 0.0
                sx_px = scale_to_px(int(sx_raw), int(abs_ranges["ABS_MT_POSITION_X"]["min"] or 0), abs_ranges["ABS_MT_POSITION_X"]["max"], screen_res[0])
                sy_px = scale_to_px(int(sy_raw), int(abs_ranges["ABS_MT_POSITION_Y"]["min"] or 0), abs_ranges["ABS_MT_POSITION_Y"]["max"], screen_res[1])
                lx_px = scale_to_px(int(lx_raw), int(abs_ranges["ABS_MT_POSITION_X"]["min"] or 0), abs_ranges["ABS_MT_POSITION_X"]["max"], screen_res[0])
                ly_px = scale_to_px(int(ly_raw), int(abs_ranges["ABS_MT_POSITION_Y"]["min"] or 0), abs_ranges["ABS_MT_POSITION_Y"]["max"], screen_res[1])
                dist = math.hypot(lx_px - sx_px, ly_px - sy_px)
                action_type = "tap" if dist <= 25 else "swipe"
                if dist <= 25 and dur_s > 0.8:
                    action_type = "long_press"

                time.sleep(SCREENSHOT_DELAY_S)
                file_name = f"touch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                take_screenshot(os.path.join(output_dir, file_name), serial)
                append_manifest(output_dir, file_name, action_type, sx_px, sy_px)

        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                pass

        if STOP_REQUESTED or os.path.exists(os.path.join(output_dir, "stop.flag")):
            break
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    screen_res = get_resolution(args.serial)
    dev_path = autodetect_touch_device(args.serial)
    abs_ranges = get_abs_ranges_for_device(dev_path, args.serial)
    collect_touch_screenshots(dev_path, args.output_dir, screen_res, abs_ranges, args.serial)


if __name__ == "__main__":
    main()
