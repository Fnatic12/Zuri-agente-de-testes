import os
import json
import subprocess
import platform
import time
from datetime import datetime

# === CONFIGURAÇÕES INICIAIS ===
if platform.system() == "Windows":
    ADB_PATH = r"C:\Users\Automation01\platform-tools\adb.exe"
else:
    ADB_PATH = "adb"

RESOLUCAO_ESPERADA = (1920, 1080)
PAUSA_ENTRE_ACOES = 1  # segundos

# === FUNÇÕES AUXILIARES ===

def print_color(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m"
    }
    print(f"{cores.get(color, '')}{msg}{cores['white']}")

def get_resolucao_dispositivo():
    cmd = [ADB_PATH, "shell", "wm", "size"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()
    if "Physical size:" in output:
        _, tamanho = output.split(": ")
        largura, altura = map(int, tamanho.strip().split("x"))
        return largura, altura
    return None

def capturar_screenshot(pasta, indice):
    nome_img = f"screenshot_{indice:02d}.png"
    caminho_local = os.path.join(pasta, nome_img)
    caminho_tmp = "/sdcard/tmp_shot.png"
    subprocess.run([ADB_PATH, "shell", "screencap", "-p", caminho_tmp])
    subprocess.run([ADB_PATH, "pull", caminho_tmp, caminho_local], stdout=subprocess.DEVNULL)
    subprocess.run([ADB_PATH, "shell", "rm", caminho_tmp])
    return nome_img

def executar_acao(acao):
    tipo = acao.get("tipo")

    if tipo == "tap":
        x = acao["x"]
        y = acao["y"]
        comando = [ADB_PATH, "shell", "input", "tap", str(x), str(y)]
        subprocess.run(comando)
        print_color(f"👉 TAP em ({x},{y})", "green")

    elif tipo == "swipe":
        x1 = acao["x1"]
        y1 = acao["y1"]
        x2 = acao["x2"]
        y2 = acao["y2"]
        duracao = acao.get("duracao_ms", 300)
        comando = [ADB_PATH, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duracao)]
        subprocess.run(comando)
        print_color(f"👉 SWIPE de ({x1},{y1}) até ({x2},{y2})", "green")

    else:
        print_color(f"⚠️ Tipo de ação desconhecido: {tipo}", "yellow")

# === ENTRADA DO USUÁRIO ===
print("📁 Execução Automática de Testes no Rádio via ADB")
categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

base_dir = os.path.join("Data", categoria, nome_teste)
json_path = os.path.join(base_dir, "json", "acoes.json")
log_path = os.path.join(base_dir, "execucao_log.json")
screenshots_dir = os.path.join(base_dir, "screenshots")
os.makedirs(screenshots_dir, exist_ok=True)

if not os.path.exists(json_path):
    print_color(f"❌ Arquivo de ações não encontrado: {json_path}", "red")
    exit()

# === VERIFICAÇÃO DE RESOLUÇÃO ===
resolucao = get_resolucao_dispositivo()
if resolucao and resolucao != RESOLUCAO_ESPERADA:
    print_color(f"⚠️ Resolução do dispositivo é {resolucao}, esperada era {RESOLUCAO_ESPERADA}", "yellow")
else:
    print_color(f"✅ Resolução confirmada: {resolucao}", "green")

with open(json_path, "r") as f:
    acoes = json.load(f)

print_color(f"\n🎬 Executando {len(acoes)} ações registradas...\n", "white")
log = []

for i, item in enumerate(acoes, start=1):
    acao = item["acao"]
    imagem = item.get("imagem", "")
    print_color(f"▶️ Ação {i}/{len(acoes)}:", "white")

    input("🕹️ Pressione ENTER para executar a ação...")

    executar_acao(acao)
    screenshot_nome = capturar_screenshot(screenshots_dir, i)

    log.append({
        "timestamp": datetime.now().isoformat(),
        "acao": acao,
        "imagem_usada": imagem,
        "screenshot_resultado": screenshot_nome
    })

    time.sleep(PAUSA_ENTRE_ACOES)

# === SALVAR LOG ===
with open(log_path, "w") as f:
    json.dump(log, f, indent=4)

print_color(f"\n✅ Execução finalizada. Log salvo em: {log_path}", "green")
