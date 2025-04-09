import os
import cv2
import numpy as np
import subprocess

# === CONFIGURAÇÕES ===
ADB_PATH = "adb"
REMOTE_PATH = "/sdcard/frame_validator.png"
LOCAL_PATH = "frame_val_result.png"
EXPECTED_FRAME = "expected_frame.png"
SIMILARIDADE_MINIMA = 0.60  # Ajustável conforme necessidade
RESIZE_DIMS = (300, 300)
    
# === CAPTURA A TELA ATUAL DO DISPOSITIVO ===
def take_screenshot():
    try:
        subprocess.run([ADB_PATH, "shell", "screencap", "-p", REMOTE_PATH], check=True)
        subprocess.run([ADB_PATH, "pull", REMOTE_PATH, LOCAL_PATH],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run([ADB_PATH, "shell", "rm", REMOTE_PATH], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao capturar screenshot: {e}")
        exit(1)

# === COMPARAÇÃO ENTRE IMAGENS ===
def compare_images(img1_path, img2_path, resize_dim):
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None or img2 is None:
        print("❌ Imagens não carregadas corretamente.")
        return 0.0
    img1 = cv2.resize(img1, resize_dim)
    img2 = cv2.resize(img2, resize_dim)
    diff = cv2.absdiff(img1, img2)
    score = 1 - np.mean(diff) / 255
    return score

# === EXECUÇÃO PRINCIPAL ===
def main():
    print("📸 Capturando tela atual para validação...")
    
    if not os.path.exists(EXPECTED_FRAME):
        print("❌ Arquivo 'expected_frame.png' não encontrado no diretório atual.")
        return

    take_screenshot()
    similarity = compare_images(LOCAL_PATH, EXPECTED_FRAME, RESIZE_DIMS)
    print(f"📊 Similaridade com imagem esperada: {similarity:.4f}")

    if similarity >= SIMILARIDADE_MINIMA:
        print("✅ Teste validado com SUCESSO!")
    else:
        print("❌ Validação FALHOU! Tela final diferente da esperada.")

if __name__ == "__main__":
    main()