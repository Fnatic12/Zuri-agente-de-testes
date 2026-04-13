from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.tester.application.runtime import parse_adb_devices
from vwait.features.tester.application.execution import (
    garantir_dataset_execucao,
    iniciar_execucoes_configuradas,
    iniciar_execucoes_teste_unico,
)
from vwait.features.tester.application.status import (
    carregar_status_execucao,
    clean_display_text,
    execucao_log_path_por_serial,
    formatar_resumo_execucao,
    resolver_pasta_logs_teste,
    resolver_teste_por_serial,
    tem_execucao_unica_ativa,
)


def test_parse_adb_devices_filters_only_ready_devices():
    lines = [
        "List of devices attached",
        "ABC123\tdevice",
        "offline01\toffline",
        "",
        "XYZ789\tdevice",
    ]

    assert parse_adb_devices(lines) == ["ABC123", "XYZ789"]


def test_clean_display_text_removes_ansi_and_nuls():
    raw = "\x1b[31mErro\x1b[0m\x00\nOK"

    assert clean_display_text(raw) == "Erro\nOK"


def test_formatar_resumo_execucao_covers_failed_log_capture_states():
    payload = {
        "resultado_final": "reprovado",
        "log_capture_status": "capturado",
        "log_capture_dir": "logs/failure_001",
    }

    assert formatar_resumo_execucao(payload) == "Finalizado reprovado | logs capturados em logs/failure_001"


def test_execucao_log_path_por_serial_normalizes_serial(tmp_path: Path):
    path = execucao_log_path_por_serial(str(tmp_path), "abc:123")

    assert path.endswith("execucao_live_abc_123.log")


def test_status_helpers_read_latest_serial_status(tmp_path: Path):
    data_dir = tmp_path / "Data" / "audio" / "teste_1"
    data_dir.mkdir(parents=True)
    status_path = data_dir / "status_SERIAL01.json"
    status_path.write_text(
        json.dumps(
            {
                "teste": "audio/teste_1",
                "atualizado_em": "2026-04-10T10:00:00",
                "resultado_final": "aprovado",
            }
        ),
        encoding="utf-8",
    )

    payload = carregar_status_execucao(str(tmp_path), "audio", "teste_1", "SERIAL01")
    categoria, teste = resolver_teste_por_serial(str(tmp_path), "SERIAL01")

    assert payload["resultado_final"] == "aprovado"
    assert (categoria, teste) == ("audio", "teste_1")


def test_resolver_pasta_logs_teste_prefers_capture_dir_from_status(tmp_path: Path):
    test_dir = tmp_path / "Data" / "audio" / "teste_1"
    capture_dir = test_dir / "logs" / "capture_001"
    capture_dir.mkdir(parents=True)
    (test_dir / "status_SERIAL01.json").write_text(
        json.dumps({"log_capture_dir": "logs/capture_001"}),
        encoding="utf-8",
    )

    resolved = resolver_pasta_logs_teste(str(tmp_path), "audio", "teste_1", "SERIAL01")

    assert resolved == str(capture_dir)


def test_tem_execucao_unica_ativa_detects_live_process():
    class Proc:
        def __init__(self, code):
            self._code = code

        def poll(self):
            return self._code

    assert tem_execucao_unica_ativa([{"proc": Proc(None)}]) is True
    assert tem_execucao_unica_ativa([{"proc": Proc(0)}]) is False


def test_garantir_dataset_execucao_runs_processor_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    warnings = []
    successes = []

    class Completed:
        returncode = 0

    def fake_run(cmd, cwd):
        assert cmd[1] == "/tmp/processar.py"
        assert cwd == str(tmp_path)
        return Completed()

    monkeypatch.setattr("vwait.features.tester.application.execution.subprocess.run", fake_run)

    ok, msg = garantir_dataset_execucao(
        str(tmp_path),
        {"Processar Dataset": "/tmp/processar.py"},
        "audio",
        "teste_1",
        on_warning=warnings.append,
        on_success=successes.append,
    )

    assert ok is True
    assert msg == ""
    assert warnings == ["Dataset nao encontrado. Gerando automaticamente..."]
    assert successes == ["Dataset processado com sucesso."]


def test_iniciar_execucoes_configuradas_rejects_duplicate_serials(tmp_path: Path):
    ok, msg, processos = iniciar_execucoes_configuradas(
        str(tmp_path),
        {"Executar Teste": "/tmp/run_test.py"},
        [
            {"categoria": "audio", "teste": "t1", "serial": "ABC", "label": "Bancada 1"},
            {"categoria": "audio", "teste": "t2", "serial": "ABC", "label": "Bancada 2"},
        ],
        {},
        tem_execucao_unica_ativa=lambda: False,
        garantir_dataset_execucao_fn=lambda categoria, teste: (True, ""),
        execucao_log_path_por_serial=lambda serial: str(tmp_path / f"{serial}.log"),
    )

    assert ok is False
    assert msg == "Selecione bancadas diferentes para executar em paralelo."
    assert processos == []


def test_iniciar_execucoes_configuradas_starts_process_and_updates_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class Proc:
        def poll(self):
            return None

    def fake_popen(cmd, cwd, stdout, stderr, text):
        assert cmd[1] == "/tmp/run_test.py"
        assert cwd == str(tmp_path)
        assert text is True
        stdout.write("")
        stdout.flush()
        return Proc()

    monkeypatch.setattr("vwait.features.tester.application.execution.subprocess.Popen", fake_popen)

    session_state = {}
    ok, msg, processos = iniciar_execucoes_configuradas(
        str(tmp_path),
        {"Executar Teste": "/tmp/run_test.py"},
        [{"categoria": "audio", "teste": "t1", "serial": "ABC123", "label": "Bancada 1"}],
        session_state,
        tem_execucao_unica_ativa=lambda: False,
        garantir_dataset_execucao_fn=lambda categoria, teste: (True, ""),
        execucao_log_path_por_serial=lambda serial: str(tmp_path / f"{serial}.log"),
    )

    assert ok is True
    assert msg == ""
    assert len(processos) == 1
    assert session_state["teste_em_execucao"] is True
    assert session_state["execucao_log_path"].endswith("ABC123.log")

    processos[0]["log_file"].close()


def test_iniciar_execucoes_teste_unico_builds_labels():
    captured = {}

    def fake_start(payload):
        captured["payload"] = payload
        return True, "", payload

    ok, msg, payload = iniciar_execucoes_teste_unico(
        "audio",
        "teste_1",
        ["SERIAL01"],
        iniciar_execucoes_configuradas_fn=fake_start,
    )

    assert ok is True
    assert msg == ""
    assert payload[0]["label"] == "Bancada selecionada"
