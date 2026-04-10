from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.execution.application import (
    bancada_key_from_serial,
    carregar_payload_bancada,
    carregar_status,
    carregar_status_bancadas,
    carregar_status_teste,
    extract_status_payload,
    failure_report_pointer_path,
    salvar_status,
    status_dir,
    test_ref as execution_test_ref,
)


def test_execution_paths_helpers_match_layout():
    assert status_dir("radio", "home") == PROJECT_ROOT / "Data" / "radio" / "home"
    assert execution_test_ref("radio", "home") == "radio/home"
    assert failure_report_pointer_path("radio", "home") == PROJECT_ROOT / "Data" / "radio" / "home" / "failure_report_latest.json"


def test_bancada_key_from_serial_has_safe_fallback():
    assert bancada_key_from_serial(None) == "2801761952320038"
    assert bancada_key_from_serial("") == "2801761952320038"
    assert bancada_key_from_serial("abc") == "abc"


def test_salvar_e_carregar_status_por_serial(tmp_path: Path, monkeypatch):
    from vwait.features.execution import application as execution_app
    from vwait.features.execution import paths as execution_paths

    monkeypatch.setattr(execution_paths, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(execution_app, "status_dir", execution_paths.status_dir)

    payload = {"SERIAL1": {"serial": "SERIAL1", "status": "executando", "teste": "radio/home"}}
    salvar_status(payload, "radio", "home", serial="SERIAL1")
    loaded = carregar_status("radio", "home", serial="SERIAL1")
    assert loaded["SERIAL1"]["status"] == "executando"


def test_carregar_payload_bancada_accepts_nested_format(tmp_path: Path, monkeypatch):
    from vwait.features.execution import paths as execution_paths

    monkeypatch.setattr(execution_paths, "DATA_ROOT", tmp_path)
    path = execution_paths.status_file_path("radio", "home", "SERIAL1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"SERIAL1": {"serial": "SERIAL1", "status": "ok"}}), encoding="utf-8")

    payload = carregar_payload_bancada("radio", "home", "SERIAL1")
    assert payload["status"] == "ok"


def test_extract_status_payload_prefers_nested_but_keeps_top_level():
    raw = {
        "SERIAL1": {"status": "executando", "acoes_totais": 5},
        "serial": "SERIAL1",
        "categoria": "radio",
        "resultado_final": "pendente",
    }
    payload = extract_status_payload("SERIAL1", raw)
    assert payload["status"] == "executando"
    assert payload["categoria"] == "radio"
    assert payload["resultado_final"] == "pendente"


def test_carregar_status_bancadas_collects_latest_file(tmp_path: Path):
    first = tmp_path / "radio" / "teste_a" / "status_SERIAL1.json"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text(json.dumps({"serial": "SERIAL1", "status": "executando", "atualizado_em": "2026-04-10T10:00:00"}), encoding="utf-8")

    second = tmp_path / "radio" / "teste_b" / "status_SERIAL1.json"
    second.parent.mkdir(parents=True, exist_ok=True)
    second.write_text(json.dumps({"serial": "SERIAL1", "status": "finalizado", "atualizado_em": "2026-04-10T10:05:00"}), encoding="utf-8")

    latest = carregar_status_bancadas(tmp_path)
    assert latest["SERIAL1"]["status"] == "finalizado"


def test_carregar_status_teste_reads_latest_status_file(tmp_path: Path):
    status_path = tmp_path / "status_SERIAL1.json"
    status_path.write_text(json.dumps({"serial": "SERIAL1", "status": "erro"}), encoding="utf-8")

    payload = carregar_status_teste(tmp_path)
    assert payload["serial"] == "SERIAL1"
    assert payload["status"] == "erro"
