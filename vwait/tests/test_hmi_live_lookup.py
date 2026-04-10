from __future__ import annotations

from HMI.hmi_report import build_validation_dimension_rows
from HMI.validacao_hmi import (
    _build_validation_report_payload,
    _compact_live_result,
    _live_monitor_belongs_to_session,
    _preferred_live_capture_size,
)


def _make_item(name: str, status: str, final: float, pixel: float, *, toggle_count: int = 0) -> dict:
    return {
        "screen_name": name,
        "screenshot_path": f"/tmp/{name.lower().replace(' ', '_')}.png",
        "reference_path": f"/tmp/figma/{name.lower().replace(' ', '_')}.png",
        "status": status,
        "scores": {
            "structure": 0.96,
            "text": 0.94,
            "component": 0.98 if toggle_count == 0 else 0.25,
            "grid_avg": 0.97,
            "grid_min": 0.95,
            "pixel": pixel,
            "final": final,
        },
        "diff_summary": {
            "pixel_match_ratio": pixel,
            "worst_cell_score": 0.95,
            "toggle_count": toggle_count,
            "semantic_score": 0.88,
            "text_score": 0.94,
        },
        "critical_region_failures": [],
        "stage1": {
            "predicted_screen_type": "home",
            "context_confidence": 0.91,
        },
    }


def test_live_lookup_report_payload_supports_export_summary_and_rows():
    items = [
        _make_item("Tela Home", "PASS", 0.97, 0.992),
        _make_item("Tela Audio", "PASS_WITH_WARNINGS", 0.86, 0.961),
        _make_item("Tela Toggle", "FAIL_COMPONENT_STATE", 0.44, 0.903, toggle_count=2),
    ]

    report = _build_validation_report_payload(
        items,
        {"figma_dir": "/tmp/figma", "generated_at": "2026-04-01T10:00:00"},
    )

    assert report["figma_dir"] == "/tmp/figma"
    assert report["summary"]["total_screens"] == 3
    assert report["summary"]["passed"] == 1
    assert report["summary"]["warnings"] == 1
    assert report["summary"]["failed"] == 1
    assert report["summary"]["result"] == "FAIL"

    rows = build_validation_dimension_rows(report)

    assert len(rows) == 3
    assert rows[0]["tela"].startswith("Tela Home")
    assert rows[1]["status"].startswith("Aprovado com ressalvas")
    assert rows[2]["icones"] == "NOK (2 toggles)"


def test_preferred_live_capture_size_uses_most_common_library_resolution():
    library_index = {
        "screens": [
            {"width": 1600, "height": 900},
            {"width": 1600, "height": 900},
            {"width": 1280, "height": 720},
        ]
    }

    assert _preferred_live_capture_size(library_index) == (1600, 900)


def test_compact_live_result_removes_debug_images_recursively():
    raw_result = {
        "screenshot_path": "/tmp/live.png",
        "screen_name": "Tela Home",
        "status": "PASS",
        "scores": {"final": 0.98},
        "diff_summary": {"pixel_match_ratio": 0.995},
        "debug_images": {"overlay": object(), "heatmap": object()},
        "candidate_results": [
            {
                "screen_name": "Tela Home",
                "status": "PASS",
                "debug_images": {"overlay": object()},
            }
        ],
    }

    compact = _compact_live_result(raw_result)

    assert compact["debug_images"] == {}
    assert compact["candidate_results"][0]["debug_images"] == {}
    assert compact["screenshot_path"] == "/tmp/live.png"


def test_live_monitor_belongs_only_to_current_streamlit_session():
    current_token = "sessao_atual"

    assert _live_monitor_belongs_to_session({"session_token": current_token}, current_token) is True
    assert _live_monitor_belongs_to_session({"session_token": "sessao_antiga"}, current_token) is False
    assert _live_monitor_belongs_to_session({}, current_token) is False


def test_compact_live_result_handles_recursive_candidate_results():
    recursive = {
        "screen_name": "Tela Home",
        "status": "PASS",
        "debug_images": {"overlay": object()},
    }
    recursive["candidate_results"] = [recursive]

    compact = _compact_live_result(recursive)

    assert compact["debug_images"] == {}
    assert compact["candidate_results"][0] == "[recursive]"
