"""Shared document identity, signature, and family routing rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class DocumentFamily(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class DocumentFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"
    PPTX = "pptx"
    PPT = "ppt"


class SignatureKind(StrEnum):
    PDF = "pdf"
    OOXML_WORD = "ooxml_word"
    OOXML_SHEET = "ooxml_sheet"
    OOXML_SLIDE = "ooxml_slide"
    OLE_WORD = "ole_word"
    OLE_SHEET = "ole_sheet"
    OLE_SLIDE = "ole_slide"
    CSV = "csv"
    RTF = "rtf"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class FailureReason(StrEnum):
    UNKNOWN_SIGNATURE = "unknown_signature"
    OUT_OF_SCOPE = "out_of_scope"
    CSV_PROSE = "csv_prose"
    RTF = "rtf"


CALAMINE_ENGINE = "calamine"


@dataclass(frozen=True)
class FileSignature:
    kind: SignatureKind
    csv_column_count: int | None = None


@dataclass(frozen=True)
class RouteDecision:
    family: DocumentFamily
    detected_format: DocumentFormat
    needs_normalization: bool
    preferred_engine: str | None = None


class FormatDetector(Protocol):
    def detect(self, path: Path) -> FileSignature:
        """Classify a file by content signature, not extension."""
        ...


@dataclass(frozen=True)
class Document:
    path: Path
    signature: FileSignature
    decision: RouteDecision | None
    failure_reason: FailureReason | None

    @classmethod
    def from_signature(cls, path: Path, signature: FileSignature) -> Document:
        decision, reason = route_signature(signature)
        return cls(
            path=path,
            signature=signature,
            decision=decision,
            failure_reason=reason,
        )

    @property
    def queued_for_failure(self) -> bool:
        return self.decision is None


def route_signature(
    signature: FileSignature,
) -> tuple[RouteDecision | None, FailureReason | None]:
    kind = signature.kind
    if kind is SignatureKind.PDF:
        return RouteDecision(DocumentFamily.B, DocumentFormat.PDF, False), None
    if kind is SignatureKind.OOXML_WORD:
        return RouteDecision(DocumentFamily.A, DocumentFormat.DOCX, False), None
    if kind is SignatureKind.OOXML_SHEET:
        return RouteDecision(DocumentFamily.C, DocumentFormat.XLSX, False), None
    if kind is SignatureKind.OOXML_SLIDE:
        return RouteDecision(DocumentFamily.D, DocumentFormat.PPTX, False), None
    if kind is SignatureKind.OLE_WORD:
        return RouteDecision(DocumentFamily.A, DocumentFormat.DOC, True), None
    if kind is SignatureKind.OLE_SHEET:
        return (
            RouteDecision(
                DocumentFamily.C,
                DocumentFormat.XLS,
                False,
                preferred_engine=CALAMINE_ENGINE,
            ),
            None,
        )
    if kind is SignatureKind.OLE_SLIDE:
        return RouteDecision(DocumentFamily.D, DocumentFormat.PPT, True), None
    if kind is SignatureKind.CSV:
        if signature.csv_column_count is None or signature.csv_column_count < 2:
            return None, FailureReason.CSV_PROSE
        return RouteDecision(DocumentFamily.C, DocumentFormat.CSV, False), None
    if kind is SignatureKind.RTF:
        return None, FailureReason.RTF
    if kind is SignatureKind.UNSUPPORTED:
        return None, FailureReason.OUT_OF_SCOPE
    return None, FailureReason.UNKNOWN_SIGNATURE
