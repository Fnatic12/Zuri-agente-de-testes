import os
import json
from datetime import datetime
from math import hypot
import cv2
import numpy as np

# === CONFIGURAÇÃO ===
TOLERANCIA_PIXELS = 15   # margem de erro para coordenadas
PRECISAO_MINIMA = 85     # % mínima para aprovação
SIMILARIDADE_MINIMA = 0.75  # limiar SSIM-like para tela final

# === FUNÇÕES AUXILIARES ===
def compare_images(img1_path, img2_path, resize_dim=(400, 400)):
    """Compara duas imagens com base em diferença média normalizada"""
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None or img2 is None:
        return 0.0
    img1 = cv2.resize(img1, resize_dim)
    img2 = cv2.resize(img2, resize_dim)
    diff = cv2.absdiff(img1, img2)
    score = 1 - np.mean(diff) / 255
    return float(score)

# === EXECUÇÃO ===
print("📁 Avaliador Automático de Execução")
categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

base_dir = os.path.join("Data", categoria, nome_teste)
acoes_path = os.path.join(base_dir, "json", "acoes.json")
log_path = os.path.join(base_dir, "execucao_log.json")
relatorio_path = os.path.join(base_dir, "avaliacao_resultado.json")

if not os.path.exists(acoes_path):
    print("❌ Ações esperadas não encontradas:", acoes_path)
    exit()
if not os.path.exists(log_path):
    print("❌ Log de execução não encontrado:", log_path)
    exit()

with open(acoes_path, "r") as f:
    conteudo_esperado = json.load(f)
with open(log_path, "r") as f:
    conteudo_execucao = json.load(f)

acoes_esperadas = conteudo_esperado["acoes"] if isinstance(conteudo_esperado, dict) else conteudo_esperado
acoes_executadas = conteudo_execucao.get("acoes_executadas", conteudo_execucao)

# === AVALIAÇÃO AÇÕES ===
divergencias = []
acertos = 0
total = min(len(acoes_esperadas), len(acoes_executadas))

for i in range(total):
    esperada = acoes_esperadas[i]["acao"]
    executada = acoes_executadas[i].get("acao", acoes_executadas[i])  # compatibilidade
    resultado_exec = acoes_executadas[i].get("resultado_exec", {})

    # Tipo da ação
    tipo_ok = esperada.get("tipo") == executada.get("tipo")

    # Coordenadas
    coords_ok = False
    if esperada.get("tipo") in ["tap", "touch"]:
        dist = hypot(esperada.get("x", 0) - executada.get("x", 0),
                     esperada.get("y", 0) - executada.get("y", 0))
        coords_ok = dist <= TOLERANCIA_PIXELS
    elif esperada.get("tipo") in ["swipe", "drag"]:
        if "x1" in esperada:
            dist_ini = hypot(esperada["x1"] - executada.get("x1", 0),
                             esperada["y1"] - executada.get("y1", 0))
            dist_fim = hypot(esperada["x2"] - executada.get("x2", 0),
                             esperada["y2"] - executada.get("y2", 0))
            coords_ok = dist_ini <= TOLERANCIA_PIXELS and dist_fim <= TOLERANCIA_PIXELS

    # Validação visual por ROI (se houver)
    valida_ok = None
    if esperada.get("valida"):
        valida_ok = resultado_exec.get("valido", False)

    if tipo_ok and coords_ok and (valida_ok is not False):
        acertos += 1
    else:
        motivo = []
        if not tipo_ok:
            motivo.append("Tipo diferente")
        if not coords_ok:
            motivo.append("Coordenadas fora da margem")
        if valida_ok is False:
            motivo.append("Falha na validação (ROI/cor)")
        if resultado_exec.get("erro"):
            motivo.append(f"Erro execução: {resultado_exec['erro']}")

        divergencias.append({
            "indice": i + 1,
            "esperada": esperada,
            "executada": executada,
            "resultado_exec": resultado_exec,
            "motivo": ", ".join(motivo) if motivo else "Desconhecido"
        })

precisao = acertos / total * 100 if total > 0 else 0
aprovado = precisao >= PRECISAO_MINIMA

# === VALIDAÇÃO FINAL (TELA) ===
resultado_final = {"comparacao": None, "resultado": "não verificado"}
if "resultado_esperado" in conteudo_esperado and "validacao_final" in conteudo_execucao:
    img_esperada = os.path.join(base_dir, conteudo_esperado["resultado_esperado"])
    img_exec = conteudo_execucao["validacao_final"]["screenshot"]
    similaridade = compare_images(img_esperada, img_exec)
    ok_final = similaridade >= SIMILARIDADE_MINIMA
    resultado_final = {
        "esperada": img_esperada,
        "obtida": img_exec,
        "similaridade": round(similaridade, 3),
        "resultado": "ok" if ok_final else "falha"
    }
    if not ok_final:
        aprovado = False  # reprova global

# === RESULTADO FINAL ===
resultado = {
    "teste": nome_teste,
    "categoria": categoria,
    "data": datetime.now().isoformat(),
    "total_acoes": total,
    "acertos": acertos,
    "falhas": len(divergencias),
    "precisao_percentual": round(precisao, 2),
    "resultado_final": "APROVADO" if aprovado else "REPROVADO",
    "divergencias": divergencias,
    "validacao_final": resultado_final
}

with open(relatorio_path, "w", encoding="utf-8") as f:
    json.dump(resultado, f, indent=4, ensure_ascii=False)

# === PRINT RESUMO ===
print("\n📊 Avaliação Concluída")
print(f"✅ Ações corretas: {acertos}/{total}")
print(f"❌ Falhas: {len(divergencias)}")
print(f"🎯 Precisão: {round(precisao, 2)}%")
if resultado_final["resultado"] != "não verificado":
    print(f"🖼️ Validação final da tela: {resultado_final['resultado']} (similaridade {resultado_final['similaridade']})")
print(f"\n🏁 Resultado: {'✅ APROVADO' if aprovado else '❌ REPROVADO'}")
print(f"📄 Relatório salvo em: {relatorio_path}")
