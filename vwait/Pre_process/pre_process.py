import os
import pandas as pd

def normalizar_csv(csv_path):
    try:
        df = pd.read_csv(csv_path)

        # Verifica se as colunas esperadas existem
        if not {"x", "y", "resolucao_largura", "resolucao_altura"}.issubset(df.columns):
            print(f"[⚠️] Colunas ausentes em: {csv_path} — pulando.")
            return False

        # Remover entradas inválidas
        df = df.dropna(subset=["x", "y"])
        df = df[(df["x"] >= 0) & (df["y"] >= 0)]

        # Normalizar coordenadas entre 0 e 1
        df["x_norm"] = df["x"] / df["resolucao_largura"]
        df["y_norm"] = df["y"] / df["resolucao_altura"]

        df.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"[✅] CSV normalizado: {csv_path}")
        return True

    except Exception as e:
        print(f"[ERRO] Falha ao normalizar {csv_path}: {e}")
        return False


def main():
    # Caminho absoluto para a raiz do projeto
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_root = os.path.join(PROJECT_ROOT, "Data")

    if not os.path.exists(data_root):
        print(f"[❌] Pasta 'Data' não encontrada em {data_root}.")
        return

    # Perguntar categoria e teste
    categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
    nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

    teste_path = os.path.join(data_root, categoria, nome_teste)
    csv_path = os.path.join(teste_path, "dataset.csv")

    if not os.path.exists(csv_path):
        print(f"❌ Arquivo dataset.csv não encontrado em {csv_path}")
        return

    normalizar_csv(csv_path)


if __name__ == "__main__":
    main()
