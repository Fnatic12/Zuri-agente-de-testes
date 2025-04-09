import os
import json
import csv

# === CONFIGURAÇÃO ===
categoria = input("Categoria (ex: bluetooth): ").strip().lower()
nome_teste = input("Nome do teste (ex: teste_2_bt): ").strip().lower()

base_dir = os.path.join("tests", categoria, nome_teste)
json_path = os.path.join(base_dir, "json", "acoes.json")
frames_dir = os.path.join(base_dir, "frames")
csv_path = os.path.join(base_dir, "dataset.csv")

# === CARREGAR JSON ===
with open(json_path, "r") as f:
    acoes = json.load(f)

# === ESCREVER CSV ===
with open(csv_path, "w", newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["image_path", "x", "y"])

    for acao in acoes:
        imagem = acao["imagem"]
        x = acao["acao"]["x"]
        y = acao["acao"]["y"]
        largura = acao["acao"]["resolucao"]["largura"]
        altura = acao["acao"]["resolucao"]["altura"]

        x_norm = x / largura
        y_norm = y / altura

        full_path = os.path.join(frames_dir, imagem)
        writer.writerow([full_path, x_norm, y_norm])

print(f"✅ CSV gerado com sucesso: {csv_path}")