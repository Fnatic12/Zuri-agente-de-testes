import os
import cv2
import time
import subprocess
import pandas as pd
import numpy as np

# === CONFIGURAÇÕES GERAIS ===
ADB_PATH = "adb"
SCREENSHOT_REMOTE = "/sdcard/frame_tmp.png"
SCREENSHOT_LOCAL = "frame_current.png"
RESOLUCAO_RADIO = (1920, 1080)
SIMILARIDADE_MINIMA = 0.70
PAUSA_ENTRE_TENTATIVAS = 3  # segundos
PAUSA_APOS_CLIQUE = 3       # segundos
MAX_TENTATIVAS = 10

# === FUNÇÕES AUXILIARES ===
def take_screenshot(local_path):
    subprocess.run([ADB_PATH, "shell", "screencap", "-p", SCREENSHOT_REMOTE])
    subprocess.run([ADB_PATH, "pull", SCREENSHOT_REMOTE, local_path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([ADB_PATH, "shell", "rm", SCREENSHOT_REMOTE])

def compare_images(img1_path, img2_path, resize_dim=(300, 300)):
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None or img2 is None:
        return 0.0
    img1 = cv2.resize(img1, resize_dim)
    img2 = cv2.resize(img2, resize_dim)
    diff = cv2.absdiff(img1, img2)
    score = 1 - np.mean(diff) / 255
    return score

def tap_on_screen(x, y):
    subprocess.run([ADB_PATH, "shell", "input", "tap", str(x), str(y)])

def call_validator(path):
    if os.path.exists(path):
        print(f"\n🧪 Executando validator: {path}")
        os.system(f"python \"{path}\"")
    else:
        print("⚠️  Nenhum validator.py encontrado.")

# === EXECUÇÃO DO TESTE ===
def main():
    csv_path = input("📄 Caminho para o arquivo dataset.csv: ").strip()
    validator_path = os.path.join(os.path.dirname(csv_path), "validator.py")
    df = pd.read_csv(csv_path)

    print(f"\n🚦 Iniciando execução de {len(df)} passos\n")

    for idx, row in df.iterrows():
        image_path = row['image_path']
        x = float(row['x'])
        y = float(row['y'])

        print(f"🧠 Verificando frame {idx+1}/{len(df)}: {os.path.basename(image_path)}")

        match = False
        for tentativa in range(MAX_TENTATIVAS):
            take_screenshot(SCREENSHOT_LOCAL)
            similarity = compare_images(SCREENSHOT_LOCAL, image_path)

            print(f"🔍 Similaridade: {similarity:.4f}")
            if similarity >= SIMILARIDADE_MINIMA:
                abs_x = int(x * RESOLUCAO_RADIO[0])
                abs_y = int(y * RESOLUCAO_RADIO[1])
                tap_on_screen(abs_x, abs_y)
                print(f"✅ Clique executado: ({abs_x}, {abs_y})")
                time.sleep(PAUSA_APOS_CLIQUE)  # Espera após o clique
                match = True
                break
            else:
                time.sleep(PAUSA_ENTRE_TENTATIVAS)

        if not match:
            print(f"❌ Não foi possível reconhecer a tela para {image_path}")
            break

    print("\n🎯 Teste finalizado. Iniciando validação...")
    call_validator(validator_path)

if __name__ == "__main__":
    main()