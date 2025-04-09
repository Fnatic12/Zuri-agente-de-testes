import os
import cv2
import json
import subprocess
from datetime import datetime
from threading import Thread
import platform

# Caminho do ADB (ajustável por sistema)
if platform.system() == "Windows":
    ADB_PATH = r"C:\adb\platform-tools\adb"
else:
    ADB_PATH = "adb"

EVENT_DEVICE = "/dev/input/event3"
RESOLUCAO_RADIO = (1920, 1080)

# Diretórios
base_dir = "dados_treino_adb"
frames_dir = os.path.join(base_dir, "frames")
json_dir = os.path.join(base_dir, "json")
os.makedirs(frames_dir, exist_ok=True)
os.makedirs(json_dir, exist_ok=True)

# JSON
json_path = os.path.join(json_dir, "acoes.json")
actions = []

# Controle
running = True

def monitor_eventos():
    global running
    proc = subprocess.Popen(
        [ADB_PATH, "shell", "getevent", "-lt", EVENT_DEVICE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )

    current_x, current_y = None, None

    for line in proc.stdout:
        if not running:
            break

        if "ABS_MT_POSITION_X" in line:
            current_x = int(line.split()[-1], 16)

        elif "ABS_MT_POSITION_Y" in line:
            current_y = int(line.split()[-1], 16)

        elif "SYN_REPORT" in line and current_x is not None and current_y is not None:
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

            actions.append({
                "imagem": img_name,
                "acao": {
                    "tipo": "touch",
                    "x": current_x,
                    "y": current_y,
                    "resolucao": {
                        "largura": RESOLUCAO_RADIO[0],
                        "altura": RESOLUCAO_RADIO[1]
                    }
                }
            })

            with open(json_path, "w") as f:
                json.dump(actions, f, indent=4)

            print(f"✅ Registrado: {img_name} em ({current_x},{current_y})")

            current_x, current_y = None, None

print("\n📡 Coletor AUTOMÁTICO de toques via ADB iniciado")
print("👆 Toque no rádio — todos os toques e arrastos serão registrados com print + coordenada")
print("🔚 Pressione CTRL+C para encerrar\n")

try:
    thread = Thread(target=monitor_eventos)
    thread.start()
    thread.join()
except KeyboardInterrupt:
    running = False
    print("\n🛑 Coleta finalizada manualmente.")
    with open(json_path, "w") as f:
        json.dump(actions, f, indent=4)
    print(f"💾 {len(actions)} ações salvas em: {json_path}")