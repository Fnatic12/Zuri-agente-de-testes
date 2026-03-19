import json
import os
import re
import subprocess
import sys
from datetime import datetime
from shutil import which

import streamlit as st
from app.shared import ui_theme as _ui_theme

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:3b")
OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "350"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")

TEXT_EXTS = {
    ".txt",
    ".log",
    ".json",
    ".xml",
    ".csv",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".trace",
    ".out",
    ".err",
    ".properties",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
MAX_VIEW_CHARS = 40000
MAX_AI_FILE_CHARS = 14000
MAX_AI_CAPTURE_CHARS = 24000

HEURISTICS = {
    "fatal": [
        r"fatal exception",
        r"fatal signal",
        r"\bsigsegv\b",
        r"\bsigabrt\b",
        r"\babort\b",
        r"\bbacktrace\b",
        r"native crash",
        r"crash",
    ],
    "anr": [
        r"\banr\b",
        r"application not responding",
        r"input dispatching timed out",
        r"broadcast of intent",
    ],
    "watchdog": [
        r"watchdog",
        r"system_server",
        r"service manager",
        r"dead object",
    ],
    "bluetooth": [
        r"bluetooth",
        r"bt_stack",
        r"btif",
        r"avrcp",
        r"a2dp",
        r"hfp",
    ],
    "radio": [
        r"broadcastradio",
        r"tuner",
        r"mcu",
        r"hal",
        r"lshal",
        r"vendor",
    ],
}


def titulo_painel(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            background: #0B0C10 !important;
            color: #E0E0E0 !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
        }}
        [data-testid="stHeader"], [data-testid="stToolbar"] {{
            display: none !important;
            height: 0 !important;
        }}
        .block-container {{
            padding-top: 1.15rem;
            max-width: 1240px;
        }}
        .main-title {{
            font-size: 2.0rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #60a5fa 40%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.1em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #9ca3af;
            font-size: 0.94rem;
            margin-bottom: 1.0em;
        }}
        .panel-card {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.45);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


def _subprocess_windowless_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _resolve_ollama_cli() -> str:
    path = which(OLLAMA_CLI)
    if path:
        return path
    local_app = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "Programs", "Ollama", "ollama.exe")
    if candidate and os.path.exists(candidate):
        return candidate
    return OLLAMA_CLI


def _open_folder(path: str) -> tuple[bool, str]:
    resolved = os.path.abspath(str(path or "").strip())
    if not resolved or not os.path.exists(resolved):
        return False, "Pasta nao encontrada."
    try:
        if os.name == "nt":
            os.startfile(resolved)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", resolved])
        else:
            subprocess.Popen(["xdg-open", resolved])
        return True, resolved
    except Exception as exc:
        return False, str(exc)


def _safe_datetime(path: str) -> datetime:
    return datetime.fromtimestamp(os.path.getmtime(path))


def _try_load_json(path: str) -> dict | list | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _clean_display_text(value: str) -> str:
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def _read_file_for_view(path: str, max_chars: int = MAX_VIEW_CHARS) -> tuple[str, bool]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except Exception as exc:
        return f"Falha ao ler arquivo: {exc}", False

    text = _clean_display_text(_decode_bytes(raw))
    truncated = False
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        text = f"{head}\n\n... [conteudo truncado] ...\n\n{tail}"
        truncated = True
    return text, truncated


def _read_file_for_ai(path: str, max_chars: int) -> str:
    ext = os.path.splitext(path)[1].lower()
    raw_json = _try_load_json(path) if ext == ".json" else None
    if raw_json is not None:
        text = json.dumps(raw_json, ensure_ascii=False, indent=2)
    else:
        text, _ = _read_file_for_view(path, max_chars=max_chars)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars // 2]}\n\n... [truncado para analise] ...\n\n{text[-max_chars // 2 :]}"


def _is_text_like(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS:
        return True
    try:
        with open(path, "rb") as handle:
            sample = handle.read(2048)
        if not sample:
            return True
        return b"\x00" not in sample
    except Exception:
        return False


def _match_lines(text: str, pattern: str, limit: int = 6) -> list[str]:
    compiled = re.compile(pattern, re.IGNORECASE)
    matches = []
    for line in text.splitlines():
        if compiled.search(line):
            matches.append(line.strip())
        if len(matches) >= limit:
            break
    return matches


def _scan_text_signals(text: str) -> dict:
    results = {}
    for label, patterns in HEURISTICS.items():
        lines = []
        for pattern in patterns:
            lines.extend(_match_lines(text, pattern, limit=4))
            if len(lines) >= 6:
                break
        results[label] = {"count": len(lines), "lines": lines[:6]}
    return results


def _scan_capture_signals(files: list[dict]) -> tuple[dict, list[dict]]:
    totals = {label: 0 for label in HEURISTICS}
    highlights = []
    for file_info in files:
        if not file_info["text_like"]:
            continue
        excerpt = _read_file_for_ai(file_info["path"], max_chars=7000)
        signals = _scan_text_signals(excerpt)
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


def _list_capture_files(capture_dir: str) -> list[dict]:
    files = []
    for root, _, names in os.walk(capture_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            relpath = os.path.relpath(path, capture_dir)
            ext = os.path.splitext(name)[1].lower()
            files.append(
                {
                    "name": name,
                    "path": path,
                    "relpath": relpath,
                    "size": os.path.getsize(path) if os.path.exists(path) else 0,
                    "ext": ext,
                    "image": ext in IMAGE_EXTS,
                    "text_like": _is_text_like(path),
                }
            )
    files.sort(key=lambda item: item["relpath"].lower())
    return files


def _load_log_captures(data_root: str = DATA_ROOT) -> list[dict]:
    captures = []
    if not os.path.isdir(data_root):
        return captures

    for categoria in os.listdir(data_root):
        categoria_dir = os.path.join(data_root, categoria)
        if not os.path.isdir(categoria_dir):
            continue
        for teste in os.listdir(categoria_dir):
            teste_dir = os.path.join(categoria_dir, teste)
            if not os.path.isdir(teste_dir):
                continue
            logs_dir = os.path.join(teste_dir, "logs")
            if not os.path.isdir(logs_dir):
                continue
            for capture_name in os.listdir(logs_dir):
                capture_dir = os.path.join(logs_dir, capture_name)
                if not os.path.isdir(capture_dir):
                    continue
                metadata_path = os.path.join(capture_dir, "capture_metadata.json")
                metadata = _try_load_json(metadata_path)
                if not isinstance(metadata, dict):
                    metadata = {}
                files = _list_capture_files(capture_dir)
                capture_dt = _parse_capture_datetime(metadata.get("started_at")) or _safe_datetime(capture_dir)
                captures.append(
                    {
                        "label": f"{categoria}/{teste} | {capture_name}",
                        "categoria": categoria,
                        "teste": teste,
                        "capture_name": capture_name,
                        "capture_dir": capture_dir,
                        "logs_dir": logs_dir,
                        "metadata": metadata,
                        "metadata_path": metadata_path if os.path.exists(metadata_path) else None,
                        "timestamp": capture_dt,
                        "files": files,
                    }
                )
    captures.sort(key=lambda item: item["timestamp"], reverse=True)
    return captures


def _parse_capture_datetime(value) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _human_size(size: int) -> str:
    size_f = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if size_f < 1024.0 or unit == "GB":
            return f"{size_f:.1f}{unit}"
        size_f /= 1024.0
    return f"{size_f:.1f}GB"


def _build_capture_context(capture: dict) -> tuple[str, list[str]]:
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
        excerpt = _read_file_for_ai(file_info["path"], max_chars=min(MAX_AI_FILE_CHARS, 7000))
        if not excerpt.strip():
            continue
        block = (
            f"\n### Arquivo: {file_info['relpath']}\n"
            f"Tamanho: {_human_size(int(file_info['size']))}\n"
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


def _ollama_generate(prompt: str, timeout_s: int = 45) -> str | None:
    payload = {
        "model": st.session_state.get("log_ollama_model", OLLAMA_MODEL),
        "prompt": prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": OLLAMA_NUM_PREDICT,
            "temperature": OLLAMA_TEMPERATURE,
            "top_p": OLLAMA_TOP_P,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }
    base_url = str(st.session_state.get("log_ollama_base_url", OLLAMA_URL) or OLLAMA_URL).rstrip("/")
    urls = [f"{base_url}/api/generate"]
    if "localhost" in base_url:
        urls.append(f"{base_url.replace('localhost', '127.0.0.1')}/api/generate")

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
            [_resolve_ollama_cli(), "run", str(payload["model"])],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            **_subprocess_windowless_kwargs(),
        )
        if result.returncode == 0 and str(result.stdout or "").strip():
            return str(result.stdout).strip()
    except Exception:
        return None
    return None


def _render_metadata(capture: dict) -> None:
    metadata = capture["metadata"] or {}
    status = str(metadata.get("status") or "desconhecido")
    motivo = str(metadata.get("motivo") or "-")
    total_artifacts = metadata.get("total_artifacts")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Teste", f"{capture['categoria']}/{capture['teste']}")
    col2.metric("Captura", capture["capture_name"])
    col3.metric("Status", status.upper())
    col4.metric("Arquivos", str(len(capture["files"])))

    col5, col6 = st.columns(2)
    col5.caption(f"Motivo: {motivo}")
    if total_artifacts is not None:
        col6.caption(f"Artefatos capturados: {total_artifacts}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Abrir pasta da captura", key=f"open_capture_{capture['capture_dir']}"):
            ok_open, detail_open = _open_folder(capture["capture_dir"])
            if ok_open:
                st.success(f"Pasta aberta: {detail_open}")
            else:
                st.error(f"Falha ao abrir pasta: {detail_open}")
    with b2:
        if st.button("Abrir raiz logs/", key=f"open_logs_{capture['logs_dir']}"):
            ok_open, detail_open = _open_folder(capture["logs_dir"])
            if ok_open:
                st.success(f"Pasta aberta: {detail_open}")
            else:
                st.error(f"Falha ao abrir pasta: {detail_open}")


def _render_local_analysis(capture: dict) -> None:
    totals, highlights = _scan_capture_signals(capture["files"])
    st.markdown("##### Sinais locais detectados")
    cols = st.columns(len(HEURISTICS))
    for idx, label in enumerate(HEURISTICS):
        cols[idx].metric(label.upper(), str(totals.get(label, 0)))

    if not highlights:
        st.info("Nenhum sinal forte encontrado nos trechos lidos localmente.")
        return

    for item in highlights[:8]:
        signal_labels = [f"{label}:{info['count']}" for label, info in item["signals"].items() if info["count"] > 0]
        st.markdown(
            f"- `{item['arquivo']}` | score `{item['score']}` | {' | '.join(signal_labels)}"
        )


def _render_file_viewer(capture: dict) -> None:
    st.markdown("##### Explorador de arquivos")
    files = capture["files"]
    if not files:
        st.warning("Nenhum arquivo encontrado nesta captura.")
        return

    file_labels = [f"{file_info['relpath']} ({_human_size(int(file_info['size']))})" for file_info in files]
    label_map = {label: file_info for label, file_info in zip(file_labels, files)}
    selected_label = st.selectbox("Arquivo", file_labels, key=f"log_file_{capture['capture_dir']}")
    selected_file = label_map[selected_label]

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.caption(f"Tipo: {'imagem' if selected_file['image'] else 'texto' if selected_file['text_like'] else 'binario'}")
    c2.caption(f"Tamanho: {_human_size(int(selected_file['size']))}")
    c3.caption(f"Caminho: {selected_file['relpath']}")

    if selected_file["image"]:
        st.image(selected_file["path"], caption=selected_file["relpath"], use_container_width=True)
        return

    if selected_file["text_like"]:
        content, truncated = _read_file_for_view(selected_file["path"], max_chars=MAX_VIEW_CHARS)
        signals = _scan_text_signals(content)
        badges = [f"{label}:{item['count']}" for label, item in signals.items() if item["count"] > 0]
        if badges:
            st.caption("Sinais no arquivo: " + " | ".join(badges))
        if truncated:
            st.warning("Conteudo truncado para visualizacao.")
        st.text_area("Conteudo do arquivo", content, height=480, key=f"viewer_{selected_file['path']}")
        return

    st.info("Arquivo binario ou nao legivel em texto. Abra a pasta local para inspecao externa.")


def _analysis_prompt_for_file(capture: dict, file_info: dict, question: str) -> str:
    excerpt = _read_file_for_ai(file_info["path"], max_chars=MAX_AI_FILE_CHARS)
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


def _analysis_prompt_for_capture(capture: dict, question: str) -> tuple[str, list[str]]:
    context, used_files = _build_capture_context(capture)
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


def _run_ai_analysis(target_key: str, prompt: str) -> None:
    with st.spinner("Analisando logs com Ollama..."):
        response = _ollama_generate(prompt)
    if not response:
        st.session_state[f"ai_result::{target_key}"] = "Falha ao obter resposta do Ollama."
    else:
        st.session_state[f"ai_result::{target_key}"] = response


def main() -> None:
    st.set_page_config(page_title="Painel de Logs - GEI", page_icon="", layout="wide")
    apply_panel_button_theme()
    titulo_painel("Painel de Logs - GEI", "Exploracao local dos logs capturados e analise assistida por IA")

    st.session_state.setdefault("log_ollama_base_url", OLLAMA_URL)
    st.session_state.setdefault("log_ollama_model", OLLAMA_MODEL)

    captures = _load_log_captures(DATA_ROOT)
    if not captures:
        st.info("Nenhuma captura de logs encontrada em Data/*/*/logs/.")
        return

    filter_text = st.text_input("Filtrar por teste ou pasta", placeholder="Ex.: audio, bluetooth, teste1")
    filtered = captures
    if filter_text.strip():
        token = filter_text.strip().lower()
        filtered = [
            capture
            for capture in captures
            if token in capture["label"].lower()
            or token in capture["capture_dir"].lower()
        ]

    if not filtered:
        st.warning("Nenhuma captura encontrada para o filtro informado.")
        return

    labels = [
        f"{capture['label']} | {capture['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
        for capture in filtered
    ]
    capture_map = {label: capture for label, capture in zip(labels, filtered)}
    selected_label = st.selectbox("Selecione a captura de logs", labels)
    capture = capture_map[selected_label]

    with st.expander("Configuracao da IA", expanded=False):
        st.text_input("OLLAMA base URL", key="log_ollama_base_url")
        st.text_input("OLLAMA model", key="log_ollama_model")
        st.caption("O painel usa o mesmo servidor Ollama local do ambiente VWAIT.")

    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    _render_metadata(capture)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    _render_local_analysis(capture)
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        _render_file_viewer(capture)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        st.markdown("##### Analise com IA")
        question = st.text_area(
            "Pergunta opcional",
            value="",
            placeholder="Ex.: houve ANR? qual a causa mais provavel? tem evidencias de bluetooth?",
            key=f"log_ai_question::{capture['capture_dir']}",
            height=100,
        )

        files = capture["files"]
        file_labels = [f"{file_info['relpath']} ({_human_size(int(file_info['size']))})" for file_info in files]
        label_map = {label: file_info for label, file_info in zip(file_labels, files)}
        selected_ai_label = st.selectbox("Arquivo para analise individual", file_labels, key=f"ai_file_{capture['capture_dir']}")
        selected_ai_file = label_map[selected_ai_label]

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Analisar arquivo", key=f"analyze_file::{selected_ai_file['path']}"):
                prompt = _analysis_prompt_for_file(capture, selected_ai_file, question)
                _run_ai_analysis(f"file::{selected_ai_file['path']}", prompt)
        with col2:
            if st.button("Analisar captura", key=f"analyze_capture::{capture['capture_dir']}"):
                prompt, used_files = _analysis_prompt_for_capture(capture, question)
                _run_ai_analysis(f"capture::{capture['capture_dir']}", prompt)
                st.session_state[f"ai_used_files::{capture['capture_dir']}"] = used_files

        file_result = st.session_state.get(f"ai_result::file::{selected_ai_file['path']}")
        if file_result:
            st.markdown("###### Resultado da analise do arquivo")
            st.markdown(file_result)

        capture_result = st.session_state.get(f"ai_result::capture::{capture['capture_dir']}")
        if capture_result:
            used_files = st.session_state.get(f"ai_used_files::{capture['capture_dir']}", [])
            st.markdown("###### Resultado da analise da captura")
            if used_files:
                st.caption("Arquivos usados: " + ", ".join(used_files))
            st.markdown(capture_result)
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
