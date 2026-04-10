from __future__ import annotations

from io import BytesIO
import sys
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.hmi.application import REPORT_HEADERS, build_validation_dimension_rows, build_validation_dimension_workbook


def test_build_validation_dimension_rows_maps_requested_columns():
    report = {
        "items": [
            {
                "screen_name": "Tela Home",
                "screenshot_path": "/tmp/resultado_01.png",
                "reference_path": "/tmp/figma/home.png",
                "status": "PASS",
                "scores": {
                    "structure": 0.97,
                    "text": 0.95,
                    "component": 0.99,
                    "grid_avg": 0.99,
                    "grid_min": 0.97,
                    "pixel": 0.991,
                    "final": 0.965,
                },
                "diff_summary": {
                    "pixel_match_ratio": 0.991,
                    "worst_cell_score": 0.97,
                    "toggle_count": 0,
                    "text_score": 0.95,
                },
                "critical_region_failures": [],
            }
        ]
    }

    rows = build_validation_dimension_rows(report)

    assert len(rows) == 1
    assert list(rows[0]) == list(REPORT_HEADERS)
    assert rows[0]["tela"].startswith("Tela Home")
    assert rows[0]["layout"].startswith("OK")
    assert rows[0]["tipografia"].startswith("OK")
    assert rows[0]["icones"].startswith("OK")
    assert rows[0]["espacamento"].startswith("OK")
    assert rows[0]["cores"].startswith("OK")
    assert rows[0]["status"].startswith("Aprovado")


def test_build_validation_dimension_rows_handles_missing_reference_and_component_failures():
    report = {
        "items": [
            {
                "screen_name": "Tela Toggle",
                "screenshot_path": "/tmp/resultado_toggle.png",
                "reference_path": "/tmp/figma/toggle.png",
                "status": "FAIL_COMPONENT_STATE",
                "scores": {
                    "structure": 0.94,
                    "text": None,
                    "component": 0.10,
                    "grid_avg": 0.95,
                    "grid_min": 0.92,
                    "pixel": 0.96,
                    "final": 0.61,
                },
                "diff_summary": {
                    "pixel_match_ratio": 0.96,
                    "worst_cell_score": 0.92,
                    "toggle_count": 2,
                    "text_score": None,
                },
                "critical_region_failures": [],
            },
            {
                "screen_name": None,
                "screenshot_path": "/tmp/sem_match.png",
                "reference_path": None,
                "status": "FAIL_SCREEN_MISMATCH",
                "scores": {"final": 0.0},
                "diff_summary": {},
                "critical_region_failures": [],
            },
        ]
    }

    rows = build_validation_dimension_rows(report)

    assert rows[0]["icones"] == "NOK (2 toggles)"
    assert rows[0]["tipografia"] == "N/A"
    assert rows[0]["status"].startswith("Falha de componente")
    assert rows[1]["tela"] == "sem_match"
    assert rows[1]["layout"] == "Sem referencia"
    assert rows[1]["cores"] == "Sem referencia"
    assert rows[1]["status"].startswith("Reprovado")


def test_build_validation_dimension_workbook_exports_headers_and_rows():
    rows = [
        {
            "tela": "Tela Home",
            "layout": "OK (97.0%)",
            "tipografia": "OK (95.0%)",
            "icones": "OK (99.0%)",
            "espacamento": "OK (97.0%)",
            "cores": "OK (99.1%)",
            "status": "Aprovado (96.5%)",
        }
    ]

    workbook = build_validation_dimension_workbook(rows)

    with ZipFile(BytesIO(workbook)) as archive:
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert workbook[:2] == b"PK"
    assert "tela" in sheet_xml
    assert "Tela Home" in sheet_xml
    assert "Aprovado (96.5%)" in sheet_xml
