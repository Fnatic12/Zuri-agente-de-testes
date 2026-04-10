from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, cast

import cv2
import numpy as np
from PIL import Image

try:
    import torch
    from torch import nn
    from torchvision import models
except Exception:  # pragma: no cover
    torch = None
    nn = None
    models = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


PROJECT_ROOT = Path(__file__).resolve().parents[5]


@dataclass
class BackendStatus:
    semantic_available: bool
    semantic_engine: str
    ocr_available: bool
    ocr_engine: str
    details: str = ""


def _normalize_vector(values: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(values))
    if norm <= 0.0:
        return values.astype(np.float32)
    return (values / norm).astype(np.float32)


def _sanitize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _candidate_tesseract_paths() -> list[str]:
    candidates = []
    env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if env_cmd:
        candidates.append(env_cmd)
    which_cmd = shutil.which("tesseract")
    if which_cmd:
        candidates.append(which_cmd)
    candidates.extend(
        [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Users\Automation01\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
        ]
    )
    seen = set()
    ordered = []
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _resolve_tesseract_cmd() -> Optional[str]:
    if pytesseract is None:
        return None
    for path in _candidate_tesseract_paths():
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return path
    return None


def _candidate_tessdata_dirs() -> list[str]:
    candidates = []
    env_dir = os.environ.get("TESSDATA_PREFIX", "").strip()
    if env_dir:
        candidates.append(env_dir)
    env_hmi_dir = os.environ.get("HMI_TESSDATA_DIR", "").strip()
    if env_hmi_dir:
        candidates.append(env_hmi_dir)
    candidates.append(str(PROJECT_ROOT / "HMI" / "tessdata"))
    cmd = _resolve_tesseract_cmd()
    if cmd:
        candidates.append(os.path.join(os.path.dirname(cmd), "tessdata"))
    seen = set()
    ordered = []
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _resolve_tessdata_dir() -> Optional[str]:
    for tessdata_dir in _candidate_tessdata_dirs():
        if os.path.isdir(tessdata_dir):
            os.environ["TESSDATA_PREFIX"] = tessdata_dir
            return tessdata_dir
    return None


def _available_ocr_languages() -> set[str]:
    tessdata_dir = _resolve_tessdata_dir()
    if not tessdata_dir:
        return set()
    languages = set()
    for name in os.listdir(tessdata_dir):
        if name.lower().endswith(".traineddata"):
            languages.add(os.path.splitext(name)[0].lower())
    return languages


def _ocr_language_config() -> str:
    langs = _available_ocr_languages()
    if "por" in langs and "eng" in langs:
        return "por+eng"
    if "eng" in langs:
        return "eng"
    if "por" in langs:
        return "por"
    return "eng"


def _ocr_cli_config() -> str:
    if _resolve_tessdata_dir():
        return "--psm 6"
    return "--psm 6"


@lru_cache(maxsize=1)
def _load_semantic_models() -> Dict[str, Any]:
    if torch is None or nn is None or models is None:
        raise RuntimeError("Torch/torchvision indisponiveis.")

    resnet_weights = models.ResNet50_Weights.DEFAULT
    resnet = models.resnet50(weights=resnet_weights)
    resnet.fc = cast(Any, nn.Identity())
    resnet.eval()

    vit_weights = models.ViT_B_16_Weights.DEFAULT
    vit = models.vit_b_16(weights=vit_weights)
    vit.heads = cast(Any, nn.Identity())
    vit.eval()

    return {
        "resnet": resnet,
        "resnet_transform": resnet_weights.transforms(),
        "vit": vit,
        "vit_transform": vit_weights.transforms(),
    }


def get_backend_status() -> BackendStatus:
    semantic_available = torch is not None and nn is not None and models is not None
    semantic_engine = "torchvision: resnet50 + vit_b_16" if semantic_available else "semantic off"
    ocr_available = False
    ocr_engine = "ocr off"
    details = "Semantic embeddings locais habilitadas." if semantic_available else "Semantic embeddings locais indisponiveis."

    tesseract_cmd = _resolve_tesseract_cmd()
    if pytesseract is not None and tesseract_cmd:
        try:
            pytesseract.get_tesseract_version()
            ocr_available = True
            ocr_engine = f"tesseract {_ocr_language_config()} ({os.path.basename(tesseract_cmd)})"
            details += f" OCR local habilitado em {tesseract_cmd}."
        except Exception:
            ocr_available = False
            ocr_engine = "tesseract indisponivel"
            details += " OCR local indisponivel."

    return BackendStatus(
        semantic_available=semantic_available,
        semantic_engine=semantic_engine,
        ocr_available=ocr_available,
        ocr_engine=ocr_engine,
        details=details,
    )


def extract_semantic_embedding(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    if torch is None or nn is None or models is None:
        return None

    try:
        pack = _load_semantic_models()
    except Exception:
        return None

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)

    with torch.no_grad():
        res_tensor = pack["resnet_transform"](pil).unsqueeze(0)
        vit_tensor = pack["vit_transform"](pil).unsqueeze(0)

        res_vector = pack["resnet"](res_tensor).detach().cpu().numpy().reshape(-1)
        vit_vector = pack["vit"](vit_tensor).detach().cpu().numpy().reshape(-1)

    res_vector = _normalize_vector(res_vector)
    vit_vector = _normalize_vector(vit_vector)
    combined = np.concatenate([res_vector, vit_vector], axis=0)
    return _normalize_vector(combined)


def embedding_to_list(embedding: Optional[np.ndarray]) -> Optional[list[float]]:
    if embedding is None:
        return None
    return cast(list[float], embedding.astype(np.float32).tolist())


def cosine_similarity_from_lists(a: Optional[list[float]], b: Optional[np.ndarray]) -> Optional[float]:
    if a is None or b is None:
        return None
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    if arr_a.size == 0 or arr_b.size == 0 or arr_a.shape != arr_b.shape:
        return None
    denom = float(np.linalg.norm(arr_a) * np.linalg.norm(arr_b))
    if denom <= 0.0:
        return None
    return float(np.dot(arr_a, arr_b) / denom)


def extract_ocr_text(img_bgr: np.ndarray) -> str:
    if pytesseract is None:
        return ""
    if _resolve_tesseract_cmd() is None:
        return ""
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return ""

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(
        thresh,
        lang=_ocr_language_config(),
        config=_ocr_cli_config(),
    )
    return _sanitize_text(text)


def compare_texts(text_a: str, text_b: str) -> Optional[float]:
    a = _sanitize_text(text_a)
    b = _sanitize_text(text_b)
    if not a or not b:
        return None
    return float(SequenceMatcher(None, a, b).ratio())
