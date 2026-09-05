"""CLI adapter for signature routing (UC-01)."""

from pathlib import Path

import typer

from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import Document
from large_files_embedding.infrastructure.format_detector import MagicFormatDetector


def ingest(path: Path) -> None:
    """Route files by signature and print family or failure-queue reason."""
    router = RouteFile(MagicFormatDetector())
    for document in router.execute_many(_expand(path)):
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
