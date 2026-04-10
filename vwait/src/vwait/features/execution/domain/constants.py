from __future__ import annotations


LOG_CAPTURE_STEP_WAIT_S = 1.1

LOG_CAPTURE_SEQUENCE_FILENAMES = (
    "failure_log_sequence.csv",
    "failure_log_sequence.json",
    "log_capture_sequence.csv",
    "log_capture_sequence.json",
    "_failure_log_sequence.csv",
    "_failure_log_sequence.json",
    "_log_capture_sequence.csv",
    "_log_capture_sequence.json",
)

DEFAULT_FAILURE_LOG_PATTERNS = (
    "/data/tombstones/*",
    "/data/anr/*",
    "/data/log/*",
    "/data/tcpdump/*",
    "/data/capture/*",
    "/data/bugreport/*",
    "/data/dumpsys/*",
    "/data/lshal/*",
    "/data/McuLog/*",
    "/data/local/traces/*",
    "/ota_download/recovery_log/*",
    "/data/misc/bluetooth*",
    "/data/vendor/broadcastradio/log*",
    "/data/vendor/extend_log_/dropbox/*",
)
