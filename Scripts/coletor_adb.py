import os
import cv2
import json
import subprocess
from datetime import datetime
import platform
import math

# === 1. CONFIGURAÇÃO INICIAL ===
if platform.system() == "Windows":
    ADB_PATH = r"C:\adb\platform-tools\adb"
else:
    ADB_PATH = "adb"

EVENT_DEVICE = "/dev/input/event0"
RESOLUCAO_RADIO = (1920, 1080)
LIMIAR_DISTANCIA_PX = 20  # abaixo disso considera toque

# === 2. INPUTS DO USUÁRIO ===
print("📂 Organização do Teste")
categoria = input("👉 Qual a categoria do teste? ").strip().lower().replace(" ", "_")
nome_teste = input("📝 Qual o nome do teste? ").strip().lower().replace(" ", "_")

base_dir = os.path.join("Data", categoria, nome_teste)
frames_dir = os.path.join(base_dir, "frames")
json_dir = os.path.join(base_dir, "json")
os.makedirs(frames_dir, exist_ok=True)
os.makedirs(json_dir, exist_ok=True)

json_path = os.path.join(json_dir, "acoes.json")
actions = []

# === 3. MONITORAMENTO DE EVENTOS ===
def monitor_eventos():
    proc = subprocess.Popen(
        [ADB_PATH, "shell", "getevent", "-lt", EVENT_DEVICE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        universal_newlines=True,
    )

    start_x, start_y = None, None
    end_x, end_y = None, None
    em_movimento = False

    while True:
        line = proc.stdout.readline()
        if not line:
            break

        if "ABS_MT_POSITION_X" in line:
            val = int(line.split()[-1], 16)
            if not em_movimento:
                start_x = val
            end_x = val

        elif "ABS_MT_POSITION_Y" in line:
            val = int(line.split()[-1], 16)
            if not em_movimento:
                start_y = val
            end_y = val

        elif "SYN_REPORT" in line and start_x is not None and start_y is not None:
            em_movimento = True
            if end_x is None or end_y is None:
                continue

            # Calcular distância do movimento
            dist = math.hypot(end_x - start_x, end_y - start_y)

            timestamp = datetime.now()
            ts_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")
            img_name = f"frame_{ts_str}.png"
            img_path = os.path.join(frames_dir, img_name)
            remote_path = "/sdcard/screencap_tmp.png"

            subprocess.run([ADB_PATH, "shell", "screencap", "-p", remote_path])
            subprocess.run([ADB_PATH, "pull", remote_path, img_path])
            subprocess.run([ADB_PATH, "shell", "rm", remote_path])

            img = cv2.imread(img_path)
            if img is None:
                print("❌ Erro ao carregar imagem. Pulando...")
                continue

            if dist < LIMIAR_DISTANCIA_PX:
                action = {
                    "tipo": "touch",
                    "x": end_x,
                    "y": end_y,
                    "resolucao": {"largura": RESOLUCAO_RADIO[0], "altura": RESOLUCAO_RADIO[1]}
                }
                print(f"✅ Toque registrado em ({end_x},{end_y})")
            else:
                action = {
                    "tipo": "drag",
                    "start": {"x": start_x, "y": start_y},
                    "end": {"x": end_x, "y": end_y},
                    "resolucao": {"largura": RESOLUCAO_RADIO[0], "altura": RESOLUCAO_RADIO[1]}
                }
                print(f"✅ Arrasto registrado: ({start_x},{start_y}) → ({end_x},{end_y})")

            actions.append({
                "imagem": img_name,
                "acao": action
            })

            with open(json_path, "w") as f:
                json.dump(actions, f, indent=4)

            # Reset para próxima ação
            start_x = start_y = end_x = end_y = None
            em_movimento = False

# === 4. EXECUÇÃO ===
print("\n📡 Coletor AUTOMÁTICO de toques via ADB iniciado")
print("👆 Toque ou arraste no rádio — tudo será registrado com print + coordenada")
print("🔚 Pressione CTRL+C para encerrar\n")

try:
    monitor_eventos()
except KeyboardInterrupt:
    print("\n🛑 Coleta finalizada manualmente.")
    with open(json_path, "w") as f:
        json.dump(actions, f, indent=4)
    print(f"💾 {len(actions)} ações salvas em: {json_path}")
