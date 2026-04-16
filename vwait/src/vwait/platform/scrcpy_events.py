from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from math import hypot
from pathlib import Path
from typing import Iterable

from vwait.core.paths import SYSTEM_ROOT


SCRCPY_TOUCH_REGEX = re.compile(
    r"input:\s+touch\s+\[id=(?P<input_id>[^\]]+)\]\s+(?P<event_type>down|up|move)\s+"
    r"position=(?P<x>\d+),(?P<y>\d+)\s+pressure=(?P<pressure>[0-9.]+)",
    re.IGNORECASE,
)

MOVE_THRESHOLD_PX = 25
LONG_PRESS_THRESHOLD_S = 0.8
SCRCPY_SESSION_TITLE = "VWAIT_DEVICE"
SCRCPY_SESSION_LOG_PATH = Path(SYSTEM_ROOT) / "scrcpy_session_verbose.log"
SCRCPY_SESSION_META_PATH = Path(SYSTEM_ROOT) / "scrcpy_session.json"
SCRCPY_SESSION_META_VERSION = 2


@dataclass
class ScrcpyTouchEvent:
    timestamp: str
    source: str
    input_id: str
    event_type: str
    x: int
    y: int
    pressure: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "input_id": self.input_id,
            "event_type": self.event_type,
            "x": self.x,
            "y": self.y,
            "pressure": self.pressure,
        }


def build_scrcpy_command(serial: str | None = None, extra_args: list[str] | None = None) -> list[str]:
    bin_path = os.environ.get("SCRCPY_BIN", "scrcpy")
    cmd = [bin_path, "-Vverbose", "--mouse=sdk", "--no-mouse-hover", "--no-audio"]
    if serial:
        cmd += ["-s", serial]
    if extra_args:
        cmd += extra_args
    return _wrap_line_buffered(cmd)


def build_scrcpy_window_command(
    serial: str | None = None,
    *,
    window_title: str | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    bin_path = os.environ.get("SCRCPY_BIN", "scrcpy")
    cmd = [bin_path, "--mouse=sdk", "--no-mouse-hover", "--stay-awake", "--no-audio"]
    if serial:
        cmd += ["-s", serial]
    if window_title:
        cmd += ["--window-title", window_title]
    if extra_args:
        cmd += extra_args
    return _wrap_line_buffered(cmd)


def _wrap_line_buffered(cmd: list[str]) -> list[str]:
    if os.name != "nt" and shutil.which("stdbuf"):
        return ["stdbuf", "-oL", "-eL", *cmd]
    return cmd


def start_scrcpy_process(serial: str | None = None, extra_args: list[str] | None = None) -> subprocess.Popen:
    cmd = build_scrcpy_command(serial=serial, extra_args=extra_args)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_scrcpy_session_meta() -> dict:
    try:
        with open(SCRCPY_SESSION_META_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_scrcpy_session_meta(payload: dict) -> None:
    os.makedirs(SCRCPY_SESSION_META_PATH.parent, exist_ok=True)
    with open(SCRCPY_SESSION_META_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def ensure_persistent_scrcpy_session(
    serial: str | None = None,
    *,
    window_title: str | None = None,
    extra_args: list[str] | None = None,
) -> tuple[dict, bool]:
    meta = load_scrcpy_session_meta()
    pid = int(meta.get("pid") or 0) if str(meta.get("pid") or "").isdigit() else 0
    if _pid_alive(pid):
        if int(meta.get("meta_version") or 0) >= SCRCPY_SESSION_META_VERSION:
            return meta, False
        _terminate_scrcpy_session(pid)

    title = window_title or os.environ.get("SCRCPY_WINDOW_TITLE") or SCRCPY_SESSION_TITLE
    cmd = build_scrcpy_command(serial=serial, extra_args=["--window-title", title, "--stay-awake"] + (extra_args or []))
    os.makedirs(SCRCPY_SESSION_LOG_PATH.parent, exist_ok=True)
    log_handle = open(SCRCPY_SESSION_LOG_PATH, "a", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    meta = {
        "meta_version": SCRCPY_SESSION_META_VERSION,
        "pid": proc.pid,
        "serial": serial or "",
        "window_title": title,
        "log_path": str(SCRCPY_SESSION_LOG_PATH),
        "started_at": datetime.now().isoformat(),
        "line_buffered": True,
        "no_audio": True,
    }
    save_scrcpy_session_meta(meta)
    return meta, True


def _terminate_scrcpy_session(pid: int) -> None:
    try:
        if os.name != "nt":
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.05)


def iter_scrcpy_touch_events_from_log(
    log_path: str,
    *,
    start_offset: int = 0,
    stop_flag_path: str | None = None,
    poll_interval_s: float = 0.05,
    stop_grace_s: float = 1.2,
    raw_line_handler=None,
) -> Iterable[ScrcpyTouchEvent]:
    if not os.path.exists(log_path):
        return
    with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(max(0, int(start_offset)))
        stop_seen_at: float | None = None
        while True:
            if stop_flag_path and os.path.exists(stop_flag_path) and stop_seen_at is None:
                stop_seen_at = time.time()
            line = handle.readline()
            if not line:
                if stop_seen_at is not None and (time.time() - stop_seen_at) >= max(0.1, float(stop_grace_s)):
                    break
                time.sleep(poll_interval_s)
                continue
            line = line.rstrip("\n")
            if callable(raw_line_handler):
                try:
                    raw_line_handler(line)
                except Exception:
                    pass
            event = parse_scrcpy_touch_line(line)
            if event:
                yield event


def launch_scrcpy_window(
    serial: str | None = None,
    *,
    window_title: str | None = None,
    extra_args: list[str] | None = None,
    stdout=None,
    stderr=None,
) -> subprocess.Popen:
    cmd = build_scrcpy_window_command(serial=serial, window_title=window_title, extra_args=extra_args)
    return subprocess.Popen(cmd, stdout=stdout, stderr=stderr)


def parse_scrcpy_touch_line(line: str) -> ScrcpyTouchEvent | None:
    match = SCRCPY_TOUCH_REGEX.search(line)
    if not match:
        return None
    return ScrcpyTouchEvent(
        timestamp=datetime.now().isoformat(),
        source="scrcpy",
        input_id=match.group("input_id"),
        event_type=match.group("event_type").lower(),
        x=int(match.group("x")),
        y=int(match.group("y")),
        pressure=float(match.group("pressure")),
    )


def _stream_reader(stream, out_queue: queue.Queue, stop_event: threading.Event):
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            if stop_event.is_set():
                break
            if line:
                out_queue.put(line.rstrip("\n"))
    except Exception:
        return


def iter_scrcpy_touch_events(
    process: subprocess.Popen,
    *,
    stop_flag_path: str | None = None,
    poll_interval_s: float = 0.1,
    raw_line_handler=None,
) -> Iterable[ScrcpyTouchEvent]:
    stop_event = threading.Event()
    line_queue: queue.Queue = queue.Queue()

    threads = [
        threading.Thread(target=_stream_reader, args=(process.stdout, line_queue, stop_event), daemon=True),
        threading.Thread(target=_stream_reader, args=(process.stderr, line_queue, stop_event), daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        while True:
            if stop_flag_path and os.path.exists(stop_flag_path):
                break
            if process.poll() is not None:
                break
            try:
                line = line_queue.get(timeout=poll_interval_s)
            except queue.Empty:
                continue
            if callable(raw_line_handler):
                try:
                    raw_line_handler(line)
                except Exception:
                    pass
            event = parse_scrcpy_touch_line(line)
            if event:
                yield event
    finally:
        stop_event.set()
        for thread in threads:
            thread.join(timeout=0.5)


def save_events_json(events: list[ScrcpyTouchEvent], output_path: str) -> None:
    payload = [event.to_dict() for event in events]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


class ScrcpyGestureAssembler:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        *,
        move_threshold_px: int = MOVE_THRESHOLD_PX,
        long_press_threshold_s: float = LONG_PRESS_THRESHOLD_S,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.move_threshold_px = int(move_threshold_px)
        self.long_press_threshold_s = float(long_press_threshold_s)
        self._reset()

    def _reset(self):
        self.down_event: ScrcpyTouchEvent | None = None
        self.last_event: ScrcpyTouchEvent | None = None
        self.moved = False
        self.start_time_s: float | None = None

    @property
    def has_active_touch(self) -> bool:
        return self.down_event is not None

    def feed(self, event: ScrcpyTouchEvent) -> dict | None:
        if event.event_type == "down":
            self._reset()
            self.down_event = event
            self.last_event = event
            self.start_time_s = self._to_epoch_seconds(event.timestamp)
            return None

        if event.event_type == "move":
            if self.down_event is None:
                return None
            self.last_event = event
            self.moved = True
            return None

        if event.event_type == "up":
            if self.down_event is None:
                return None
            self.last_event = event
            down = self.down_event
            end = self.last_event
            duration_s = max(0.0, self._to_epoch_seconds(end.timestamp) - (self.start_time_s or self._to_epoch_seconds(down.timestamp)))
            duration_ms = int(round(duration_s * 1000))
            distance_px = hypot(end.x - down.x, end.y - down.y)

            if distance_px > self.move_threshold_px:
                action = {
                    "tipo": "swipe",
                    "gesture": "drag",
                    "x1": down.x,
                    "y1": down.y,
                    "x2": end.x,
                    "y2": end.y,
                    "duracao_ms": duration_ms,
                }
            elif duration_s >= self.long_press_threshold_s:
                action = {
                    "tipo": "long_press",
                    "gesture": "long_press",
                    "x": down.x,
                    "y": down.y,
                    "duracao_s": round(duration_s, 2),
                }
            else:
                action = {
                    "tipo": "tap",
                    "gesture": "tap",
                    "x": down.x,
                    "y": down.y,
                    "duracao_s": round(duration_s, 2),
                }
            action["resolucao"] = {"largura": self.screen_width, "altura": self.screen_height}
            self._reset()
            return action

        return None

    @staticmethod
    def _to_epoch_seconds(timestamp: str) -> float:
        try:
            return datetime.fromisoformat(timestamp).timestamp()
        except Exception:
            return time.time()


def events_to_actions(events: Iterable[ScrcpyTouchEvent], screen_width: int, screen_height: int) -> list[dict]:
    assembler = ScrcpyGestureAssembler(screen_width, screen_height)
    actions: list[dict] = []
    for event in events:
        action = assembler.feed(event)
        if action:
            actions.append(action)
    return actions


__all__ = [
    "SCRCPY_SESSION_LOG_PATH",
    "SCRCPY_SESSION_META_PATH",
    "SCRCPY_SESSION_TITLE",
    "ScrcpyGestureAssembler",
    "ScrcpyTouchEvent",
    "build_scrcpy_command",
    "build_scrcpy_window_command",
    "ensure_persistent_scrcpy_session",
    "iter_scrcpy_touch_events",
    "iter_scrcpy_touch_events_from_log",
    "launch_scrcpy_window",
    "events_to_actions",
    "load_scrcpy_session_meta",
    "parse_scrcpy_touch_line",
    "save_events_json",
    "save_scrcpy_session_meta",
    "start_scrcpy_process",
]
