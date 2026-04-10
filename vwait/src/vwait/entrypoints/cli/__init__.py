"""CLI entrypoints for the modular VWAIT application."""
from .diff_tool import main as diff_tool_main
from .run_test import capturar_logs_teste, main as run_test_main

__all__ = ["capturar_logs_teste", "diff_tool_main", "run_test_main"]
