import os
import platform
import subprocess
import pandas as pd
import time
import sys
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

PAUSA_ENTRE_ACOES = 5  # segundos entre cada ação
SIMILARIDADE_HOME_OK = 0.85  # limite mínimo para considerar que está na Home

# Caminho absoluto da raiz do projeto (este arquivo está em /Run)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

# =========================
# FUNÇÕES AUXILIARES
# =========================
def adb_cmd(serial=None):
    """Retorna o comando adb com ou sem -s <serial>"""
    if serial:
        return [ADB_PATH, "-s", serial]
    return [ADB_PATH]

def print_color(msg, color="white"):
    """Imprime mensagens coloridas no terminal"""
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{cores.get(color,'')}{msg}{cores['white']}", flush=True)

def executar_tap(x, y, serial=None):
    """Executa um toque na tela via ADB"""
    comando = adb_cmd(serial) + ["shell", "input", "tap", str(x), str(y)]
    subprocess.run(comando)
    print_color(f"👉 TAP em ({x},{y})", "green")

def executar_long_press(x, y, duracao_ms=1000, serial=None):
    """Simula um toque longo (pressionar e segurar)."""
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x), str(y), str(x), str(y), str(int(duracao_ms))
    ]
    subprocess.run(comando)
    print_color(f"🖐️ LONG PRESS em ({x},{y}) por {duracao_ms/1000:.2f}s", "green")

def executar_swipe(x1, y1, x2, y2, duracao=300, serial=None):
    """Executa um swipe (arrastar) na tela via ADB"""
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x1), str(y1), str(x2), str(y2), str(duracao)
    ]
    subprocess.run(comando)
    print_color(f"👉 SWIPE ({x1},{y1}) → ({x2},{y2}) [{duracao}ms]", "green")

def capturar_screenshot(pasta, nome, serial=None):
    """Captura uma screenshot do dispositivo"""
    os.makedirs(pasta, exist_ok=True)
    caminho_local = os.path.join(pasta, nome)
    caminho_tmp = "/sdcard/tmp_shot.png"
    subprocess.run(adb_cmd(serial) + ["shell", "screencap", "-p", caminho_tmp])
    subprocess.run(adb_cmd(serial) + ["pull", caminho_tmp, caminho_local], stdout=subprocess.DEVNULL)
    subprocess.run(adb_cmd(serial) + ["shell", "rm", caminho_tmp])
    return caminho_local

def comparar_imagens(img1_path, img2_path):
    """Compara duas imagens e retorna o índice de similaridade (SSIM)"""
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

    # 🔹 Agora aceita argumentos OU modo interativo
    if len(sys.argv) >= 3:
        categoria = sys.argv[1].strip().lower().replace(" ", "_")
        nome_teste = sys.argv[2].strip().lower().replace(" ", "_")
    else:
        print_color("⚠️ Nenhum argumento fornecido. Entrando em modo interativo...\n", "yellow")
        categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
        nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

    # 🔹 Verifica se foi passado --serial
    serial = None
    if "--serial" in sys.argv:
        idx = sys.argv.index("--serial")
        if idx + 1 < len(sys.argv):
            serial = sys.argv[idx + 1]

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
        print_color(
            f"❌ Arquivo dataset.csv não encontrado.\n"
            f"   Esperado em: {dataset_path}\n"
            f"   Dica: rode a opção 'Processar Dataset' no menu.",
            "red"
        )
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

        # 🔸 Verifica se deve pausar (a cada ação)
        pause_path = os.path.join(BASE_DIR, "pause.flag")
        while os.path.exists(pause_path):
            print_color("⏸️ Execução pausada... aguardando retomada.", "yellow")
            time.sleep(2)

        inicio = time.time()

        # Executa ação
        if tipo == "tap":
            executar_tap(int(row["x"]), int(row["y"]), serial)

        elif tipo in ["swipe", "swipe_inicio"]:
            if i + 1 < len(df):
                proxima = df.iloc[i + 1]
                if str(proxima.get("tipo", "")).lower() in ["swipe_fim", "swipe"]:
                    executar_swipe(
                        int(row["x"]), int(row["y"]),
                        int(proxima.get("x2", proxima.get("x", 0))),
                        int(proxima.get("y2", proxima.get("y", 0))),
                        int(row.get("duracao_ms", 300)),
                        serial
                    )
                else:
                    print_color("⚠️ swipe sem fim válido — ignorado.", "yellow")
            else:
                print_color("⚠️ swipe é a última linha — ignorado.", "yellow")

        elif tipo == "long_press":
            duracao_press_ms = float(row.get("duracao_s", 1.0)) * 1000
            executar_long_press(int(row["x"]), int(row["y"]), duracao_press_ms, serial)
            print_color(f"🕒 Long press detectado por {duracao_press_ms/1000:.2f}s", "cyan")

        # Captura screenshot do resultado
        screenshot_nome = f"resultado_{i+1:02d}.png"
        screenshot_path = capturar_screenshot(resultados_dir, screenshot_nome, serial)

        esperado_rel = os.path.join("frames", f"frame_{i+1:02d}.png")
        esperado_abs = os.path.join(teste_dir, esperado_rel)

        similaridade = comparar_imagens(screenshot_path, esperado_abs)
        status = "✅ OK" if similaridade >= 0.85 else "❌ Divergente"

        fim = time.time()
        duracao = round(fim - inicio, 2)

        print_color(f"🔎 Similaridade: {similaridade:.3f} → {status} | ⏱️ {duracao:.2f}s", "cyan")

        log.append({
            "id": i+1,
            "timestamp": datetime.now().isoformat(),
            "acao": tipo,
            "coordenadas": row.to_dict(),
            "screenshot": os.path.join("resultados", screenshot_nome),
            "frame_esperado": esperado_rel,
            "similaridade": similaridade,
            "status": status,
            "duracao": duracao
        })

        i += 1
        time.sleep(PAUSA_ENTRE_ACOES)


    # === SALVAR LOG ===
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4, ensure_ascii=False)

    print_color(f"\n✅ Execução finalizada. Log salvo em: {log_path}", "green")


if __name__ == "__main__":
    main()
