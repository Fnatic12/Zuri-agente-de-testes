from __future__ import annotations

import json

from vwait.features.tester.application.dataset_builder import generate_and_normalize_dataset


def test_generate_and_normalize_dataset_creates_normalized_csv(tmp_path):
    payload = {
        "acoes": [
            {
                "timestamp": "2026-04-13T10:00:00",
                "acao": {
                    "tipo": "tap",
                    "x": 960,
                    "y": 540,
                    "resolucao": {"largura": 1920, "altura": 1080},
                },
            },
            {
                "timestamp": "2026-04-13T10:00:01",
                "acao": {
                    "x1": 100,
                    "y1": 200,
                    "x2": 300,
                    "y2": 400,
                    "resolucao": {"largura": 1000, "altura": 500},
                },
            },
        ]
    }
    json_path = tmp_path / "acoes.json"
    csv_path = tmp_path / "dataset.csv"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    ok = generate_and_normalize_dataset(str(json_path), str(csv_path))

    assert ok is True
    content = csv_path.read_text(encoding="utf-8")
    assert "x_norm" in content
    assert "y_norm" in content
    assert "swipe_inicio" in content
    assert "swipe_fim" in content
