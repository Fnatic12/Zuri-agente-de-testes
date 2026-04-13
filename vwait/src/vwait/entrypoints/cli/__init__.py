"""CLI entrypoints for the modular VWAIT application."""
from .build_index import main as build_index_main
from .classify import main as classify_main
from .coletor_adb import main as coletor_adb_main
from .diff_tool import main as diff_tool_main
from .hmi_touch_monitor import main as hmi_touch_monitor_main
from .main import main as operator_menu_main
from .processar_dataset import main as processar_dataset_main
from .run_test import capturar_logs_teste, main as run_test_main
from .validate import main as validate_main
from .visual_qa import main as visual_qa_main

__all__ = [
    "build_index_main",
    "capturar_logs_teste",
    "classify_main",
    "coletor_adb_main",
    "diff_tool_main",
    "hmi_touch_monitor_main",
    "operator_menu_main",
    "processar_dataset_main",
    "run_test_main",
    "validate_main",
    "visual_qa_main",
]
