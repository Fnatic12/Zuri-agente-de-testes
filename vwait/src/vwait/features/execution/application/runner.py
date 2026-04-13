from __future__ import annotations

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
from pathlib import Path
from skimage.metrics import structural_similarity as ssim
import cv2
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[5]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.platform.adb import resolve_adb_path
from vwait.core.paths import (
    DATA_ROOT as DATA_ROOT_PATH,
    create_tester_run_dir,
    tester_dataset_path,
    tester_execution_log_path,
    tester_recorded_frames_dir,
    tester_results_dir,
)
from vwait.features.execution.application import (
    bancada_key_from_serial as _execution_bancada_key_from_serial,
    build_action_outcome as _execution_build_action_outcome,
    carregar_payload_bancada as _execution_carregar_payload_bancada,
    carregar_status as _execution_carregar_status,
    conclude_execution_flow as _execution_conclude_execution_flow,
    default_log_label as _execution_default_log_label,
    execute_default_log_capture as _execution_execute_default_log_capture,
    execute_post_failure_log_capture as _execution_execute_post_failure_log_capture,
    finalize_runtime_status as _execution_finalize_runtime_status,
    failure_report_pointer_path as _execution_failure_report_pointer_path,
    initialize_runtime_status as _execution_initialize_runtime_status,
    load_failure_log_steps as _execution_load_failure_log_steps,
    log_capture_dir as _execution_log_capture_dir,
    limpar_relatorio_falha_automatico as _execution_limpar_relatorio_falha_automatico,
    prepare_logs_post_failure as _execution_prepare_logs_post_failure,
    resolve_failure_log_sequence as _execution_resolve_failure_log_sequence,
    resolve_execution_final_result as _execution_resolve_execution_final_result,
    sanitize_action_payload as _execution_sanitize_action_payload,
    salvar_status as _execution_salvar_status,
    status_dir as _execution_status_dir,
    test_ref as _execution_test_ref,
    update_log_capture_status as _execution_update_log_capture_status,
    update_runtime_status as _execution_update_runtime_status,
)

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
DEFAULT_FAILURE_LOG_PATTERNS = (
    "/data/tombstones/*",
    "/data/anr/*",
    "/data/log/*",
    "/data/tcpdump/*",
    "/data/capture/*",
    "/data/bugreport/*",
    "/data/dumpsys/*",
    "/data/lshal/*",
    "/data/McuLog/*",
    "/data/local/traces/*",
    "/ota_download/recovery_log/*",
    "/data/misc/bluetooth*",
    "/data/vendor/broadcastradio/log*",
    "/data/vendor/extend_log_/dropbox/*",
)

# Caminho absoluto da raiz do projeto (este arquivo estÃ¡ em /Run)
BASE_DIR = str(PROJECT_ROOT)
DATA_ROOT = str(DATA_ROOT_PATH)

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


def _default_log_label(pattern):
    return _execution_default_log_label(pattern)


def _listar_matches_device_glob(pattern, serial=None):
    return _execution_listar_matches_device_glob(pattern, serial=serial)


def _execution_listar_matches_device_glob(pattern, *, serial=None):
    from vwait.features.execution.application import list_matches_device_glob

    return list_matches_device_glob(
        pattern,
        serial=serial,
        adb_cmd_builder=adb_cmd,
        run_subprocess=run_subprocess,
        adb_timeout=ADB_TIMEOUT,
    )


def preparar_logs_pos_falha(serial=None):
    return _execution_prepare_logs_post_failure(
        serial=serial,
        adb_cmd_builder=adb_cmd,
        run_subprocess=run_subprocess,
        adb_timeout=ADB_TIMEOUT,
        patterns=DEFAULT_FAILURE_LOG_PATTERNS,
    )


def _log_capture_dir(base_dir, started_at):
    return _execution_log_capture_dir(base_dir, started_at)


def _executar_captura_logs_default(categoria, nome_teste, serial, motivo):
    return _execution_execute_default_log_capture(
        categoria,
        nome_teste,
        serial,
        motivo,
        base_dir=_status_dir(categoria, nome_teste),
        adb_cmd_builder=adb_cmd,
        run_subprocess=run_subprocess,
        adb_timeout=ADB_TIMEOUT,
        pull_file=puxar_arquivo_dispositivo,
        capture_screenshot=capturar_screenshot,
        atomic_write_json=atomic_write_json,
        patterns=DEFAULT_FAILURE_LOG_PATTERNS,
    )


def _failure_log_sequence_candidates(categoria, nome_teste):
    teste_dir = _status_dir(categoria, nome_teste)
    categoria_dir = os.path.join(DATA_ROOT, categoria)
    candidates = []
    for root in (teste_dir, categoria_dir, DATA_ROOT):
        for filename in LOG_CAPTURE_SEQUENCE_FILENAMES:
            candidates.append(os.path.join(root, filename))
    return candidates


def _resolver_failure_log_sequence(categoria, nome_teste):
    return _execution_resolve_failure_log_sequence(
        categoria,
        nome_teste,
        data_root=DATA_ROOT,
        test_dir=_status_dir(categoria, nome_teste),
        sequence_filenames=LOG_CAPTURE_SEQUENCE_FILENAMES,
    )


def _carregar_failure_log_steps(sequence_path):
    return _execution_load_failure_log_steps(sequence_path)


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
        return _executar_captura_logs_default(categoria, nome_teste, serial, motivo)
    return _execution_execute_post_failure_log_capture(
        categoria,
        nome_teste,
        serial,
        motivo,
        base_dir=_status_dir(categoria, nome_teste),
        data_root=DATA_ROOT,
        execute_step=_executar_passo_failure_log,
        capture_screenshot=capturar_screenshot,
        atomic_write_json=atomic_write_json,
        sequence_filenames=LOG_CAPTURE_SEQUENCE_FILENAMES,
    )


def capturar_logs_teste(categoria, nome_teste, serial, motivo="manual", limpar_antes=False):
    if limpar_antes:
        preparar_logs_pos_falha(serial)

    capture_result = executar_captura_logs_pos_falha(categoria, nome_teste, serial, motivo)
    bancada_key = _bancada_key_from_serial(serial)
    sequence_path = capture_result.get("sequence_path")
    capture_sequence = None
    if sequence_path:
        if sequence_path == "default_auto_capture":
            capture_sequence = sequence_path
        else:
            try:
                capture_sequence = os.path.relpath(sequence_path, _status_dir(categoria, nome_teste))
            except Exception:
                capture_sequence = sequence_path

    atualizar_status_captura_logs(
        bancada_key,
        categoria,
        nome_teste,
        capture_result.get("status"),
        log_capture_dir=capture_result.get("artifact_dir"),
        log_capture_error=capture_result.get("error"),
        log_capture_sequence=capture_sequence,
    )
    return capture_result


# =========================
# STATUS DAS BANCADAS (padronizado)
# =========================
STATUS_FILE = os.path.join(DATA_ROOT, "status_bancadas.json")
INICIO_EXECUCAO = {}

def _bancada_key_from_serial(serial):
    return _execution_bancada_key_from_serial(serial)

def _status_dir(categoria, nome_teste):
    return str(_execution_status_dir(categoria, nome_teste))

def _teste_ref(categoria, nome_teste):
    return _execution_test_ref(categoria, nome_teste)

def carregar_status(categoria, nome_teste, serial=None):
    return _execution_carregar_status(categoria, nome_teste, serial=serial)

status_lock = threading.Lock()  # adiciona lock global

def _carregar_payload_bancada(categoria, nome_teste, bancada_key):
    return _execution_carregar_payload_bancada(categoria, nome_teste, bancada_key)

def salvar_status(status, categoria, nome_teste, serial=None):
    _execution_salvar_status(status, categoria, nome_teste, serial=serial)


def _failure_report_pointer_path(categoria, nome_teste):
    return str(_execution_failure_report_pointer_path(categoria, nome_teste))


def limpar_relatorio_falha_automatico(categoria, nome_teste):
    _execution_limpar_relatorio_falha_automatico(categoria, nome_teste)


def gerar_relatorio_falha_automatico(categoria, nome_teste, log_path, similarity_threshold=SIMILARIDADE_HOME_OK):
    try:
        from vwait.features.failures.application.generate_reports import generate_failure_report
    except Exception as exc:
        return {
            "status": "falha",
            "error": f"Falha ao importar gerador de relatorio: {exc}",
        }

    try:
        result = generate_failure_report(
            categoria,
            nome_teste,
            log_path,
            similarity_threshold=similarity_threshold,
        )
    except Exception as exc:
        return {
            "status": "falha",
            "error": f"Falha ao gerar relatorio estruturado: {exc}",
        }

    if not result:
        return {
            "status": "nao_gerado",
            "error": "Nenhuma falha elegivel encontrada para gerar relatorio.",
        }

    json_path, md_path, csv_path = [str(path) for path in result]
    report_payload = {}
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            report_payload = loaded
    except Exception:
        report_payload = {}

    pointer_payload = {
        "status": "gerado",
        "generated_at": report_payload.get("generated_at"),
        "short_text": report_payload.get("short_text"),
        "json_path": json_path,
        "markdown_path": md_path,
        "csv_path": csv_path,
        "report_dir": os.path.dirname(json_path),
    }
    try:
        atomic_write_json(_failure_report_pointer_path(categoria, nome_teste), pointer_payload)
    except Exception:
        pass

    return {
        "status": "gerado",
        "generated_at": pointer_payload.get("generated_at"),
        "short_text": pointer_payload.get("short_text"),
        "json_path": json_path,
        "markdown_path": md_path,
        "csv_path": csv_path,
        "report_dir": pointer_payload.get("report_dir"),
        "error": None,
    }

def inicializar_status_bancada(bancada_key, categoria, teste_nome, total_acoes):
    _execution_initialize_runtime_status(
        bancada_key,
        categoria,
        teste_nome,
        total_acoes,
        load_payload=_carregar_payload_bancada,
        save_status=lambda status, cat, teste: salvar_status(
            status, cat, teste, serial=bancada_key
        ),
        test_ref_fn=_teste_ref,
        execution_start_times=INICIO_EXECUCAO,
    )

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
    _execution_update_runtime_status(
        bancada_key,
        categoria,
        teste_nome,
        total_acoes,
        executadas,
        ultima_acao,
        load_payload=_carregar_payload_bancada,
        save_status=lambda status, cat, teste: salvar_status(
            status, cat, teste, serial=bancada_key
        ),
        test_ref_fn=_teste_ref,
        execution_start_times=INICIO_EXECUCAO,
        status_resultado=status_resultado,
        similaridade=similaridade,
        screenshot_rel=screenshot_rel,
    )

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
    failure_report_status=None,
    failure_report_dir=None,
    failure_report_json=None,
    failure_report_markdown=None,
    failure_report_csv=None,
    failure_report_short_text=None,
    failure_report_generated_at=None,
    failure_report_error=None,
):
    _execution_finalize_runtime_status(
        bancada_key,
        categoria,
        teste_nome,
        load_payload=_carregar_payload_bancada,
        save_status=lambda status, cat, teste: salvar_status(
            status, cat, teste, serial=bancada_key
        ),
        test_ref_fn=_teste_ref,
        resultado=resultado,
        motivo=motivo,
        resultado_final=resultado_final,
        log_capture_status=log_capture_status,
        log_capture_dir=log_capture_dir,
        log_capture_error=log_capture_error,
        log_capture_sequence=log_capture_sequence,
        failure_report_status=failure_report_status,
        failure_report_dir=failure_report_dir,
        failure_report_json=failure_report_json,
        failure_report_markdown=failure_report_markdown,
        failure_report_csv=failure_report_csv,
        failure_report_short_text=failure_report_short_text,
        failure_report_generated_at=failure_report_generated_at,
        failure_report_error=failure_report_error,
    )


def atualizar_status_captura_logs(
    bancada_key,
    categoria,
    teste_nome,
    log_capture_status,
    log_capture_dir=None,
    log_capture_error=None,
    log_capture_sequence=None,
):
    _execution_update_log_capture_status(
        bancada_key,
        categoria,
        teste_nome,
        log_capture_status,
        load_payload=_carregar_payload_bancada,
        save_status=lambda status, cat, teste: salvar_status(
            status, cat, teste, serial=bancada_key
        ),
        test_ref_fn=_teste_ref,
        log_capture_dir=log_capture_dir,
        log_capture_error=log_capture_error,
        log_capture_sequence=log_capture_sequence,
    )

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
        _execution_conclude_execution_flow(
            bancada_key,
            categoria,
            nome_teste,
            serial,
            status_execucao,
            resultado_final,
            motivo=motivo,
            capture_logs=capturar_logs,
            log_path=log_path,
            similarity_threshold=SIMILARIDADE_HOME_OK,
            status_dir=_status_dir(categoria, nome_teste),
            finalize_status=finalizar_status_bancada,
            capture_logs_fn=executar_captura_logs_pos_falha,
            generate_report_fn=gerar_relatorio_falha_automatico,
            emit_message=print_color,
        )

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

    try:
        clean_results = preparar_logs_pos_falha(serial)
        cleaned_ok = sum(1 for item in clean_results if item.get("status") == "ok")
        print_color(
            f"ðŸ§¹ Limpeza preventiva dos logs remotos concluida: {cleaned_ok}/{len(clean_results)} origem(ns).",
            "cyan",
        )
    except Exception as exc:
        print_color(f"âš ï¸ Falha ao preparar limpeza preventiva dos logs: {exc}", "yellow")

    run_dir = str(create_tester_run_dir(categoria, nome_teste))
    teste_dir = run_dir
    limpar_relatorio_falha_automatico(categoria, nome_teste)
    dataset_path = str(tester_dataset_path(categoria, nome_teste))
    frames_dir = str(tester_recorded_frames_dir(categoria, nome_teste))
    resultados_dir = str(tester_results_dir(categoria, nome_teste, create=True))
    log_path = str(tester_execution_log_path(categoria, nome_teste, create=True))

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
        fim = time.time()
        duracao = round(fim - inicio, 2)

        action_outcome = _execution_build_action_outcome(
            action_idx,
            tipo,
            _execution_sanitize_action_payload(row.to_dict(), is_missing=pd.isna),
            os.path.join("resultados", screenshot_nome),
            esperado_rel,
            similaridade,
            duracao,
            threshold=SIMILARIDADE_HOME_OK,
        )
        status_txt = action_outcome["status"]
        if action_outcome["divergent"]:
            houve_divergencia = True

        print_color(f"ðŸ”Ž Similaridade: {similaridade:.3f} â†’ {status_txt} | â±ï¸ {duracao:.2f}s", "cyan")

        registro = action_outcome["log_record"]
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

    resultado_final, motivo_final = _execution_resolve_execution_final_result(houve_divergencia)
    concluir_execucao("finalizado", resultado_final, motivo=motivo_final, capturar_logs=houve_divergencia)
    print_color(f"Status atualizado em: Data/runs/tester/{categoria}/{nome_teste}/<run>/status/{bancada_key}.json", "cyan")

if __name__ == "__main__":
    main()


__all__ = ["capturar_logs_teste", "comparar_imagens", "main"]
