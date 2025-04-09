import os
import json
import cv2
import torch
import numpy as np
from torchvision import transforms
from modelo_clicks import ResNetClickPredictor  # ajuste se necessário
from tqdm import tqdm

# Configurações
JSON_PATH = "dados_treino_adb/json/acoes.json"
FRAMES_PATH = "dados_treino_adb/frames"
MODEL_PATH = "models/wifi_test_01.pth"
RESOLUCAO = (1560, 878)  # resolução original do rádio

# Carrega modelo
model = ResNetClickPredictor()
model.load_state_dict(torch.load(MODEL_PATH))
model.eval()

# Transformação da imagem
transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((240, 320)),
    transforms.ToTensor()
])

# Carrega JSON
with open(JSON_PATH, "r") as f:
    acoes = json.load(f)

# Avaliação
total_dist = 0
maiores_20px = 0
samples = 0

print(f"🔍 Avaliando {len(acoes)} amostras...\n")

for item in tqdm(acoes):
    img_path = os.path.join(FRAMES_PATH, item['imagem'])
    x_real = item['acao']['x']
    y_real = item['acao']['y']

    img = cv2.imread(img_path)
    if img is None:
        continue

    # Prepara para input do modelo
    tensor = transform(img).unsqueeze(0)

    with torch.no_grad():
        pred = model(tensor).squeeze(0).numpy()

    # Desnormaliza
    x_pred = int(pred[0] * RESOLUCAO[0])
    y_pred = int(pred[1] * RESOLUCAO[1])

    # Distância Euclidiana
    dist = np.sqrt((x_pred - x_real)**2 + (y_pred - y_real)**2)
    total_dist += dist
    samples += 1

    if dist > 20:
        maiores_20px += 1

# Resultados
media = total_dist / samples if samples > 0 else 0
print(f"\n📊 Média de distância do clique: {media:.2f} px")
print(f"📌 Porcentagem de cliques com erro > 20px: {(maiores_20px / samples) * 100:.2f}%")