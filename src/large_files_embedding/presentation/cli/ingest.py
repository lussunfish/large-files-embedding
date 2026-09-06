"""CLI adapter: route, skip unchanged, normalize OLE, ingest A/B/C/D."""

import logging
import traceback
from pathlib import Path

import typer

from large_files_embedding.application.ingest_narrative import IngestNarrative
from large_files_embedding.application.ingest_tabular import IngestTabular
from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.application.skip_unchanged_ingest import (
    SkipIngestResult,
    SkipUnchangedIngest,
)
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
from large_files_embedding.infrastructure.mariadb_manifest_store import (
    MariaDbManifestStore,
)
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore


def ingest(
    path: Path,
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Route by signature, skip unchanged bytes, ingest narrative or tabular."""
    router = RouteFile(MagicFormatDetector())
    office = NormalizeOffice(LibreOfficeNormalizer())
    narrative: IngestNarrative | None = None
    tabular: IngestTabular | None = None
    objects: MinioObjectStore | None = None
    skipper: SkipUnchangedIngest | None = None

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

    def get_skipper() -> SkipUnchangedIngest:
        nonlocal skipper
        if skipper is None:
            skipper = SkipUnchangedIngest(MariaDbManifestStore.from_env())
        return skipper

    for document in router.execute_many(_expand(path)):
        if document.decision is None:
            typer.echo(_format_line(document))
            continue
        if not document.decision.needs_normalization:
            typer.echo(_format_line(document))

        def run_ingest(
            current: Document,
        ) -> NarrativeIngestResult | TabularIngestResult:
            ingest_path = current.path
            decision = current.decision
            assert decision is not None
            if decision.needs_normalization:
                result = office.execute(current)
                typer.echo(_format_normalization(current, result))
                if result.failed or result.derived_path is None:
                    return NarrativeIngestResult(
                        current.path,
                        None,
                        0,
                        None,
                        None,
                        result.failure_reason,
                    )
                ingest_path = result.derived_path
            if decision.family is DocumentFamily.C:
                try:
                    return get_tabular().execute(current, ingest_path=ingest_path)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "tabular ingest crashed for %s", current.path
                    )
                    typer.echo(traceback.format_exc(), err=True)
                    return TabularIngestResult(
                        current.path,
                        None,
                        0,
                        None,
                        (),
                        None,
                        0,
                        FailureReason.EXTRACT_FAILED,
                    )
            try:
                return get_narrative().execute(current, ingest_path=ingest_path)
            except Exception:
                logging.getLogger(__name__).exception(
                    "narrative ingest crashed for %s", current.path
                )
                typer.echo(traceback.format_exc(), err=True)
                return NarrativeIngestResult(
                    current.path,
                    None,
                    0,
                    None,
                    None,
                    FailureReason.PARSE_FAILED,
                )

        try:
            outcome = get_skipper().execute(document, ingest=run_ingest, force=force)
        except Exception:
            logging.getLogger(__name__).exception(
                "skip/ingest crashed for %s", document.path
            )
            typer.echo(traceback.format_exc(), err=True)
            reason = FailureReason.MANIFEST_LOOKUP_FAILED.value
            typer.echo(f"{document.path} FAIL reason={reason}")
            continue
        if outcome.skipped:
            typer.echo(_format_skip(document, outcome))
            continue
        ingested = outcome.ingest_result
        write_failed = outcome.failed and ingested is not None and not ingested.failed
        if ingested is None or write_failed:
            reason = (
                outcome.failure_reason.value
                if outcome.failure_reason is not None
                else FailureReason.MANIFEST_LOOKUP_FAILED.value
            )
            typer.echo(f"{document.path} FAIL reason={reason}")
            continue
        if document.decision.needs_normalization and ingested.failed:
            continue
        if document.decision.family is DocumentFamily.C:
            assert isinstance(ingested, TabularIngestResult)
            typer.echo(_format_tabular(document, ingested))
            continue
        assert isinstance(ingested, NarrativeIngestResult)
        typer.echo(_format_narrative(document, ingested))


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


def _format_skip(document: Document, result: SkipIngestResult) -> str:
    reason = result.skip_reason or "unchanged_content"
    return f"{document.path} SKIP reason={reason} sha256={result.content_sha256}"


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
