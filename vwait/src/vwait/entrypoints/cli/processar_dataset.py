from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.core.paths import PROJECT_ROOT as PROJECT_ROOT_PATH
from vwait.core.paths import tester_actions_path
from vwait.features.tester.application.dataset_builder import (
    generate_and_normalize_dataset,
    normalize_cli_value,
    resolve_dataset_paths,
)


def main() -> None:
    data_root = PROJECT_ROOT_PATH / "Data"
    if not data_root.exists():
        print(f"❌ Pasta 'Data' não encontrada em {data_root}.")
        return

    if len(sys.argv) >= 3:
        categoria = normalize_cli_value(sys.argv[1])
        nome_teste = normalize_cli_value(sys.argv[2])
    else:
        categoria = normalize_cli_value(input("📂 Categoria do teste: "))
        nome_teste = normalize_cli_value(input("📝 Nome do teste: "))

    json_path, csv_output_path = resolve_dataset_paths(categoria, nome_teste)
    if not tester_actions_path(categoria, nome_teste).exists():
        print(f"❌ Arquivo JSON não encontrado em {json_path}")
        return

    generate_and_normalize_dataset(json_path, csv_output_path)


if __name__ == "__main__":
    main()
