import os
import platform
import subprocess
import pandas as pd
import threading
import time
import sys
import json
from datetime import datetime
from skimage.metrics import structural_similarity as ssim
import cv2
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

# ===== Locks multiplataforma (para escrita concorrente do status) =====
try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None

try:
    import fcntl  # Linux/Mac
except ImportError:
    fcntl = None

# =========================
# CONFIG
# =========================
if platform.system() == "Windows":
    # Ajuste este caminho se seu adb estiver em outro local
    ADB_PATH = r"C:\Users\Automation01\platform-tools\adb.exe"
else:
    ADB_PATH = "adb"

PAUSA_ENTRE_ACOES = 4              # segundos entre cada ação
SIMILARIDADE_HOME_OK = 0.85        # limite mínimo para considerar OK
ADB_TIMEOUT = 25                   # timeout padrão para chamadas ADB (seg)

# Caminho absoluto da raiz do projeto (este arquivo está em /Run)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

# Dicionário local de controle do tempo (por processo)
INICIO_EXECUCAO = {}

# =========================
# UTIL: Locks e escrita segura
# =========================
class LockedFile:
    """Context manager para lock de arquivo multiplataforma."""
    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        self.f = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, self.mode, encoding="utf-8")
        try:
            if msvcrt:
                msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)
            elif fcntl:
                fcntl.flock(self.f, fcntl.LOCK_EX)
        except Exception:
            # Em último caso segue sem lock (melhor do que travar)
            pass
        return self.f

    def __exit__(self, exc_type, exc, tb):
        try:
            if msvcrt:
                try:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            elif fcntl:
                try:
                    fcntl.flock(self.f, fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            self.f.close()


def atomic_write_json(path, data):
    """Escrita atômica de JSON (evita arquivo corrompido)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=os.path.dirname(path)) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


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


def run_subprocess(cmd, timeout=ADB_TIMEOUT, quiet=False):
    """Wrapper com timeout e verificação de falhas ADB."""
    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if "device '" in result.stderr and "not found" in result.stderr:
            print_color(f"❌ Dispositivo ADB não encontrado: {cmd}", "red")
            return None

        if result.returncode != 0 and not quiet:
            print_color(f"⚠️ Erro ADB: {result.stderr.strip()}", "yellow")

        return result
    except subprocess.TimeoutExpired:
        print_color(f"⏳ Timeout ao executar: {' '.join(cmd)}", "yellow")
    except FileNotFoundError:
        print_color(f"❌ Comando não encontrado: {cmd[0]}", "red")
    except Exception as e:
        print_color(f"⚠️ Erro inesperado: {e}", "red")
    return None


def ensure_adb():
    """Verifica ADB antes de iniciar; falha amigável se não encontrado."""
    if not ADB_PATH:
        print_color("❌ ADB_PATH não configurado.", "red")
        sys.exit(2)
    if not shutil_which(ADB_PATH):
        print_color(f"❌ ADB não encontrado em: {ADB_PATH}", "red")
        sys.exit(2)


def shutil_which(path):
    """Compatível com caminho absoluto no Windows; retorna path se existir."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    from shutil import which
    return which(path)


def executar_tap(x, y, serial=None):
    """Executa um toque na tela via ADB"""
    comando = adb_cmd(serial) + ["shell", "input", "tap", str(x), str(y)]
    result = run_subprocess(comando)
    if result:
        print_color(f"👉 TAP em ({x},{y})", "green")
    return result


def executar_long_press(x, y, duracao_ms=1000, serial=None):
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x), str(y), str(x), str(y), str(int(duracao_ms))
    ]
    result = run_subprocess(comando)
    if result:
        print_color(f"🖐️ LONG PRESS em ({x},{y}) por {duracao_ms/1000:.2f}s", "green")
    return result


def executar_swipe(x1, y1, x2, y2, duracao=300, serial=None):
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x1), str(y1), str(x2), str(y2), str(duracao)
    ]
    result = run_subprocess(comando)
    if result:
        print_color(f"👉 SWIPE ({x1},{y1}) → ({x2},{y2}) [{duracao}ms]", "green")
    return result


def capturar_screenshot(pasta, nome, serial=None):
    """Captura uma screenshot do dispositivo e valida o resultado"""
    os.makedirs(pasta, exist_ok=True)
    caminho_local = os.path.join(pasta, nome)
    caminho_tmp = "/sdcard/tmp_shot.png"

    res1 = run_subprocess(adb_cmd(serial) + ["shell", "screencap", "-p", caminho_tmp])
    if res1 is None:
        print_color("❌ Falha ao capturar screenshot no dispositivo.", "red")
        return None

    res2 = run_subprocess(adb_cmd(serial) + ["pull", caminho_tmp, caminho_local], quiet=True)
    if res2 is None:
        print_color("⚠️ Falha ao transferir screenshot para o PC.", "yellow")
        return None

    run_subprocess(adb_cmd(serial) + ["shell", "rm", caminho_tmp], quiet=True)

    if not os.path.exists(caminho_local):
        print_color(f"⚠️ Screenshot não encontrada em {caminho_local}", "yellow")
        return None

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
# STATUS DAS BANCADAS (padronizado)
# =========================
STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data", "status_bancadas.json")
INICIO_EXECUCAO = {}

def _bancada_key_from_serial(serial):
    """Retorna a chave de identificação da bancada."""
    if not serial or str(serial).strip() == "":
        return "2801761952320038"  # fallback seguro
    return str(serial)

def carregar_status(serial=None):
    """Carrega status da bancada específica (ou global, se serial for None)."""
    if serial:
        status_file = os.path.join(DATA_ROOT, f"status_{serial}.json")
    else:
        status_file = os.path.join(DATA_ROOT, "status_bancadas.json")

    if not os.path.exists(status_file):
        return {}

    try:
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

status_lock = threading.Lock()  # adiciona lock global

def salvar_status(status, serial=None):
    """
    Salva status da execução de forma segura e isolada por bancada.
    Se 'serial' for fornecido, cria um arquivo status_<serial>.json.
    """
    try:
        with status_lock:
            if serial:
                status_file = os.path.join(DATA_ROOT, f"status_{serial}.json")
            else:
                status_file = os.path.join(DATA_ROOT, "status_bancadas.json")

            tmp_path = status_file + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, status_file)
    except Exception as e:
        print(f"⚠️ Erro ao salvar status: {e}")

def inicializar_status_bancada(bancada_key, teste_nome, total_acoes):
    status = carregar_status()
    INICIO_EXECUCAO[bancada_key] = time.time()
    status[bancada_key] = {
        "teste": teste_nome,
        "status": "executando",
        "acoes_totais": int(total_acoes),
        "acoes_executadas": 0,
        "progresso": 0.0,
        "ultima_acao": "-",
        "tempo_decorrido_s": 0.0,
        "inicio": datetime.now().isoformat()
    }
    salvar_status(status, serial=bancada_key)

def atualizar_status_bancada(bancada_key, teste_nome, total_acoes, executadas, ultima_acao):
    status = carregar_status()
    inicio = INICIO_EXECUCAO.get(bancada_key, time.time())
    tempo_decorrido = time.time() - inicio
    progresso = round(((executadas or 0) / max(total_acoes, 1)) * 100, 1)
    status[bancada_key] = {
        "teste": teste_nome,
        "status": "executando",
        "acoes_totais": int(total_acoes),
        "acoes_executadas": int(executadas),
        "progresso": progresso,
        "ultima_acao": str(ultima_acao),
        "tempo_decorrido_s": float(tempo_decorrido),
        "inicio": status.get(bancada_key, {}).get("inicio")
    }
    salvar_status(status, serial=bancada_key)

def finalizar_status_bancada(bancada_key, resultado="finalizado"):
    status = carregar_status()
    if bancada_key in status:
        status[bancada_key]["status"] = resultado
        status[bancada_key]["fim"] = datetime.now().isoformat()
    else:
        status[bancada_key] = {"status": resultado, "fim": datetime.now().isoformat()}
    salvar_status(status, serial=bancada_key)

def reverse_tester_actions(categoria, nome_teste, serial=None):
    """
    Executa o caminho inverso das ações registradas em acoes.json,
    simulando uma execução normal (com pausas e logs).
    """
    json_path = os.path.join(DATA_ROOT, categoria, nome_teste, "json", "acoes.json")
    if not os.path.exists(json_path):
        print_color(f"⚠️ Nenhum JSON de ações encontrado para {categoria}/{nome_teste}.", "yellow")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    actions = data.get("acoes", [])
    if not actions:
        print_color("⚠️ Nenhuma ação registrada para reverter.", "yellow")
        return

    print_color(f"\n♻️ Iniciando reset comportamental ({len(actions)} ações)...", "cyan")

    total = len(actions)
    for i, act in enumerate(reversed(actions)):
        a = act.get("acao", {})
        tipo = a.get("tipo")

        inicio = time.time()
        print_color(f"↩️ Reset Ação {i+1}/{total} ({tipo})", "white")

        if tipo == "tap":
            run_subprocess(adb_cmd(serial) + ["shell", "input", "tap", str(a["x"]), str(a["y"])])
            print_color(f"↩️ TAP reverso em ({a['x']},{a['y']})", "green")

        elif tipo == "swipe":
            run_subprocess(adb_cmd(serial) + [
                "shell", "input", "swipe",
                str(a["x2"]), str(a["y2"]),
                str(a["x1"]), str(a["y1"]),
                str(a.get("duracao_ms", 300))
            ])
            print_color(f"↩️ SWIPE reverso ({a['x2']},{a['y2']})→({a['x1']},{a['y1']})", "green")

        elif tipo == "long_press":
            duracao = int(a.get("duracao_ms", 1000))
            run_subprocess(adb_cmd(serial) + [
                "shell", "input", "swipe",
                str(a["x"]), str(a["y"]), str(a["x"]), str(a["y"]), str(duracao)
            ])
            print_color(f"↩️ LONG PRESS revertido em ({a['x']},{a['y']}) por {duracao/1000:.1f}s", "green")

        fim = time.time()
        print_color(f"⏱️ Duração ação: {fim - inicio:.2f}s", "cyan")

        # 🔹 Captura opcional (pode comentar se quiser mais velocidade)
        # nome = f"reset_{i+1:02d}.png"
        # pasta_result = os.path.join(DATA_ROOT, categoria, nome_teste, "resultados_reset")
        # capturar_screenshot(pasta_result, nome, serial)

        # 🔹 Pausa entre ações (igual ao teste normal)
        time.sleep(PAUSA_ENTRE_ACOES)

    print_color("✅ Reset comportamental concluído. Estado restaurado.", "green")

# =========================
# MAIN
# =========================
def main():
    print("📁 Execução Automática de Testes no Rádio via ADB")

    # 🔹 Argumentos ou modo interativo
    if len(sys.argv) >= 3:
        categoria = sys.argv[1].strip().lower().replace(" ", "_")
        nome_teste = sys.argv[2].strip().lower().replace(" ", "_")
    else:
        print_color("⚠️ Nenhum argumento fornecido. Entrando em modo interativo...\n", "yellow")
        categoria = input("📂 Categoria do teste: ").strip().lower().replace(" ", "_")
        nome_teste = input("📝 Nome do teste: ").strip().lower().replace(" ", "_")

    # 🔹 Detecta modo reset
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "reset":
        if len(sys.argv) < 3:
            print_color("⚠️ Informe o nome do teste para resetar. Exemplo: python run_noia.py reset geral1", "yellow")
            return

        nome_teste = sys.argv[2].strip().lower().replace(" ", "_")

        # Detecta serial, se passado
        serial = None
        if "--serial" in sys.argv:
            idx = sys.argv.index("--serial")
            if idx + 1 < len(sys.argv):
                serial = sys.argv[idx + 1]

        if not serial:
            # Detecta automaticamente o primeiro dispositivo ADB conectado
            try:
                devices = subprocess.check_output([ADB_PATH, "devices"], text=True)
                lines = devices.strip().split("\n")[1:]
                serials = [l.split("\t")[0] for l in lines if "\tdevice" in l]
                serial = serials[0] if serials else None
            except Exception:
                serial = None

        if not serial:
            print_color("❌ Nenhum dispositivo ADB conectado. Conecte o rádio e tente novamente.", "red")
            return

        print_color(f"\n♻️ Iniciando reset comportamental do teste '{nome_teste}' (serial {serial})...\n", "cyan")
        reverse_tester_actions("geral", nome_teste, serial)
        print_color("✅ Reset concluído com sucesso!\n", "green")
        return

    # 🔹 Verifica se foi passado --serial
    serial = None
    if "--serial" in sys.argv:
        idx = sys.argv.index("--serial")
        if idx + 1 < len(sys.argv):
            serial = sys.argv[idx + 1]

    # 🔹 Garante que sempre exista uma bancada_key
    if not serial or serial.strip() == "":
        print_color("⚠️ Nenhum serial ADB detectado — atribuindo Bancada 1 (2801761952320038)", "yellow")
        serial = "2801761952320038"

    # ✅ Define identificador único da bancada (corrige o NameError)
    bancada_key = _bancada_key_from_serial(serial)

    # 🔍 Verifica se o dispositivo está conectado
    print_color("🔍 Verificando dispositivos ADB conectados...", "cyan")
    try:
        devices = subprocess.check_output([ADB_PATH, "devices"], text=True)
        if serial not in devices:
            print_color(f"❌ Dispositivo {serial} não encontrado. Conecte o rádio e tente novamente.", "red")
            finalizar_status_bancada(serial, "erro_adb")
            return
    except Exception as e:
        print_color(f"⚠️ Falha ao verificar dispositivos ADB: {e}", "red")
        finalizar_status_bancada(serial, "erro_adb")
        return

    teste_dir = os.path.join(DATA_ROOT, categoria, nome_teste)
    dataset_path = os.path.join(teste_dir, "dataset.csv")
    frames_dir = os.path.join(teste_dir, "frames")
    resultados_dir = os.path.join(teste_dir, "resultados")
    log_path = os.path.join(teste_dir, "execucao_log.json")

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
    try:
        df = pd.read_csv(dataset_path)
    except Exception as e:
        print_color(f"❌ Falha ao ler dataset.csv: {e}", "red")
        return

    total_acoes = len(df)
    print_color(f"\n🎬 Executando {total_acoes} ações do dataset...\n", "cyan")
    log = []

    # 🔹 Inicializa status
    inicializar_status_bancada(bancada_key, nome_teste, len(df))

    for i, row in df.iterrows():
        try:
            tipo = str(row.get("tipo", "tap")).lower()
        except Exception:
            tipo = "tap"

        print_color(f"▶️ Ação {i+1}/{total_acoes} ({tipo})", "white")

        # Pausa se necessário (auto-limpa se sobrou de execução anterior)
        pause_path = os.path.join(BASE_DIR, "pause.flag")
        if os.path.exists(pause_path):
            print_color("⚠️ Arquivo de pausa residual detectado — removendo para evitar travamento.", "yellow")
            try:
                os.remove(pause_path)
            except Exception as e:
                print_color(f"⚠️ Não foi possível remover pause.flag: {e}", "red")

        while os.path.exists(pause_path):
            print_color("⏸️ Execução pausada... aguardando retomada.", "yellow")
            time.sleep(2)

        inicio = time.time()

        # ===== Executa ação =====
        try:
            if tipo == "tap":
                res = executar_tap(int(row["x"]), int(row["y"]), serial)
                if res is None:
                    print_color("❌ Falha na execução do TAP — interrompendo teste.", "red")
                    finalizar_status_bancada(bancada_key, "erro_adb")
                    return


            elif tipo in ["swipe", "swipe_inicio"]:
                # Busca próximo registro com término do swipe
                x1, y1 = int(row.get("x", 0)), int(row.get("y", 0))
                dur = int(row.get("duracao_ms", 300))
                x2, y2 = None, None

                if i + 1 < len(df):
                    proxima = df.iloc[i + 1]
                    prox_tipo = str(proxima.get("tipo", "")).lower()
                    if prox_tipo in ["swipe_fim", "swipe"]:
                        x2 = int(proxima.get("x2", proxima.get("x", 0)))
                        y2 = int(proxima.get("y2", proxima.get("y", 0)))

                if x2 is not None and y2 is not None:
                    executar_swipe(x1, y1, x2, y2, duracao=dur, serial=serial)
                else:
                    print_color("⚠️ swipe sem fim válido — ignorado.", "yellow")

            elif tipo == "long_press":
                duracao_press_ms = float(row.get("duracao_s", 1.0)) * 1000
                executar_long_press(int(row["x"]), int(row["y"]), duracao_press_ms, serial)

            else:
                print_color(f"⚠️ Tipo de ação '{tipo}' não reconhecido — ignorado.", "yellow")

        except Exception as e:
            print_color(f"⚠️ Erro ao executar ação {i+1}: {e}", "red")

        # ===== Screenshot e Similaridade =====
        time.sleep(1)
        screenshot_nome = f"resultado_{i+1:02d}.png"
        screenshot_path = capturar_screenshot(resultados_dir, screenshot_nome, serial)

        esperado_rel = os.path.join("frames", f"frame_{i+1:02d}.png")
        esperado_abs = os.path.join(teste_dir, esperado_rel)

        similaridade = comparar_imagens(screenshot_path, esperado_abs)
        status_txt = "✅ OK" if similaridade >= SIMILARIDADE_HOME_OK else "❌ Divergente"

        fim = time.time()
        duracao = round(fim - inicio, 2)

        print_color(f"🔎 Similaridade: {similaridade:.3f} → {status_txt} | ⏱️ {duracao:.2f}s", "cyan")

        # Monta registro de log da ação
        registro = {
            "id": i + 1,
            "timestamp": datetime.now().isoformat(),
            "acao": tipo,
            "coordenadas": {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()},
            "screenshot": os.path.join("resultados", screenshot_nome),
            "frame_esperado": esperado_rel,
            "similaridade": similaridade,
            "status": status_txt,
            "duracao": duracao
        }
        log.append(registro)

        # 🔹 Atualiza status da bancada
        atualizar_status_bancada(bancada_key, nome_teste, total_acoes, i + 1, tipo)

        time.sleep(PAUSA_ENTRE_ACOES)

    # 🔹 Finaliza status
    try:
        finalizar_status_bancada(bancada_key, resultado="finalizado")
    except Exception as e:
        print_color(f"⚠️ Falha ao atualizar status final: {e}", "yellow")


    # === SALVAR LOG FINAL ===
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=4, ensure_ascii=False)
        print_color(f"\n✅ Execução finalizada. Log salvo em: {log_path}", "green")
        print_color(f"📊 Status atualizado em: Data/status_{bancada_key}.json", "cyan")
    except Exception as e:
        print_color(f"❌ Falha ao salvar log final: {e}", "red")

    # === RESET COMPORTAMENTAL ===
    try:
        print_color("\n⏳ Restaurando estado inicial (reset comportamental)...", "yellow")
        reverse_tester_actions(categoria, nome_teste, serial)
        print_color("✅ Ambiente restaurado com sucesso.\n", "green")
    except Exception as e:
        print_color(f"⚠️ Falha ao reverter ações: {e}", "red")

if __name__ == "__main__":
    main()
