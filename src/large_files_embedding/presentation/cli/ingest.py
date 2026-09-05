"""CLI adapter for signature routing (UC-01) and office normalization (UC-02)."""

from pathlib import Path

import typer

from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import Document, NormalizationResult
from large_files_embedding.infrastructure.format_detector import MagicFormatDetector
from large_files_embedding.infrastructure.libreoffice_normalizer import (
    LibreOfficeNormalizer,
)


def ingest(path: Path) -> None:
    """Route files by signature; normalize OLE .doc/.ppt. Do not ingest further."""
    router = RouteFile(MagicFormatDetector())
    office = NormalizeOffice(LibreOfficeNormalizer())
    for document in router.execute_many(_expand(path)):
        if document.decision is not None and document.decision.needs_normalization:
            result = office.execute(document)
            typer.echo(_format_normalization(document, result))
        else:
            typer.echo(_format_line(document))


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
