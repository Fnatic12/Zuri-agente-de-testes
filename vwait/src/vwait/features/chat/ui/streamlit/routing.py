import random
import re
import subprocess
from typing import Callable


def resolve_navigation_command(
    text: str,
    *,
    normalize: Callable[[str], str],
    replace_number_words: Callable[[str], str],
    select_page: Callable[[str], None],
    open_menu_tester: Callable[[], str],
    dashboard_page: str,
    logs_page: str,
    failures_page: str,
    hmi_page: str,
    brain_page: str,
    chat_page: str,
) -> str | None:
    text_norm = replace_number_words(normalize(text))
    navigation_intent = any(
        snippet in text_norm
        for snippet in [
            "abrir",
            "abre",
            "abra",
            "ir para",
            "ir pro",
            "ir pra",
            "vai para",
            "acesse",
            "acessar",
            "mostrar",
            "mostra",
        ]
    )
    direct_commands = {
        "dashboard",
        "painel de logs",
        "logs do radio",
        "painel de logs do radio",
        "controle de falhas",
        "falhas",
        "painel de falhas",
        "menu tester",
        "menu testers",
        "menu dos testers",
        "validacao hmi",
        "validar hmi",
        "hmi",
        "mapa neural",
        "mapa da ia",
        "cerebro da ia",
        "cerebro",
    }
    if not navigation_intent and text_norm not in direct_commands:
        return None

    if "dashboard" in text_norm:
        select_page(dashboard_page)
        return "Abrindo o dashboard."

    if ("painel de logs" in text_norm or "logs do radio" in text_norm) and any(
        token in text_norm for token in ["abrir", "abre", "abra", "mostrar", "mostra", "painel", "logs"]
    ):
        select_page(logs_page)
        return "Abrindo o painel de logs."

    if "falha" in text_norm and any(
        token in text_norm
        for token in ["abrir", "abre", "abra", "mostrar", "mostra", "painel", "controle", "falhas"]
    ):
        select_page(failures_page)
        return "Abrindo o controle de falhas."

    if "hmi" in text_norm and any(token in text_norm for token in ["valid", "validacao", "validar", "hmi"]):
        select_page(hmi_page)
        return "Abrindo a validação HMI."

    if any(token in text_norm for token in ["mapa neural", "mapa da ia", "cerebro da ia", "cerebro"]):
        select_page(brain_page)
        return "Abrindo o mapa neural da IA."

    if re.search(r"\bmenu\s+(dos?\s+)?testers?\b", text_norm) or "menu tester" in text_norm:
        select_page(chat_page)
        return open_menu_tester()

    return None


def interpret_command(
    command: str,
    *,
    session_state,
    normalize: Callable[[str], str],
    has_any: Callable[[str, list[str]], bool],
    resolve_navigation,
    list_categories: Callable[[], list[str]],
    list_tests: Callable[[str], list[str]],
    format_benches: Callable[[dict], str],
    list_benches: Callable[[], dict],
    extract_parallel_executions,
    run_parallel_tests: Callable[[list[dict[str, str]]], str],
    extract_category: Callable[[str], str | None],
    extract_test_token: Callable[[str], str | None],
    resolve_test: Callable[[str], tuple[str | None, str | None]],
    execute_test: Callable[[str, str, str | None], str],
    extract_bench: Callable[[str], str | None],
    is_log_sequence_command: Callable[[str], bool],
    record_global_log_sequence: Callable[[str | None], str],
    record_test: Callable[[str, str, str | None], str],
    process_test: Callable[[str, str], str],
    delete_test: Callable[[str, str], str],
    capture_radio_logs: Callable[[str], str],
    finalize_log_sequence: Callable[[], str],
    pause_execution: Callable[[], str],
    resume_execution: Callable[[], str],
    stop_execution: Callable[[], str],
    execute_keywords: list[str],
    record_keywords: list[str],
    process_keywords: list[str],
    delete_keywords: list[str],
    list_keywords: list[str],
    help_keywords: list[str],
    run_script: str,
    base_dir: str,
) -> str:
    text = command.strip()
    text_norm = normalize(text)

    navigation_response = resolve_navigation(text)
    if navigation_response:
        return navigation_response

    if has_any(text_norm, help_keywords):
        return (
            "**Comandos suportados**\n"
            "- **executar/rodar** `<teste>` [na bancada N|todas]\n"
            "- **executar em paralelo** `executar teste_x na bancada 1 e executar teste_y na bancada 2`\n"
            "- **gravar/coletar** `<teste>` [na bancada N|todas]\n"
            "- **capturar log** [do `<teste>`] [na bancada N]\n"
            "- **gravar sequencia padrao de coleta de logs** [na bancada N]\n"
            "- **processar** `<teste>`\n"
            "- **apagar/deletar/remover** `<teste>`\n"
            "- **listar/mostrar** categorias | testes [de <categoria>]\n"
            "- **listar bancadas**\n"
            "- **abrir** dashboard | mapa neural | painel de logs | controle de falhas | menu tester | validacao HMI\n"
            "Ex.: `execute o teste audio_1 na bancada 2`"
        )

    if session_state.log_sequence_recording and any(
        token in text_norm
        for token in [
            "finalizar gravacao da sequencia de log",
            "finalizar sequencia de log",
            "salvar sequencia de log",
            "encerrar sequencia de log",
            "parar gravacao da sequencia de log",
        ]
    ):
        return finalize_log_sequence()

    if has_any(text_norm, ["listar bancadas", "mostrar bancadas", "listar devices", "mostrar devices"]) or (
        has_any(text_norm, list_keywords) and any(token in text_norm for token in ["bancada", "bancadas", "devices", "dispositivos"])
    ):
        return format_benches(list_benches())

    if any(
        token in text_norm
        for token in [
            "capturar log",
            "capturar logs",
            "coletar log",
            "coletar logs",
            "capturar log do radio",
            "capturar logs do radio",
        ]
    ):
        return capture_radio_logs(text)

    if has_any(text_norm, execute_keywords):
        parallel_runs, parallel_error = extract_parallel_executions(text)
        if parallel_error:
            return parallel_error
        if parallel_runs:
            return run_parallel_tests(parallel_runs)

        if re.search(r"todos\s+os\s+testes\s+da\s+categoria", text_norm):
            category = extract_category(text)
            if not category:
                return "Aviso: especifique a categoria (ex: rodar todos os testes da categoria audio)."
            tests = list_tests(category)
            if not tests:
                return f"A categoria **{category}** nao possui testes."
            bench = extract_bench(text)
            responses = [f"Rodando todos os testes da categoria **{category}** na bancada {bench or '(padrao)'}..."]
            for test_name in tests:
                responses.append(execute_test(category, test_name, bench))
            return "\n".join(responses)

        token = extract_test_token(text)
        if token:
            category, name = resolve_test(token)
            if category and name:
                return execute_test(category, name, extract_bench(text))
            for category_try in list_categories():
                if token in list_tests(category_try):
                    return execute_test(category_try, token, extract_bench(text))
            return f"ERRO: teste **{token}** nao encontrado em `Data/*/`."
        return "Aviso: especifique o teste a executar (ex: `executar teste geral_1 na bancada 1`)."

    if has_any(text_norm, record_keywords):
        if is_log_sequence_command(text):
            return record_global_log_sequence(extract_bench(text))
        token = extract_test_token(text)
        if token:
            if "_" not in token:
                return "Aviso: use o formato categoria_nome (ex: audio_3)."
            category, _name = token.split("_", 1)
            return record_test(category, token, extract_bench(text))
        return "Aviso: especifique o teste (ex: `gravar audio_1 na bancada 1`)."

    if has_any(text_norm, process_keywords):
        token = extract_test_token(text)
        if token:
            if "_" in token:
                category, _name = token.split("_", 1)
                return process_test(category, token)
            return "Aviso: use o formato categoria_nome (ex: audio_3)."
        return "Aviso: especifique o teste (ex: `processar audio_1`)."

    if has_any(text_norm, delete_keywords):
        token = extract_test_token(text)
        if token:
            category, test_name = resolve_test(token)
            if category and test_name:
                return delete_test(category, test_name)
            return f"ERRO: nao encontrei o teste **{token}** em `Data/*/`."
        return "Aviso: especifique o teste (ex: `apagar audio_1`)."

    if has_any(text_norm, list_keywords):
        category = extract_category(text)
        if category:
            tests = list_tests(category)
            if tests:
                return f"Testes em **{category}**:\n- " + "\n- ".join(tests)
            return f"A categoria **{category}** nao possui testes."
        categories = list_categories()
        if categories:
            return "Categorias disponiveis:\n- " + "\n- ".join(categories)
        return "Nenhuma categoria encontrada em `Data/`."

    if any(normalize(token) in text_norm for token in ["reset", "resetar", "reverter", "restaurar", "desfazer"]):
        token = extract_test_token(text)
        if token:
            category, name = resolve_test(token)
            if category and name:
                bench = extract_bench(text)
                try:
                    cmd = ["python", run_script, "--reset", category, name]
                    if bench:
                        cmd += ["--serial", bench]
                    subprocess.Popen(cmd, cwd=base_dir)
                    return f"Reset comportamental iniciado para **{category}/{name}** na bancada `{bench or 'padrao'}`."
                except Exception as exc:
                    return f"ERRO: falha ao iniciar reset: {exc}"
            return f"ERRO: teste **{token}** nao encontrado."
        return "Aviso: especifique o teste para resetar (ex: `reset geral_1 na bancada 1`)."

    if any(normalize(token) in text_norm for token in ["pausar", "pause", "parar teste", "interromper", "stop"]):
        return pause_execution()
    if any(normalize(token) in text_norm for token in ["retomar", "continuar", "resume", "seguir"]):
        return resume_execution()
    if any(normalize(token) in text_norm for token in ["cancelar", "encerrar", "finalizar", "stop all", "terminar"]):
        return stop_execution()
    return "ERRO: nao entendi o comando. Digite **ajuda** para ver exemplos."


def respond_conversational(
    command: str,
    *,
    session_state,
    normalize: Callable[[str], str],
    resolve_navigation,
    resolve_command: Callable[[str], str],
    llm_respond: Callable[[str], str | None],
    conversation_mode: bool,
    continue_recording_flow: Callable[[str], str],
    extract_test_token: Callable[[str], str | None],
    is_log_sequence_command: Callable[[str], bool],
    start_recording_flow: Callable[[], str],
    finalize_log_sequence: Callable[[], str],
) -> str:
    replacements = {
        "star bancadas": "listar bancadas",
        "esta bancadas": "listar bancadas",
        "instalar bancadas": "listar bancadas",
        "historia bancadas": "listar bancadas",
        "listar bancada": "listar bancadas",
        "listra bancadas": "listar bancadas",
        "ver bancadas": "listar bancadas",
        "mostra bancadas": "listar bancadas",
        "voltar": "resetar",
        "voltar teste": "resetar",
        "voltar o teste": "resetar",
        "voltar geral": "resetar geral",
        "volta geral": "resetar geral",
        "reset": "resetar",
        "refazer estado": "resetar",
    }
    for wrong, right in replacements.items():
        if wrong in command.lower():
            command = command.lower().replace(wrong, right)

    command_norm = normalize(command)
    if session_state.pending_gravacao is not None:
        return continue_recording_flow(command)

    navigation_response = resolve_navigation(command)
    if navigation_response:
        return navigation_response

    opening_phrases = ["Entendido", "Certo", "Perfeito", "Beleza", "Ok, ja vou cuidar disso"]
    execution_phrases = [
        "Iniciando o teste agora",
        "Rodando o caso de teste no radio",
        "Executando o cenario solicitado",
        "Comecando a sequencia de validacoes",
    ]
    collection_phrases = [
        "Iniciando gravacao",
        "Pode tocar na tela, estou coletando os gestos.",
        "Gravando as interacoes agora",
    ]
    processing_phrases = [
        "Gerando o dataset, aguarde um instante",
        "Transformando os logs em dados uteis",
        "Processando o dataset para voce",
    ]
    bench_phrases = [
        "Consultando bancadas ADB conectadas",
        "Um segundo, vou listar as bancadas disponiveis",
        "Beleza, verificando conexoes com as bancadas",
    ]
    help_phrases = [
        "Aqui esta o que posso fazer",
        "Claro! Aqui estao alguns comandos que voce pode usar",
        "Lista de comandos a disposicao",
    ]
    quick_responses = {
        "oi": "Ola! Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "ola": "Ola! Posso ajudar com testes ou explicar comandos. Ex.: `executar audio_1 na bancada 1`",
        "eai": "Fala! Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "e a?": "Fala! Se quiser rodar algo: `executar audio_1 na bancada 1`",
        "bom dia": "Bom dia! Posso ajudar com testes ou comandos.",
        "boa tarde": "Boa tarde! Posso ajudar com testes ou comandos.",
        "boa noite": "Boa noite! Posso ajudar com testes ou comandos.",
        "tudo bem": "Tudo sim! Posso ajudar com testes ou comandos.",
        "beleza": "Beleza! Posso ajudar com testes ou comandos.",
        "blz": "Blz! Posso ajudar com testes ou comandos.",
    }

    normalized_clean = re.sub(r"[^a-z0-9\s]", "", command_norm).strip()
    for greeting in quick_responses:
        if normalized_clean == greeting or normalized_clean.startswith(greeting + " "):
            session_state.chat_history.append({"role": "assistant", "content": quick_responses[greeting]})
            return ""

    if command_norm.startswith("zuri"):
        command_norm = command_norm.replace("zuri", "", 1).strip()

    if session_state.log_sequence_recording and any(
        token in command_norm
        for token in [
            "finalizar gravacao da sequencia de log",
            "finalizar sequencia de log",
            "salvar sequencia de log",
            "encerrar sequencia de log",
            "parar gravacao da sequencia de log",
        ]
    ):
        session_state.chat_history.append({"role": "assistant", "content": "Encerrando a gravacao da sequencia padrao de logs."})
        return finalize_log_sequence()

    if any(token in command_norm for token in ["listar bancadas", "ver bancadas", "bancadas conectadas"]):
        session_state.chat_history.append({"role": "assistant", "content": random.choice(bench_phrases)})
        return resolve_command("listar bancadas")

    if any(
        token in command_norm
        for token in [
            "capturar log",
            "capturar logs",
            "coletar log",
            "coletar logs",
            "capturar log do radio",
            "capturar logs do radio",
        ]
    ):
        session_state.chat_history.append({"role": "assistant", "content": "Capturando os logs do radio para a bancada solicitada."})
        return resolve_command(command)

    if any(token in command_norm for token in ["reset", "resetar", "reverter", "restaurar", "desfazer", "voltar estado inicial"]):
        session_state.chat_history.append({"role": "assistant", "content": f"{random.choice(opening_phrases)}. Restaurando estado inicial do teste..."})
        if extract_test_token(command) is None and "gravar" in command_norm:
            return start_recording_flow()
        return resolve_command(command)

    if any(token in command_norm for token in ["executar", "rodar", "testar", "rodar o teste"]):
        session_state.chat_history.append({"role": "assistant", "content": f"{random.choice(opening_phrases)} {random.choice(execution_phrases)}"})
        if extract_test_token(command) is None and "gravar" in command_norm:
            return start_recording_flow()
        return resolve_command(command)

    if any(token in command_norm for token in ["gravar teste", "gravar", "coletar teste", "coletar", "capturar"]):
        if is_log_sequence_command(command):
            session_state.chat_history.append({"role": "assistant", "content": "Iniciando a gravacao da sequencia padrao de coleta de logs."})
            return resolve_command(command)
        session_state.chat_history.append({"role": "assistant", "content": f"{random.choice(opening_phrases)} {random.choice(collection_phrases)}"})
        if extract_test_token(command) is None and "gravar" in command_norm:
            return start_recording_flow()
        return resolve_command(command)

    if any(token in command_norm for token in ["processar", "gerar dataset", "montar csv"]):
        session_state.chat_history.append({"role": "assistant", "content": f"{random.choice(opening_phrases)} {random.choice(processing_phrases)}"})
        if extract_test_token(command) is None and "gravar" in command_norm:
            return start_recording_flow()
        return resolve_command(command)

    if any(token in command_norm for token in ["ajuda", "comandos", "socorro", "me ajuda"]):
        session_state.chat_history.append({"role": "assistant", "content": random.choice(help_phrases)})
        return resolve_command("ajuda")

    llm_response = llm_respond(command) if conversation_mode else None
    if llm_response:
        session_state.chat_history.append({"role": "assistant", "content": llm_response})
        return ""

    session_state.chat_history.append(
        {"role": "assistant", "content": "Posso ajudar com comandos de testes. Ex.: `executar audio_1 na bancada 1`"}
    )
    return ""

