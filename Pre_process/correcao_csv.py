import pandas as pd
import os

def corrigir_csv(csv_path):
    df = pd.read_csv(csv_path)

    # Remover entradas sem coordenadas válidas
    df = df.dropna(subset=["x", "y"])
    df = df[df["x"] >= 0]
    df = df[df["y"] >= 0]

    # Normalizar coordenadas entre 0 e 1
    df["x_norm"] = df["x"] / df["resolucao_largura"]
    df["y_norm"] = df["y"] / df["resolucao_altura"]

    df.to_csv(csv_path, index=False)
    print(f"[✅] CSV corrigido e normalizado salvo em: {csv_path}")

def main():
    data_root = "Data"
    total_corrigidos = 0

    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if not os.path.isdir(cat_path):
            continue

        for nome_teste in os.listdir(cat_path):
            teste_path = os.path.join(cat_path, nome_teste)
            csv_path = os.path.join(teste_path, "dataset.csv")

            if os.path.exists(csv_path):
                try:
                    corrigir_csv(csv_path)
                    total_corrigidos += 1
                except Exception as e:
                    print(f"[ERRO] Falha ao corrigir {csv_path}: {e}")

    if total_corrigidos == 0:
        print("⚠️ Nenhum CSV encontrado para correção.")
    else:
        print(f"\n✨ {total_corrigidos} arquivos corrigidos com sucesso.")

if __name__ == "__main__":
    main()
