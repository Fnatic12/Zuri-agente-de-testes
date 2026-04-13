from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.logs.application import (
    analysis_prompt_for_capture,
    human_size,
    load_log_captures,
    scan_capture_signals,
    scan_text_signals,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scan_text_signals_detects_anr_and_bluetooth() -> None:
    text = """
    01-01 10:00:00 Application Not Responding
    01-01 10:00:01 bluetooth stack timeout
    """.strip()

    results = scan_text_signals(text)

    assert results["anr"]["count"] >= 1
    assert results["bluetooth"]["count"] >= 1


def test_scan_capture_signals_scores_files() -> None:
    files = [
        {
            "path": __file__,
            "relpath": "capture/logcat.txt",
            "size": 100,
            "text_like": True,
        }
    ]

    # Reuse this source file path but patch relpath/size only; count may be zero.
    totals, highlights = scan_capture_signals(files)

    assert set(totals.keys()) == {"fatal", "anr", "watchdog", "bluetooth", "radio"}
    assert isinstance(highlights, list)


def test_load_log_captures_reads_metadata_and_files(tmp_path: Path) -> None:
    capture_dir = tmp_path / "radio" / "teste_a" / "logs" / "capture_001"
    _write_text(capture_dir / "logcat.txt", "fatal exception\nwatchdog")
    (capture_dir / "capture_metadata.json").write_text(
        json.dumps({"started_at": "2026-04-10T10:00:00", "status": "ok"}, ensure_ascii=False),
        encoding="utf-8",
    )

    captures = load_log_captures(tmp_path)

    assert len(captures) == 1
    capture = captures[0]
    assert capture["categoria"] == "radio"
    assert capture["teste"] == "teste_a"
    assert capture["capture_name"] == "capture_001"
    assert capture["metadata"]["status"] == "ok"
    assert capture["files"][0]["relpath"] == "capture_metadata.json" or capture["files"][0]["relpath"] == "logcat.txt"


def test_analysis_prompt_for_capture_mentions_used_files() -> None:
    capture = {
        "categoria": "radio",
        "teste": "teste_a",
        "capture_name": "capture_001",
        "metadata": {"status": "ok"},
        "files": [
            {
                "path": __file__,
                "relpath": "logcat.txt",
                "size": 123,
                "text_like": True,
            }
        ],
    }

    prompt, used_files = analysis_prompt_for_capture(capture, "houve crash?")

    assert "houve crash?" in prompt
    assert isinstance(used_files, list)


def test_human_size_formats_bytes() -> None:
    assert human_size(512) == "512.0B"
    assert human_size(2048) == "2.0KB"
