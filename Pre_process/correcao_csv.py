import os
import json
import pandas as pd

def processar_json(json_path, csv_output_path):
    try:
        with open(json_path, 'r') as f:
            acoes = json.load(f)

        registros = []
        for acao in acoes:
            if "x" in acao and "y" in acao:
                registros.append({
                    "x": acao["x"],
                    "y": acao["y"],
                    "tipo": acao.get("tipo", ""),
                    "timestamp": acao.get("timestamp", ""),
                    "resolucao_largura": acao.get("resolucao_largura", 1920),
                    "resolucao_altura": acao.get("resolucao_altura", 1080),
                })

        df = pd.DataFrame(registros)
        df.to_csv(csv_output_path, index=False)
        print(f"[✅] CSV gerado: {csv_output_path}")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao processar {json_path}: {e}")
        return False

def main():
    data_root = "Data"
    total = 0

    if not os.path.exists(data_root):
        print("❌ Pasta 'Data' não encontrada. Execute o script a partir da raiz do projeto.")
        return

    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if not os.path.isdir(cat_path):
            continue

        for nome_teste in os.listdir(cat_path):
            teste_path = os.path.join(cat_path, nome_teste)
            json_path = os.path.join(teste_path, "json", "acoes.json")
            csv_output_path = os.path.join(teste_path, "dataset.csv")

            if os.path.exists(json_path):
                if processar_json(json_path, csv_output_path):
                    total += 1

    if total == 0:
        print("⚠️ Nenhum CSV encontrado para correção.")
    else:
        print(f"\n✨ {total} CSV(s) gerados com sucesso.")

if __name__ == "__main__":
    main()
