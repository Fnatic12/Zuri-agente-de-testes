import os
import platform
import subprocess
import pandas as pd
import threading
import time
import sys
import json
import csv
import re
from datetime import datetime
from skimage.metrics import structural_similarity as ssim
import cv2
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.shared.adb_utils import resolve_adb_path

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
ADB_PATH = resolve_adb_path()

PAUSA_ENTRE_ACOES = 1.7              # segundos entre cada aÃ§Ã£o (mais lento)
ESPERA_POS_ACAO_S = 1.9              # espera apos cada acao antes do screenshot
SIMILARIDADE_HOME_OK = 0.85        # limite mÃ­nimo para considerar OK
ADB_TIMEOUT = 25                   # timeout padrÃ£o para chamadas ADB (seg)
LOG_CAPTURE_STEP_WAIT_S = 1.1
LOG_CAPTURE_SEQUENCE_FILENAMES = (
    "failure_log_sequence.csv",
    "failure_log_sequence.json",
    "log_capture_sequence.csv",
    "log_capture_sequence.json",
    "_failure_log_sequence.csv",
    "_failure_log_sequence.json",
    "_log_capture_sequence.csv",
    "_log_capture_sequence.json",
)

# Caminho absoluto da raiz do projeto (este arquivo estÃ¡ em /Run)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

# DicionÃ¡rio local de controle do tempo (por processo)
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
            # Em Ãºltimo caso segue sem lock (melhor do que travar)
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
    """Escrita atÃ´mica de JSON (evita arquivo corrompido)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=os.path.dirname(path)) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


# =========================
# FUNÃ‡Ã•ES AUXILIARES
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
    """Wrapper com timeout e verificaÃ§Ã£o de falhas ADB."""
    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if "device '" in result.stderr and "not found" in result.stderr:
            print_color(f"âŒ Dispositivo ADB nÃ£o encontrado: {cmd}", "red")
            return None

        if result.returncode != 0 and not quiet:
            print_color(f"âš ï¸ Erro ADB: {result.stderr.strip()}", "yellow")

        return result
    except subprocess.TimeoutExpired:
        print_color(f"â³ Timeout ao executar: {' '.join(cmd)}", "yellow")
    except FileNotFoundError:
        print_color(f"âŒ Comando nÃ£o encontrado: {cmd[0]}", "red")
    except Exception as e:
        print_color(f"âš ï¸ Erro inesperado: {e}", "red")
    return None


def ensure_adb():
    """Verifica ADB antes de iniciar; falha amigÃ¡vel se nÃ£o encontrado."""
    if not ADB_PATH:
        print_color("âŒ ADB_PATH nÃ£o configurado.", "red")
        sys.exit(2)
    if not shutil_which(ADB_PATH):
        print_color(f"âŒ ADB nÃ£o encontrado em: {ADB_PATH}", "red")
        sys.exit(2)


def shutil_which(path):
    """CompatÃ­vel com caminho absoluto no Windows; retorna path se existir."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    from shutil import which
    return which(path)


def executar_tap(x, y, serial=None):
    """Executa um toque na tela via ADB"""
    comando = adb_cmd(serial) + ["shell", "input", "tap", str(x), str(y)]
    result = run_subprocess(comando)
    if result:
        print_color(f"ðŸ‘‰ TAP em ({x},{y})", "green")
    return result


def executar_long_press(x, y, duracao_ms=1000, serial=None):
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x), str(y), str(x), str(y), str(int(duracao_ms))
    ]
    result = run_subprocess(comando)
    if result:
        print_color(f"ðŸ–ï¸ LONG PRESS em ({x},{y}) por {duracao_ms/1000:.2f}s", "green")
    return result


def executar_swipe(x1, y1, x2, y2, duracao=300, serial=None):
    comando = adb_cmd(serial) + [
        "shell", "input", "swipe",
        str(x1), str(y1), str(x2), str(y2), str(duracao)
    ]
    result = run_subprocess(comando)
    if result:
        print_color(f"ðŸ‘‰ SWIPE ({x1},{y1}) â†’ ({x2},{y2}) [{duracao}ms]", "green")
    return result


def capturar_screenshot(pasta, nome, serial=None):
    """Captura uma screenshot do dispositivo e valida o resultado"""
    os.makedirs(pasta, exist_ok=True)
    caminho_local = os.path.join(pasta, nome)
    caminho_tmp = "/sdcard/tmp_shot.png"

    res1 = run_subprocess(adb_cmd(serial) + ["shell", "screencap", "-p", caminho_tmp])
    if res1 is None:
        print_color("âŒ Falha ao capturar screenshot no dispositivo.", "red")
        return None

    res2 = run_subprocess(adb_cmd(serial) + ["pull", caminho_tmp, caminho_local], quiet=True)
    if res2 is None:
        print_color("âš ï¸ Falha ao transferir screenshot para o PC.", "yellow")
        return None

    run_subprocess(adb_cmd(serial) + ["shell", "rm", caminho_tmp], quiet=True)

    if not os.path.exists(caminho_local):
        print_color(f"âš ï¸ Screenshot nÃ£o encontrada em {caminho_local}", "yellow")
        return None

    return caminho_local


def comparar_imagens(img1_path, img2_path):
    """Compara duas imagens e retorna o Ã­ndice de similaridade (SSIM)"""
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


def _sanitize_scalar(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _pick_action_value(action, *keys, default=None):
    for key in keys:
        if key not in action:
            continue
        value = _sanitize_scalar(action.get(key))
        if value is not None:
            return value
    return default


def _pick_float_value(action, *keys, default=None):
    raw = _pick_action_value(action, *keys, default=None)
    if raw is None:
        return default
    try:
        return float(str(raw).replace(",", "."))
    except Exception:
        return default


def _pick_int_value(action, *keys, default=None):
    raw = _pick_action_value(action, *keys, default=None)
    if raw is None:
        return default
    try:
        return int(float(str(raw).replace(",", ".")))
    except Exception:
        return default


def _slugify(text):
    value = str(text or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "item"


def executar_keyevent(keyevent, serial=None):
    comando = adb_cmd(serial) + ["shell", "input", "keyevent", str(keyevent)]
    result = run_subprocess(comando)
    if result:
        print_color(f"⌨️ KEYEVENT {keyevent}", "green")
    return result


def executar_texto(texto, serial=None):
    texto_limpo = str(texto or "").strip()
    if not texto_limpo:
        return None
    texto_adb = texto_limpo.replace(" ", "%s")
    comando = adb_cmd(serial) + ["shell", "input", "text", texto_adb]
    result = run_subprocess(comando)
    if result:
        print_color(f"⌨️ TEXTO enviado: {texto_limpo}", "green")
    return result


def puxar_arquivo_dispositivo(device_path, destino_local, serial=None):
    os.makedirs(os.path.dirname(destino_local), exist_ok=True)
    result = run_subprocess(adb_cmd(serial) + ["pull", device_path, destino_local], timeout=max(ADB_TIMEOUT, 90))
    if result is None or result.returncode != 0:
        return None
    return destino_local if os.path.exists(destino_local) else None


def _failure_log_sequence_candidates(categoria, nome_teste):
    teste_dir = _status_dir(categoria, nome_teste)
    categoria_dir = os.path.join(DATA_ROOT, categoria)
    candidates = []
    for root in (teste_dir, categoria_dir, DATA_ROOT):
        for filename in LOG_CAPTURE_SEQUENCE_FILENAMES:
            candidates.append(os.path.join(root, filename))
    return candidates


def _resolver_failure_log_sequence(categoria, nome_teste):
    for candidate in _failure_log_sequence_candidates(categoria, nome_teste):
        if os.path.exists(candidate):
            return candidate
    return None


def _carregar_failure_log_steps(sequence_path):
    if not sequence_path or not os.path.exists(sequence_path):
        return []

    ext = os.path.splitext(sequence_path)[1].lower()
    if ext == ".csv":
        with open(sequence_path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    if ext == ".json":
        with open(sequence_path, "r", encoding="utf-8", errors="ignore") as handle:
            raw = json.load(handle)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            for key in ("acoes", "steps", "actions"):
                values = raw.get(key)
                if isinstance(values, list):
                    return [item for item in values if isinstance(item, dict)]
    return []


def _executar_passo_failure_log(action, serial, artifacts_dir, step_index):
    action_type = str(_pick_action_value(action, "tipo", "acao", "type", "action", default="tap")).strip().lower()
    label = _pick_action_value(action, "label", "nome", "descricao", "description", default=f"passo_{step_index:02d}")
    wait_s = _pick_float_value(action, "espera_s", "wait_s", "sleep_s", "delay_s", default=LOG_CAPTURE_STEP_WAIT_S)
    started_at = datetime.now().isoformat()
    artifact_rel = None
    error = None
    ok = False

    try:
        if action_type == "wait":
            duration_s = _pick_float_value(action, "duracao_s", "duration_s", "espera_s", "wait_s", default=1.0) or 0.0
            time.sleep(max(0.0, duration_s))
            ok = True
        elif action_type == "tap":
            x = _pick_int_value(action, "x")
            y = _pick_int_value(action, "y")
            if x is None or y is None:
                raise ValueError("tap exige colunas x e y")
            ok = executar_tap(x, y, serial) is not None
        elif action_type == "long_press":
            x = _pick_int_value(action, "x")
            y = _pick_int_value(action, "y")
            duration_ms = _pick_int_value(action, "duracao_ms", default=None)
            if duration_ms is None:
                duration_s = _pick_float_value(action, "duracao_s", default=1.0) or 1.0
                duration_ms = int(duration_s * 1000)
            if x is None or y is None:
                raise ValueError("long_press exige colunas x e y")
            ok = executar_long_press(x, y, duration_ms, serial) is not None
        elif action_type in {"swipe", "swipe_inicio"}:
            x1 = _pick_int_value(action, "x1", "x")
            y1 = _pick_int_value(action, "y1", "y")
            x2 = _pick_int_value(action, "x2")
            y2 = _pick_int_value(action, "y2")
            duration_ms = _pick_int_value(action, "duracao_ms", default=300) or 300
            if None in (x1, y1, x2, y2):
                raise ValueError("swipe exige colunas x1, y1, x2 e y2")
            ok = executar_swipe(x1, y1, x2, y2, duracao=duration_ms, serial=serial) is not None
        elif action_type == "keyevent":
            keyevent = _pick_action_value(action, "keyevent", "key", "valor", "value")
            if keyevent is None:
                raise ValueError("keyevent exige coluna keyevent")
            ok = executar_keyevent(keyevent, serial) is not None
        elif action_type == "text":
            texto = _pick_action_value(action, "texto", "text", "valor", "value")
            if texto is None:
                raise ValueError("text exige coluna texto")
            ok = executar_texto(texto, serial) is not None
        elif action_type == "screenshot":
            file_name = _pick_action_value(action, "arquivo", "nome_arquivo", "output_name", "screenshot_name")
            file_name = file_name or f"step_{step_index:02d}.png"
            if not str(file_name).lower().endswith(".png"):
                file_name = f"{file_name}.png"
            saved = capturar_screenshot(artifacts_dir, file_name, serial)
            ok = saved is not None
            if saved:
                artifact_rel = os.path.relpath(saved, artifacts_dir)
        elif action_type == "pull_file":
            device_path = _pick_action_value(action, "device_path", "remote_path", "origem_device")
            output_name = _pick_action_value(action, "output_name", "arquivo", "nome_arquivo")
            if device_path is None:
                raise ValueError("pull_file exige coluna device_path")
            output_name = output_name or os.path.basename(str(device_path).replace("\\", "/")) or f"arquivo_{step_index:02d}.bin"
            local_path = os.path.join(artifacts_dir, output_name)
            saved = puxar_arquivo_dispositivo(str(device_path), local_path, serial)
            ok = saved is not None
            if saved:
                artifact_rel = os.path.relpath(saved, artifacts_dir)
        else:
            raise ValueError(f"tipo de passo nao suportado: {action_type}")

        if not ok:
            raise RuntimeError(f"falha ao executar passo do tipo {action_type}")

        if action_type != "wait" and wait_s and wait_s > 0:
            time.sleep(wait_s)
    except Exception as exc:
        error = str(exc)
        ok = False

    finished_at = datetime.now().isoformat()
    return {
        "step": step_index,
        "label": str(label),
        "type": action_type,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "ok" if ok else "erro",
        "artifact": artifact_rel,
        "error": error,
    }


def executar_captura_logs_pos_falha(categoria, nome_teste, serial, motivo):
    sequence_path = _resolver_failure_log_sequence(categoria, nome_teste)
    if not sequence_path:
        return {
            "status": "sem_roteiro",
            "artifact_dir": None,
            "error": "Nenhum roteiro de captura de logs configurado para este teste/categoria.",
            "sequence_path": None,
        }

    steps = _carregar_failure_log_steps(sequence_path)
    if not steps:
        return {
            "status": "sem_roteiro",
            "artifact_dir": None,
            "error": f"Roteiro encontrado em {sequence_path}, mas sem passos validos.",
            "sequence_path": sequence_path,
        }

    started_at = datetime.now()
    base_dir = _status_dir(categoria, nome_teste)
    capture_dir = os.path.join(base_dir, "failure_logs", started_at.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(capture_dir, exist_ok=True)
    metadata_path = os.path.join(capture_dir, "capture_metadata.json")
    metadata = {
        "categoria": categoria,
        "teste": nome_teste,
        "serial": serial,
        "motivo": motivo,
        "sequence_path": os.path.relpath(sequence_path, base_dir),
        "status": "executando",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "steps": [],
    }
    atomic_write_json(metadata_path, metadata)

    for step_index, step in enumerate(steps, start=1):
        result = _executar_passo_failure_log(step, serial, capture_dir, step_index)
        metadata["steps"].append(result)
        if result["status"] != "ok":
            metadata["status"] = "falha"
            metadata["finished_at"] = datetime.now().isoformat()
            metadata["error"] = result.get("error")
            atomic_write_json(metadata_path, metadata)
            return {
                "status": "falha",
                "artifact_dir": os.path.relpath(capture_dir, base_dir),
                "error": result.get("error"),
                "sequence_path": sequence_path,
            }
        atomic_write_json(metadata_path, metadata)

    final_shot = capturar_screenshot(capture_dir, "estado_final.png", serial)
    metadata["status"] = "capturado"
    metadata["finished_at"] = datetime.now().isoformat()
    metadata["final_screenshot"] = (
        os.path.relpath(final_shot, capture_dir) if final_shot and os.path.exists(final_shot) else None
    )
    atomic_write_json(metadata_path, metadata)
    return {
        "status": "capturado",
        "artifact_dir": os.path.relpath(capture_dir, base_dir),
        "error": None,
        "sequence_path": sequence_path,
    }


# =========================
# STATUS DAS BANCADAS (padronizado)
# =========================
STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data", "status_bancadas.json")
INICIO_EXECUCAO = {}

def _bancada_key_from_serial(serial):
    """Retorna a chave de identificaÃ§Ã£o da bancada."""
    if not serial or str(serial).strip() == "":
        return "2801761952320038"  # fallback seguro
    return str(serial)

def _status_dir(categoria, nome_teste):
    return os.path.join(DATA_ROOT, categoria, nome_teste)

def _teste_ref(categoria, nome_teste):
    return f"{categoria}/{nome_teste}"

def carregar_status(categoria, nome_teste, serial=None):
    """Carrega status da bancada (por teste)."""
    if serial:
        status_file = os.path.join(_status_dir(categoria, nome_teste), f"status_{serial}.json")
    else:
        status_file = os.path.join(_status_dir(categoria, nome_teste), "status_bancadas.json")

    if not os.path.exists(status_file):
        return {}

    try:
        with open(status_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

status_lock = threading.Lock()  # adiciona lock global

def _carregar_payload_bancada(categoria, nome_teste, bancada_key):
    raw = carregar_status(categoria, nome_teste, serial=bancada_key)
    if not isinstance(raw, dict):
        return {}
    nested = raw.get(bancada_key)
    if isinstance(nested, dict):
        return dict(nested)
    if str(raw.get("serial", "")).strip() == str(bancada_key):
        return dict(raw)
    return {}

def salvar_status(status, categoria, nome_teste, serial=None):
    """
    Salva status da execucao de forma segura e isolada por bancada.
    Se serial for fornecido, cria um arquivo status_<serial>.json.
    """
    try:
        with status_lock:
            os.makedirs(_status_dir(categoria, nome_teste), exist_ok=True)
            if serial:
                status_file = os.path.join(_status_dir(categoria, nome_teste), f"status_{serial}.json")
            else:
                status_file = os.path.join(_status_dir(categoria, nome_teste), "status_bancadas.json")
            atomic_write_json(status_file, status)
    except Exception as e:
        print(f"ERRO: falha ao salvar status: {e}")

def inicializar_status_bancada(bancada_key, categoria, teste_nome, total_acoes):
    agora = datetime.now().isoformat()
    anterior = _carregar_payload_bancada(categoria, teste_nome, bancada_key)
    INICIO_EXECUCAO[bancada_key] = time.time()
    status = {
        bancada_key: {
        "serial": bancada_key,
        "categoria": categoria,
        "teste": _teste_ref(categoria, teste_nome),
        "status": "executando",
        "acoes_totais": int(total_acoes),
        "acoes_executadas": 0,
        "progresso": 0.0,
        "ultima_acao": "-",
        "ultima_acao_idx": 0,
        "ultima_acao_status": "-",
        "tempo_decorrido_s": 0.0,
        "inicio": anterior.get("inicio") or agora,
        "fim": None,
        "atualizado_em": agora,
        "resultados_ok": 0,
        "resultados_divergentes": 0,
        "similaridade_media": 0.0,
        "ultima_similaridade": None,
        "ultimo_screenshot": None,
        "resultado_final": anterior.get("resultado_final") or "pendente",
        "log_capture_status": anterior.get("log_capture_status") or "nao_necessario",
        "log_capture_dir": anterior.get("log_capture_dir"),
        "log_capture_error": anterior.get("log_capture_error"),
        "log_capture_sequence": anterior.get("log_capture_sequence"),
        }
    }
    salvar_status(status, categoria, teste_nome, serial=bancada_key)

def atualizar_status_bancada(
    bancada_key,
    categoria,
    teste_nome,
    total_acoes,
    executadas,
    ultima_acao,
    status_resultado=None,
    similaridade=None,
    screenshot_rel=None,
):
    anterior = _carregar_payload_bancada(categoria, teste_nome, bancada_key)
    inicio = INICIO_EXECUCAO.get(bancada_key, time.time())
    tempo_decorrido = time.time() - inicio
    progresso = round(((executadas or 0) / max(total_acoes, 1)) * 100, 1)
    ok_count = int(anterior.get("resultados_ok", 0) or 0)
    divergente_count = int(anterior.get("resultados_divergentes", 0) or 0)
    if str(status_resultado).strip().lower() == "ok":
        ok_count += 1
    elif str(status_resultado).strip().lower() == "divergente":
        divergente_count += 1

    media_anterior = float(anterior.get("similaridade_media", 0.0) or 0.0)
    similaridade_media = media_anterior
    if similaridade is not None and int(executadas or 0) > 0:
        similaridade_media = ((media_anterior * max(int(executadas) - 1, 0)) + float(similaridade)) / float(executadas)

    velocidade_acoes_min = 0.0
    if tempo_decorrido > 0 and int(executadas or 0) > 0:
        velocidade_acoes_min = round((float(executadas) / tempo_decorrido) * 60.0, 2)

    status = {
        bancada_key: {
        "serial": bancada_key,
        "categoria": categoria,
        "teste": _teste_ref(categoria, teste_nome),
        "status": "executando",
        "acoes_totais": int(total_acoes),
        "acoes_executadas": int(executadas),
        "progresso": progresso,
        "ultima_acao": str(ultima_acao),
        "ultima_acao_idx": int(executadas),
        "ultima_acao_status": str(status_resultado or anterior.get("ultima_acao_status") or "-"),
        "tempo_decorrido_s": float(tempo_decorrido),
        "inicio": anterior.get("inicio") or datetime.now().isoformat(),
        "fim": None,
        "atualizado_em": datetime.now().isoformat(),
        "resultados_ok": ok_count,
        "resultados_divergentes": divergente_count,
        "similaridade_media": round(similaridade_media, 4) if similaridade is not None else round(float(anterior.get("similaridade_media", 0.0) or 0.0), 4),
        "ultima_similaridade": round(float(similaridade), 4) if similaridade is not None else anterior.get("ultima_similaridade"),
        "ultimo_screenshot": str(screenshot_rel or anterior.get("ultimo_screenshot") or ""),
        "velocidade_acoes_min": velocidade_acoes_min,
        "resultado_final": anterior.get("resultado_final") or "pendente",
        "log_capture_status": anterior.get("log_capture_status") or "nao_necessario",
        "log_capture_dir": anterior.get("log_capture_dir"),
        "log_capture_error": anterior.get("log_capture_error"),
        "log_capture_sequence": anterior.get("log_capture_sequence"),
        }
    }
    salvar_status(status, categoria, teste_nome, serial=bancada_key)

def finalizar_status_bancada(
    bancada_key,
    categoria,
    teste_nome,
    resultado="finalizado",
    motivo=None,
    resultado_final=None,
    log_capture_status=None,
    log_capture_dir=None,
    log_capture_error=None,
    log_capture_sequence=None,
):
    anterior = _carregar_payload_bancada(categoria, teste_nome, bancada_key)
    agora = datetime.now().isoformat()
    status = {
        bancada_key: {
        "serial": bancada_key,
        "categoria": categoria,
        "teste": anterior.get("teste") or _teste_ref(categoria, teste_nome),
        "status": resultado,
        "acoes_totais": int(anterior.get("acoes_totais", 0) or 0),
        "acoes_executadas": int(anterior.get("acoes_executadas", 0) or 0),
        "progresso": float(anterior.get("progresso", 0.0) or 0.0),
        "ultima_acao": anterior.get("ultima_acao", "-"),
        "ultima_acao_idx": int(anterior.get("ultima_acao_idx", 0) or 0),
        "ultima_acao_status": anterior.get("ultima_acao_status", "-"),
        "tempo_decorrido_s": float(anterior.get("tempo_decorrido_s", 0.0) or 0.0),
        "inicio": anterior.get("inicio"),
        "fim": agora if resultado in {"finalizado", "erro"} else None,
        "atualizado_em": agora,
        "resultados_ok": int(anterior.get("resultados_ok", 0) or 0),
        "resultados_divergentes": int(anterior.get("resultados_divergentes", 0) or 0),
        "similaridade_media": round(float(anterior.get("similaridade_media", 0.0) or 0.0), 4),
        "ultima_similaridade": anterior.get("ultima_similaridade"),
        "ultimo_screenshot": anterior.get("ultimo_screenshot"),
        "velocidade_acoes_min": float(anterior.get("velocidade_acoes_min", 0.0) or 0.0),
        "resultado_final": resultado_final or anterior.get("resultado_final") or "pendente",
        "log_capture_status": log_capture_status or anterior.get("log_capture_status") or "nao_necessario",
        "log_capture_dir": log_capture_dir if log_capture_dir is not None else anterior.get("log_capture_dir"),
        "log_capture_error": log_capture_error if log_capture_error is not None else anterior.get("log_capture_error"),
        "log_capture_sequence": log_capture_sequence if log_capture_sequence is not None else anterior.get("log_capture_sequence"),
        "erro_motivo": motivo,
        }
    }
    if resultado in {"finalizado", "coletando_logs"} and status[bancada_key]["acoes_totais"] > 0:
        status[bancada_key]["progresso"] = 100.0
    salvar_status(status, categoria, teste_nome, serial=bancada_key)

# =========================
# MAIN
# =========================
def main():
    print("ðŸ“ ExecuÃ§Ã£o AutomÃ¡tica de Testes no RÃ¡dio via ADB")

    # ðŸ”¹ Argumentos ou modo interativo
    if len(sys.argv) >= 3:
        categoria = sys.argv[1].strip().lower().replace(" ", "_")
        nome_teste = sys.argv[2].strip().lower().replace(" ", "_")
    else:
        print_color("âš ï¸ Nenhum argumento fornecido. Entrando em modo interativo...\n", "yellow")
        categoria = input("ðŸ“‚ Categoria do teste: ").strip().lower().replace(" ", "_")
        nome_teste = input("ðŸ“ Nome do teste: ").strip().lower().replace(" ", "_")

    serial = None
    if "--serial" in sys.argv:
        idx = sys.argv.index("--serial")
        if idx + 1 < len(sys.argv):
            serial = sys.argv[idx + 1]

    # ðŸ”¹ Garante que sempre exista uma bancada_key
    if not serial or serial.strip() == "":
        print_color("âš ï¸ Nenhum serial ADB detectado â€” atribuindo Bancada 1 (2801761952320038)", "yellow")
        serial = "2801761952320038"

    # âœ… Define identificador Ãºnico da bancada (corrige o NameError)
    bancada_key = _bancada_key_from_serial(serial)

    def concluir_execucao(status_execucao, resultado_final, motivo=None, capturar_logs=False):
        capture_status = "nao_necessario"
        capture_dir = None
        capture_error = None
        capture_sequence = None

        if capturar_logs:
            print_color("ðŸ§¾ Falha detectada â€” iniciando captura de logs da peca...", "yellow")
            try:
                finalizar_status_bancada(
                    bancada_key,
                    categoria,
                    nome_teste,
                    resultado="coletando_logs",
                    motivo=motivo,
                    resultado_final=resultado_final,
                    log_capture_status="executando",
                )
            except Exception as exc:
                print_color(f"âš ï¸ Nao foi possivel marcar status de coleta de logs: {exc}", "yellow")

            capture_result = executar_captura_logs_pos_falha(categoria, nome_teste, serial, motivo or resultado_final)
            capture_status = capture_result.get("status") or "falha"
            capture_dir = capture_result.get("artifact_dir")
            capture_error = capture_result.get("error")
            sequence_path = capture_result.get("sequence_path")
            if sequence_path:
                try:
                    capture_sequence = os.path.relpath(sequence_path, _status_dir(categoria, nome_teste))
                except Exception:
                    capture_sequence = sequence_path

            if capture_status == "capturado":
                print_color(f"âœ… Logs da peca capturados em Data/{categoria}/{nome_teste}/{capture_dir}", "green")
            elif capture_status == "sem_roteiro":
                print_color(f"âš ï¸ Falha detectada, mas sem roteiro de captura configurado: {capture_error}", "yellow")
            else:
                print_color(f"âŒ Captura de logs falhou: {capture_error}", "red")

        try:
            finalizar_status_bancada(
                bancada_key,
                categoria,
                nome_teste,
                resultado=status_execucao,
                motivo=motivo,
                resultado_final=resultado_final,
                log_capture_status=capture_status,
                log_capture_dir=capture_dir,
                log_capture_error=capture_error,
                log_capture_sequence=capture_sequence,
            )
        except Exception as exc:
            print_color(f"âš ï¸ Falha ao atualizar status final: {exc}", "yellow")

    # ðŸ” Verifica se o dispositivo estÃ¡ conectado
    print_color("ðŸ” Verificando dispositivos ADB conectados...", "cyan")
    try:
        devices = subprocess.check_output([ADB_PATH, "devices"], text=True)
        if serial not in devices:
            print_color(f"âŒ Dispositivo {serial} nÃ£o encontrado. Conecte o rÃ¡dio e tente novamente.", "red")
            concluir_execucao("erro", "erro_tecnico", motivo="adb", capturar_logs=False)
            return
    except Exception as e:
        print_color(f"âš ï¸ Falha ao verificar dispositivos ADB: {e}", "red")
        concluir_execucao("erro", "erro_tecnico", motivo="adb", capturar_logs=False)
        return

    teste_dir = os.path.join(DATA_ROOT, categoria, nome_teste)
    dataset_path = os.path.join(teste_dir, "dataset.csv")
    frames_dir = os.path.join(teste_dir, "frames")
    resultados_dir = os.path.join(teste_dir, "resultados")
    log_path = os.path.join(teste_dir, "execucao_log.json")

    print_color(f"\nðŸ—‚ï¸ Dataset: {dataset_path}", "cyan")
    print_color(f"ðŸ—‚ï¸ Frames:  {frames_dir}", "cyan")
    print_color(f"ðŸ—‚ï¸ Result.: {resultados_dir}\n", "cyan")

    if not os.path.exists(dataset_path):
        print_color(
            f"âŒ Arquivo dataset.csv nÃ£o encontrado.\n"
            f"   Esperado em: {dataset_path}\n"
            f"   Dica: rode a opÃ§Ã£o 'Processar Dataset' no menu.",
            "red"
        )
        concluir_execucao("erro", "erro_tecnico", motivo="dataset", capturar_logs=False)
        return

    os.makedirs(resultados_dir, exist_ok=True)
    try:
        df = pd.read_csv(dataset_path)
    except Exception as e:
        print_color(f"âŒ Falha ao ler dataset.csv: {e}", "red")
        concluir_execucao("erro", "erro_tecnico", motivo="dataset", capturar_logs=False)
        return

    total_acoes = sum(1 for _, r in df.iterrows() if str(r.get("tipo", "")).lower() != "swipe_fim")
    print_color(f"\nðŸŽ¬ Executando {total_acoes} aÃ§Ãµes do dataset...\n", "cyan")
    log = []
    houve_divergencia = False

    # ðŸ”¹ Inicializa status
    inicializar_status_bancada(bancada_key, categoria, nome_teste, total_acoes)

    action_idx = 0
    for i, row in df.iterrows():
        try:
            tipo = str(row.get("tipo", "tap")).lower()
        except Exception:
            tipo = "tap"

        if tipo == "swipe_fim":
            # swipe_fim Ã© consumido pelo swipe_inicio e nÃ£o deve gerar aÃ§Ã£o/screenshot
            continue

        print_color(f"â–¶ï¸ AÃ§Ã£o {action_idx+1}/{total_acoes} ({tipo})", "white")

        # Pausa se necessÃ¡rio (auto-limpa se sobrou de execuÃ§Ã£o anterior)
        pause_path = os.path.join(BASE_DIR, "pause.flag")
        if os.path.exists(pause_path):
            print_color("âš ï¸ Arquivo de pausa residual detectado â€” removendo para evitar travamento.", "yellow")
            try:
                os.remove(pause_path)
            except Exception as e:
                print_color(f"âš ï¸ NÃ£o foi possÃ­vel remover pause.flag: {e}", "red")

        while os.path.exists(pause_path):
            print_color("â¸ï¸ ExecuÃ§Ã£o pausada... aguardando retomada.", "yellow")
            time.sleep(2)

        inicio = time.time()

        # ===== Executa aÃ§Ã£o =====
        try:
            if tipo == "tap":
                res = executar_tap(int(row["x"]), int(row["y"]), serial)
                if res is None:
                    print_color("âŒ Falha na execuÃ§Ã£o do TAP â€” interrompendo teste.", "red")
                    concluir_execucao("erro", "erro_tecnico", motivo="adb", capturar_logs=True)
                    return


            elif tipo in ["swipe", "swipe_inicio"]:
                # Busca coordenadas do swipe (prioriza x1/y1/x2/y2 se existirem)
                x1 = int(row.get("x1", row.get("x", 0)))
                y1 = int(row.get("y1", row.get("y", 0)))
                dur = int(row.get("duracao_ms", 300))
                x2, y2 = None, None

                if tipo == "swipe":
                    x2 = int(row.get("x2", row.get("x", 0)))
                    y2 = int(row.get("y2", row.get("y", 0)))
                else:
                    # Busca prÃ³ximo registro com tÃ©rmino do swipe
                    if i + 1 < len(df):
                        proxima = df.iloc[i + 1]
                        prox_tipo = str(proxima.get("tipo", "")).lower()
                        if prox_tipo in ["swipe_fim", "swipe"]:
                            x2 = int(proxima.get("x2", proxima.get("x", 0)))
                            y2 = int(proxima.get("y2", proxima.get("y", 0)))

                if x2 is not None and y2 is not None:
                    res = executar_swipe(x1, y1, x2, y2, duracao=dur, serial=serial)
                    if res is None:
                        print_color("âŒ Falha na execuÃ§Ã£o do SWIPE â€” interrompendo teste.", "red")
                        concluir_execucao("erro", "erro_tecnico", motivo="adb", capturar_logs=True)
                        return
                else:
                    print_color("âš ï¸ swipe sem fim vÃ¡lido â€” ignorado.", "yellow")

            elif tipo == "long_press":
                duracao_press_ms = float(row.get("duracao_s", 1.0)) * 1000
                res = executar_long_press(int(row["x"]), int(row["y"]), duracao_press_ms, serial)
                if res is None:
                    print_color("âŒ Falha na execuÃ§Ã£o do LONG PRESS â€” interrompendo teste.", "red")
                    concluir_execucao("erro", "erro_tecnico", motivo="adb", capturar_logs=True)
                    return

            else:
                print_color(f"âš ï¸ Tipo de aÃ§Ã£o '{tipo}' nÃ£o reconhecido â€” ignorado.", "yellow")

        except Exception as e:
            print_color(f"âš ï¸ Erro ao executar aÃ§Ã£o {i+1}: {e}", "red")
            concluir_execucao("erro", "erro_tecnico", motivo="execucao_acao", capturar_logs=True)
            return

        # Aguarda a UI estabilizar apÃ³s a aÃ§Ã£o antes de capturar o screenshot.
        time.sleep(ESPERA_POS_ACAO_S)
        # ===== Screenshot e Similaridade =====
        action_idx += 1
        screenshot_nome = f"resultado_{action_idx:02d}.png"
        screenshot_path = capturar_screenshot(resultados_dir, screenshot_nome, serial)

        esperado_rel = os.path.join("frames", f"frame_{action_idx:02d}.png")
        esperado_abs = os.path.join(teste_dir, esperado_rel)

        similaridade = comparar_imagens(screenshot_path, esperado_abs)
        status_txt = "OK" if similaridade >= SIMILARIDADE_HOME_OK else "Divergente"
        if status_txt != "OK":
            houve_divergencia = True

        fim = time.time()
        duracao = round(fim - inicio, 2)

        print_color(f"ðŸ”Ž Similaridade: {similaridade:.3f} â†’ {status_txt} | â±ï¸ {duracao:.2f}s", "cyan")

        # Monta registro de log da aÃ§Ã£o
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
        atomic_write_json(log_path, log)

        # ðŸ”¹ Atualiza status da bancada
        atualizar_status_bancada(
            bancada_key,
            categoria,
            nome_teste,
            total_acoes,
            action_idx,
            tipo,
            status_resultado=status_txt,
            similaridade=similaridade,
            screenshot_rel=registro["screenshot"],
        )

        time.sleep(PAUSA_ENTRE_ACOES)

    # === SALVAR LOG FINAL ===
    try:
        atomic_write_json(log_path, log)
        print_color(f"\nâœ… ExecuÃ§Ã£o finalizada. Log salvo em: {log_path}", "green")
    except Exception as e:
        print_color(f"âŒ Falha ao salvar log final: {e}", "red")

    resultado_final = "reprovado" if houve_divergencia else "aprovado"
    motivo_final = "divergencia_visual" if houve_divergencia else None
    concluir_execucao("finalizado", resultado_final, motivo=motivo_final, capturar_logs=houve_divergencia)
    print_color(f"Status atualizado em: Data/{categoria}/{nome_teste}/status_{bancada_key}.json", "cyan")

if __name__ == "__main__":
    main()

