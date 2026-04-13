from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

from vwait.features.visual_qa.application.ports.embedding_provider import EmbeddingProvider
from vwait.features.visual_qa.application.ports.vector_index_repository import VectorIndexRepository
from vwait.features.visual_qa.domain.entities import ScreenMatch
from vwait.features.visual_qa.domain.scaffold_entities import ScreenMatch as Stage1ScreenMatch


def _as_mapping(item: Any) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        return item
    raise TypeError(f"Expected mapping-like search result item, got: {type(item)!r}")


def _normalize_result_item(item: Any) -> dict[str, Any]:
    row = _as_mapping(item)
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        metadata = {}

    screen_type = str(
        row.get("screen_type")
        or metadata.get("screen_type")
        or "unknown"
    )
    image_path = str(
        row.get("image_path")
        or metadata.get("image_path")
        or ""
    )
    score = float(row.get("score", 0.0))
    tags_raw = row.get("tags")
    if tags_raw is None:
        tags_raw = metadata.get("tags")
    tags = list(tags_raw or [])

    return {
        "screen_type": screen_type,
        "image_path": image_path,
        "score": score,
        "tags": tags,
        "metadata": dict(metadata),
    }


def _choose_best(items: list[dict[str, Any]], threshold: float) -> tuple[str, str | None, float]:
    if not items:
        return "unknown", None, 0.0

    best = items[0]
    score = float(best["score"])
    if score < threshold:
        return "unknown", None, score
    return str(best["screen_type"]), str(best["image_path"] or None), score


def _choose_vote(items: list[dict[str, Any]], threshold: float) -> tuple[str, str | None, float]:
    if not items:
        return "unknown", None, 0.0

    totals: dict[str, float] = {}
    best_item_by_type: dict[str, dict[str, Any]] = {}
    for item in items:
        screen_type = str(item["screen_type"])
        score = float(item["score"])
        totals[screen_type] = totals.get(screen_type, 0.0) + score

        prev = best_item_by_type.get(screen_type)
        if prev is None or float(prev["score"]) < score:
            best_item_by_type[screen_type] = item

    winner_type, winner_score = sorted(
        totals.items(),
        key=lambda pair: (
            pair[1],  # weighted vote score
            float(best_item_by_type[pair[0]]["score"]),  # deterministic tie-breaker
            pair[0],
        ),
        reverse=True,
    )[0]

    if winner_score < threshold:
        return "unknown", None, winner_score

    winner_best = best_item_by_type[winner_type]
    return winner_type, str(winner_best["image_path"] or None), winner_score


@dataclass
class ClassifyScreenshot:
    embedding_provider: EmbeddingProvider
    vector_repo: VectorIndexRepository

    def execute(
        self,
        screenshot_path: str,
        top_k: int,
        threshold: float,
        strategy: str = "best",
        index_dir: str | None = None,
    ) -> Dict[str, Any]:
        if index_dir:
            self.vector_repo.load(index_dir)

        mode = str(strategy or "best").strip().lower()
        if mode not in {"best", "vote"}:
            raise ValueError("strategy must be one of: 'best', 'vote'")

        query = self.embedding_provider.embed_image(screenshot_path)
        results = self.vector_repo.search(query, top_k=max(1, int(top_k)))
        normalized = [_normalize_result_item(item) for item in results]

        matches: List[ScreenMatch] = []
        top_k_rows: list[dict[str, Any]] = []
        for rank, item in enumerate(normalized, start=1):
            md = item["metadata"]
            matches.append(
                ScreenMatch(
                    rank=rank,
                    screen_type=str(item["screen_type"] or "unknown"),
                    image_path=str(item["image_path"] or ""),
                    similarity=float(item["score"]),
                    tags=list(item["tags"]),
                    metadata=md,
                )
            )
            top_k_rows.append(
                {
                    "rank": rank,
                    "screen_type": str(item["screen_type"]),
                    "image_path": str(item["image_path"]),
                    "score": float(item["score"]),
                    "tags": list(item["tags"]),
                }
            )

        score_threshold = float(threshold)
        if mode == "best":
            predicted, selected_baseline, winning_score = _choose_best(normalized, score_threshold)
        else:
            predicted, selected_baseline, winning_score = _choose_vote(normalized, score_threshold)

        stage1_match = Stage1ScreenMatch(
            screen_type=predicted,
            similarity_score=float(winning_score),
            matched_baseline_path=Path(selected_baseline) if selected_baseline else None,
            top_k=top_k_rows,
        )

        return {
            "screenshot_path": screenshot_path,
            "predicted_screen_type": predicted,
            "classification_threshold": float(threshold),
            "classification_strategy": mode,
            "winning_score": float(winning_score),
            "selected_baseline_image": selected_baseline,
            "matches": matches,
            "screen_match": stage1_match,
        }
