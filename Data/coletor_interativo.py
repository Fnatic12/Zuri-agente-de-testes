import os
import cv2
import json
import subprocess
from datetime import datetime
import platform
import shutil

# === 1. CONFIGURAÇÃO INICIAL ===
if platform.system() == "Windows":
    ADB_PATH = r"C:\\adb\\platform-tools\\adb"
else:
    ADB_PATH = "adb"

EVENT_DEVICE = "/dev/input/event3"
RESOLUCAO_RADIO = (1920, 1080)

# === 2. INPUT DO USUÁRIO ===
categoria = input("Categoria do teste (ex: bluetooth, wifi): ").lower().strip()
nome_teste = input("Nome do teste (ex: teste_2_bt): ").lower().strip().replace(" ", "_")

# === 3. CRIAÇÃO DE ESTRUTURA DE PASTAS ===
base_dir = os.path.join("tests", categoria, nome_teste)
frames_dir = os.path.join(base_dir, "frames")
json_dir = os.path.join(base_dir, "json")
os.makedirs(frames_dir, exist_ok=True)
os.makedirs(json_dir, exist_ok=True)

json_path = os.path.join(json_dir, "acoes.json")
actions = []

print("\n📡 Coletor INICIADO. Toque na tela para registrar coordenadas e screenshot.")
print("🧠 Pasta de destino: ", base_dir)
print("🔚 Pressione CTRL+C para encerrar\n")

# === 4. LOOP PRINCIPAL DE COLETA ===
def monitor_eventos():
    proc = subprocess.Popen(
        [ADB_PATH, "shell", "getevent", "-lt", EVENT_DEVICE],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )

    current_x, current_y = None, None

    for line in proc.stdout:
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

# === 5. EXECUÇÃO ===
try:
    monitor_eventos()
except KeyboardInterrupt:
    print("\n🛑 Coleta finalizada manualmente.")
    with open(json_path, "w") as f:
        json.dump(actions, f, indent=4)
    print(f"💾 {len(actions)} ações salvas em: {json_path}")

    # === 6. Pergunta se usuário deseja salvar expected_frame.png ===
    expected_frame_path = os.path.join(base_dir, "expected_frame.png")
    ultima_imagem = actions[-1]["imagem"] if actions else None

    if ultima_imagem:
        resposta = input("\n🖼️ Deseja salvar a última imagem como expected_frame.png para validação? (s/n): ").strip().lower()
        if resposta == "s":
            origem = os.path.join(frames_dir, ultima_imagem)
            shutil.copy(origem, expected_frame_path)
            print(f"✅ expected_frame.png salvo em: {expected_frame_path}")