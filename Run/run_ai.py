import torch
from torchvision import transforms
from PIL import Image
import subprocess
import time
import os
import cv2

# Modelo
from torchvision import models

class ResNetClickPredictor(torch.nn.Module):
    def __init__(self):
        super(ResNetClickPredictor, self).__init__()
        self.backbone = models.resnet34(weights=None)
        self.backbone.fc = torch.nn.Linear(self.backbone.fc.in_features, 2)

    def forward(self, x):
        return self.backbone(x)

# Configurações
MODEL_PATH = "/Users/victormilani/train_ia_stag/Train/wifi_test_01_resnet.pth"
SCREENSHOT_REMOTE = "/sdcard/frame_tmp.png"
SCREENSHOT_LOCAL = "frame.png"

# Resolução da tela real (1920x1080)
SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
INPUT_WIDTH, INPUT_HEIGHT = 960, 540  # resolução usada no treino

# Modelo
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = ResNetClickPredictor()
model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
model.eval().to(device)

# Transformações da imagem
transform = transforms.Compose([
    transforms.Resize((INPUT_HEIGHT, INPUT_WIDTH)),
    transforms.ToTensor(),
    transforms.Normalize([0.5]*3, [0.5]*3)
])

print("✅ Modelo carregado. Iniciando execução automática...\n")

while True:
    try:
        # Captura e transferência da imagem do rádio
        subprocess.run(["adb", "shell", "screencap", "-p", SCREENSHOT_REMOTE])
        subprocess.run(["adb", "pull", SCREENSHOT_REMOTE, SCREENSHOT_LOCAL])
        subprocess.run(["adb", "shell", "rm", SCREENSHOT_REMOTE])

        # Validação da imagem
        img_cv = cv2.imread(SCREENSHOT_LOCAL)
        if img_cv is None:
            print("❌ Erro ao carregar imagem. Pulando...")
            time.sleep(1)
            continue

        # PIL para modelo
        image = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
        image_tensor = transform(image).unsqueeze(0).to(device)

        # Inferência
        with torch.no_grad():
            output = model(image_tensor)
            x_pred, y_pred = output[0].tolist()

        # Log da saída da IA (bruto)
        print(f"📐 Predição bruta do modelo: ({x_pred:.2f}, {y_pred:.2f})")

        # Escalonamento direto para resolução real da tela     
        x_real = int(x_pred * SCREEN_WIDTH)
        y_real = int(y_pred * SCREEN_HEIGHT)

        # Sanitização (limite dentro da tela)
        x_real = max(0, min(SCREEN_WIDTH - 1, x_real))
        y_real = max(0, min(SCREEN_HEIGHT - 1, y_real))

        # Comando ADB de toque
        subprocess.run(f"adb shell input tap {x_real} {y_real}", shell=True)
        print(f"🧠 Clique executado: ({x_real}, {y_real})\n")

        time.sleep(2)

    except Exception as e:
        print(f"⚠️ Erro durante execução: {e}")
        time.sleep(2)