import os
import json
import sys
from datetime import datetime, timedelta
import subprocess
import re
from typing import Any, cast

import cv2
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from PIL import Image
from app.shared.adb_utils import candidate_adb_paths
from app.shared import ui_theme as _ui_theme


def apply_panel_button_theme() -> None:
    handler = getattr(_ui_theme, "apply_panel_button_theme", None)
    if callable(handler):
        handler()

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None


def _identity_decorator(func):
    return func


_REALTIME_FRAGMENT = st.fragment(run_every="3s") if hasattr(st, "fragment") else _identity_decorator


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


def titulo_painel(titulo: str, subtitulo: str = ""):
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"]  {{
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
        [data-testid="stHeader"] {{
            display: none !important;
            height: 0 !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        .main .block-container, .block-container {{
            background: transparent !important;
        }}
        .block-container {{
            padding-top: 1.15rem;
            max-width: 1180px;
        }}
        .main-title {{
            font-size: 2.05rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #8b5cf6 48%, #d946ef 76%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.15em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #9ca3af;
            font-size: 0.95rem;
            margin-bottom: 1.1em;
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div {{
            color: #e5e7eb;
        }}
        [data-testid="stSelectbox"] label, [data-testid="stNumberInput"] label {{
            color: #a8b3c5 !important;
        }}
        [data-baseweb="select"] > div {{
            background: rgba(20, 24, 32, 0.9) !important;
            border-color: #334155 !important;
            color: #e5e7eb !important;
        }}
        input, textarea {{
            background: rgba(20, 24, 32, 0.9) !important;
            color: #e5e7eb !important;
            border-color: #334155 !important;
        }}
        .clean-card {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.55);
            border-radius: 14px;
            padding: 0.75rem 0.9rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 6px 18px rgba(2, 6, 23, 0.45);
        }}
        .executive-banner {{
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.88), rgba(17, 24, 39, 0.82));
            border: 1px solid rgba(56, 189, 248, 0.22);
            border-radius: 16px;
            padding: 0.95rem 1rem;
            margin: 0.5rem 0 0.85rem 0;
            box-shadow: 0 10px 30px rgba(2, 6, 23, 0.28);
        }}
        .executive-banner-title {{
            color: #f8fafc;
            font-size: 0.9rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-bottom: 0.2rem;
        }}
        .executive-banner-body {{
            color: #cbd5e1;
            font-size: 0.88rem;
            line-height: 1.45;
        }}
        .signal-badge {{
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            margin: 0.18rem 0.28rem 0 0;
            font-size: 0.75rem;
            font-weight: 700;
            border: 1px solid transparent;
        }}
        .card-kpi-label {{
            color: #94a3b8;
            font-size: 0.78rem;
            margin-bottom: 0.15rem;
        }}
        .card-kpi-value {{
            color: #f8fafc;
            font-weight: 700;
            font-size: 1.28rem;
            line-height: 1.1;
        }}
        div[data-testid="stMetric"] {{
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.45);
            border-radius: 12px;
            padding: 0.35rem 0.65rem;
        }}
        div[data-testid="stMetricLabel"] p {{
            color: #94a3b8 !important;
        }}
        div[data-testid="stMetricValue"] {{
            color: #f8fafc !important;
        }}
        .stExpander {{
            border: 1px solid rgba(71, 85, 105, 0.35) !important;
            border-radius: 10px !important;
            background: rgba(15, 23, 42, 0.5) !important;
        }}
        [data-testid="stExpander"] details {{
            background: rgba(15, 23, 42, 0.5) !important;
            border: 1px solid rgba(71, 85, 105, 0.35) !important;
            border-radius: 10px !important;
        }}
        [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {{
            color: #dbe4f0 !important;
        }}
        [data-testid="stMarkdownContainer"] code {{
            color: #bfdbfe !important;
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


# === CONFIGURACOES ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(BASE_DIR, "Data")
st.set_page_config(page_title="Dashboard - VWAIT", page_icon="", layout="wide")
apply_panel_button_theme()
BANCADA_LABELS = {
    "2801761952320038": "Bancada 1",
    "2801780E52320038": "Bancada 2",
    "2801780c52320038": "Bancada 2",
    "2801839552320038": "Bancada 3",
}
BANCADA_LABELS_NORM = {str(k).lower(): v for k, v in BANCADA_LABELS.items()}

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


# === FUNCOES AUXILIARES ===
def carregar_logs(data_root=DATA_ROOT):
    """Lista execucoes disponiveis"""
    logs = []
    for categoria in os.listdir(data_root):
        cat_path = os.path.join(data_root, categoria)
        if os.path.isdir(cat_path):
            for teste in os.listdir(cat_path):
                teste_path = os.path.join(cat_path, teste)
                if os.path.isdir(teste_path):
                    arq = os.path.join(teste_path, "execucao_log.json")
                    if os.path.exists(arq):
                        logs.append((f"{categoria}/{teste}", arq))
    return logs


def _tempo_formatado(segundos: float) -> str:
    segundos = max(0, int(segundos))
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m {segundos % 60}s"
    return f"{segundos // 3600}h {(segundos % 3600) // 60}m"


def _parse_datetime(value) -> datetime | None:
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


def _clean_display_text(value) -> str:
    text = value if isinstance(value, str) else str(value)
    text = ANSI_ESCAPE_RE.sub("", text)

    for _ in range(3):
        try:
            if any(mark in text for mark in ("Ã", "Â", "â", "т", "�")):
                text = text.encode("latin1", "ignore").decode("utf-8", "ignore")
                continue
        except Exception:
            pass
        try:
            if any(mark in text for mark in ("Ã", "Â", "â", "т", "�")):
                text = text.encode("cp1252", "ignore").decode("utf-8", "ignore")
                continue
        except Exception:
            pass
        break

    text = text.replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def _clean_status_text(value) -> str:
    text = _clean_display_text(value)
    upper = text.upper()
    if "DIVERG" in upper:
        return "Divergente"
    if "OK" in upper:
        return "OK"
    return text


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, str):
        return _clean_display_text(value)
    return value


def _normalizar_execucao(execucao: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalizada: list[dict[str, Any]] = []
    for idx, acao in enumerate(execucao, start=1):
        if not isinstance(acao, dict):
            continue
        item = cast(dict[str, Any], _sanitize_value(dict(acao)))
        item["id"] = item.get("id") or idx
        item["acao"] = _clean_display_text(item.get("acao", "")).lower() or "acao"
        item["status"] = _clean_status_text(item.get("status", ""))
        item["coordenadas"] = _sanitize_value(item.get("coordenadas", {}))
        normalizada.append(item)
    return normalizada


def _candidate_adb_commands() -> list[str]:
    return candidate_adb_paths()


def _listar_dispositivos_adb() -> set[str]:
    for adb_cmd in _candidate_adb_commands():
        try:
            out = subprocess.run(
                [adb_cmd, "devices"],
                capture_output=True,
                text=True,
                timeout=4,
                **_subprocess_windowless_kwargs(),
            )
        except Exception:
            continue

        if out.returncode != 0:
            continue

        seriais = set()
        for line in out.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                seriais.add(parts[0])
        return seriais
    return set()


def _extract_status_payload(serial: str, raw: dict) -> dict:
    payload = {}
    nested = raw.get(serial)
    if isinstance(nested, dict):
        payload.update(nested)
    for key in (
        "serial",
        "status",
        "teste",
        "acoes_totais",
        "acoes_executadas",
        "progresso",
        "tempo_decorrido_s",
        "inicio",
        "fim",
        "atualizado_em",
        "categoria",
        "ultima_acao",
        "ultima_acao_idx",
        "ultima_acao_status",
        "resultados_ok",
        "resultados_divergentes",
        "similaridade_media",
        "ultima_similaridade",
        "ultimo_screenshot",
        "velocidade_acoes_min",
        "resultado_final",
        "log_capture_status",
        "log_capture_dir",
        "log_capture_error",
        "log_capture_sequence",
        "erro_motivo",
    ):
        if key in raw and raw.get(key) is not None:
            payload[key] = raw.get(key)
    payload["serial"] = serial
    return payload


def _carregar_status_bancadas(data_root=DATA_ROOT):
    latest = {}
    if not os.path.isdir(data_root):
        return latest

    for root, _, files in os.walk(data_root):
        for name in files:
            if not (name.startswith("status_") and name.endswith(".json")):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    continue
            except Exception:
                continue

            serial = str(raw.get("serial") or name[len("status_") : -5]).strip()
            if not serial:
                continue

            payload = _extract_status_payload(serial, raw)
            ts = (
                _parse_datetime(payload.get("atualizado_em"))
                or _parse_datetime(payload.get("inicio"))
                or _parse_datetime(payload.get("fim"))
                or datetime.fromtimestamp(os.path.getmtime(path))
            )

            prev = latest.get(serial)
            if prev is None or ts > prev.get("_timestamp_dt", datetime.min):
                payload["_timestamp_dt"] = ts
                payload["_status_path"] = path
                latest[serial] = payload
    return latest


def _status_human(status: str) -> str:
    normalized = _status_normalized(status)
    mapping = {
        "executando": "Executando",
        "coletando_logs": "Coletando logs",
        "finalizado": "Finalizado",
        "erro": "Erro",
        "ociosa": "Ociosa",
    }
    return mapping.get(normalized, normalized.capitalize() if normalized else "Desconhecido")


def _status_chip_html(status: str) -> str:
    normalized = _status_normalized(status)
    if normalized == "executando":
        color = "#f59e0b"
    elif normalized == "coletando_logs":
        color = "#38bdf8"
    elif normalized == "finalizado":
        color = "#22c55e"
    elif normalized == "erro":
        color = "#ef4444"
    else:
        color = "#94a3b8"
    return (
        "<span style='display:inline-block;padding:0.22rem 0.6rem;border-radius:999px;"
        f"font-size:0.76rem;font-weight:700;background:{color}20;color:{color};border:1px solid {color}66;'>"
        f"{_status_human(status)}</span>"
    )


def _estimativa_restante(info: dict) -> float | None:
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    tempo_decorrido = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
    if total <= 0 or executadas <= 0 or executadas >= total:
        return None
    por_acao = tempo_decorrido / float(executadas)
    return max(0.0, (total - executadas) * por_acao)


def _status_age_seconds(info: dict, now: datetime) -> float:
    ts = info.get("_timestamp_dt")
    if not isinstance(ts, datetime):
        return float("inf")
    return max(0.0, (now - ts).total_seconds())


def _is_live_status(info: dict, now: datetime) -> bool:
    status = _status_normalized(info.get("status", ""))
    teste = str(info.get("teste", "")).strip()
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    age_s = _status_age_seconds(info, now)

    if status == "executando":
        return bool(teste) and total > 0 and executadas <= total and age_s <= 60.0
    if status == "coletando_logs":
        return bool(teste) and age_s <= 120.0
    if status == "finalizado":
        return bool(teste) and total > 0 and age_s <= 45.0
    if status == "erro":
        return bool(teste) and age_s <= 90.0
    return False


def _filtrar_bancadas_reais(status_map: dict, conectadas: set[str]) -> dict:
    now = datetime.now()
    conectadas_norm = {str(serial).lower() for serial in conectadas}
    filtered = {}
    for serial, info in status_map.items():
        if str(serial).lower() not in conectadas_norm:
            continue
        if not _is_live_status(info, now):
            continue
        filtered[serial] = info
    return filtered


def _nome_bancada(serial: str) -> str:
    return BANCADA_LABELS.get(serial) or BANCADA_LABELS_NORM.get(str(serial).lower()) or serial


def _status_normalized(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized.startswith("erro"):
        return "erro"
    return normalized


def _abrir_pasta_local(path: str) -> tuple[bool, str]:
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


def _resolver_diretorio_teste(info: dict) -> str | None:
    status_path = str(info.get("_status_path") or "").strip()
    if status_path:
        candidate = os.path.dirname(status_path)
        if os.path.isdir(candidate):
            return candidate

    teste = str(info.get("teste") or "").strip().replace("\\", "/")
    if "/" in teste:
        categoria, nome = teste.split("/", 1)
        candidate = os.path.join(DATA_ROOT, categoria, nome)
        if os.path.isdir(candidate):
            return candidate
    return None


def _resolver_logs_root(info: dict) -> str | None:
    test_dir = _resolver_diretorio_teste(info)
    if not test_dir:
        return None
    logs_root = os.path.join(test_dir, "logs")
    return logs_root if os.path.isdir(logs_root) else None


def _resolver_log_capture_dir(info: dict) -> str | None:
    test_dir = _resolver_diretorio_teste(info)
    if not test_dir:
        return None

    relative_capture_dir = str(info.get("log_capture_dir") or "").strip()
    if relative_capture_dir:
        candidate = os.path.join(test_dir, relative_capture_dir)
        if os.path.isdir(candidate):
            return candidate

    logs_root = _resolver_logs_root(info)
    if not logs_root:
        return None

    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def _resolver_logs_root_from_base_dir(base_dir: str) -> str | None:
    candidate = os.path.join(base_dir, "logs")
    return candidate if os.path.isdir(candidate) else None


def _resolver_latest_log_capture_from_base_dir(base_dir: str) -> str | None:
    logs_root = _resolver_logs_root_from_base_dir(base_dir)
    if not logs_root:
        return None
    candidates = [
        os.path.join(logs_root, name)
        for name in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, name))
    ]
    if not candidates:
        return logs_root
    return max(candidates, key=os.path.getmtime)


def _ultima_screenshot_bancada(info: dict) -> str | None:
    test_dir = _resolver_diretorio_teste(info)
    if not test_dir:
        return None

    hinted = str(info.get("ultimo_screenshot") or "").strip()
    if hinted:
        hinted_path = os.path.join(test_dir, hinted)
        if os.path.exists(hinted_path):
            return hinted_path

    candidates: list[str] = []
    for folder in ("resultados", "frames"):
        img_dir = os.path.join(test_dir, folder)
        if not os.path.isdir(img_dir):
            continue
        for name in os.listdir(img_dir):
            ext = os.path.splitext(name)[1].lower()
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                candidates.append(os.path.join(img_dir, name))

    resultado_final = os.path.join(test_dir, "resultado_final.png")
    if os.path.exists(resultado_final):
        candidates.append(resultado_final)

    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def _contar_arquivos_imagem(dir_path: str | None) -> int:
    if not dir_path or not os.path.isdir(dir_path):
        return 0
    return sum(
        1
        for name in os.listdir(dir_path)
        if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    )


def _carregar_execucao_parcial(info: dict) -> list[dict]:
    test_dir = _resolver_diretorio_teste(info)
    if not test_dir:
        return []
    exec_path = os.path.join(test_dir, "execucao_log.json")
    if not os.path.exists(exec_path):
        return []
    try:
        with open(exec_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    execucao = raw.get("execucao") if isinstance(raw, dict) else raw
    if not isinstance(execucao, list):
        return []
    return _normalizar_execucao(execucao)


def _quality_snapshot(info: dict, execucao: list[dict]) -> dict:
    executadas = int(info.get("acoes_executadas", 0) or 0)
    ok_count = int(info.get("resultados_ok", 0) or 0)
    divergente_count = int(info.get("resultados_divergentes", 0) or 0)

    if execucao:
        ok_count = sum(1 for item in execucao if "OK" in str(item.get("status", "")).upper())
        divergente_count = sum(1 for item in execucao if "DIVERG" in str(item.get("status", "")).upper())

    amostra = ok_count + divergente_count
    if amostra <= 0:
        amostra = executadas if executadas > 0 else 0

    aprovacao = (ok_count / amostra) * 100.0 if amostra > 0 else None
    return {
        "ok": ok_count,
        "divergente": divergente_count,
        "amostra": amostra,
        "aprovacao": aprovacao,
    }


def _velocidade_live(info: dict) -> float | None:
    velocidade = info.get("velocidade_acoes_min")
    if velocidade is not None:
        try:
            parsed = float(velocidade)
            if parsed > 0:
                return parsed
        except Exception:
            pass
    executadas = int(info.get("acoes_executadas", 0) or 0)
    tempo = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
    if executadas <= 0 or tempo <= 0:
        return None
    return round((executadas / tempo) * 60.0, 2)


def _percent_text(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}%"


def _age_text(age_s: float) -> str:
    if age_s < 1:
        return "agora"
    if age_s < 60:
        return f"{int(age_s)}s"
    return _tempo_formatado(age_s)


def _saude_execucao(info: dict, now: datetime, quality: dict) -> dict:
    status = _status_normalized(info.get("status", ""))
    age_s = _status_age_seconds(info, now)
    progresso = float(info.get("progresso", 0.0) or 0.0)
    divergente = int(quality.get("divergente", 0) or 0)
    aprovacao = quality.get("aprovacao")

    if status == "erro":
        return {"label": "Critico", "color": "#ef4444", "reason": "Execucao interrompida"}
    if status == "coletando_logs":
        return {"label": "Atencao", "color": "#38bdf8", "reason": "Coletando logs da peca apos a falha"}
    if age_s > 20:
        return {"label": "Critico", "color": "#ef4444", "reason": "Sem heartbeat recente"}
    if divergente >= 2 or (aprovacao is not None and quality.get("amostra", 0) >= 3 and aprovacao < 80):
        return {"label": "Critico", "color": "#ef4444", "reason": "Qualidade parcial abaixo do esperado"}
    if divergente >= 1 or age_s > 10:
        return {"label": "Atencao", "color": "#f59e0b", "reason": "Ha sinal de risco nesta rodada"}
    if progresso >= 90:
        return {"label": "Saudavel", "color": "#22c55e", "reason": "Execucao perto do fechamento"}
    return {"label": "Saudavel", "color": "#38bdf8", "reason": "Fluxo estavel"}


def _saude_chip_html(saude: dict) -> str:
    color = saude.get("color", "#38bdf8")
    label = saude.get("label", "Saudavel")
    return (
        "<span style='display:inline-block;padding:0.22rem 0.6rem;border-radius:999px;"
        f"font-size:0.76rem;font-weight:700;background:{color}20;color:{color};border:1px solid {color}66;'>"
        f"Saude: {label}</span>"
    )


def _portfolio_live_summary(executando_rows: dict, finalizado_rows: dict, erro_rows: dict, conectadas: set[str]) -> dict:
    now = datetime.now()
    quality_rows = []
    for serial, info in executando_rows.items():
        execucao = _carregar_execucao_parcial(info)
        quality = _quality_snapshot(info, execucao)
        saude = _saude_execucao(info, now, quality)
        quality_rows.append((serial, info, quality, saude))

    progressos = [float(info.get("progresso", 0.0) or 0.0) for _, info, _, _ in quality_rows]
    velocidades = [value for _, info, _, _ in quality_rows if (value := _velocidade_live(info)) is not None]
    ok_total = sum(int(quality.get("ok", 0) or 0) for _, _, quality, _ in quality_rows)
    divergente_total = sum(int(quality.get("divergente", 0) or 0) for _, _, quality, _ in quality_rows)
    amostra_total = sum(int(quality.get("amostra", 0) or 0) for _, _, quality, _ in quality_rows)
    aprovacao = (ok_total / amostra_total) * 100.0 if amostra_total > 0 else None
    criticos = [item for item in quality_rows if item[3].get("label") == "Critico"]
    atencao = [item for item in quality_rows if item[3].get("label") == "Atencao"]

    foco = None
    prioridades = {"Critico": 2, "Atencao": 1, "Saudavel": 0}
    if quality_rows:
        foco = max(
            quality_rows,
            key=lambda item: (
                prioridades.get(item[3].get("label"), 0),
                int(item[2].get("divergente", 0) or 0),
                float(_estimativa_restante(item[1]) or 0.0),
            ),
        )

    return {
        "conectadas": len(conectadas),
        "executando": len(executando_rows),
        "finalizadas": len(finalizado_rows),
        "erros": len(erro_rows),
        "progresso_medio": (sum(progressos) / len(progressos)) if progressos else None,
        "aprovacao": aprovacao,
        "divergencias": divergente_total,
        "velocidade_total": sum(velocidades) if velocidades else None,
        "criticos": len(criticos),
        "atencao": len(atencao),
        "foco": foco,
    }


@_REALTIME_FRAGMENT
def exibir_bancadas_tempo_real():
    st.subheader("Bancadas em tempo real")
    st.caption("Somente execuções reais: bancada conectada + status recente.")

    if st_autorefresh is not None and not hasattr(st, "fragment"):
        st_autorefresh(interval=3000, limit=None, key="dash_realtime_refresh")

    conectadas = _listar_dispositivos_adb()
    status_raw = _carregar_status_bancadas(DATA_ROOT)
    bancadas = _filtrar_bancadas_reais(status_raw, conectadas)

    executando_rows = {
        s: v
        for s, v in bancadas.items()
        if _status_normalized(v.get("status", "")) in {"executando", "coletando_logs"}
    }
    finalizado_rows = {s: v for s, v in bancadas.items() if _status_normalized(v.get("status", "")) == "finalizado"}
    erro_rows = {s: v for s, v in bancadas.items() if _status_normalized(v.get("status", "")) == "erro"}

    restantes = [
        _estimativa_restante(v)
        for v in executando_rows.values()
        if _status_normalized(v.get("status", "")) == "executando"
    ]
    restantes = [value for value in restantes if value is not None]
    eta_global_s = max(restantes) if restantes else None
    final_previsto = (
        (datetime.now() + timedelta(seconds=float(eta_global_s))).strftime("%H:%M:%S")
        if eta_global_s is not None
        else "-"
    )

    summary = _portfolio_live_summary(executando_rows, finalizado_rows, erro_rows, conectadas)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Bancadas conectadas", len(conectadas))
    c2.metric("Executando agora", len(executando_rows))
    c3.metric("Progresso medio", _percent_text(summary.get("progresso_medio")))
    c4.metric("Aprovacao parcial", _percent_text(summary.get("aprovacao")))
    c5.metric("Divergencias abertas", str(summary.get("divergencias", 0)))
    c6.metric("ETA global", _tempo_formatado(eta_global_s) if eta_global_s is not None else "-")
    st.caption(f"Previsao de termino global: {final_previsto}")

    if not conectadas:
        st.warning("Nenhuma bancada ADB conectada no momento.")
        return
    if not executando_rows:
        st.info("Nenhum teste em execucao neste momento.")
        return

    foco = summary.get("foco")
    if foco:
        serial_foco, info_foco, quality_foco, saude_foco = foco
        texto_foco = (
            f"{_nome_bancada(serial_foco)} em {_clean_display_text(info_foco.get('teste', '-'))}: "
            f"{saude_foco.get('reason', '').lower()}, "
            f"{int(quality_foco.get('divergente', 0) or 0)} divergencias, "
            f"ETA {_tempo_formatado(_estimativa_restante(info_foco) or 0.0) if _estimativa_restante(info_foco) is not None else '-'}."
        )
    else:
        texto_foco = "Nenhuma bancada ativa com dados suficientes para destaque."

    badges = []
    if summary.get("criticos", 0):
        badges.append(
            "<span class='signal-badge' style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            f"{summary.get('criticos', 0)} critico(s)</span>"
        )
    if summary.get("atencao", 0):
        badges.append(
            "<span class='signal-badge' style='background:#f59e0b20;border-color:#f59e0b66;color:#fde68a;'>"
            f"{summary.get('atencao', 0)} em atencao</span>"
        )
    if summary.get("finalizadas", 0):
        badges.append(
            "<span class='signal-badge' style='background:#22c55e20;border-color:#22c55e66;color:#bbf7d0;'>"
            f"{summary.get('finalizadas', 0)} finalizada(s) agora</span>"
        )
    if summary.get("erros", 0):
        badges.append(
            "<span class='signal-badge' style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            f"{summary.get('erros', 0)} erro(s) recentes</span>"
        )

    st.markdown(
        (
            "<div class='executive-banner'>"
            "<div class='executive-banner-title'>Leitura Executiva</div>"
            f"<div class='executive-banner-body'>{texto_foco}</div>"
            f"<div>{''.join(badges)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    layout_mode = st.radio(
        "Layout dos cards",
        options=["2x2", "2x3"],
        horizontal=True,
        index=0,
        key="realtime_layout_mode",
    )
    cols_per_row = 2 if layout_mode == "2x2" else 3

    rows = sorted(
        executando_rows.items(),
        key=lambda item: (
            {"Critico": 0, "Atencao": 1, "Saudavel": 2}.get(
                str(
                    _saude_execucao(
                        item[1],
                        datetime.now(),
                        _quality_snapshot(item[1], _carregar_execucao_parcial(item[1])),
                    ).get("label", "")
                ),
                2,
            ),
            item[0],
        ),
    )

    for start in range(0, len(rows), cols_per_row):
        chunk = rows[start : start + cols_per_row]
        cols = st.columns(cols_per_row)
        for i, col in enumerate(cols):
            if i >= len(chunk):
                continue
            serial, info = chunk[i]
            nome = _nome_bancada(serial)
            teste = str(info.get("teste", "-"))
            status = str(info.get("status", ""))
            progresso = float(info.get("progresso", 0.0) or 0.0)
            total = int(info.get("acoes_totais", 0) or 0)
            executadas = int(info.get("acoes_executadas", 0) or 0)
            tempo = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
            restante = _estimativa_restante(info)
            atualizado = str(info.get("atualizado_em") or info.get("inicio") or "-")
            age_s = _status_age_seconds(info, datetime.now())
            thumb = _ultima_screenshot_bancada(info)
            execucao = _carregar_execucao_parcial(info)
            quality = _quality_snapshot(info, execucao)
            saude = _saude_execucao(info, datetime.now(), quality)
            similaridade_media = info.get("similaridade_media")
            similaridade_media_txt = (
                f"{float(similaridade_media) * 100:.1f}%"
                if similaridade_media is not None and str(similaridade_media).strip() != ""
                else "-"
            )
            test_dir = _resolver_diretorio_teste(info)
            capturas = _contar_arquivos_imagem(os.path.join(test_dir, "resultados")) if test_dir else 0

            with col:
                st.markdown(
                    (
                        "<div class='clean-card'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center;gap:0.5rem;'>"
                        f"<div style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{nome}</div>"
                        f"<div style='display:flex;gap:0.35rem;flex-wrap:wrap;justify-content:flex-end;'>"
                        f"{_status_chip_html(status)}{_saude_chip_html(saude)}"
                        "</div>"
                        "</div>"
                        f"<div style='margin-top:0.35rem;color:#a8b3c5;font-size:0.84rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                        f"Teste: {teste}"
                        "</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, max(0.0, progresso / 100.0)), text=f"{progresso:.1f}%")
                st.caption(saude.get("reason", "Sem leitura executiva"))
                d1, d2 = st.columns(2)
                d1.metric("Acoes", f"{executadas}/{total}" if total > 0 else str(executadas))
                d2.metric("ETA", _tempo_formatado(restante) if restante is not None else "-")
                d4, d5 = st.columns(2)
                d4.metric("Aprovacao", _percent_text(quality.get("aprovacao")))
                d5.metric("Divergencias", str(quality.get("divergente", 0)))
                d7, d8, d9 = st.columns(3)
                d7.metric("Tempo", _tempo_formatado(tempo))
                d8.metric("Capturas", str(capturas))
                d9.metric("Similaridade media", similaridade_media_txt)
                st.caption(
                    f"Atualizado em {atualizado.split('T')[1][:8] if 'T' in atualizado else atualizado}"
                )

                if thumb and os.path.exists(thumb):
                    st.image(thumb, caption=f"Ultima tela: {os.path.basename(thumb)}", use_container_width=True)
                else:
                    st.caption("Sem screenshot recente para esta bancada.")


def calcular_metricas(execucao):
    total = len(execucao)
    if total == 0:
        return {
            "total_acoes": 0,
            "acertos": 0,
            "falhas": 0,
            "flakes": 0,
            "precisao_percentual": 0,
            "tempo_total": 0,
            "cobertura_telas": 0,
            "resultado_final": "SEM DADOS",
        }

    acertos = sum(1 for a in execucao if "OK" in a.get("status", "").upper())
    falhas = total - acertos
    flakes = sum(1 for a in execucao if "FLAKE" in a.get("status", ""))
    tempo_total = sum(a.get("duracao", 1) for a in execucao)

    # Tolerante a ausencia de 'id' e/ou 'tela'
    telas_unicas = {(a.get("tela") or f"id{a.get('id', idx)}") for idx, a in enumerate(execucao)}
    cobertura = round((len(telas_unicas) / total) * 100, 1)
    precisao = round((acertos / total) * 100, 2)

    return {
        "total_acoes": total,
        "acertos": acertos,
        "falhas": falhas,
        "flakes": flakes,
        "precisao_percentual": precisao,
        "tempo_total": tempo_total,
        "cobertura_telas": cobertura,
        "resultado_final": "APROVADO" if falhas == 0 else "REPROVADO",
    }


def _kpi_card(label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='clean-card'>"
            f"<div class='card-kpi-label'>{label}</div>"
            f"<div class='card-kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _style_axes_clean(ax):
    ax.set_facecolor("#0f172a")
    ax.grid(axis="y", color="#1f2937", linewidth=0.9)
    ax.tick_params(colors="#cbd5e1", labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#334155")
        spine.set_linewidth(0.8)


# === DASHBOARD ===
def exibir_metricas(metricas):
    st.subheader("Resumo")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _kpi_card("Total de acoes", str(metricas["total_acoes"]))
    with col2:
        _kpi_card("Acertos", str(metricas["acertos"]))
    with col3:
        _kpi_card("Falhas", str(metricas["falhas"]))
    with col4:
        _kpi_card("Instabilidades", str(metricas["flakes"]))

    st.caption("Instabilidades = acoes marcadas com status `FLAKE`, ou seja, comportamento intermitente/não deterministico durante a execucao.")

    col5, col6, col7 = st.columns(3)
    with col5:
        _kpi_card("Precisao", f"{metricas['precisao_percentual']}%")
    with col6:
        _kpi_card("Cobertura de telas", f"{metricas['cobertura_telas']}%")
    with col7:
        _kpi_card("Tempo total", f"{metricas['tempo_total']}s")

    if metricas["resultado_final"] == "APROVADO":
        st.success("Resultado final: APROVADO")
    else:
        st.error("Resultado final: REPROVADO")

    st.markdown("##### Distribuicao de resultado")
    labels = ["Acertos", "Falhas"]
    sizes = [max(0, metricas["acertos"]), max(0, metricas["falhas"])]
    if sum(sizes) == 0:
        sizes = [1, 0]
    colors = ["#22c55e", "#ef4444"]

    fig, ax = plt.subplots(figsize=(3.35, 2.05), dpi=120)
    ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
        startangle=110,
        wedgeprops=dict(width=0.42, edgecolor="#0f172a", linewidth=1.2),
        textprops=dict(color="#e2e8f0", fontsize=8.2),
    )
    ax.text(0, 0, str(metricas["total_acoes"]), ha="center", va="center", fontsize=11, color="#f8fafc", weight="bold")
    ax.set(aspect="equal")
    fig.patch.set_facecolor("#070b12")
    fig.tight_layout(pad=0.5)
    st.pyplot(fig)
    plt.close(fig)


def exibir_timeline(execucao):
    st.subheader("Tempo por acao")
    if not execucao:
        st.info("Sem acoes para montar timeline.")
        return

    tempos = [a.get("duracao", 1) for a in execucao]
    ids = [a.get("id", idx + 1) for idx, a in enumerate(execucao)]
    status_colors = ["#16a34a" if "OK" in str(a.get("status", "")).upper() else "#dc2626" for a in execucao]

    fig, ax = plt.subplots(figsize=(5.6, 2.25), dpi=125)
    ax.bar(ids, tempos, color=status_colors, edgecolor="#0f172a", linewidth=0.65)
    _style_axes_clean(ax)
    ax.set_xlabel("Acao", color="#cbd5e1", fontsize=8.5)
    ax.set_ylabel("Duracao (s)", color="#cbd5e1", fontsize=8.5)
    ax.set_title("Timeline", color="#e5e7eb", fontsize=9.8, pad=6)
    fig.patch.set_facecolor("#070b12")
    fig.tight_layout(pad=0.6)
    st.pyplot(fig)
    plt.close(fig)


def exibir_acoes(execucao, base_dir):
    st.subheader("Detalhes das acoes")
    if not execucao:
        st.info("Nenhuma acao encontrada.")
        return

    st.caption(f"{len(execucao)} acoes carregadas.")

    resumo = []
    for idx, acao in enumerate(execucao, start=1):
        resumo.append(
            {
                "Acao": idx,
                "ID": acao.get("id", idx),
                "Tipo": str(acao.get("acao", "")).upper(),
                "Status": acao.get("status", "-"),
                "Similaridade": round(float(acao.get("similaridade", 0.0) or 0.0), 3),
                "Duracao (s)": round(float(acao.get("duracao", 0.0) or 0.0), 2),
            }
        )

    st.dataframe(resumo, use_container_width=True, hide_index=True)

    indice_acao = st.selectbox(
        "Selecione a acao para ver os detalhes",
        options=list(range(len(execucao))),
        format_func=lambda i: (
            f"Acao {i + 1} - {str(execucao[i].get('acao', '')).upper()} | {execucao[i].get('status', '-')}"
        ),
        key="dashboard_acao_detalhe",
    )

    acao = execucao[indice_acao]

    frame_path = os.path.join(base_dir, str(acao.get("frame_esperado", "")))
    resultado_path = os.path.join(base_dir, str(acao.get("screenshot", "")))

    col_meta_1, col_meta_2, col_meta_3 = st.columns(3)
    col_meta_1.metric("Status", acao.get("status", "-"))
    col_meta_2.metric("Similaridade", f"{float(acao.get('similaridade', 0.0) or 0.0):.2f}")
    col_meta_3.metric("Duracao", f"{float(acao.get('duracao', 0.0) or 0.0):.2f}s")

    col1, col2 = st.columns(2)

    if frame_path and os.path.exists(frame_path):
        col1.image(
            Image.open(frame_path),
            caption=f"Esperado: {acao.get('frame_esperado', '-')}",
            use_container_width=True,
        )
    else:
        col1.warning("Frame esperado nao encontrado")

    if resultado_path and os.path.exists(resultado_path):
        col2.image(
            Image.open(resultado_path),
            caption=f"Obtido: {acao.get('screenshot', '-')}",
            use_container_width=True,
        )
    else:
        col2.warning("Screenshot nao encontrado")

def _simples_similarity(img_a: Image.Image, img_b: Image.Image) -> float:
    """Similaridade simples baseada em diferenca media normalizada (0..1)."""
    a = img_a.convert("L")
    b = img_b.convert("L").resize(a.size)
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    diff = np.abs(arr_a - arr_b)
    score = 1.0 - (np.mean(diff) / 255.0)
    return float(max(0.0, min(1.0, score)))


def _apply_ignore_mask(mask: np.ndarray, ignore_regions):
    if not ignore_regions:
        return mask
    h, w = mask.shape[:2]
    for (x, y, bw, bh) in ignore_regions:
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(w, int(x + bw))
        y2 = min(h, int(y + bh))
        mask[y1:y2, x1:x2] = 0
    return mask


def _compute_diff_mask_cv(img_a: np.ndarray, img_b: np.ndarray, diff_threshold=25):
    lab_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2LAB)
    lab_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2LAB)
    diff = cv2.absdiff(lab_a, lab_b)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(diff_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if diff_threshold:
        _, hard = cv2.threshold(diff_gray, diff_threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_or(otsu, hard)
    else:
        mask = otsu
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def _find_bboxes(mask: np.ndarray, min_area=200, max_area=200000):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area or area > max_area:
            continue
        bboxes.append((x, y, w, h, float(area)))
    return bboxes


def _is_toggle_candidate(bbox, img_shape, aspect_min=1.7, aspect_max=5.5):
    x, y, w, h, _ = bbox
    if h <= 0:
        return False
    img_h, img_w = img_shape[:2]
    ratio = w / float(h)
    # Filtro geometrico: evita classificar texto pequeno/linhas como toggle.
    if not (aspect_min <= ratio <= aspect_max):
        return False
    if w < 28 or h < 12:
        return False
    if w > int(img_w * 0.35) or h > int(img_h * 0.12):
        return False
    return True


def _toggle_state_by_color(img_roi: np.ndarray):
    hsv = cv2.cvtColor(img_roi, cv2.COLOR_BGR2HSV)
    lower = np.array((90, 60, 60), dtype=np.uint8)
    upper = np.array((130, 255, 255), dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    if ratio >= 0.08:
        return "ON", min(1.0, ratio / 0.2)
    return "OFF", min(1.0, (0.08 - ratio) / 0.08)


def _toggle_state_by_knob(img_roi: np.ndarray):
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0
    roi_area = float(img_roi.shape[0] * img_roi.shape[1])
    best = None
    best_conf = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < 20:
            continue
        per = cv2.arcLength(c, True)
        if per <= 0:
            continue
        circularity = float((4.0 * np.pi * area) / (per * per))
        x, y, w, h = cv2.boundingRect(c)
        if h <= 0:
            continue
        wh_ratio = w / float(h)
        area_ratio = area / roi_area
        # Knob tipico: quase circular, area moderada dentro da ROI.
        if circularity < 0.55 or wh_ratio < 0.65 or wh_ratio > 1.45:
            continue
        if area_ratio < 0.02 or area_ratio > 0.40:
            continue
        conf = min(1.0, (circularity - 0.55) / 0.35 + 0.25)
        if conf > best_conf:
            cx = x + w / 2.0
            best = cx
            best_conf = conf
    if best is None:
        return None, 0.0
    state = "ON" if best > (img_roi.shape[1] / 2.0) else "OFF"
    return state, best_conf


def _compare_images_cv(img_a: np.ndarray, img_b: np.ndarray, ignore_regions=None):
    mask = _compute_diff_mask_cv(img_a, img_b, diff_threshold=25)
    mask = _apply_ignore_mask(mask, ignore_regions or [])
    bboxes = _find_bboxes(mask)

    diffs = []
    toggles = []
    overlay = img_a.copy()
    for bbox in bboxes:
        x, y, w, h, score = bbox
        roi_a = img_a[y : y + h, x : x + w]
        roi_b = img_b[y : y + h, x : x + w]
        dtype = "generic"
        if _is_toggle_candidate(bbox, img_a.shape):
            state_a_c, conf_a_c = _toggle_state_by_color(roi_a)
            state_b_c, conf_b_c = _toggle_state_by_color(roi_b)
            state_a_k, conf_a_k = _toggle_state_by_knob(roi_a)
            state_b_k, conf_b_k = _toggle_state_by_knob(roi_b)
            # So aceita toggle quando o knob e detectado nas duas imagens.
            if state_a_k is not None and state_b_k is not None:
                state_a = state_a_k
                state_b = state_b_k
                conf = (conf_a_k + conf_b_k + conf_a_c + conf_b_c) / 4.0
            else:
                state_a = state_a_c
                state_b = state_b_c
                conf = (conf_a_c + conf_b_c) / 2.0
            if state_a_k is not None and state_b_k is not None and state_a != state_b:
                dtype = "toggle"
                toggles.append(
                    {
                        "bbox": (x, y, w, h),
                        "stateA": state_a,
                        "stateB": state_b,
                        "confidence": round(conf, 3),
                    }
                )

        diffs.append({"bbox": (x, y, w, h), "score": score, "type": dtype})
        color = (0, 255, 0) if dtype == "toggle" else (0, 200, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, dtype, (x, max(0, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    return {
        "diffs": diffs,
        "toggle_changes": toggles,
        "diff_mask": mask,
        "overlay": overlay,
    }


def _carregar_ignore_regions(esperados_dir: str) -> list:
    ignore_path = os.path.join(esperados_dir, "ignore.json")
    if not os.path.exists(ignore_path):
        return []
    try:
        with open(ignore_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, list) else []
    except Exception:
        return []


def _comparar_esperado_com_final(exp_path: str, final_path: str, ignore_regions=None):
    img_exp = Image.open(exp_path)
    img_final = Image.open(final_path)
    score = _simples_similarity(img_exp, img_final)

    exp_bgr = cv2.cvtColor(np.array(img_exp), cv2.COLOR_RGB2BGR)
    fin_bgr = cv2.cvtColor(np.array(img_final), cv2.COLOR_RGB2BGR)
    if fin_bgr.shape[:2] != exp_bgr.shape[:2]:
        fin_bgr = cv2.resize(fin_bgr, (exp_bgr.shape[1], exp_bgr.shape[0]))

    diff_res = _compare_images_cv(exp_bgr, fin_bgr, ignore_regions=ignore_regions or [])
    exp_box = exp_bgr.copy()
    fin_box = fin_bgr.copy()
    for diff in diff_res["diffs"]:
        x, y, w, h = diff["bbox"]
        color = (0, 255, 0) if diff["type"] == "toggle" else (0, 200, 255)
        cv2.rectangle(exp_box, (x, y), (x + w, y + h), color, 2)
        cv2.rectangle(fin_box, (x, y), (x + w, y + h), color, 2)

    return {
        "nome": os.path.basename(exp_path),
        "score": score,
        "img_exp": img_exp,
        "img_final": img_final,
        "diff_res": diff_res,
        "exp_box": cv2.cvtColor(exp_box, cv2.COLOR_BGR2RGB),
        "fin_box": cv2.cvtColor(fin_box, cv2.COLOR_BGR2RGB),
    }


def exibir_comparacao_esperados(base_dir):
    st.subheader("Comparacao com resultados esperados")
    esperados_dir = os.path.join(base_dir, "esperados")
    final_path = os.path.join(base_dir, "resultado_final.png")

    if not os.path.exists(final_path):
        st.warning("resultado_final.png nao encontrado para comparacao.")
        return

    if not os.path.isdir(esperados_dir):
        st.info("Nenhuma pasta 'esperados' encontrada para este teste.")
        return

    esperados = [f for f in os.listdir(esperados_dir) if f.lower().endswith(".png")]
    if not esperados:
        st.info("Nenhum esperado salvo para comparacao.")
        return

    try:
        Image.open(final_path)
    except Exception:
        st.error("Falha ao abrir resultado_final.png.")
        return

    ignore_regions = _carregar_ignore_regions(esperados_dir)

    for nome in sorted(esperados):
        exp_path = os.path.join(esperados_dir, nome)
        try:
            comp = _comparar_esperado_com_final(exp_path, final_path, ignore_regions=ignore_regions)
        except Exception:
            st.warning(f"Falha ao comparar {nome}.")
            continue

        st.markdown(f"**Comparacao:** `{nome}` x `resultado_final.png`")
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.image(comp["img_exp"], caption=f"Esperado: {nome}", use_container_width=True)
        col2.image(comp["img_final"], caption="Resultado final", use_container_width=True)
        col3.metric("Similaridade (global)", f"{comp['score'] * 100:.1f}%")


def exibir_comparacao_toggles(base_dir):
    st.subheader("Comparacao de toggles")
    esperados_dir = os.path.join(base_dir, "esperados")
    final_path = os.path.join(base_dir, "resultado_final.png")

    if not os.path.exists(final_path):
        st.info("resultado_final.png nao encontrado para comparacao de toggles.")
        return
    if not os.path.isdir(esperados_dir):
        st.info("Nenhuma pasta 'esperados' encontrada para avaliar toggles.")
        return

    esperados = sorted(f for f in os.listdir(esperados_dir) if f.lower().endswith(".png"))
    if not esperados:
        st.info("Nenhuma imagem esperada disponivel para comparar toggles.")
        return

    ignore_regions = _carregar_ignore_regions(esperados_dir)
    resultados = []
    for nome in esperados:
        exp_path = os.path.join(esperados_dir, nome)
        try:
            resultados.append(_comparar_esperado_com_final(exp_path, final_path, ignore_regions=ignore_regions))
        except Exception:
            st.warning(f"Falha ao avaliar toggles em {nome}.")

    if not resultados:
        st.info("Nao foi possivel gerar a comparacao de toggles desta execucao.")
        return

    total_toggles = sum(len(item["diff_res"]["toggle_changes"]) for item in resultados)
    com_divergencia = sum(1 for item in resultados if item["diff_res"]["toggle_changes"])
    sem_divergencia = len(resultados) - com_divergencia

    if total_toggles > 0:
        resumo = (
            f"Foram detectados {total_toggles} toggle(s) divergente(s) em "
            f"{com_divergencia} comparacao(oes) desta execucao. "
            "Revise os cards abaixo antes de aprovar o resultado."
        )
        badge = (
            "<span class='signal-badge' "
            "style='background:#ef444420;border-color:#ef444466;color:#fecaca;'>"
            "Toggle divergente detectado"
            "</span>"
        )
        banner_style = (
            "background:linear-gradient(135deg, rgba(127, 29, 29, 0.92), rgba(69, 10, 10, 0.88));"
            "border:1px solid rgba(248, 113, 113, 0.45);"
        )
    else:
        resumo = (
            f"As {len(resultados)} comparacao(oes) avaliadas nao apresentaram divergencia de toggle. "
            "O comportamento visual desta execucao permaneceu consistente."
        )
        badge = (
            "<span class='signal-badge' "
            "style='background:#22c55e20;border-color:#22c55e66;color:#bbf7d0;'>"
            "Sem divergencia de toggle"
            "</span>"
        )
        banner_style = (
            "background:linear-gradient(135deg, rgba(6, 78, 59, 0.92), rgba(2, 44, 34, 0.88));"
            "border:1px solid rgba(74, 222, 128, 0.35);"
        )

    st.markdown(
        (
            f"<div class='executive-banner' style='{banner_style}'>"
            "<div class='executive-banner-title'>Resumo Executivo dos Toggles</div>"
            f"<div class='executive-banner-body'>{resumo}</div>"
            f"{badge}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Esperados analisados", str(len(resultados)))
    m2.metric("Comparacoes sem divergencia", str(sem_divergencia))
    m3.metric("Comparacoes com divergencia", str(com_divergencia))
    m4.metric("Toggles divergentes", str(total_toggles))

    for item in resultados:
        nome = item["nome"]
        diff_res = item["diff_res"]
        toggle_count = len(diff_res["toggle_changes"])
        status = "Divergencia detectada" if toggle_count else "Sem divergencia"
        status_prefix = "error" if toggle_count else "success"
        with st.expander(f"{nome} | {status} | similaridade {item['score'] * 100:.1f}%"):
            c1, c2, c3 = st.columns(3)
            c1.image(item["exp_box"], caption="Esperado (com boxes)", use_container_width=True)
            c2.image(item["fin_box"], caption="Resultado final (com boxes)", use_container_width=True)
            c3.image(diff_res["diff_mask"], caption="Mascara de diferencas", use_container_width=True)

            if toggle_count:
                getattr(st, status_prefix)(
                    f"{toggle_count} toggle(s) divergente(s) detectado(s) nesta comparacao."
                )
                for toggle in diff_res["toggle_changes"]:
                    st.write(
                        f"- {toggle['stateA']} -> {toggle['stateB']} | "
                        f"conf={toggle['confidence']} | bbox={toggle['bbox']}"
                    )
            else:
                getattr(st, status_prefix)("Nenhum toggle divergente detectado.")


def exibir_validacao_final(execucao, base_dir):
    st.subheader("Validacao final da tela")
    resultado_final_path = os.path.join(base_dir, "resultado_final.png")
    if not execucao:
        st.warning("Nenhuma acao registrada.")
        return

    ultima = execucao[-1]
    frame_esperado = ultima.get("frame_esperado")
    frame_path = os.path.join(base_dir, frame_esperado) if frame_esperado else ""

    col1, col2 = st.columns(2)
    if frame_path and os.path.exists(frame_path):
        col1.image(Image.open(frame_path), caption="Esperada (ultima acao)", use_container_width=True)
    else:
        col1.error("Frame esperado nao encontrado")

    if os.path.exists(resultado_final_path):
        col2.image(Image.open(resultado_final_path), caption="Resultado final", use_container_width=True)
    else:
        col2.error("resultado_final.png nao encontrado")

    sim = float(ultima.get("similaridade", 0.0))
    st.write(f"Similaridade final: {sim:.2f}")


def main():
    titulo_painel("Dashboard de Execução de Testes - VWAIT", "")
    exibir_bancadas_tempo_real()
    st.markdown("---")
    st.subheader("Execução detalhada por teste")

    if not os.path.isdir(DATA_ROOT):
        st.error(f"Pasta de dados nao encontrada: {DATA_ROOT}")
        return

    logs = carregar_logs()
    if not logs:
        st.info("Nenhum execucao_log.json encontrado em Data/*/*/.")
        return

    labels = [label for label, _ in logs]
    selected = st.selectbox("Selecione a execucao", labels)
    path_map = {label: path for label, path in logs}
    log_path = path_map.get(selected)
    if not log_path or not os.path.exists(log_path):
        st.error("Execucao selecionada nao encontrada.")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        st.error(f"Falha ao ler execucao_log.json: {e}")
        return

    execucao = data.get("execucao") if isinstance(data, dict) else data
    if not isinstance(execucao, list):
        st.error("Formato invalido de execucao_log.json (esperado lista ou {'execucao': []}).")
        return

    execucao = _normalizar_execucao(execucao)

    base_dir = os.path.dirname(log_path)
    logs_root = _resolver_logs_root_from_base_dir(base_dir)
    latest_log_capture = _resolver_latest_log_capture_from_base_dir(base_dir)
    metricas = calcular_metricas(execucao)

    st.markdown("##### Logs do radio")
    log_col1, log_col2 = st.columns(2)
    with log_col1:
        if st.button("Abrir pasta logs/", key=f"open_logs_root_{selected}"):
            if not logs_root:
                st.error("Nenhuma pasta logs encontrada para este teste.")
            else:
                ok_open, detalhe_open = _abrir_pasta_local(logs_root)
                if ok_open:
                    st.success(f"Pasta aberta: {logs_root}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")
    with log_col2:
        if st.button("Abrir ultima captura de logs", key=f"open_logs_latest_{selected}"):
            if not latest_log_capture:
                st.error("Nenhuma captura de logs encontrada para este teste.")
            else:
                ok_open, detalhe_open = _abrir_pasta_local(latest_log_capture)
                if ok_open:
                    st.success(f"Pasta aberta: {latest_log_capture}")
                else:
                    st.error(f"Falha ao abrir a pasta: {detalhe_open}")

    if logs_root:
        st.caption(f"Raiz dos logs: {logs_root}")
    else:
        st.caption("Raiz dos logs: nenhuma pasta logs/ encontrada para esta execucao.")

    exibir_metricas(metricas)
    exibir_timeline(execucao)
    exibir_comparacao_toggles(base_dir)
    exibir_comparacao_esperados(base_dir)
    exibir_validacao_final(execucao, base_dir)
    exibir_acoes(execucao, base_dir)


if __name__ == "__main__":
    main()
