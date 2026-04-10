from __future__ import annotations

from pathlib import Path

from ..paths import REPORTS_DIR

from .report_builder import build_failure_report, find_execution_logs
from .report_exporters import export_csv, export_json, export_markdown, make_report_dir


def printc(msg: str, color: str = "white") -> None:
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m",
    }
    print(f"{colors.get(color, '')}{msg}{colors['white']}", flush=True)


def generate_failure_report(
    category: str,
    test_name: str,
    log_path: str | Path,
    similarity_threshold: float = 0.85,
):
    report = build_failure_report(
        category,
        test_name,
        Path(log_path),
        similarity_threshold=similarity_threshold,
    )
    if not report:
        printc(f"Nenhuma falha encontrada em {category}/{test_name}", "green")
        return None

    out_dir = make_report_dir(category, test_name, report["generated_at"])
    json_path = export_json(report, out_dir)
    md_path = export_markdown(report, out_dir)
    csv_path = export_csv(report, out_dir)

    printc(f"Relatorios gerados em {out_dir}", "yellow")
    return json_path, md_path, csv_path


def main() -> None:
    printc("Procurando execucao_log.json em Data/*/*/...", "cyan")
    logs = find_execution_logs()
    if not logs:
        printc("Nenhum log de execucao encontrado.", "red")
        return

    generated = 0
    for cat, test_name, log in logs:
        result = generate_failure_report(cat, test_name, log)
        if result:
            generated += 1

    printc(f"Finalizado. Relatorios disponiveis em {REPORTS_DIR}", "green")
    printc(f"Total de testes com relatorio de falha: {generated}", "cyan")
