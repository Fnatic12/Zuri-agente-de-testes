from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT_PATH / "src"

if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.core.paths import project_root, root_path


if platform.system() == "Windows":
    PYTHON_CMD = "python"
else:
    PYTHON_CMD = "python3"

PROJECT_ROOT = project_root()
ENTRYPOINTS_CLI_DIR = root_path("src", "vwait", "entrypoints", "cli")


def print_color(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m",
    }
    print(f"{cores.get(color, '')}{msg}{cores['white']}")


def menu():
    print_color("\n=== MENU PRINCIPAL ===", "cyan")
    print_color("1 - Coletar gestos automaticamente", "yellow")
    print_color("2 - Processar dataset (JSON -> CSV + normalizacao)", "yellow")
    print_color("3 - Executar testes no radio", "yellow")
    print_color("4 - Abrir dashboard", "yellow")
    print_color("0 - Sair", "red")


def executar_script(path, nome, extra_args=None, new_console=False):
    if not os.path.exists(path):
        print_color(f"{nome} nao encontrado em {path}", "red")
        return

    print_color(f"\nExecutando: {nome}\n", "green")

    cmd = [PYTHON_CMD, path]
    if extra_args:
        cmd.extend(extra_args)

    cwd = os.path.dirname(path)

    if platform.system() == "Windows" and new_console:
        subprocess.Popen(cmd, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.run(cmd, cwd=cwd)


def executar_coletor():
    executar_script(os.path.join(ENTRYPOINTS_CLI_DIR, "coletor_adb.py"), "coletor_adb.py", new_console=True)


def processar_dataset():
    executar_script(os.path.join(ENTRYPOINTS_CLI_DIR, "processar_dataset.py"), "processar_dataset.py")


def executar_testes():
    executar_script(os.path.join(ENTRYPOINTS_CLI_DIR, "run_test.py"), "run_test.py")


def abrir_dashboard():
    dash_path = os.path.join(PROJECT_ROOT, "src", "vwait", "entrypoints", "streamlit", "visualizador_execucao.py")
    if not os.path.exists(dash_path):
        print_color("visualizador_execucao.py nao encontrado!", "red")
        return
    print_color("\nAbrindo dashboard no navegador...\n", "green")
    subprocess.Popen(
        ["streamlit", "run", dash_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0,
    )


def main():
    while True:
        menu()
        escolha = input("\nDigite a opcao: ").strip()

        if escolha == "1":
            executar_coletor()
        elif escolha == "2":
            processar_dataset()
        elif escolha == "3":
            executar_testes()
        elif escolha == "4":
            abrir_dashboard()
        elif escolha == "0":
            print_color("Saindo...", "red")
            break
        else:
            print_color("Opcao invalida!", "red")


if __name__ == "__main__":
    main()
