import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from typing import Callable

from vwait.core.paths import (
    DATA_ROOT,
    TESTER_CATALOG_ROOT,
    iter_tester_categories,
    iter_tester_tests,
    tester_actions_path,
    tester_status_file_path,
)


def parse_adb_devices(raw_lines):
    serials = []
    for line in raw_lines[1:]:
        line = line.strip()
        match = __import__("re").match(r"^(\S+)\s+device$", line)
        if match:
            serials.append(match.group(1))
    return serials


def list_benches(*, adb_path: str, subprocess_kwargs: dict) -> dict[str, str]:
    try:
        result = subprocess.check_output([adb_path, "devices"], text=True, **subprocess_kwargs).strip().splitlines()
        devices = parse_adb_devices(result)
        return {str(index + 1): device for index, device in enumerate(devices)}
    except Exception:
        return {}


def format_benches(benches: dict) -> str:
    if not benches:
        return "Nenhuma bancada conectada."
    lines = ["**Bancadas disponiveis:**"]
    for key, value in benches.items():
        lines.append(f"{key} -> `{value}`")
    return "\n".join(lines)


def resolve_test(
    token_or_name: str,
    *,
    normalize_token_fn: Callable[[str], str],
    norm_fn: Callable[[str], str],
    list_categories_fn: Callable[[], list[str]],
    list_tests_fn: Callable[[str], list[str]],
) -> tuple[str | None, str | None]:
    if not token_or_name:
        return None, None
    target = normalize_token_fn(token_or_name)
    categories = list_categories_fn()

    for category in categories:
        for test_name in list_tests_fn(category):
            if normalize_token_fn(test_name) == target:
                return category, test_name

    parts = __import__("re").split(r"[_\-\s]+", norm_fn(token_or_name))
    if parts:
        candidate_category = parts[0]
        if candidate_category in categories:
            remaining = normalize_token_fn("".join(parts[1:]))
            for test_name in list_tests_fn(candidate_category):
                if normalize_token_fn(test_name) in (target, remaining):
                    return candidate_category, test_name

    candidates = []
    for category in categories:
        for test_name in list_tests_fn(category):
            ratio = SequenceMatcher(None, normalize_token_fn(test_name), target).ratio()
            if ratio >= 0.82:
                candidates.append((ratio, category, test_name))
    candidates.sort(reverse=True)
    if len(candidates) == 1:
        _, category, test_name = candidates[0]
        return category, test_name
    if len(candidates) > 1 and (candidates[0][0] - candidates[1][0]) >= 0.08:
        _, category, test_name = candidates[0]
        return category, test_name
    return None, None


def select_bench(bench: str | None, benches: dict):
    if not benches:
        return [], "ERRO: nenhuma bancada conectada."
    if bench is None or str(bench).strip() == "":
        return [benches[sorted(benches.keys(), key=int)[0]]], None
    text = str(bench).strip().lower()
    if text in ("todas", "todas as bancadas", "todas-bancadas", "all"):
        return list(benches.values()), None
    if text.isdigit() and text in benches:
        return [benches[text]], None
    return [], f"ERRO: bancada '{bench}' nao encontrada. Use **listar bancadas**."


def popen_host_python(cmd, *, base_dir: str):
    try:
        subprocess.Popen(cmd, cwd=base_dir)
        return True, None
    except Exception as exc:
        return False, f"Falha ao executar comando: {exc}"


def build_log_sequence_csv_rows(actions: list[dict]) -> list[dict[str, str]]:
    rows = []
    for index, item in enumerate(actions, start=1):
        action = item.get("acao") or {}
        action_type = str(action.get("tipo", "")).strip().lower()
        if not action_type:
            continue
        row = {
            "tipo": action_type,
            "label": f"passo_{index:02d}_{action_type}",
            "x": "",
            "y": "",
            "x1": "",
            "y1": "",
            "x2": "",
            "y2": "",
            "duracao_ms": "",
            "duracao_s": "",
            "espera_s": "1.0",
            "texto": "",
            "keyevent": "",
            "device_path": "",
            "output_name": "",
        }
        if action_type in {"tap", "long_press"}:
            row["x"] = str(action.get("x", ""))
            row["y"] = str(action.get("y", ""))
            if action_type == "long_press":
                row["duracao_s"] = str(action.get("duracao_s", "1.0"))
        elif action_type == "swipe":
            row["x1"] = str(action.get("x1", ""))
            row["y1"] = str(action.get("y1", ""))
            row["x2"] = str(action.get("x2", ""))
            row["y2"] = str(action.get("y2", ""))
            row["duracao_ms"] = str(action.get("duracao_ms", "300"))
        else:
            continue
        rows.append(row)
    return rows


def export_global_log_sequence(
    category: str,
    test_name: str,
    serial: str,
    *,
    data_root: str,
    csv_path: str,
    raw_json_path: str,
    meta_json_path: str,
) -> tuple[bool, str]:
    actions_path = str(tester_actions_path(category, test_name))
    if not os.path.exists(actions_path):
        return False, "acoes.json da sequencia de logs ainda nao foi gerado."
    try:
        with open(actions_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception as exc:
        return False, f"Falha ao ler acoes.json da sequencia de logs: {exc}"

    actions = raw.get("acoes") if isinstance(raw, dict) else None
    if not isinstance(actions, list) or not actions:
        return False, "Nenhuma acao valida encontrada na sequencia gravada."
    rows = build_log_sequence_csv_rows(actions)
    if not rows:
        return False, "A sequencia gravada nao gerou taps/swipes/long press exportaveis."

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    fieldnames = [
        "tipo", "label", "x", "y", "x1", "y1", "x2", "y2", "duracao_ms", "duracao_s",
        "espera_s", "texto", "keyevent", "device_path", "output_name",
    ]
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        with open(raw_json_path, "w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)
        meta = {
            "categoria_origem": category,
            "teste_origem": test_name,
            "serial": serial,
            "exportado_em": datetime.now().isoformat(),
            "total_passos": len(rows),
        }
        with open(meta_json_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        return False, f"Falha ao salvar a sequencia global de logs: {exc}"
    return True, f"Sequencia global de coleta de logs salva em `{csv_path}`."


def update_bench_status(
    serial,
    status,
    *,
    category=None,
    test_name=None,
    data_root: str,
    status_lock,
    error_logger: Callable[[str], None],
) -> None:
    try:
        with status_lock:
            status_dir = os.path.join(data_root, category, test_name) if category and test_name else None
            if category and test_name:
                status_dir = os.path.dirname(str(tester_status_file_path(category, test_name, serial)))
            if not status_dir:
                return
            os.makedirs(status_dir, exist_ok=True)
            status_file = str(tester_status_file_path(category, test_name, serial))
            data = {}
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as handle:
                    try:
                        data = json.load(handle)
                    except json.JSONDecodeError:
                        data = {}
            data.update(
                {
                    "status": status,
                    "teste": f"{category}/{test_name}" if category and test_name else None,
                    "atualizado_em": datetime.now().isoformat(),
                    "serial": serial,
                }
            )
            with open(status_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        error_logger(f"ERRO: falha ao atualizar status da bancada {serial}: {exc}")


def read_serial_status(serial: str, *, data_root: str):
    latest = None
    latest_ts = None
    for root, _, files in os.walk(DATA_ROOT):
        for name in files:
            if name != f"{serial}.json" and name != f"status_{serial}.json":
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            ts = data.get("atualizado_em") or data.get("inicio")
            if ts is None:
                try:
                    ts = os.path.getmtime(path)
                except Exception:
                    ts = None
            if latest_ts is None or str(ts) > str(latest_ts):
                latest_ts = ts
                latest = data
    return latest


def capture_radio_logs_for_test(category: str, test_name: str, serial: str, *, reason: str = "captura_manual_chat"):
    from vwait.entrypoints.cli.run_test import capturar_logs_teste

    return capturar_logs_teste(category, test_name, serial, motivo=reason, limpar_antes=False)


def capture_radio_log_command(
    text: str,
    *,
    list_benches_fn,
    extract_bench_fn,
    select_bench_fn,
    extract_test_token_fn,
    resolve_test_fn,
    list_categories_fn,
    list_tests_fn,
    read_serial_status_fn,
    capture_logs_fn,
) -> str:
    benches = list_benches_fn()
    bench = extract_bench_fn(text)
    serials, error = select_bench_fn(bench, benches)
    if error:
        return error
    if len(serials) != 1:
        return "Aviso: informe uma bancada numerada para capturar logs do radio."
    serial = serials[0]
    token = extract_test_token_fn(text)
    category = None
    test_name = None
    if token:
        category, test_name = resolve_test_fn(token)
        if category is None or test_name is None:
            for category_try in list_categories_fn():
                if token in list_tests_fn(category_try):
                    category, test_name = category_try, token
                    break
        if category is None or test_name is None:
            return f"ERRO: teste **{token}** nao encontrado em `Data/catalog/tester/*/`."
    else:
        latest = read_serial_status_fn(serial)
        test_ref = str((latest or {}).get("teste", "") or "").strip()
        if "/" in test_ref:
            category, test_name = test_ref.split("/", 1)
        else:
            return "Aviso: informe o teste ou uma bancada que ja tenha execucao registrada para capturar os logs."

    result = capture_logs_fn(category, test_name, serial)
    capture_status = str(result.get("status", "") or "")
    logs_dir = result.get("artifact_dir")
    error_logs = result.get("error")
    if capture_status == "capturado":
        return f"Logs do radio capturados em **Data/runs/tester/{category}/{test_name}/<run>/{logs_dir}**."
    if capture_status == "sem_artefatos":
        return f"Nenhum log novo encontrado. Pasta gerada em **Data/runs/tester/{category}/{test_name}/<run>/{logs_dir}**."
    return f"ERRO: falha ao capturar logs do radio: {error_logs or 'erro desconhecido'}"


def ollama_generate(
    prompt: str,
    *,
    ollama_url: str,
    ollama_model: str,
    ollama_keep_alive: str,
    num_predict: int,
    temperature: float,
    top_p: float,
    num_ctx: int,
    requests_module,
    resolve_ollama_cli: Callable[[], str],
    timeout_s: int = 12,
    allow_cli: bool = True,
) -> str | None:
    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": ollama_keep_alive,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": num_ctx,
        },
    }
    urls = [ollama_url]
    if "localhost" in ollama_url:
        urls.append(ollama_url.replace("localhost", "127.0.0.1"))
    if requests_module is not None:
        for url in urls:
            try:
                response = requests_module.post(f"{url}/api/generate", json=payload, timeout=timeout_s)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip() or None
            except Exception:
                pass
    for url in urls:
        try:
            req = urllib.request.Request(
                f"{url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                body = response.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                return data.get("response", "").strip() or None
        except Exception:
            pass
    if allow_cli:
        try:
            result = subprocess.run(
                [resolve_ollama_cli(), "run", ollama_model],
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_s,
            )
            if result.returncode == 0:
                output = (result.stdout or "").strip()
                return output or None
        except Exception:
            pass
    return None


def llm_command(text: str, tests_available: list[str], categories: list[str], *, ollama_generate_fn) -> str | None:
    prompt = f"""
Classifique em JSON.
Frase: "{text}"
Comandos: executar/rodar, gravar/coletar, processar, apagar/deletar, listar categorias, listar testes, listar bancadas, resetar, pausar, retomar, parar.
Categorias: {categories}
Testes: {tests_available[:25]}
Formato:
{{"acao":"executar|gravar|processar|apagar|listar_categorias|listar_testes|listar_bancadas|resetar|pausar|retomar|parar|nenhuma",
  "teste":"audio_1",
  "categoria":"audio",
  "bancada":"1|todas|",
  "confidence":0.0}}
""".strip()
    try:
        response = ollama_generate_fn(prompt, timeout_s=6, allow_cli=False)
        if not response:
            return None
        parsed = json.loads(response)
    except Exception:
        return None
    if parsed.get("confidence", 0) < 0.6:
        return None
    action = parsed.get("acao", "")
    test_name = parsed.get("teste", "")
    category = parsed.get("categoria", "")
    bench = parsed.get("bancada", "")
    if action == "executar":
        return f"executar {test_name} na bancada {bench}".strip()
    if action == "gravar":
        return f"gravar {test_name} na bancada {bench}".strip()
    if action == "processar":
        return f"processar {test_name}".strip()
    if action == "apagar":
        return f"apagar {test_name}".strip()
    if action == "listar_categorias":
        return "listar categorias"
    if action == "listar_testes":
        return f"listar testes de {category}".strip()
    if action == "listar_bancadas":
        return "listar bancadas"
    if action == "resetar":
        return f"resetar {test_name} na bancada {bench}".strip()
    if action == "pausar":
        return "pausar"
    if action == "retomar":
        return "retomar"
    if action == "parar":
        return "parar"
    return None


def llm_chat_response(text: str, *, ollama_generate_fn) -> str | None:
    prompt = f"""
Responda em pt-BR com no maximo 2 frases.
Se a pergunta for sobre uso, de 1 exemplo de comando.
Usuario: "{text}"
Assistente:
""".strip()
    try:
        return ollama_generate_fn(prompt, timeout_s=4, allow_cli=False) or None
    except Exception:
        return None


def resolve_command_with_llm_or_fallback(text: str, *, list_categories_fn, list_tests_fn, llm_command_fn, interpret_command_fn) -> str:
    try:
        categories = list_categories_fn()
        tests = []
        for category in categories:
            tests.extend(list_tests_fn(category))
        command = llm_command_fn(text, tests, categories)
        if command:
            return interpret_command_fn(command)
    except Exception:
        pass
    return interpret_command_fn(text)


def ensure_execution_dataset(category: str, test_name: str, *, data_root: str, process_script: str, base_dir: str, logger: Callable[[str, str], str]) -> tuple[bool, str]:
    test_path = os.path.join(data_root, category, test_name)
    dataset_path = os.path.join(test_path, "dataset.csv")
    os.makedirs(test_path, exist_ok=True)
    if not os.path.exists(dataset_path):
        logger(f"⚙️ Dataset não encontrado para {category}/{test_name}, gerando automaticamente...", "yellow")
        try:
            proc_dataset = subprocess.run(
                [sys.executable, process_script, category, test_name],
                cwd=base_dir,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            return False, f"ERRO: falha ao processar dataset de {category}/{test_name}: {exc}"
        if proc_dataset.returncode != 0 or not os.path.exists(dataset_path):
            details = "\n".join(part.strip() for part in [proc_dataset.stdout, proc_dataset.stderr] if part and part.strip())
            if details:
                return False, f"ERRO: falha ao gerar dataset de {category}/{test_name}.\n{details}"
            return False, f"ERRO: o dataset de {category}/{test_name} nao foi gerado."
        logger("✅ Dataset gerado com sucesso.", "green")
    return True, ""


def append_execution_log(log_path, entry, *, error_logger: Callable[[str], None]) -> None:
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = []
        data.append(entry)
        with open(log_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        error_logger(f"⚠️ Falha ao registrar log: {exc}")


def start_execution_on_serial(
    category: str,
    test_name: str,
    serial: str,
    *,
    bench_label: str | None,
    data_root: str,
    run_script: str,
    base_dir: str,
    read_serial_status_fn,
    update_bench_status_fn,
    append_execution_log_fn,
    logger: Callable[[str, str], str],
    session_state,
    conversation_mode: bool,
    rerun,
) -> str:
    test_path = os.path.join(data_root, category, test_name)
    log_path = os.path.join(test_path, "execucao_log.json")
    current_status = read_serial_status_fn(serial) or {}
    if str(current_status.get("status", "")).lower() == "executando":
        return f"Aviso: a bancada `{serial}` ja esta executando outro teste."

    update_bench_status_fn(serial, "executando", category=category, test_name=test_name)
    append_execution_log_fn(
        log_path,
        {
            "acao": "execucao_iniciada",
            "categoria": category,
            "teste": test_name,
            "serial": serial,
            "inicio": datetime.now().isoformat(),
        },
    )
    cmd = [sys.executable, run_script, category, test_name, "--serial", serial]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=base_dir,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def _monitor_process(process, serial_value, category_value, test_value):
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                update_bench_status_fn(serial_value, "erro", category=category_value, test_name=test_value)
                logger(f"ERRO: execucao do teste {category_value}/{test_value} falhou na bancada {serial_value}.", "red")
                print(stdout.decode(errors="ignore"))
                print(stderr.decode(errors="ignore"))
                if conversation_mode and "chat_history" in session_state:
                    session_state.chat_history.append(
                        {"role": "assistant", "content": f"ERRO: o teste **{category_value}/{test_value}** falhou na bancada `{serial_value}`."}
                    )
            else:
                update_bench_status_fn(serial_value, "finalizado", category=category_value, test_name=test_value)
                logger(f"OK: teste {category_value}/{test_value} finalizado na bancada {serial_value}.", "green")
                if conversation_mode and "chat_history" in session_state:
                    session_state.chat_history.append(
                        {"role": "assistant", "content": f"OK: teste **{category_value}/{test_value}** finalizado na bancada `{serial_value}`."}
                    )
                try:
                    rerun()
                except Exception:
                    pass

        threading.Thread(target=_monitor_process, args=(proc, serial, category, test_name), daemon=True).start()
        session_state.execucoes_ativas.append(
            {
                "serial": serial,
                "categoria": category,
                "nome_teste": test_name,
                "status_file": os.path.join(data_root, category, test_name, f"status_{serial}.json"),
                "proc": proc,
            }
        )
        prefix = f"{bench_label}: " if bench_label else ""
        logger(f"🚀 Teste {category}/{test_name} iniciado em {serial} (PID={proc.pid})", "cyan")
        return f"{prefix}Executando **{category}/{test_name}** na bancada `{serial}` em background..."
    except Exception as exc:
        update_bench_status_fn(serial, "erro", category=category, test_name=test_name)
        return f"ERRO: falha ao iniciar execucao na bancada `{serial}`: {exc}"


def run_parallel_tests(
    executions: list[dict[str, str]],
    *,
    list_benches_fn,
    ensure_execution_dataset_fn,
    start_execution_on_serial_fn,
) -> str:
    if len(executions) < 2:
        return "Aviso: informe pelo menos duas execucoes para rodar em paralelo."
    benches = list_benches_fn()
    if len(benches) < 2:
        return "ERRO: conecte pelo menos duas bancadas para executar testes em paralelo."
    used_serials = set()
    resolved: list[dict[str, str]] = []
    for execution in executions:
        bench_num = str(execution.get("bancada", "")).strip()
        if bench_num not in benches:
            return f"ERRO: bancada '{bench_num}' nao encontrada. Use **listar bancadas**."
        if bench_num in used_serials:
            return "ERRO: nao e permitido usar a mesma bancada em duas execucoes paralelas."
        used_serials.add(bench_num)
        category = str(execution.get("categoria", "")).strip()
        test_name = str(execution.get("teste", "")).strip()
        ok_dataset, error_dataset = ensure_execution_dataset_fn(category, test_name)
        if not ok_dataset:
            return error_dataset or f"ERRO: falha ao preparar dataset de {category}/{test_name}."
        resolved.append(
            {
                "categoria": category,
                "teste": test_name,
                "serial": benches[bench_num],
                "label": str(execution.get("label", f"Bancada {bench_num}")),
            }
        )
    responses = ["Executando testes em paralelo:"]
    for execution in resolved:
        responses.append(
            start_execution_on_serial_fn(
                execution["categoria"],
                execution["teste"],
                execution["serial"],
                bench_label=execution["label"],
            )
        )
    return "\n".join(responses)
