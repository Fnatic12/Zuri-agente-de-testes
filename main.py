import os

def executar_coleta():
    print("\n🔴 Iniciando coleta de dados...\n")
    os.system("py Scripts/coletor_adb.py")  # Caminho atualizado

def executar_pre_processamento():
    print("\n🟡 Executando pré-processamento e correção...\n")
    os.system("py Pre_process/pre_process.py")
    os.system("py Pre_process/correcao_csv.py")

def executar_run():
    print("\n🟢 Executando teste automatizado...\n")
    os.system("py Run/run_noia.py")

def menu():
    while True:
        print("\n" + "="*30)
        print(" ZURI TEST AUTOMATION - MAIN")
        print("="*30)
        print("1️⃣  Executar COLETA de dados")
        print("2️⃣  Executar PRÉ-PROCESSAMENTO e CORREÇÃO")
        print("3️⃣  Executar TESTE AUTOMATIZADO")
        print("0️⃣  Sair\n")

        opcao = input("Selecione uma opção: ").strip()

        if opcao == "1":
            executar_coleta()
        elif opcao == "2":
            executar_pre_processamento()
        elif opcao == "3":
            executar_run()
        elif opcao == "0":
            print("\n👋 Encerrando.")
            break
        else:
            print("❌ Opção inválida. Tente novamente.")

if __name__ == "__main__":
    menu()
