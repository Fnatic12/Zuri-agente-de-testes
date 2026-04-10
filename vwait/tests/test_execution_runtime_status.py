from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.application.runtime_status import (
    finalize_runtime_status,
    initialize_runtime_status,
    update_log_capture_status,
    update_runtime_status,
)


def test_initialize_runtime_status_sets_baseline():
    saved = []
    starts = {}

    def load_payload(_categoria, _teste, _bancada):
        return {}

    def save_status(status, categoria, teste):
        saved.append((status, categoria, teste))

    initialize_runtime_status(
        "SERIAL1",
        "radio",
        "home",
        5,
        load_payload=load_payload,
        save_status=save_status,
        test_ref_fn=lambda c, t: f"{c}/{t}",
        execution_start_times=starts,
        now_iso_fn=lambda: "2026-04-10T10:00:00",
        now_ts_fn=lambda: 100.0,
    )

    payload = saved[0][0]["SERIAL1"]
    assert payload["status"] == "executando"
    assert payload["acoes_totais"] == 5
    assert payload["teste"] == "radio/home"
    assert starts["SERIAL1"] == 100.0


def test_update_runtime_status_tracks_progress_and_similarity():
    saved = []
    starts = {"SERIAL1": 100.0}
    previous = {
        "inicio": "2026-04-10T10:00:00",
        "resultados_ok": 1,
        "resultados_divergentes": 0,
        "similaridade_media": 0.8,
        "resultado_final": "pendente",
    }

    def load_payload(_categoria, _teste, _bancada):
        return previous

    def save_status(status, categoria, teste):
        saved.append((status, categoria, teste))

    update_runtime_status(
        "SERIAL1",
        "radio",
        "home",
        5,
        2,
        "Abrir home",
        load_payload=load_payload,
        save_status=save_status,
        test_ref_fn=lambda c, t: f"{c}/{t}",
        execution_start_times=starts,
        status_resultado="ok",
        similaridade=0.9,
        screenshot_rel="shots/home.png",
        now_iso_fn=lambda: "2026-04-10T10:00:30",
        now_ts_fn=lambda: 130.0,
    )

    payload = saved[0][0]["SERIAL1"]
    assert payload["progresso"] == 40.0
    assert payload["resultados_ok"] == 2
    assert payload["similaridade_media"] == 0.85
    assert payload["ultimo_screenshot"] == "shots/home.png"


def test_finalize_runtime_status_merges_final_fields():
    saved = []
    previous = {
        "teste": "radio/home",
        "acoes_totais": 5,
        "acoes_executadas": 5,
        "progresso": 80.0,
        "ultima_acao": "Fim",
        "ultima_acao_idx": 5,
        "ultima_acao_status": "ok",
        "tempo_decorrido_s": 12.0,
        "inicio": "2026-04-10T10:00:00",
        "resultados_ok": 4,
        "resultados_divergentes": 1,
        "similaridade_media": 0.91,
        "resultado_final": "divergente",
    }

    def load_payload(_categoria, _teste, _bancada):
        return previous

    def save_status(status, categoria, teste):
        saved.append((status, categoria, teste))

    finalize_runtime_status(
        "SERIAL1",
        "radio",
        "home",
        load_payload=load_payload,
        save_status=save_status,
        test_ref_fn=lambda c, t: f"{c}/{t}",
        resultado="finalizado",
        failure_report_status="gerado",
        failure_report_dir="/tmp/report",
        now_iso_fn=lambda: "2026-04-10T10:01:00",
    )

    payload = saved[0][0]["SERIAL1"]
    assert payload["status"] == "finalizado"
    assert payload["progresso"] == 100.0
    assert payload["fim"] == "2026-04-10T10:01:00"
    assert payload["failure_report_status"] == "gerado"


def test_update_log_capture_status_preserves_execution_fields():
    saved = []
    previous = {
        "teste": "radio/home",
        "status": "coletando_logs",
        "acoes_totais": 5,
        "acoes_executadas": 5,
        "progresso": 100.0,
        "ultima_acao": "Fim",
        "ultima_acao_idx": 5,
        "ultima_acao_status": "ok",
        "tempo_decorrido_s": 15.0,
        "inicio": "2026-04-10T10:00:00",
        "fim": "2026-04-10T10:01:00",
        "resultados_ok": 4,
        "resultados_divergentes": 1,
        "similaridade_media": 0.91,
        "resultado_final": "divergente",
        "erro_motivo": None,
    }

    def load_payload(_categoria, _teste, _bancada):
        return previous

    def save_status(status, categoria, teste):
        saved.append((status, categoria, teste))

    update_log_capture_status(
        "SERIAL1",
        "radio",
        "home",
        "capturado",
        load_payload=load_payload,
        save_status=save_status,
        test_ref_fn=lambda c, t: f"{c}/{t}",
        log_capture_dir="/tmp/logs",
        log_capture_sequence="failure_log_sequence.json",
        now_iso_fn=lambda: "2026-04-10T10:01:30",
    )

    payload = saved[0][0]["SERIAL1"]
    assert payload["status"] == "coletando_logs"
    assert payload["log_capture_status"] == "capturado"
    assert payload["log_capture_dir"] == "/tmp/logs"
    assert payload["log_capture_sequence"] == "failure_log_sequence.json"
