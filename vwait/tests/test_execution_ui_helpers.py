from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.ui.streamlit.helpers import (
    clean_status_text,
    filtrar_bancadas_reais,
    normalizar_execucao,
    saude_execucao,
    tempo_formatado,
)


def test_tempo_formatado_handles_short_and_long_durations():
    assert tempo_formatado(12) == "12s"
    assert tempo_formatado(75) == "1m 15s"


def test_clean_status_text_normalizes_ok_and_divergent():
    assert clean_status_text("ok") == "OK"
    assert clean_status_text("divergente detectado") == "Divergente"


def test_normalizar_execucao_sanitizes_action_payload():
    result = normalizar_execucao([{"acao": " TAP ", "status": "ok", "coordenadas": {"x": 1}}])
    assert result[0]["acao"] == "tap"
    assert result[0]["status"] == "OK"


def test_filtrar_bancadas_reais_keeps_live_connected_statuses():
    now = datetime.now()
    info = {
        "SERIAL1": {
            "status": "executando",
            "teste": "radio/home",
            "acoes_totais": 5,
            "acoes_executadas": 2,
            "_timestamp_dt": now - timedelta(seconds=5),
        }
    }
    result = filtrar_bancadas_reais(info, {"SERIAL1"}, now=now)
    assert "SERIAL1" in result


def test_saude_execucao_flags_critical_when_stale():
    now = datetime.now()
    info = {
        "status": "executando",
        "progresso": 10.0,
        "_timestamp_dt": now - timedelta(seconds=25),
    }
    health = saude_execucao(info, now, {"divergente": 0, "amostra": 0, "aprovacao": None})
    assert health["label"] == "Critico"
