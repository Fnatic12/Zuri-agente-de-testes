from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from shutil import which

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from ..domain import HEURISTICS, MAX_AI_CAPTURE_CHARS, MAX_AI_FILE_CHARS
from .captures import human_size, read_file_for_ai


def match_lines(text: str, pattern: str, limit: int = 6) -> list[str]:
    compiled = re.compile(pattern, re.IGNORECASE)
    matches = []
    for line in text.splitlines():
        if compiled.search(line):
            matches.append(line.strip())
        if len(matches) >= limit:
            break
    return matches


def scan_text_signals(text: str) -> dict:
    results = {}
    for label, patterns in HEURISTICS.items():
        lines = []
        for pattern in patterns:
            lines.extend(match_lines(text, pattern, limit=4))
            if len(lines) >= 6:
                break
        results[label] = {"count": len(lines), "lines": lines[:6]}
    return results


def scan_capture_signals(files: list[dict]) -> tuple[dict, list[dict]]:
    totals = {label: 0 for label in HEURISTICS}
    highlights = []
    for file_info in files:
        if not file_info["text_like"]:
            continue
        excerpt = read_file_for_ai(file_info["path"], max_chars=7000)
        signals = scan_text_signals(excerpt)
        file_score = sum(item["count"] for item in signals.values())
        for label, item in signals.items():
            totals[label] += int(item["count"])
        if file_score > 0:
            highlights.append(
                {
                    "arquivo": file_info["relpath"],
                    "score": file_score,
                    "signals": signals,
                }
            )
    highlights.sort(key=lambda item: (-int(item["score"]), item["arquivo"]))
    return totals, highlights[:12]


def build_capture_context(capture: dict) -> tuple[str, list[str]]:
    text_files = [file_info for file_info in capture["files"] if file_info["text_like"]][:20]
    ranked = sorted(
        text_files,
        key=lambda item: (
            -int(any(token in item["relpath"].lower() for token in ("tomb", "anr", "dropbox", "trace", "log"))),
            -int(item["size"]),
            item["relpath"].lower(),
        ),
    )

    sections = []
    used_files = []
    total_chars = 0
    for file_info in ranked:
        excerpt = read_file_for_ai(file_info["path"], max_chars=min(MAX_AI_FILE_CHARS, 7000))
        if not excerpt.strip():
            continue
        block = (
            f"\n### Arquivo: {file_info['relpath']}\n"
            f"Tamanho: {human_size(int(file_info['size']))}\n"
            f"Conteudo:\n{excerpt}\n"
        )
        if total_chars + len(block) > MAX_AI_CAPTURE_CHARS and sections:
            break
        sections.append(block)
        used_files.append(file_info["relpath"])
        total_chars += len(block)

    if not sections:
        return "Nenhum arquivo de texto legivel encontrado nesta captura.", []
    return "\n".join(sections), used_files


def analysis_prompt_for_file(capture: dict, file_info: dict, question: str) -> str:
    excerpt = read_file_for_ai(file_info["path"], max_chars=MAX_AI_FILE_CHARS)
    return f"""
Voce e um analista tecnico de logs automotivos/Android.
Analise o arquivo abaixo e responda em portugues do Brasil.

Contexto:
- teste: {capture['categoria']}/{capture['teste']}
- captura: {capture['capture_name']}
- arquivo: {file_info['relpath']}

Objetivo:
- encontrar erros, falhas, crashes, ANRs, sintomas relevantes e causa mais provavel
- citar evidencias objetivas do proprio log
- dizer severidade: critica, alta, media ou baixa
- sugerir proximos passos tecnicos

Formato de resposta:
1. Resumo executivo
2. Principais erros ou sinais
3. Evidencias do log
4. Hipotese mais provavel
5. Proximos passos

Pergunta adicional do usuario:
{question or 'Nenhuma. Foque em diagnosticar o arquivo.'}

Conteudo do arquivo:
{excerpt}
""".strip()


def analysis_prompt_for_capture(capture: dict, question: str) -> tuple[str, list[str]]:
    context, used_files = build_capture_context(capture)
    metadata_json = json.dumps(capture["metadata"] or {}, ensure_ascii=False, indent=2)
    prompt = f"""
Voce e um analista tecnico de logs automotivos/Android.
Analise a captura completa de logs abaixo e responda em portugues do Brasil.

Contexto:
- teste: {capture['categoria']}/{capture['teste']}
- captura: {capture['capture_name']}
- quantidade total de arquivos: {len(capture['files'])}

Objetivo:
- resumir o incidente ou a ausencia de incidente
- apontar os arquivos mais importantes
- listar erros, crashes, ANRs, watchdogs ou sinais suspeitos
- citar evidencias concretas
- dar uma hipotese principal e proximos passos tecnicos

Formato de resposta:
1. Resumo executivo
2. Arquivos mais relevantes
3. Erros e sinais encontrados
4. Evidencias
5. Hipotese principal
6. Proximos passos

Pergunta adicional do usuario:
{question or 'Nenhuma. Foque em diagnosticar a captura.'}

Metadata:
{metadata_json}

Arquivos analisados:
{", ".join(used_files) if used_files else 'Nenhum arquivo de texto aproveitavel'}

Conteudo consolidado:
{context}
""".strip()
    return prompt, used_files


def subprocess_windowless_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def resolve_ollama_cli(ollama_cli: str) -> str:
    path = which(ollama_cli)
    if path:
        return path
    local_app = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "Programs", "Ollama", "ollama.exe")
    if candidate and os.path.exists(candidate):
        return candidate
    return ollama_cli


def ollama_generate(
    prompt: str,
    *,
    base_url: str,
    model: str,
    ollama_cli: str,
    timeout_s: int = 45,
    num_predict: int = 350,
    temperature: float = 0.1,
    top_p: float = 0.9,
    num_ctx: int = 4096,
    keep_alive: str = "10m",
) -> str | None:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": num_ctx,
        },
    }
    normalized_base_url = str(base_url or "http://localhost:11434").rstrip("/")
    urls = [f"{normalized_base_url}/api/generate"]
    if "localhost" in normalized_base_url:
        urls.append(f"{normalized_base_url.replace('localhost', '127.0.0.1')}/api/generate")

    if requests is not None:
        for url in urls:
            try:
                response = requests.post(url, json=payload, timeout=timeout_s)
                if response.ok:
                    body = response.json()
                    text = str(body.get("response", "") or "").strip()
                    if text:
                        return text
            except Exception:
                continue

    try:
        result = subprocess.run(
            [resolve_ollama_cli(ollama_cli), "run", str(model)],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            **subprocess_windowless_kwargs(),
        )
        if result.returncode == 0 and str(result.stdout or "").strip():
            return str(result.stdout).strip()
    except Exception:
        return None
    return None
