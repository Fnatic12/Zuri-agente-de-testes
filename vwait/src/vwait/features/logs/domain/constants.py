from __future__ import annotations


TEXT_EXTS = {
    ".txt",
    ".log",
    ".json",
    ".xml",
    ".csv",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".trace",
    ".out",
    ".err",
    ".properties",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

MAX_VIEW_CHARS = 40000
MAX_AI_FILE_CHARS = 14000
MAX_AI_CAPTURE_CHARS = 24000

HEURISTICS = {
    "fatal": [
        r"fatal exception",
        r"fatal signal",
        r"\bsigsegv\b",
        r"\bsigabrt\b",
        r"\babort\b",
        r"\bbacktrace\b",
        r"native crash",
        r"crash",
    ],
    "anr": [
        r"\banr\b",
        r"application not responding",
        r"input dispatching timed out",
        r"broadcast of intent",
    ],
    "watchdog": [
        r"watchdog",
        r"system_server",
        r"service manager",
        r"dead object",
    ],
    "bluetooth": [
        r"bluetooth",
        r"bt_stack",
        r"btif",
        r"avrcp",
        r"a2dp",
        r"hfp",
    ],
    "radio": [
        r"broadcastradio",
        r"tuner",
        r"mcu",
        r"hal",
        r"lshal",
        r"vendor",
    ],
}
