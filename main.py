import os
import subprocess

# Caminhos dos scripts
SCRIPTS = {
    "coleta": "Scripts/coletor_adb.py",
    "pre_process": "Pre_process/pre_process.py",
    "correcao": "Pre_process/correcao_csv.py",
    "run": "Run/run_noia.py"
}

def executar_script(caminho, titulo):
    if not os.path.isfile(caminho):
        print(f"❌ Script não encontrado: {caminho}")
        return
    print(f"\n🚀 {titulo}...\n")
    try:
        subprocess.run(["py", caminho], check=True)
    except subprocess.CalledProcessError:
        print(f"❌ Erro durante a execução de {caminho}")

def executar_coleta():
    executar_script(SCRIPTS["coleta"], "Iniciando coleta de dados")

def executar_pre_processamento():
    executar_script(SCRIPTS["pre_process"], "Executando pré-processamento")
    executar_script(SCRIPTS["correcao"], "Aplicando correção no dataset")

def executar_run():
    executar_script(SCRIPTS["run"], "Executando teste automatizado")

def menu():
    while True:
        print("\n" + "="*40)
        print("🔧 ZURI TEST AUTOMATION - MENU PRINCIPAL")
        print("="*40)
        print("1️⃣  Executar COLETA de dados")
        print("2️⃣  Executar PRÉ-PROCESSAMENTO e CORREÇÃO")
        print("3️⃣  Executar TESTE AUTOMATIZADO")
        print("0️⃣  Sair")
        print("-" * 40)

        opcao = input("👉 Escolha uma opção: ").strip()

        if opcao == "1":
            executar_coleta()
        elif opcao == "2":
            executar_pre_processamento()
        elif opcao == "3":
            executar_run()
        elif opcao == "0":
            print("\n👋 Encerrando o sistema. Até mais!")
            break
        else:
            print("❌ Opção inválida. Tente novamente.")

if __name__ == "__main__":
    menu()
