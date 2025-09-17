# Run/run_noia.py
import os
import platform
import subprocess
import pandas as pd
import time
import json
from datetime import datetime
from skimage.metrics import structural_similarity as ssim
import cv2

# =========================
# CONFIG
# =========================
if platform.system() == "Windows":
    ADB_PATH = r"C:\Users\Automation01\platform-tools\adb.exe"
else:
    ADB_PATH = "adb"

PAUSA_ENTRE_ACOES = 2  # segundos

# Caminho absoluto da raiz do projeto (este arquivo está em /Run)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

# =========================
# FUNÇÕES AUXILIARES
# =========================
def print_color(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{cores.get(color,'')}{msg}{cores['white']}", flush=True)

def executar_tap(x, y):
    comando = [ADB_PATH, "shell", "input", "tap", str(x), str(y)]
    subprocess.run(comando)
    print_color(f"👉 TAP em ({x},{y})", "green")

def executar_swipe(x1, y1, x2, y2, duracao=300):
    comando = [ADB_PATH, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duracao)]
    subprocess.run(comando)
    print_color(f"👉 SWIPE ({x1},{y1}) → ({x2},{y2}) [{duracao}ms]", "green")

def capturar_screenshot(pasta, nome):
    os.makedirs(pasta, exist_ok=True)
    caminho_local = os.path.join(pasta, nome)
    caminho_tmp = "/sdcard/tmp_shot.png"
    subprocess.run([ADB_PATH, "shell", "screencap", "-p", caminho_tmp])
    subprocess.run([ADB_PATH, "pull", caminho_tmp, caminho_local], stdout=subprocess.DEVNULL)
    subprocess.run([ADB_PATH, "shell", "rm", caminho_tmp])
    return caminho_local

def comparar_imagens(img1_path, img2_path):
    try:
        img1 = cv2.imread(img1_path)
        img2 = cv2.imread(img2_path)

        if img1 is None or img2 is None:
            return 0.0

        img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        score, _ = ssim(img1_gray, img2_gray, full=True)
        return float(score)
    except Exception:
        return 0.0

# =========================
# MAIN
# =========================
def main():
    print("📁 Execução Automática de Testes no Rádio via ADB")

    categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
    nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

    teste_dir = os.path.join(DATA_ROOT, categoria, nome_teste)
    dataset_path = os.path.join(teste_dir, "dataset.csv")
    frames_dir = os.path.join(teste_dir, "frames")
    resultados_dir = os.path.join(teste_dir, "resultados")
    log_path = os.path.join(teste_dir, "execucao_log.json")

    # Log de caminhos para diagnóstico
    print_color(f"\n🗂️ Dataset: {dataset_path}", "cyan")
    print_color(f"🗂️ Frames:  {frames_dir}", "cyan")
    print_color(f"🗂️ Result.: {resultados_dir}\n", "cyan")

    if not os.path.exists(dataset_path):
        print_color(f"❌ Arquivo dataset.csv não encontrado.\n   Esperado em: {dataset_path}\n   Dica: rode a opção 2 do menu (Processar dataset).", "red")
        return

    os.makedirs(resultados_dir, exist_ok=True)

    df = pd.read_csv(dataset_path)

    print_color(f"\n🎬 Executando {len(df)} ações do dataset...\n", "cyan")
    log = []

    i = 0
    while i < len(df):
        row = df.iloc[i]
        tipo = str(row.get("tipo", "tap")).lower()
        print_color(f"▶️ Ação {i+1}/{len(df)} ({tipo})", "white")

        if tipo == "tap":
            executar_tap(int(row["x"]), int(row["y"]))

        elif tipo == "swipe_inicio":
            # Usa a próxima linha como fim do swipe
            if i + 1 < len(df):
                proxima = df.iloc[i + 1]
                if str(proxima.get("tipo", "")).lower() == "swipe_fim":
                    executar_swipe(
                        int(row["x"]), int(row["y"]),
                        int(proxima["x"]), int(proxima["y"]),
                        int(row.get("duracao_ms", 300))
                    )
                    # Vamos também registrar um log adicional para o fim (opcional)
                else:
                    print_color("⚠️ swipe_inicio sem swipe_fim logo após — ignorado.", "yellow")
            else:
                print_color("⚠️ swipe_inicio é a última linha — ignorado.", "yellow")

        # Captura screenshot do resultado
        screenshot_nome = f"resultado_{i+1:02d}.png"
        screenshot_path = capturar_screenshot(resultados_dir, screenshot_nome)

        # Frame esperado (segue convenção frame_XX.png)
        esperado_rel = os.path.join("frames", f"frame_{i+1:02d}.png")
        esperado_abs = os.path.join(teste_dir, esperado_rel)

        similaridade = comparar_imagens(screenshot_path, esperado_abs)
        status = "✅ OK" if similaridade >= 0.85 else "❌ Divergente"

        print_color(f"🔎 Similaridade: {similaridade:.3f} → {status}", "cyan")

        log.append({
            "id": i+1,
            "timestamp": datetime.now().isoformat(),
            "acao": tipo,
            "coordenadas": row.to_dict(),
            "screenshot": os.path.join("resultados", screenshot_nome),
            "frame_esperado": esperado_rel,
            "similaridade": similaridade,
            "status": status
        })

        # Se era swipe_inicio e tratamos o swipe_fim, podemos pular o próximo índice na visualização
        if tipo == "swipe_inicio" and i + 1 < len(df) and str(df.iloc[i + 1].get("tipo", "")).lower() == "swipe_fim":
            # Ainda assim tiramos screenshot para a posição i+1? Aqui mantemos uma captura por linha do dataset.
            pass

        i += 1
        time.sleep(PAUSA_ENTRE_ACOES)

    # === SALVAR LOG ===
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4, ensure_ascii=False)

    print_color(f"\n✅ Execução finalizada. Log salvo em: {log_path}", "green")

if __name__ == "__main__":
    main()
