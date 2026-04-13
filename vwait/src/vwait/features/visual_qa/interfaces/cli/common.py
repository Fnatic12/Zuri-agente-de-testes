from __future__ import annotations

from dataclasses import dataclass

from visual_qa.application.use_cases.build_vector_index import BuildVectorIndex
from visual_qa.application.use_cases.classify_screenshot import ClassifyScreenshot
from visual_qa.application.use_cases.generate_report import GenerateReport
from visual_qa.application.use_cases.validate_screenshot import ValidateScreenshot
from visual_qa.application.use_cases.visual_qa_pipeline import VisualQaPipeline
from visual_qa.config import VisualQaConfig
from visual_qa.infrastructure.embeddings.factory import build_embedding_provider
from visual_qa.infrastructure.llm.factory import build_report_generator
from visual_qa.infrastructure.pixel_compare.existing_pixel_adapter import ExistingPixelAdapter
from visual_qa.infrastructure.storage.local_artifact_store import LocalArtifactStore
from visual_qa.infrastructure.vector_index.faiss_repository import FaissVectorIndexRepository


@dataclass
class CliContainer:
    build_index: BuildVectorIndex
    classify: ClassifyScreenshot
    validate: ValidateScreenshot
    pipeline: VisualQaPipeline


def make_container(config: VisualQaConfig) -> CliContainer:
    embedding_provider = build_embedding_provider(config)
    vector_repo_for_build = FaissVectorIndexRepository(use_faiss=config.use_faiss)
    vector_repo_for_query = FaissVectorIndexRepository(use_faiss=config.use_faiss)

    build_index = BuildVectorIndex(embedding_provider=embedding_provider, vector_repo=vector_repo_for_build)
    classify = ClassifyScreenshot(embedding_provider=embedding_provider, vector_repo=vector_repo_for_query)

    pixel_adapter = ExistingPixelAdapter()
    validate = ValidateScreenshot(classifier=classify, pixel_comparator=pixel_adapter)

    report_generator = build_report_generator(config)
    report_use_case = GenerateReport(report_generator=report_generator)
    artifact_store = LocalArtifactStore(runs_dir=str(config.runs_dir))
    pipeline = VisualQaPipeline(validator=validate, report_use_case=report_use_case, artifact_store=artifact_store)

    return CliContainer(build_index=build_index, classify=classify, validate=validate, pipeline=pipeline)
