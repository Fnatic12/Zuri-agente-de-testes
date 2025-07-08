import os
import pandas as pd

def normalizar_csv(csv_path):
    try:
        df = pd.read_csv(csv_path)

        # Remover entradas sem coordenadas válidas
        df = df.dropna(subset=["x", "y"])
        df = df[(df["x"] >= 0) & (df["y"] >= 0)]

        # Normalizar coordenadas entre 0 e 1
        df["x_norm"] = df["x"] / df["resolucao_largura"]
        df["y_norm"] = df["y"] / df["resolucao_altura"]

        df.to_csv(csv_path, index=False)
        print(f"[✅] CSV normalizado: {csv_path}")
    except Exception as e:
        print(f"[ERRO] Falha ao normalizar {csv_path}: {e}")

def main():
    data_root = "Data"
    total = 0

    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if not os.path.isdir(cat_path):
            continue

        for nome_teste in os.listdir(cat_path):
            teste_path = os.path.join(cat_path, nome_teste)
            csv_path = os.path.join(teste_path, "dataset.csv")

            if os.path.exists(csv_path):
                normalizar_csv(csv_path)
                total += 1

    if total == 0:
        print("⚠️ Nenhum dataset.csv encontrado para pré-processar.")
    else:
        print(f"\n✨ {total} arquivos normalizados com sucesso.")

if __name__ == "__main__":
    main()
