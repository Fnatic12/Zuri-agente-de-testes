from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class VisualQaConfig:
    reference_dir: Path
    index_dir: Path
    runs_dir: Path
    top_k: int
    classification_threshold: float
    embedding_provider: str
    mobileclip_model: str
    openclip_model: str
    openclip_pretrained: str
    use_faiss: bool
    report_mode: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_s: int
    config_path: Optional[Path]

    def snapshot(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        return data


DEFAULTS = {
    "reference_dir": "reference_images",
    "index_dir": "artifacts/vector_index",
    "runs_dir": "runs",
    "top_k": 5,
    "classification_threshold": 0.35,
    "embedding_provider": "auto",
    "mobileclip_model": "MobileCLIP-S1",
    "openclip_model": "ViT-B-32",
    "openclip_pretrained": "laion2b_s34b_b79k",
    "use_faiss": True,
    "report_mode": "null",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3.1:8b",
    "ollama_timeout_s": 45,
}


def load_config(explicit_config_path: Optional[str] = None) -> VisualQaConfig:
    cwd = Path.cwd()
    path_from_env = os.getenv("VISUAL_QA_CONFIG_PATH")
    raw_path = explicit_config_path or path_from_env
    config_path: Optional[Path] = Path(raw_path).resolve() if raw_path else None

    merged: Dict[str, Any] = dict(DEFAULTS)
    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            file_data = json.load(fh)
        if isinstance(file_data, dict):
            merged.update(file_data)

    merged["reference_dir"] = os.getenv("VISUAL_QA_REFERENCE_DIR", merged["reference_dir"])
    merged["index_dir"] = os.getenv("VISUAL_QA_INDEX_DIR", merged["index_dir"])
    merged["runs_dir"] = os.getenv("VISUAL_QA_RUNS_DIR", merged["runs_dir"])
    merged["top_k"] = int(os.getenv("VISUAL_QA_TOP_K", str(merged["top_k"])))
    merged["classification_threshold"] = float(
        os.getenv("VISUAL_QA_CLASSIFICATION_THRESHOLD", str(merged["classification_threshold"]))
    )
    merged["embedding_provider"] = os.getenv("VISUAL_QA_EMBEDDING_PROVIDER", merged["embedding_provider"])
    merged["mobileclip_model"] = os.getenv("VISUAL_QA_MOBILECLIP_MODEL", merged["mobileclip_model"])
    merged["openclip_model"] = os.getenv("VISUAL_QA_OPENCLIP_MODEL", merged["openclip_model"])
    merged["openclip_pretrained"] = os.getenv("VISUAL_QA_OPENCLIP_PRETRAINED", merged["openclip_pretrained"])
    merged["use_faiss"] = _as_bool(os.getenv("VISUAL_QA_USE_FAISS", str(merged["use_faiss"])), default=True)
    merged["report_mode"] = os.getenv("VISUAL_QA_REPORT_MODE", merged["report_mode"]).strip().lower()
    merged["ollama_base_url"] = os.getenv("VISUAL_QA_OLLAMA_BASE_URL", merged["ollama_base_url"])
    merged["ollama_model"] = os.getenv("VISUAL_QA_OLLAMA_MODEL", merged["ollama_model"])
    merged["ollama_timeout_s"] = int(os.getenv("VISUAL_QA_OLLAMA_TIMEOUT_S", str(merged["ollama_timeout_s"])))

    reference_dir = Path(str(merged["reference_dir"]))
    index_dir = Path(str(merged["index_dir"]))
    runs_dir = Path(str(merged["runs_dir"]))
    if not reference_dir.is_absolute():
        reference_dir = (cwd / reference_dir).resolve()
    if not index_dir.is_absolute():
        index_dir = (cwd / index_dir).resolve()
    if not runs_dir.is_absolute():
        runs_dir = (cwd / runs_dir).resolve()

    return VisualQaConfig(
        reference_dir=reference_dir,
        index_dir=index_dir,
        runs_dir=runs_dir,
        top_k=max(1, int(merged["top_k"])),
        classification_threshold=float(merged["classification_threshold"]),
        embedding_provider=str(merged["embedding_provider"]).strip().lower(),
        mobileclip_model=str(merged["mobileclip_model"]),
        openclip_model=str(merged["openclip_model"]),
        openclip_pretrained=str(merged["openclip_pretrained"]),
        use_faiss=bool(merged["use_faiss"]),
        report_mode=str(merged["report_mode"]).strip().lower(),
        ollama_base_url=str(merged["ollama_base_url"]).rstrip("/"),
        ollama_model=str(merged["ollama_model"]),
        ollama_timeout_s=max(1, int(merged["ollama_timeout_s"])),
        config_path=config_path,
    )
