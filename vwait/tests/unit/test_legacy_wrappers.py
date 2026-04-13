from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures.ui.streamlit import (
    apply_panel_button_theme,
    main as failures_ui_main,
    render_failure_control_page,
    titulo_painel,
)
