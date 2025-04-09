import os
import json
import pandas as pd
from PIL import Image

# Configurações
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Diretórios
base_dir = '/Users/victormilani/train_ia_stag/Data/tests/bluetooth/teste_1'
frames_dir = os.path.join(base_dir, "frames")
json_path = os.path.join(base_dir, "json", "acoes.json")
output_csv = os.path.join(base_dir, "dataset.csv")

# Verifica se arquivos existem
if not os.path.exists(json_path):
    print("❌ JSON de ações não encontrado!")
    exit(1)

if not os.path.exists(frames_dir):
    print("❌ Pasta de frames não encontrada!")
    exit(1)

# Carrega ações
with open(json_path, "r") as f:
    try:
        actions = json.load(f)
    except Exception as e:
        print("❌ Erro ao ler JSON:", e)
        exit(1)

# Estrutura de dados
data = []

for action in actions:
    try:
        img_file = action["imagem"]
        x = action["acao"]["x"]
        y = action["acao"]["y"]

        # Normaliza coordenadas
        x_norm = x / SCREEN_WIDTH
        y_norm = y / SCREEN_HEIGHT

        # Caminho completo da imagem
        img_path = os.path.join(frames_dir, img_file)

        # Verifica imagem
        if not os.path.exists(img_path):
            print(f"⚠️ Imagem não encontrada: {img_path}")
            continue

        with Image.open(img_path) as img:
            img.verify()  # Confirma que a imagem está íntegra

        # Adiciona ao dataset
        data.append({
            "image_path": img_path,
            "x": x_norm,
            "y": y_norm
        })

    except Exception as e:
        print(f"❌ Erro com ação {action}: {e}")

# Salva CSV
df = pd.DataFrame(data)
df.to_csv(output_csv, index=False)
print(f"✅ Dataset salvo com {len(df)} exemplos em: {output_csv}")