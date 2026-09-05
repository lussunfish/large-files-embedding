"""CLI adapter: route, normalize OLE, ingest narrative A/B/D and tabular C."""

from pathlib import Path

import typer

from large_files_embedding.application.ingest_narrative import IngestNarrative
from large_files_embedding.application.ingest_tabular import IngestTabular
from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import (
    Document,
    DocumentFamily,
    FailureReason,
    NarrativeIngestResult,
    NormalizationResult,
    TabularIngestResult,
)
from large_files_embedding.infrastructure.calamine_extractor import (
    CalamineTabularExtractor,
)
from large_files_embedding.infrastructure.docling_adapter import DoclingNarrativeParser
from large_files_embedding.infrastructure.embedding_encoder import DenseSparseEncoder
from large_files_embedding.infrastructure.format_detector import MagicFormatDetector
from large_files_embedding.infrastructure.libreoffice_normalizer import (
    LibreOfficeNormalizer,
)
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore


def ingest(path: Path) -> None:
    """Route by signature, normalize OLE, ingest narrative A/B/D and tabular C."""
    router = RouteFile(MagicFormatDetector())
    office = NormalizeOffice(LibreOfficeNormalizer())
    narrative: IngestNarrative | None = None
    tabular: IngestTabular | None = None
    objects: MinioObjectStore | None = None

    def get_objects() -> MinioObjectStore:
        nonlocal objects
        if objects is None:
            objects = MinioObjectStore.from_env()
        return objects

    def get_narrative() -> IngestNarrative:
        nonlocal narrative
        if narrative is None:
            narrative = IngestNarrative(
                DoclingNarrativeParser(),
                DenseSparseEncoder.from_env(),
                MilvusChunkStore.from_env(),
                get_objects(),
            )
        return narrative

    def get_tabular() -> IngestTabular:
        nonlocal tabular
        if tabular is None:
            tabular = IngestTabular(
                CalamineTabularExtractor(),
                MariaDbTableStore.from_env(),
                get_objects(),
                xls_fallback=LibreOfficeNormalizer(),
            )
        return tabular

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
            try:
                tresult = get_tabular().execute(document, ingest_path=ingest_path)
            except Exception:
                tresult = TabularIngestResult(
                    document.path,
                    None,
                    0,
                    None,
                    (),
                    None,
                    0,
                    FailureReason.EXTRACT_FAILED,
                )
            typer.echo(_format_tabular(document, tresult))
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
    return (
        f"{document.path} family={decision.family.value} "
        f"format={decision.detected_format.value} normalize={normalize}{engine}"
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


def _format_tabular(document: Document, result: TabularIngestResult) -> str:
    if result.failure_reason is not None:
        return f"{document.path} FAIL reason={result.failure_reason.value}"
    fact = result.fact_table or "none"
    return (
        f"{document.path} sheets={result.sheet_count} "
        f"profile={result.profile_key} parquet={len(result.parquet_keys)} "
        f"fact={fact}"
    )
