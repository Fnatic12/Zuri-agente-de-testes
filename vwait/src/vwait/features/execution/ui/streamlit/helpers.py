from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, cast


BANCADA_LABELS = {
    "2801761952320038": "Bancada 1",
    "2801780E52320038": "Bancada 2",
    "2801780c52320038": "Bancada 2",
    "2801839552320038": "Bancada 3",
}
BANCADA_LABELS_NORM = {str(key).lower(): value for key, value in BANCADA_LABELS.items()}
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def tempo_formatado(segundos: float) -> str:
    segundos = max(0, int(segundos))
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m {segundos % 60}s"
    return f"{segundos // 3600}h {(segundos % 3600) // 60}m"


def parse_datetime(value: Any) -> datetime | None:
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


def clean_display_text(value: Any) -> str:
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


def clean_status_text(value: Any) -> str:
    text = clean_display_text(value)
    upper = text.upper()
    if "DIVERG" in upper:
        return "Divergente"
    if "OK" in upper:
        return "OK"
    return text


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return clean_display_text(value)
    return value


def normalizar_execucao(execucao: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalizada: list[dict[str, Any]] = []
    for idx, acao in enumerate(execucao, start=1):
        if not isinstance(acao, dict):
            continue
        item = cast(dict[str, Any], sanitize_value(dict(acao)))
        item["id"] = item.get("id") or idx
        item["acao"] = clean_display_text(item.get("acao", "")).lower() or "acao"
        item["status"] = clean_status_text(item.get("status", ""))
        item["coordenadas"] = sanitize_value(item.get("coordenadas", {}))
        normalizada.append(item)
    return normalizada


def status_normalized(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized.startswith("erro"):
        return "erro"
    return normalized


def status_human(status: str) -> str:
    normalized = status_normalized(status)
    mapping = {
        "executando": "Executando",
        "coletando_logs": "Coletando logs",
        "finalizado": "Finalizado",
        "erro": "Erro",
        "ociosa": "Ociosa",
    }
    return mapping.get(normalized, normalized.capitalize() if normalized else "Desconhecido")


def status_chip_html(status: str) -> str:
    normalized = status_normalized(status)
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
        f"{status_human(status)}</span>"
    )


def estimativa_restante(info: dict[str, Any]) -> float | None:
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    tempo_decorrido = float(info.get("tempo_decorrido_s", 0.0) or 0.0)
    if total <= 0 or executadas <= 0 or executadas >= total:
        return None
    por_acao = tempo_decorrido / float(executadas)
    return max(0.0, (total - executadas) * por_acao)


def status_age_seconds(info: dict[str, Any], now: datetime) -> float:
    ts = info.get("_timestamp_dt")
    if not isinstance(ts, datetime):
        return float("inf")
    return max(0.0, (now - ts).total_seconds())


def is_live_status(info: dict[str, Any], now: datetime) -> bool:
    status = status_normalized(info.get("status", ""))
    teste = str(info.get("teste", "")).strip()
    total = int(info.get("acoes_totais", 0) or 0)
    executadas = int(info.get("acoes_executadas", 0) or 0)
    age_s = status_age_seconds(info, now)
    if status == "executando":
        return bool(teste) and total > 0 and executadas <= total and age_s <= 60.0
    if status == "coletando_logs":
        return bool(teste) and age_s <= 120.0
    if status == "finalizado":
        return bool(teste) and total > 0 and age_s <= 45.0
    if status == "erro":
        return bool(teste) and age_s <= 90.0
    return False


def filtrar_bancadas_reais(status_map: dict[str, Any], conectadas: set[str], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    conectadas_norm = {str(serial).lower() for serial in conectadas}
    filtered: dict[str, Any] = {}
    for serial, info in status_map.items():
        if str(serial).lower() not in conectadas_norm:
            continue
        if not is_live_status(info, now):
            continue
        filtered[serial] = info
    return filtered


def nome_bancada(serial: str) -> str:
    return BANCADA_LABELS.get(serial) or BANCADA_LABELS_NORM.get(str(serial).lower()) or serial


def velocidade_live(info: dict[str, Any]) -> float | None:
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


def quality_snapshot(info: dict[str, Any], execucao: list[dict[str, Any]]) -> dict[str, Any]:
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


def percent_text(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}%"


def age_text(age_s: float) -> str:
    if age_s < 1:
        return "agora"
    if age_s < 60:
        return f"{int(age_s)}s"
    return tempo_formatado(age_s)


def saude_execucao(info: dict[str, Any], now: datetime, quality: dict[str, Any]) -> dict[str, str]:
    status = status_normalized(info.get("status", ""))
    age_s = status_age_seconds(info, now)
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


def saude_chip_html(saude: dict[str, Any]) -> str:
    color = saude.get("color", "#38bdf8")
    label = saude.get("label", "Saudavel")
    return (
        "<span style='display:inline-block;padding:0.22rem 0.6rem;border-radius:999px;"
        f"font-size:0.76rem;font-weight:700;background:{color}20;color:{color};border:1px solid {color}66;'>"
        f"Saude: {label}</span>"
    )


def abrir_pasta_local(path: str) -> tuple[bool, str]:
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


__all__ = [
    "abrir_pasta_local",
    "age_text",
    "clean_display_text",
    "clean_status_text",
    "estimativa_restante",
    "filtrar_bancadas_reais",
    "is_live_status",
    "nome_bancada",
    "normalizar_execucao",
    "parse_datetime",
    "percent_text",
    "quality_snapshot",
    "saude_chip_html",
    "saude_execucao",
    "sanitize_value",
    "status_age_seconds",
    "status_chip_html",
    "status_human",
    "status_normalized",
    "tempo_formatado",
    "velocidade_live",
]
