from __future__ import annotations

import argparse
import json
from pathlib import Path

from vwait.features.visual_qa.config import load_config
from vwait.features.visual_qa.infrastructure.embeddings.factory import build_embedding_provider
from vwait.features.visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository


def _load_labels(labels_json: str | None) -> dict[str, str] | None:
    if not labels_json:
        return None

    candidate = Path(labels_json).expanduser()
    if candidate.exists() and candidate.is_file():
        raw = candidate.read_text(encoding="utf-8")
    else:
        raw = labels_json

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--labels-json must resolve to a JSON object/dict")
    return {str(k): str(v) for k, v in payload.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build vector index from reference images.")
    parser.add_argument("--reference-dir", default=None, help="Reference images directory")
    parser.add_argument("--index-dir", default=None, help="Output vector index directory")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders recursively")
    parser.add_argument(
        "--labels-json",
        default=None,
        help="Optional JSON mapping for labels (inline JSON or file path)",
    )
    parser.add_argument("--config", default=None, help="Optional JSON config path")
    args = parser.parse_args()

    config = load_config(args.config)
    reference_dir = args.reference_dir or str(config.reference_dir)
    index_dir = args.index_dir or str(config.index_dir)
    labels = _load_labels(args.labels_json)

    embedding_provider = build_embedding_provider(config)
    repo = FaissVectorIndexRepository(index_dir=index_dir, embedding_provider=embedding_provider, use_faiss=True)
    repo.build_from_folder(reference_dir=reference_dir, label_map=labels, recursive=bool(args.recursive))
    repo.save()

    metadata_path = Path(index_dir).resolve() / "metadata.json"
    metadata_count = 0
    if metadata_path.exists():
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            metadata_count = len(loaded)

    summary = {
        "reference_dir": str(Path(reference_dir).resolve()),
        "index_dir": str(Path(index_dir).resolve()),
        "recursive": bool(args.recursive),
        "images_indexed": metadata_count,
        "metadata_path": str(metadata_path),
        "index_path": str(Path(index_dir).resolve() / "index.faiss"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
