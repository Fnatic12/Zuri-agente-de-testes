def normalize_post_speech(
    text: str,
    *,
    replace_number_words_fn,
    norm_fn,
    extract_test_token_fn,
    extract_bench_fn,
    resolve_test_fn,
) -> str:
    replacements = {
        "executa": "executar",
        "executarr": "executar",
        "executtar": "executar",
        "ezecutar": "executar",
        "rode": "rodar",
        "voltar ": "resetar ",
        "volta ": "resetar ",
        "reset ": "resetar ",
        "geral um": "geral 1",
        "geral dois": "geral 2",
        "geral tres": "geral 3",
        "bancada um": "bancada 1",
        "bancada dois": "bancada 2",
        "bancada três": "bancada 3",
        "na bancada um": "na bancada 1",
        "na bancada dois": "na bancada 2",
        "na bancada três": "na bancada 3",
        "na ba": "",
        "na ban": "",
        "na banca": "",
        "na bancada": "",
        "rodar todos os teste": "rodar todos os testes",
        "listar a bancada": "listar bancadas",
        "listar bancada": "listar bancadas",
    }
    normalized = text.strip().lower()
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    compact = replace_number_words_fn(norm_fn(normalized))

    import re

    if len(re.findall(r"\b(executar|rodar|testar)\b", compact)) >= 2 and len(re.findall(r"\bbancada\s+\d+\b", compact)) >= 2:
        return normalized

    token = extract_test_token_fn(compact)
    bench = extract_bench_fn(compact)

    if any(part in compact for part in ["executar", "rodar", "testar", "rodar o teste"]):
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"executar {test_name}" + (f" na bancada {bench}" if bench else "")

    if any(part in compact for part in ["gravar", "coletar", "capturar"]):
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"gravar {test_name}" + (f" na bancada {bench}" if bench else "")

    if "processar" in compact:
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"processar {test_name}"

    if any(part in compact for part in ["listar bancada", "listar bancadas", "mostra bancadas", "ver bancadas"]):
        return "listar bancadas"

    return normalized
