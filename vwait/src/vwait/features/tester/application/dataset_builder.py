from __future__ import annotations

import json

import pandas as pd

from vwait.core.paths import tester_actions_path, tester_dataset_path


def generate_and_normalize_dataset(json_path: str, csv_output_path: str) -> bool:
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            content = json.load(handle)

        rows: list[dict[str, object]] = []
        for item in content.get("acoes", []):
            action = item.get("acao", {})

            if "x" in action and "y" in action:
                rows.append(
                    {
                        "x": action["x"],
                        "y": action["y"],
                        "tipo": action.get("tipo", "tap"),
                        "timestamp": item.get("timestamp", ""),
                        "resolucao_largura": action.get("resolucao", {}).get("largura", 1920),
                        "resolucao_altura": action.get("resolucao", {}).get("altura", 1080),
                    }
                )
                continue

            if all(key in action for key in ("x1", "y1", "x2", "y2")):
                rows.extend(
                    [
                        {
                            "x": action["x1"],
                            "y": action["y1"],
                            "tipo": "swipe_inicio",
                            "timestamp": item.get("timestamp", ""),
                            "resolucao_largura": action.get("resolucao", {}).get("largura", 1920),
                            "resolucao_altura": action.get("resolucao", {}).get("altura", 1080),
                        },
                        {
                            "x": action["x2"],
                            "y": action["y2"],
                            "tipo": "swipe_fim",
                            "timestamp": item.get("timestamp", ""),
                            "resolucao_largura": action.get("resolucao", {}).get("largura", 1920),
                            "resolucao_altura": action.get("resolucao", {}).get("altura", 1080),
                        },
                    ]
                )

        if not rows:
            print(f"[⚠️] Nenhum registro válido encontrado em {json_path}")
            return False

        dataframe = pd.DataFrame(rows)
        dataframe = dataframe.dropna(subset=["x", "y"])
        dataframe = dataframe[(dataframe["x"] >= 0) & (dataframe["y"] >= 0)]
        dataframe["x_norm"] = dataframe["x"] / dataframe["resolucao_largura"]
        dataframe["y_norm"] = dataframe["y"] / dataframe["resolucao_altura"]
        dataframe.to_csv(csv_output_path, index=False, encoding="utf-8")
        print(f"[✅] Dataset gerado e normalizado: {csv_output_path}")
        return True
    except Exception as exc:
        print(f"[ERRO] Falha ao processar {json_path}: {exc}")
        return False


def normalize_cli_value(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def resolve_dataset_paths(categoria: str, nome_teste: str) -> tuple[str, str]:
    return str(tester_actions_path(categoria, nome_teste)), str(tester_dataset_path(categoria, nome_teste))


__all__ = [
    "generate_and_normalize_dataset",
    "normalize_cli_value",
    "resolve_dataset_paths",
]
