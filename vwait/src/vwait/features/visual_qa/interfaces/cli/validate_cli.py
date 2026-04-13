from __future__ import annotations

import argparse

from vwait.features.visual_qa.config import load_config
from vwait.features.visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
from vwait.features.visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
from vwait.features.visual_qa.infrastructure.embeddings.factory import build_embedding_provider
from vwait.features.visual_qa.infrastructure.llm.factory import build_report_generator
from vwait.features.visual_qa.infrastructure.llm.null_report_generator import NullReportGenerator
from vwait.features.visual_qa.infrastructure.pixel_compare.existing_pixel_adapter import ExistingPixelAdapter
from vwait.features.visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore
from vwait.features.visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full Visual QA pipeline.")
    parser.add_argument("--image", required=True, help="Screenshot path to validate")
    parser.add_argument("--index-dir", default=None, help="Vector index directory")
    parser.add_argument("--top-k", type=int, default=None, help="Top K matches")
    parser.add_argument("--threshold", type=float, default=None, help="Classification threshold")
    parser.add_argument(
        "--strategy",
        default="best",
        choices=["best", "vote"],
        help="Classification strategy",
    )
    parser.add_argument("--runs-dir", default=None, help="Output runs directory")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM and use deterministic Null report")
    parser.add_argument("--config", default=None, help="Optional JSON config path")
    args = parser.parse_args()

    config = load_config(args.config)
    index_dir = args.index_dir or str(config.index_dir)
    runs_dir = args.runs_dir or str(config.runs_dir)

    embedding_provider = build_embedding_provider(config)
    vector_repo = FaissVectorIndexRepository(index_dir=index_dir, use_faiss=True)
    classifier = ClassifyScreenshot(embedding_provider=embedding_provider, vector_repo=vector_repo)

    pixel_adapter = ExistingPixelAdapter()
    artifact_store = LocalArtifactStore(runs_dir=runs_dir)
    report_generator = NullReportGenerator() if args.no_llm else build_report_generator(config)

    validate = ValidateScreenshot(
        classifier=classifier,
        pixel_comparator=pixel_adapter,
        report_generator=report_generator,
        artifact_store=artifact_store,
    )

    run = validate.execute(
        screenshot_path=args.image,
        index_dir=index_dir,
        top_k=args.top_k or config.top_k,
        threshold=args.threshold if args.threshold is not None else config.classification_threshold,
        strategy=args.strategy,
        output_dir=None,
        config_snapshot=config.snapshot(),
    )

    if run.json_path is None:
        raise RuntimeError("Validation completed but run_result.json was not created.")
    print(str(run.json_path))


if __name__ == "__main__":
    main()
