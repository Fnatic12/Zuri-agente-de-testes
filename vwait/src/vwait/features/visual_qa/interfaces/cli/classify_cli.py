from __future__ import annotations

import argparse
import json

from vwait.features.visual_qa.config import load_config
from vwait.features.visual_qa.interfaces.cli.common import make_container


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify screenshot using vector similarity index.")
    parser.add_argument("--image", required=True, help="Screenshot path")
    parser.add_argument("--index-dir", default=None, help="Vector index directory")
    parser.add_argument("--top-k", type=int, default=None, help="Top K matches")
    parser.add_argument("--threshold", type=float, default=None, help="Classification threshold")
    parser.add_argument(
        "--strategy",
        default="best",
        choices=["best", "vote"],
        help="Classification strategy",
    )
    parser.add_argument("--config", default=None, help="Optional JSON config path")
    args = parser.parse_args()

    config = load_config(args.config)
    container = make_container(config)

    result = container.classify.execute(
        screenshot_path=args.image,
        index_dir=args.index_dir or str(config.index_dir),
        top_k=args.top_k or config.top_k,
        threshold=args.threshold if args.threshold is not None else config.classification_threshold,
        strategy=args.strategy,
    )

    out = {
        "screenshot_path": result["screenshot_path"],
        "predicted_screen_type": result["predicted_screen_type"],
        "classification_threshold": result["classification_threshold"],
        "classification_strategy": result.get("classification_strategy"),
        "winning_score": result.get("winning_score"),
        "selected_baseline_image": result["selected_baseline_image"],
        "matches": [
            {
                "rank": m.rank,
                "screen_type": m.screen_type,
                "image_path": m.image_path,
                "similarity": m.similarity,
                "tags": m.tags,
            }
            for m in result["matches"]
        ],
        "top_k": result.get("screen_match").top_k if result.get("screen_match") else [],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
