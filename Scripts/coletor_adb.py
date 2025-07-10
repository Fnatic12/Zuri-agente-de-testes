import os
import cv2
import time
import subprocess
import pandas as pd
import numpy as np
import json
from datetime import datetime

# === CONFIGURAÇÕES GERAIS ===
ADB_PATH = "adb"
SCREENSHOT_REMOTE = "/sdcard/frame_tmp.png"
SCREENSHOT_LOCAL = "frame_current.png"
RESOLUCAO_ATUAL = (1920, 1080)  # resolução do rádio no momento do teste
SIMILARIDADE_MINIMA = 0.70
PAUSA_ENTRE_TENTATIVAS = 3
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

def resolver_coordenadas(orig, resolucao_origem, resolucao_destino):
    escala_x = resolucao_destino[0] / resolucao_origem[0]
    escala_y = resolucao_destino[1] / resolucao_origem[1]
    return int(orig[0] * escala_x), int(orig[1] * escala_y)

def tap_on_screen(x, y):
    subprocess.run([ADB_PATH, "shell", "input", "tap", str(x), str(y)])

def swipe_screen(x0, y0, x1, y1):
    subprocess.run([ADB_PATH, "shell", "input", "swipe",
                    str(x0), str(y0), str(x1), str(y1), "300"])

def call_validator(path):
    if os.path.exists(path):
        print(f"\n🧪 Executando validator: {path}")
        os.system(f"python {path}")
    else:
        print("⚠️  Nenhum validator.py encontrado.")

def listar_testes(data_root="Data"):
    testes = []
    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if os.path.isdir(cat_path):
            for nome_teste in os.listdir(cat_path):
                teste_path = os.path.join(cat_path, nome_teste)
                if os.path.isdir(teste_path):
                    testes.append((f"{categoria}/{nome_teste}", teste_path))
    return testes

# === EXECUÇÃO DO TESTE ===
def main():
    print("\n📂 Testes disponíveis:")
    testes = listar_testes()

    if not testes:
        print("❌ Nenhum teste encontrado em 'Data/'.")
        return

    for i, (nome, _) in enumerate(testes):
        print(f"{i + 1}. {nome}")

    while True:
        try:
            opcao = int(input("\n🟢 Selecione o número do teste que deseja executar: "))
            if 1 <= opcao <= len(testes):
                break
            else:
                print("❌ Opção inválida.")
        except ValueError:
            print("❌ Digite um número válido.")

    nome_teste, base_path = testes[opcao - 1]
    json_path = os.path.join(base_path, "json", "acoes.json")
    validator_path = os.path.join(base_path, "validator.py")

    with open(json_path, "r") as f:
        acoes = json.load(f)

    print(f"\n🚦 Executando {len(acoes)} ações automatizadas do teste: {nome_teste}\n")

    log_execucao = []

    for idx, acao in enumerate(acoes):
        img_ref_path = os.path.join(base_path, "frames", acao["imagem"])
        tipo = acao["acao"]["tipo"]
        resolucao_original = (
            acao["acao"]["resolucao"]["largura"],
            acao["acao"]["resolucao"]["altura"]
        )
        erro = None
        timestamp_inicio = datetime.now()

        for tentativa in range(MAX_TENTATIVAS):
            take_screenshot(SCREENSHOT_LOCAL)
            similarity = compare_images(SCREENSHOT_LOCAL, img_ref_path)
            print(f"🔍 Similaridade: {similarity:.4f} (tentativa {tentativa+1})")
            if similarity >= SIMILARIDADE_MINIMA:
                break
            time.sleep(PAUSA_ENTRE_TENTATIVAS)
        else:
            erro = f"Similaridade abaixo do mínimo ({SIMILARIDADE_MINIMA})"
            print(f"❌ {erro}")

        if not erro:
            if tipo == "touch":
                orig_x = acao["acao"]["x"]
                orig_y = acao["acao"]["y"]
                x, y = resolver_coordenadas((orig_x, orig_y), resolucao_original, RESOLUCAO_ATUAL)
                tap_on_screen(x, y)
                print(f"✅ Clique executado: ({x}, {y})")
                coordenadas = (x, y)
            elif tipo == "drag":
                start_orig = acao["acao"]["start"]
                end_orig = acao["acao"]["end"]
                x0, y0 = resolver_coordenadas((start_orig["x"], start_orig["y"]), resolucao_original, RESOLUCAO_ATUAL)
                x1, y1 = resolver_coordenadas((end_orig["x"], end_orig["y"]), resolucao_original, RESOLUCAO_ATUAL)
                swipe_screen(x0, y0, x1, y1)
                print(f"✅ Arrasto executado: ({x0}, {y0}) → ({x1}, {y1})")
                coordenadas = (x0, y0, x1, y1)
            else:
                coordenadas = None
        else:
            coordenadas = None

        timestamp_fim = datetime.now()

        log_execucao.append({
            "indice": idx,
            "tipo": tipo,
            "coordenadas": coordenadas,
            "imagem_referencia": img_ref_path,
            "similaridade_final": similarity,
            "timestamp_inicio": timestamp_inicio.isoformat(),
            "timestamp_fim": timestamp_fim.isoformat(),
            "erro": erro
        })

        time.sleep(3)

    print("\n🌟 Teste finalizado. Iniciando validação...")
    call_validator(validator_path)

    # Salvar log de execução
    log_path = os.path.join(base_path, "execucao_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_execucao, f, indent=4, ensure_ascii=False, default=str)
    print(f"📁 Log salvo em: {log_path}")

if __name__ == "__main__":
    main()
