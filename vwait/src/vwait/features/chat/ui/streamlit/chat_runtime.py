import json
import os

from vwait.core.paths import tester_expected_final_path


def record_global_log_sequence(
    bench: str | None = None,
    *,
    session_state,
    record_test_fn,
    list_benches_fn,
    select_bench_fn,
    global_log_sequence_category: str,
    global_log_sequence_test: str,
    global_log_sequence_csv: str,
) -> str:
    response = record_test_fn(global_log_sequence_category, global_log_sequence_test, bench)
    if response.startswith("ERRO:"):
        return response

    resolved_serial = None
    benches = list_benches_fn()
    serials, error = select_bench_fn(bench, benches)
    if not error and serials:
        resolved_serial = serials[0]

    session_state.log_sequence_recording = {
        "categoria": global_log_sequence_category,
        "nome": global_log_sequence_test,
        "bancada": resolved_serial or bench,
        "iniciado_em": __import__("datetime").datetime.now().isoformat(),
    }
    return (
        "Gravando **sequencia padrao de coleta de logs**. "
        "Quando terminar, use **finalizar gravacao da sequencia de log** ou clique em **Finalizar gravacao**. "
        f"O arquivo global sera salvo em `{global_log_sequence_csv}`."
    )


def finalize_global_log_sequence(
    *,
    session_state,
    finalize_recording_fn,
) -> str:
    recording = session_state.log_sequence_recording
    if not isinstance(recording, dict):
        return "Aviso: nao existe gravacao da sequencia de log em andamento."
    category = recording.get("categoria")
    name = recording.get("nome")
    bench = recording.get("bancada")
    if not isinstance(category, str) or not isinstance(name, str) or not isinstance(bench, str):
        return "Aviso: a gravacao da sequencia de log nao possui contexto suficiente para finalizar."
    return finalize_recording_fn(category=category, test_name=name, serial=bench)


def check_finalizations(
    *,
    session_state,
    data_root: str,
    export_global_log_sequence_fn,
) -> None:
    pending = list(session_state.finalizacoes_pendentes)
    remaining = []
    for item in pending:
        mode = category = name = serial = None
        if isinstance(item, dict):
            category = item.get("categoria") if isinstance(item.get("categoria"), str) and item.get("categoria") else None
            name = item.get("nome") if isinstance(item.get("nome"), str) and item.get("nome") else None
            serial = item.get("serial") if isinstance(item.get("serial"), str) and item.get("serial") else None
            mode = item.get("mode") if isinstance(item.get("mode"), str) and item.get("mode") else None
        else:
            try:
                category_raw, name_raw, serial_raw = item
            except Exception:
                continue
            category = category_raw if isinstance(category_raw, str) and category_raw else None
            name = name_raw if isinstance(name_raw, str) and name_raw else None
            serial = serial_raw if isinstance(serial_raw, str) and serial_raw else None
        if not category or not name:
            continue
        final_path = str(tester_expected_final_path(category, name))
        if os.path.exists(final_path):
            if mode == "global_log_sequence":
                if not serial:
                    session_state.chat_history.append(
                        {"role": "assistant", "content": "Coleta finalizada, mas o serial da gravacao da sequencia global nao foi encontrado."}
                    )
                    session_state.log_sequence_recording = None
                    continue
                ok, message = export_global_log_sequence_fn(category, name, serial)
                session_state.log_sequence_recording = None
                session_state.chat_history.append(
                    {"role": "assistant", "content": message if ok else f"Coleta finalizada, mas nao consegui exportar a sequencia global: {message}"}
                )
            else:
                session_state.chat_history.append(
                    {"role": "assistant", "content": f"Coleta finalizada: {category}/{name} (bancada {serial})."}
                )
        else:
            remaining.append(item)
    session_state.finalizacoes_pendentes = remaining


def check_finished_executions(*, session_state) -> None:
    active_runs = list(session_state.execucoes_ativas)
    remaining = []
    for item in active_runs:
        serial = item.get("serial")
        category = item.get("categoria")
        test_name = item.get("nome_teste")
        status_file = item.get("status_file")
        proc = item.get("proc")
        finished = False
        success = False
        try:
            if proc is not None and proc.poll() is not None:
                finished = True
                success = proc.returncode == 0
        except Exception:
            pass
        if not finished and status_file and os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as handle:
                    status_data = json.load(handle)
                current_status = str(status_data.get("status", "")).lower()
                if current_status in ("finalizado", "erro"):
                    finished = True
                    success = current_status == "finalizado"
            except Exception:
                pass
        if finished:
            if success:
                session_state.chat_history.append(
                    {"role": "assistant", "content": f"Teste {category}/{test_name} finalizado na bancada `{serial}`. Voce ja pode verificar o resultado no dashboard."}
                )
            else:
                session_state.chat_history.append(
                    {"role": "assistant", "content": f"Teste {category}/{test_name} finalizou com erro na bancada `{serial}`. Verifique os logs e o dashboard."}
                )
        else:
            remaining.append(item)
    session_state.execucoes_ativas = remaining
