from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures import paths as failure_paths


def test_failures_paths_match_project_layout():
    assert failure_paths.PROJECT_ROOT == PROJECT_ROOT
    assert failure_paths.DATA_DIR == PROJECT_ROOT / "Data"
    assert failure_paths.WORKSPACE_DIR == PROJECT_ROOT / "workspace"
    assert failure_paths.REPORTS_DIR == PROJECT_ROOT / "workspace" / "reports" / "failures"
    assert failure_paths.LEGACY_REPORTS_DIR == PROJECT_ROOT / "KPM" / "reports"
    assert failure_paths.iter_report_roots() == (
        PROJECT_ROOT / "workspace" / "reports" / "failures",
        PROJECT_ROOT / "KPM" / "reports",
    )
    assert failure_paths.test_dir("radio", "home") == PROJECT_ROOT / "Data" / "radio" / "home"
