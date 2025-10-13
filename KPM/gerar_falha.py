import os
import json
import csv
from datetime import datetime

# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "Data")
RELATORIOS_DIR = os.path.join(BASE_DIR, "Relatorios_Falhas")

os.makedirs(RELATORIOS_DIR, exist_ok=True)

# =========================
# FUNÇÕES AUXILIARES
# =========================
def printc(msg, color="white"):
    cores = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{cores.get(color,'')}{msg}{cores['white']}")


def encontrar_logs_execucao():
    """Percorre Data/*/*/ e encontra todos os execucao_log.json."""
    logs = []
    for categoria in os.listdir(DATA_DIR):
        cat_path = os.path.join(DATA_DIR, categoria)
        if not os.path.isdir(cat_path):
            continue
        for teste in os.listdir(cat_path):
            teste_path = os.path.join(cat_path, teste)
            log_path = os.path.join(teste_path, "execucao_log.json")
            if os.path.exists(log_path):
                logs.append((categoria, teste, log_path))
    return logs


def gerar_relatorio_falhas(categoria, teste, log_path):
    """Gera um arquivo .md e .csv com as falhas detectadas."""
    with open(log_path, "r", encoding="utf-8") as f:
        execucao = json.load(f)

    falhas = [a for a in execucao if "❌" in a.get("status", "") or a.get("similaridade", 1) < 0.85]

    if not falhas:
        printc(f"✅ Nenhuma falha encontrada em {categoria}/{teste}", "green")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{categoria}_{teste}_{timestamp}"
    md_path = os.path.join(RELATORIOS_DIR, f"{base_name}.md")
    csv_path = os.path.join(RELATORIOS_DIR, f"{base_name}.csv")

    # === Arquivo Markdown ===
    with open(md_path, "w", encoding="utf-8") as md:
        md.write(f"# 🧩 Falhas detectadas - {categoria}/{teste}\n")
        md.write(f"**Data de geração:** {datetime.now().isoformat()}\n\n")

        for i, f in enumerate(falhas, 1):
            md.write(f"## ⚠️ Falha {i}\n\n")
            md.write(f"**[1. Short Text]**\n")
            md.write(f"Desvio visual detectado (SSIM={f.get('similaridade', 0):.2f})\n\n")

            md.write(f"**[2. Precondition]**\n")
            md.write(f"Teste: `{categoria}/{teste}`\nDispositivo: [SERIAL_PLACEHOLDER]\n\n")

            md.write(f"**[3. Action]**\n")
            md.write(f"Ação {f.get('id')} - {f.get('acao','')}\nCoordenadas: {f.get('coordenadas','')}\n\n")

            md.write(f"**[4. Actual Result]**\n")
            md.write(f"{f.get('status','')} | Similaridade: {f.get('similaridade',0):.2f}\nScreenshot: {f.get('screenshot','')}\n\n")

            md.write(f"**[5. Expected Result]**\n")
            md.write("UI aligned, localized and matching reference (SSIM ≥ 0.85)\n\n")

            md.write(f"**[6. Recovery]**\n")
            md.write("ZURI continuou execução automaticamente.\n\n")

            md.write(f"**[7. Observation]**\n")
            md.write("Reproduz 100% sob mesmas condições.\n\n")

            md.write(f"**[8. Log File / Trace]**\n")
            md.write(f"{log_path}\n\n")
            md.write("---\n\n")

    # === Arquivo CSV ===
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Short Text", "Precondition", "Action", "Actual Result",
            "Expected Result", "Recovery", "Observation", "Log File"
        ])

        for f in falhas:
            writer.writerow([
                f"Desvio visual detectado (SSIM={f.get('similaridade',0):.2f})",
                f"Teste: {categoria}/{teste}",
                f"Ação {f.get('id')} - {f.get('acao','')} ({f.get('coordenadas','')})",
                f"{f.get('status','')} | {f.get('screenshot','')}",
                "UI aligned (SSIM ≥ 0.85)",
                "Execução continuou automaticamente.",
                "Reproduz sob mesmas condições.",
                log_path
            ])

    printc(f"📝 Relatórios gerados:\n- {md_path}\n- {csv_path}", "yellow")
    return md_path, csv_path


def main():
    printc("🔍 Procurando execucao_log.json em Data/*/*/...", "cyan")
    logs = encontrar_logs_execucao()
    if not logs:
        printc("❌ Nenhum log de execução encontrado.", "red")
        return

    for cat, teste, log in logs:
        gerar_relatorio_falhas(cat, teste, log)

    printc("\n✅ Finalizado. Relatórios disponíveis em /Relatorios_Falhas", "green")


if __name__ == "__main__":
    main()
