import os
import json
import pandas as pd
from PIL import Image

# === ENTRADAS DO USUÁRIO ===
categoria = input("📂 Categoria do teste (ex: bluetooth, wifi): ").strip().lower()
nome_teste = input("🧪 Nome do teste (ex: teste_1_bt): ").strip().lower().replace(" ", "_")

# === CONFIGURAÇÕES ===
RESOLUCAO_PADRAO = (1920, 1080)  # Largura x Altura

# === DEFINIÇÃO DE DIRETÓRIOS ===
base_dir = os.path.join("tests", categoria, nome_teste)
frames_dir = os.path.join(base_dir, "frames")
json_path = os.path.join(base_dir, "json", "acoes.json")
output_csv = os.path.join(base_dir, "dataset.csv")

# === VALIDAÇÕES INICIAIS ===
if not os.path.exists(json_path):
    print("❌ JSON de ações não encontrado:", json_path)
    exit(1)

if not os.path.exists(frames_dir):
    print("❌ Pasta de frames não encontrada:", frames_dir)
    exit(1)

# === CARREGAR JSON ===
try:
    with open(json_path, "r") as f:
        actions = json.load(f)
except Exception as e:
    print("❌ Erro ao carregar JSON:", e)
    exit(1)

# === PROCESSAMENTO ===
data = []
for acao in actions:
    try:
        imagem = acao["imagem"]
        x = acao["acao"]["x"]
        y = acao["acao"]["y"]
        largura = acao["acao"]["resolucao"].get("largura", RESOLUCAO_PADRAO[0])
        altura = acao["acao"]["resolucao"].get("altura", RESOLUCAO_PADRAO[1])

        # Normalização
        x_norm = x / largura
        y_norm = y / altura

        # Caminho absoluto
        full_img_path = os.path.join(frames_dir, imagem)

        # Verificação da imagem
        if not os.path.exists(full_img_path):
            print(f"⚠️ Imagem não encontrada: {full_img_path}")
            continue

        with Image.open(full_img_path) as img:
            img.verify()  # Confirma que a imagem está íntegra

        data.append({
            "image_path": full_img_path,
            "x": x_norm,
            "y": y_norm
        })
    except Exception as e:
        print(f"❌ Erro ao processar ação {acao}: {e}")

# === SALVAMENTO CSV ===
df = pd.DataFrame(data)
df.to_csv(output_csv, index=False)
print(f"\n✅ Dataset gerado com {len(df)} entradas em:\n{output_csv}")