"""CLI adapter: route, normalize OLE, ingest narrative families A/B/D."""

from pathlib import Path

import typer

from large_files_embedding.application.ingest_narrative import IngestNarrative
from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import (
    Document,
    DocumentFamily,
    FailureReason,
    NarrativeIngestResult,
    NormalizationResult,
)
from large_files_embedding.infrastructure.docling_adapter import DoclingNarrativeParser
from large_files_embedding.infrastructure.embedding_encoder import DenseSparseEncoder
from large_files_embedding.infrastructure.format_detector import MagicFormatDetector
from large_files_embedding.infrastructure.libreoffice_normalizer import (
    LibreOfficeNormalizer,
)
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore


def ingest(path: Path) -> None:
    """Route by signature, normalize OLE, ingest narrative A/B/D. Skip tabular C."""
    router = RouteFile(MagicFormatDetector())
    office = NormalizeOffice(LibreOfficeNormalizer())
    narrative: IngestNarrative | None = None

    def get_narrative() -> IngestNarrative:
        nonlocal narrative
        if narrative is None:
            narrative = IngestNarrative(
                DoclingNarrativeParser(),
                DenseSparseEncoder.from_env(),
                MilvusChunkStore.from_env(),
                MinioObjectStore.from_env(),
            )
        return narrative

    for document in router.execute_many(_expand(path)):
        ingest_path = document.path
        if document.decision is not None and document.decision.needs_normalization:
            result = office.execute(document)
            typer.echo(_format_normalization(document, result))
            if result.failed or result.derived_path is None:
                continue
            ingest_path = result.derived_path
        else:
            typer.echo(_format_line(document))
            if document.decision is None:
                continue
        if document.decision.family is DocumentFamily.C:
            continue
        try:
            nresult = get_narrative().execute(document, ingest_path=ingest_path)
        except Exception:
            nresult = NarrativeIngestResult(
                document.path,
                None,
                0,
                None,
                None,
                FailureReason.PARSE_FAILED,
            )
        typer.echo(_format_narrative(document, nresult))


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            child
            for child in path.iterdir()
            if child.is_file() and not child.name.startswith(".")
        )
    return [path]


def _format_line(document: Document) -> str:
    if document.decision is None:
        reason = (
            document.failure_reason.value
            if document.failure_reason is not None
            else "unknown_signature"
        )
        return f"{document.path} FAIL reason={reason}"
    decision = document.decision
    engine = f" engine={decision.preferred_engine}" if decision.preferred_engine else ""
    normalize = "true" if decision.needs_normalization else "false"
    skip = " skip=tabular" if decision.family is DocumentFamily.C else ""
    return (
        f"{document.path} family={decision.family.value} "
        f"format={decision.detected_format.value} normalize={normalize}{engine}{skip}"
    )


def _format_normalization(document: Document, result: NormalizationResult) -> str:
    if result.failure_reason is not None:
        return f"{document.path} FAIL reason={result.failure_reason.value}"
    decision = document.decision
    metadata = result.metadata
    assert decision is not None
    assert metadata is not None
    assert result.derived_path is not None
    return (
        f"{document.path} family={decision.family.value} "
        f"format={decision.detected_format.value} normalize=true "
        f"derived={result.derived_path} converter={metadata.converter} "
        f"converted_from={metadata.converted_from.value} "
        f"converted_at={metadata.converted_at.isoformat()}"
    )


def _format_narrative(document: Document, result: NarrativeIngestResult) -> str:
    if result.failure_reason is not None:
        return f"{document.path} FAIL reason={result.failure_reason.value}"
    return (
        f"{document.path} chunks={result.chunk_count} "
        f"collection=market_quality_chunks_hybrid json={result.json_key}"
    )
