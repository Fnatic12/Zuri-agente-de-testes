import os
import json
from datetime import datetime
from math import hypot

# === CONFIGURAÇÃO ===
TOLERANCIA_PIXELS = 15  # margem de erro permitida para coordenadas

print("📁 Avaliador Automático de Execução")
categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

base_dir = os.path.join("Data", categoria, nome_teste)
acoes_path = os.path.join(base_dir, "json", "acoes.json")
log_path = os.path.join(base_dir, "execucao_log.json")
relatorio_path = os.path.join(base_dir, "avaliacao_resultado.json")

# === VERIFICAÇÃO DE ARQUIVOS ===
if not os.path.exists(acoes_path):
    print("❌ Ações esperadas não encontradas:", acoes_path)
    exit()
if not os.path.exists(log_path):
    print("❌ Log de execução não encontrado:", log_path)
    exit()

with open(acoes_path, "r") as f:
    acoes_esperadas = json.load(f)
with open(log_path, "r") as f:
    acoes_executadas = json.load(f)

# === AVALIAÇÃO ===
divergencias = []
acertos = 0
total = min(len(acoes_esperadas), len(acoes_executadas))

for i in range(total):
    esperada = acoes_esperadas[i]["acao"]
    executada = acoes_executadas[i]["acao"]

    tipo_ok = esperada["tipo"] == executada["tipo"]
    coords_ok = False

    if esperada["tipo"] == "tap":
        dist = hypot(esperada["x"] - executada["x"], esperada["y"] - executada["y"])
        coords_ok = dist <= TOLERANCIA_PIXELS

    elif esperada["tipo"] == "swipe":
        dist_ini = hypot(esperada["x1"] - executada["x1"], esperada["y1"] - executada["y1"])
        dist_fim = hypot(esperada["x2"] - executada["x2"], esperada["y2"] - executada["y2"])
        coords_ok = dist_ini <= TOLERANCIA_PIXELS and dist_fim <= TOLERANCIA_PIXELS

    if tipo_ok and coords_ok:
        acertos += 1
    else:
        divergencias.append({
            "indice": i + 1,
            "esperada": esperada,
            "executada": executada,
            "motivo": "Tipo diferente" if not tipo_ok else "Coordenadas fora da margem"
        })

# === RESULTADO FINAL ===
precisao = acertos / total * 100 if total > 0 else 0
aprovado = precisao >= 85  # limiar mínimo para aprovação

resultado = {
    "teste": nome_teste,
    "categoria": categoria,
    "data": datetime.now().isoformat(),
    "total_acoes": total,
    "acertos": acertos,
    "falhas": len(divergencias),
    "precisao_percentual": round(precisao, 2),
    "resultado": "APROVADO" if aprovado else "REPROVADO",
    "divergencias": divergencias
}

with open(relatorio_path, "w") as f:
    json.dump(resultado, f, indent=4)

# === IMPRESSÃO NO TERMINAL ===
print("\n📊 Avaliação Concluída")
print(f"✅ Ações corretas: {acertos}/{total}")
print(f"❌ Falhas: {len(divergencias)}")
print(f"🎯 Precisão: {round(precisao, 2)}%")
print(f"\n🏁 Resultado final: {'✅ APROVADO' if aprovado else '❌ REPROVADO'}")
print(f"📄 Relatório salvo em: {relatorio_path}")
