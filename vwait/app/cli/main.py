import os
import subprocess
import platform
from app.shared.project_paths import project_root, root_path

# === CONFIGURAÇÕES INICIAIS ===
if platform.system() == "Windows":
    PYTHON_CMD = "python"
else:
    PYTHON_CMD = "python3"

# Caminho absoluto da raiz do projeto
PROJECT_ROOT = project_root()
SCRIPTS_DIR = root_path("Scripts")
PREPROCESS_DIR = root_path("Pre_process")
RUN_DIR = root_path("Run")
DASHBOARD_DIR = root_path("Dashboard")

def print_color(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{cores.get(color, '')}{msg}{cores['white']}")

def menu():
    print_color("\n=== MENU PRINCIPAL ===", "cyan")
    print_color("1 - Coletar gestos automaticamente", "yellow")
    print_color("2 - Processar dataset (JSON → CSV + normalização)", "yellow")
    print_color("3 - Executar testes no rádio", "yellow")
    print_color("4 - Abrir dashboard", "yellow")
    print_color("0 - Sair", "red")

def executar_script(path, nome, extra_args=None, new_console=False):
    if not os.path.exists(path):
        print_color(f"❌ {nome} não encontrado em {path}", "red")
        return

    print_color(f"\n▶️ Executando: {nome}\n", "green")

    cmd = [PYTHON_CMD, path]
    if extra_args:
        cmd.extend(extra_args)

    # Define o diretório de trabalho como a pasta onde o script está
    cwd = os.path.dirname(path)

    if platform.system() == "Windows" and new_console:
        subprocess.Popen(cmd, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.run(cmd, cwd=cwd)


def executar_coletor():
    executar_script(os.path.join(SCRIPTS_DIR, "coletor_adb.py"), "coletor_adb.py", new_console=True)

def processar_dataset():
    executar_script(os.path.join(PREPROCESS_DIR, "processar_dataset.py"), "processar_dataset.py")

def executar_testes():
    executar_script(os.path.join(RUN_DIR, "run_noia.py"), "run_noia.py")

def abrir_dashboard():
    dash_path = os.path.join(DASHBOARD_DIR, "visualizador_execucao.py")
    if not os.path.exists(dash_path):
        print_color("❌ visualizador_execucao.py não encontrado!", "red")
        return
    print_color("\n▶️ Abrindo dashboard no navegador...\n", "green")
    subprocess.Popen(["streamlit", "run", dash_path], creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system()=="Windows" else 0)

def main():
    while True:
        menu()
        escolha = input("\nDigite a opção: ").strip()

        if escolha == "1":
            executar_coletor()
        elif escolha == "2":
            processar_dataset()
        elif escolha == "3":
            executar_testes()
        elif escolha == "4":
            abrir_dashboard()
        elif escolha == "0":
            print_color("🚪 Saindo...", "red")
            break
        else:
            print_color("❌ Opção inválida!", "red")

if __name__ == "__main__":
    main()
