import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from typing import Callable


def start_recording_flow(session_state) -> str:
    session_state.pending_gravacao = {"step": "categoria"}
    return "Qual categoria voce quer gravar?"


def is_log_sequence_command(text: str, *, norm_fn: Callable[[str], str]) -> bool:
    text_norm = norm_fn(text)
    return (
        any(token in text_norm for token in ["gravar", "grave", "coletar", "colete", "capturar"])
        and "sequencia" in text_norm
        and "log" in text_norm
        and any(token in text_norm for token in ["padrao", "global", "coleta"])
    )


def continue_recording_flow(
    response: str,
    *,
    session_state,
    list_benches_fn: Callable[[], dict],
    extract_bench_fn: Callable[[str], str | None],
    record_test_fn: Callable[[str, str, str | None], str],
) -> str:
    pending = session_state.pending_gravacao or {"step": "categoria"}
    step = pending.get("step")

    if step == "categoria":
        category = response.strip().lower().replace(" ", "_")
        if not category:
            return "Informe a categoria do teste."
        pending["categoria"] = category
        pending["step"] = "nome"
        session_state.pending_gravacao = pending
        return "Qual nome do teste voce quer gravar?"

    if step == "nome":
        name = response.strip().lower().replace(" ", "_")
        if not name:
            return "Informe o nome do teste."
        pending["nome"] = name
        benches = list_benches_fn()
        if len(benches) > 1:
            pending["step"] = "bancada"
            session_state.pending_gravacao = pending
            return "Qual bancada voce esta? (ex: 1, 2, 3)"
        session_state.pending_gravacao = None
        return record_test_fn(pending["categoria"], pending["nome"], None)

    if step == "bancada":
        bench = extract_bench_fn(response)
        if not bench:
            return "Informe a bancada (ex: 1, 2, 3)."
        session_state.pending_gravacao = None
        return record_test_fn(pending["categoria"], pending["nome"], bench)

    session_state.pending_gravacao = None
    return "Nao entendi. Tente novamente."


def adb_cmd(*, adb_path: str, serial=None):
    if serial:
        return [adb_path, "-s", serial]
    return [adb_path]


def save_partial_result(
    category,
    test_name,
    serial=None,
    *,
    data_root: str,
    adb_path: str,
) -> str:
    base_dir = os.path.join(data_root, category, test_name)
    expected_dir = os.path.join(base_dir, "esperados")
    os.makedirs(expected_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_name = f"esperado_{ts}.png"
    image_path = os.path.join(expected_dir, image_name)
    try:
        cmd = adb_cmd(adb_path=adb_path, serial=serial) + ["exec-out", "screencap", "-p"]
        with open(image_path, "wb") as handle:
            subprocess.run(cmd, stdout=handle, stderr=subprocess.PIPE)
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            return f"Resultado esperado salvo: {image_name}"
        return "Falha ao salvar resultado esperado."
    except Exception as exc:
        return f"Falha ao salvar resultado esperado: {exc}"


def record_test(
    category,
    test_name,
    bench: str | None = None,
    *,
    project_root: str,
    collector_script: str,
    list_benches_fn: Callable[[], dict],
    select_bench_fn: Callable[[str | None, dict], tuple[list, str | None]],
    popen_host_python_fn: Callable[[list[str]], tuple[bool, str | None]],
) -> str:
    stop_path = os.path.join(project_root, "stop.flag")
    if os.path.exists(stop_path):
        try:
            os.remove(stop_path)
        except Exception:
            pass

    benches = list_benches_fn()
    serials, error = select_bench_fn(bench, benches)
    if error:
        return error

    responses = []
    for serial in serials:
        cmd = ["python", collector_script, category, test_name, "--serial", serial]
        ok, message = popen_host_python_fn(cmd)
        if ok:
            responses.append(f"Gravando **{category}/{test_name}** na bancada `{serial}`...")
        else:
            responses.append(f"ERRO: {message}")
    return "\n".join(responses)


def finalize_recording(
    *,
    project_root: str,
    session_state,
    category=None,
    test_name=None,
    serial=None,
    global_log_sequence_category: str,
    global_log_sequence_test: str,
) -> str:
    stop_path = os.path.join(project_root, "stop.flag")
    try:
        with open(stop_path, "w") as handle:
            handle.write("stop")

        def _cleanup():
            try:
                time.sleep(15)
                if os.path.exists(stop_path):
                    os.remove(stop_path)
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()
        if category and test_name and serial:
            if category == global_log_sequence_category and test_name == global_log_sequence_test:
                session_state.finalizacoes_pendentes.append(
                    {"categoria": category, "nome": test_name, "serial": serial, "mode": "global_log_sequence"}
                )
            else:
                session_state.finalizacoes_pendentes.append((category, test_name, serial))
        session_state.coleta_atual = None
        if category == global_log_sequence_category and test_name == global_log_sequence_test:
            return (
                "Finalizando gravacao da sequencia de log... "
                "apos o print final, vou exportar automaticamente para o arquivo global."
            )
        return "Finalizando gravacao... toque na tela do radio para capturar o print final."
    except Exception as exc:
        return f"Falha ao finalizar gravacao: {exc}"


def cancel_recording(
    *,
    project_root: str,
    data_root: str,
    session_state,
    global_log_sequence_category: str,
    global_log_sequence_test: str,
    category=None,
    test_name=None,
) -> str:
    if category and test_name:
        try:
            path = os.path.join(data_root, category, test_name)
            if os.path.exists(path):
                shutil.rmtree(path)
        except Exception:
            pass
    stop_path = os.path.join(project_root, "stop.flag")
    try:
        with open(stop_path, "w") as handle:
            handle.write("stop")
    except Exception:
        pass
    session_state.coleta_atual = None
    if category == global_log_sequence_category and test_name == global_log_sequence_test:
        session_state.log_sequence_recording = None
    return "Gravacao cancelada e teste removido."


def process_test(category, test_name, *, process_script: str, popen_host_python_fn: Callable[[list[str]], tuple[bool, str | None]]) -> str:
    cmd = ["python", process_script, category, test_name]
    ok, message = popen_host_python_fn(cmd)
    if ok:
        return f"Processando dataset de **{category}/{test_name}**..."
    return f"ERRO: {message}"


def delete_test(category, test_name, *, data_root: str) -> str:
    path = os.path.join(data_root, category, test_name)
    if os.path.exists(path):
        shutil.rmtree(path)
        return f"Teste **{category}/{test_name}** apagado com sucesso."
    return f"ERRO: teste {category}/{test_name} nao encontrado."


def list_categories(*, data_root: str):
    if not os.path.isdir(data_root):
        return []
    return [category for category in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, category))]


def list_tests(category, *, data_root: str):
    category_path = os.path.join(data_root, category)
    if os.path.isdir(category_path):
        return [test_name for test_name in os.listdir(category_path) if os.path.isdir(os.path.join(category_path, test_name))]
    return []


def pause_execution(*, pause_flag_path: str) -> str:
    try:
        with open(pause_flag_path, "w") as handle:
            handle.write("PAUSED")
        return "Execucao pausada. O runner sera interrompido no proximo checkpoint."
    except Exception as exc:
        return f"ERRO: falha ao pausar execucao: {exc}"


def resume_execution(*, pause_flag_path: str) -> str:
    try:
        if os.path.exists(pause_flag_path):
            os.remove(pause_flag_path)
            return "Execucao retomada."
        return "Aviso: nenhuma execucao estava pausada."
    except Exception as exc:
        return f"ERRO: falha ao retomar execucao: {exc}"


def stop_execution(*, project_root: str) -> str:
    stop_path = os.path.join(project_root, "stop.flag")
    try:
        with open(stop_path, "w") as handle:
            handle.write("STOP")
        return "Execucao interrompida completamente."
    except Exception as exc:
        return f"ERRO: falha ao interromper execucao: {exc}"

