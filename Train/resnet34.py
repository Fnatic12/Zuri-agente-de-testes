import os
import time
import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
from PIL import Image
from datetime import datetime
from torchvision import transforms, models
from torch.utils.data import Dataset, DataLoader, random_split

# Configurações
CSV_PATH = "/Users/victormilani/train_ia_stag/Data/dados_treino_adb/dataset.csv"
MODEL_PATH = "/Users/victormilani/train_ia_stag/Train/wifi_test_01_resnet.pth"
LOG_PATH = "/Users/victormilani/train_ia_stag/Train/training_log.csv"
EPOCHS = 50
BATCH_SIZE = 32
LR = 1e-4
IMG_WIDTH = 960
IMG_HEIGHT = 540
VAL_SPLIT = 0.2

# Dataset personalizado
class TouchDataset(Dataset):
    def __init__(self, csv_file, transform=None):
        self.data = pd.read_csv(csv_file)
        self.transform = transform

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        img_path = self.data.iloc[idx, 0]
        x = self.data.iloc[idx, 1]
        y = self.data.iloc[idx, 2]
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, torch.tensor([x, y], dtype=torch.float32)

# Modelo
class ResNetClickPredictor(nn.Module):
    def __init__(self):
        super(ResNetClickPredictor, self).__init__()
        self.backbone = models.resnet34(weights=None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, 2)

    def forward(self, x):
        return self.backbone(x)

# Transforms
transform = transforms.Compose([
    transforms.Resize((IMG_HEIGHT, IMG_WIDTH)),
    transforms.ToTensor(),
    transforms.Normalize([0.5]*3, [0.5]*3)
])

# Dados
dataset = TouchDataset(CSV_PATH, transform=transform)
val_size = int(len(dataset) * VAL_SPLIT)
train_size = len(dataset) - val_size
train_set, val_set = random_split(dataset, [train_size, val_size])
train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)
val_loader = DataLoader(val_set, batch_size=BATCH_SIZE, shuffle=False)

# Modelo
model = ResNetClickPredictor()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# Otimizador, perda e scheduler
optimizer = optim.Adam(model.parameters(), lr=LR)
criterion = nn.MSELoss()
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5, verbose=True)

# Log inicial
print(f"🚀 Iniciando treinamento em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"📦 Treino: {train_size} | Validação: {val_size} | Dispositivo: {device}")

# Arquivo de log
log_lines = ["epoch,train_loss,val_loss,lr\n"]

start_time = time.time()

# Loop de treino
for epoch in range(EPOCHS):
    model.train()
    train_loss = 0.0
    for images, coords in train_loader:
        images, coords = images.to(device), coords.to(device)
        optimizer.zero_grad()
        output = model(images)
        loss = criterion(output, coords)
        loss.backward()
        optimizer.step()
        train_loss += loss.item()

    train_loss /= len(train_loader)

    # Validação
    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for images, coords in val_loader:
            images, coords = images.to(device), coords.to(device)
            output = model(images)
            loss = criterion(output, coords)
            val_loss += loss.item()
    val_loss /= len(val_loader)

    # Ajuste do LR
    scheduler.step(val_loss)
    current_lr = optimizer.param_groups[0]['lr']

    print(f"📚 Época {epoch+1}/{EPOCHS} - Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | LR: {current_lr:.6f}")
    log_lines.append(f"{epoch+1},{train_loss:.6f},{val_loss:.6f},{current_lr:.8f}\n")

# Salvamento do modelo e log
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
torch.save(model.state_dict(), MODEL_PATH)
with open(LOG_PATH, "w") as f:
    f.writelines(log_lines)

print(f"\n✅ Modelo salvo em: {MODEL_PATH}")
print(f"📝 Log salvo em: {LOG_PATH}")
print(f"⏱️ Tempo total: {time.time() - start_time:.2f} segundos")