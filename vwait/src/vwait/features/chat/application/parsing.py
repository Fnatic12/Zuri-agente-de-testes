import re
import unicodedata
from difflib import SequenceMatcher
from typing import Callable

KW_EXECUTAR = [
    "executar", "execute", "rodar", "rode", "run", "iniciar teste",
    "inicia o teste", "começa o teste", "roda o teste", "faz o teste",
    "testa", "teste agora", "starta o teste", "começar teste", "faça o teste",
    "rodar tudo", "rodar todos", "rodar todos os testes", "executa tudo",
]

KW_GRAVAR = [
    "gravar", "grave", "coletar", "colete", "capturar", "record",
    "começar gravação", "iniciar gravação", "grava agora", "fazer gravação",
    "fazer coleta", "começar coleta", "startar gravação", "inicia a coleta",
    "começa a gravar", "grava o gesto", "grava o teste",
]

KW_PROCESS = [
    "processar", "processa", "pré-processar", "preprocessar", "pre", "gerar dataset",
    "processa o dataset", "gera o dataset", "montar dataset", "gerar base",
    "monta o csv", "gerar csv", "converter dados", "processa os dados",
]

KW_APAGAR = [
    "apagar", "apague", "deletar", "delete", "remover", "remova", "excluir", "exclua",
    "apaga", "apaga o teste", "deleta o teste", "limpa", "limpar teste", "remove o teste",
    "apagar teste", "excluir teste", "deleta tudo",
]

KW_LISTAR = [
    "listar", "liste", "mostrar", "mostre", "exibir", "exiba", "lista", "me mostra",
    "me exibe", "quais são", "ver", "ver lista", "ver testes", "mostra pra mim",
    "quero ver", "ver categorias", "mostrar categorias", "mostrar testes",
]

KW_BANCADAS = [
    "bancada", "bancadas", "devices", "dispositivos", "adb", "hardware conectado",
    "listar bancadas", "mostrar bancadas", "listar dispositivos", "mostrar dispositivos",
    "quais bancadas", "tem bancada", "quais estão conectadas", "ver bancadas",
    "ver dispositivos", "me mostra as bancadas", "fala as bancadas", "lista as bancadas",
]

KW_AJUDA = [
    "ajuda", "help", "comandos", "o que posso dizer", "fala os comandos",
    "me ajuda", "quais comandos", "mostra os comandos", "explica comandos",
    "fala os exemplos", "ensina", "socorro",
]

_NUM_PT = {
    "zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "três": "3",
    "quatro": "4", "cinco": "5", "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10",
    "onze": "11", "doze": "12", "treze": "13", "catorze": "14", "quatorze": "14", "quinze": "15",
    "dezesseis": "16", "dezessete": "17", "dezoito": "18", "dezenove": "19", "vinte": "20",
}


def norm(text: str) -> str:
    text = text.strip().lower()
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")


def replace_number_words(text: str) -> str:
    for key, value in _NUM_PT.items():
        text = re.sub(rf"\b{key}\b", value, text)
    return text


def normalize_token(text: str) -> str:
    text = norm(text)
    return re.sub(r"[\s_-]+", "", text)


def has_any(text_norm: str, terms: list[str]) -> bool:
    normalized_text = norm(text_norm)
    normalized_terms = [norm(term) for term in terms]
    for term in normalized_terms:
        ratio = SequenceMatcher(None, normalized_text, term).ratio()
        if term in normalized_text or ratio > 0.8:
            return True
    return False


def extract_bench(text: str) -> str | None:
    normalized = replace_number_words(norm(text))
    if re.search(r"\btodas(\s+as\s+)?bancadas\b", normalized) or re.search(r"\ball\b", normalized):
        return "todas"
    match = re.search(r"bancada\s*=\s*(\d+)", normalized)
    if match:
        return match.group(1)
    match = re.search(r"\bbancada\s*(\d+)\b", normalized)
    if match:
        return match.group(1)
    return None


def extract_test_token(text: str) -> str | None:
    normalized = replace_number_words(norm(text))
    match = re.search(r"\b([a-z0-9]+)[_\-]([0-9]+)\b", normalized)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    match = re.search(r"\b([a-z]+)(\d+)\b", normalized)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    match = re.search(r"\b([a-z]+)\s+(\d+)\b", normalized)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    return None


def extract_category(text: str, *, list_categories: Callable[[], list[str]]) -> str | None:
    normalized = norm(text)
    match = re.search(r"\bde\s+([a-z0-9_-]+)\b", normalized)
    categories = list_categories()
    if match and match.group(1) in categories:
        return match.group(1)
    for category in categories:
        if norm(category) in normalized:
            return category
    return None


def normalize_post_speech(
    text: str,
    *,
    replace_number_words_fn: Callable[[str], str],
    norm_fn: Callable[[str], str],
    extract_test_token_fn: Callable[[str], str | None],
    extract_bench_fn: Callable[[str], str | None],
    resolve_test_fn: Callable[[str], tuple[str | None, str | None]],
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

    transformed = replace_number_words_fn(norm_fn(normalized))

    if len(re.findall(r"\b(executar|rodar|testar)\b", transformed)) >= 2 and len(re.findall(r"\bbancada\s+\d+\b", transformed)) >= 2:
        return normalized

    token = extract_test_token_fn(transformed)
    bench = extract_bench_fn(transformed)

    if any(term in transformed for term in ["executar", "rodar", "testar", "rodar o teste"]):
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"executar {test_name}" + (f" na bancada {bench}" if bench else "")

    if any(term in transformed for term in ["gravar", "coletar", "capturar"]):
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"gravar {test_name}" + (f" na bancada {bench}" if bench else "")

    if "processar" in transformed:
        _category, name = resolve_test_fn(token) if token else (None, None)
        test_name = name or token
        if test_name:
            return f"processar {test_name}"

    if any(term in transformed for term in ["listar bancada", "listar bancadas", "mostra bancadas", "ver bancadas"]):
        return "listar bancadas"

    return normalized


def resolve_execution_from_chunk(
    text: str,
    *,
    extract_test_token_fn: Callable[[str], str | None],
    resolve_test_fn: Callable[[str], tuple[str | None, str | None]],
    list_categories_fn: Callable[[], list[str]],
    list_tests_fn: Callable[[str], list[str]],
) -> tuple[str | None, str | None, str | None]:
    token = extract_test_token_fn(text)
    if token:
        category, name = resolve_test_fn(token)
        if category and name:
            return category, name, None
        for category_try in list_categories_fn():
            if token in list_tests_fn(category_try):
                return category_try, token, None
        return None, None, f"ERRO: teste **{token}** nao encontrado em `Data/catalog/tester/*/`."
    return None, None, "Aviso: nao encontrei o nome do teste em um dos comandos paralelos."


def extract_parallel_executions(
    text: str,
    *,
    replace_number_words_fn: Callable[[str], str],
    norm_fn: Callable[[str], str],
    extract_bench_fn: Callable[[str], str | None],
    resolve_execution_chunk_fn: Callable[[str], tuple[str | None, str | None, str | None]],
) -> tuple[list[dict[str, str]] | None, str | None]:
    text_norm = replace_number_words_fn(norm_fn(text))
    parts = [
        part.strip(" ,.;")
        for part in re.split(r"\s+e\s+(?=(?:executar|rodar|testar)\b)", text_norm)
        if part.strip(" ,.;")
    ]
    execution_parts = [part for part in parts if re.search(r"\b(executar|rodar|testar)\b", part)]
    if len(execution_parts) < 2:
        return None, None

    executions: list[dict[str, str]] = []
    for index, part in enumerate(execution_parts, start=1):
        bench = extract_bench_fn(part)
        if not bench or bench == "todas":
            return [], f"Aviso: informe uma bancada numerada para cada execução paralela. Falha em Bancada {index}."

        category, name, error = resolve_execution_chunk_fn(part)
        if error:
            return [], error
        if category is None or name is None:
            return [], "Aviso: nao foi possivel resolver categoria e nome do teste em um dos comandos paralelos."

        executions.append(
            {"categoria": category, "teste": name, "bancada": bench, "label": f"Bancada {bench}"}
        )

    return executions, None
