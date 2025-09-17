import os
import json
import pandas as pd

def gerar_e_normalizar(json_path, csv_output_path):
    try:
        with open(json_path, 'r', encoding="utf-8") as f:
            conteudo = json.load(f)

        registros = []
        for item in conteudo.get("acoes", []):
            acao = item.get("acao", {})

            # TAP normal
            if "x" in acao and "y" in acao:
                registros.append({
                    "x": acao["x"],
                    "y": acao["y"],
                    "tipo": acao.get("tipo", "tap"),
                    "timestamp": item.get("timestamp", ""),
                    "resolucao_largura": acao.get("resolucao", {}).get("largura", 1920),
                    "resolucao_altura": acao.get("resolucao", {}).get("altura", 1080),
                })

            # SWIPE (entrada e saída)
            elif all(k in acao for k in ("x1", "y1", "x2", "y2")):
                registros.append({
                    "x": acao["x1"],
                    "y": acao["y1"],
                    "tipo": "swipe_inicio",
                    "timestamp": item.get("timestamp", ""),
                    "resolucao_largura": acao.get("resolucao", {}).get("largura", 1920),
                    "resolucao_altura": acao.get("resolucao", {}).get("altura", 1080),
                })
                registros.append({
                    "x": acao["x2"],
                    "y": acao["y2"],
                    "tipo": "swipe_fim",
                    "timestamp": item.get("timestamp", ""),
                    "resolucao_largura": acao.get("resolucao", {}).get("largura", 1920),
                    "resolucao_altura": acao.get("resolucao", {}).get("altura", 1080),
                })

        if not registros:
            print(f"[⚠️] Nenhum registro válido encontrado em {json_path}")
            return False

        df = pd.DataFrame(registros)

        # Normalizar coordenadas
        df = df.dropna(subset=["x", "y"])
        df = df[(df["x"] >= 0) & (df["y"] >= 0)]
        df["x_norm"] = df["x"] / df["resolucao_largura"]
        df["y_norm"] = df["y"] / df["resolucao_altura"]

        df.to_csv(csv_output_path, index=False, encoding="utf-8")
        print(f"[✅] Dataset gerado e normalizado: {csv_output_path}")
        return True

    except Exception as e:
        print(f"[ERRO] Falha ao processar {json_path}: {e}")
        return False


def main():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_root = os.path.join(PROJECT_ROOT, "Data")

    if not os.path.exists(data_root):
        print(f"❌ Pasta 'Data' não encontrada em {data_root}.")
        return

    # Perguntar categoria e teste
    categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
    nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

    teste_path = os.path.join(data_root, categoria, nome_teste)
    json_path = os.path.join(teste_path, "json", "acoes.json")
    csv_output_path = os.path.join(teste_path, "dataset.csv")

    if not os.path.exists(json_path):
        print(f"❌ Arquivo JSON não encontrado em {json_path}")
        return

    gerar_e_normalizar(json_path, csv_output_path)


if __name__ == "__main__":
    main()
