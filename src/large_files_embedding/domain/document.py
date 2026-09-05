"""Shared document identity, signature, and family routing rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    HANG = "hang"
    SOFFICE_MISSING = "soffice_missing"
    MOJIBAKE = "mojibake"
    UNSUPPORTED_CONVERTER = "unsupported_converter"
    CONVERSION_FAILED = "conversion_failed"


CALAMINE_ENGINE = "calamine"
LIBREOFFICE_CONVERTER = "libreoffice"
DEFAULT_OFFICE_TIMEOUT_SECONDS = 120.0
WORD_2007_FILTER = "docx:MS Word 2007 XML"
PPTX_FILTER = "pptx:Impress MS PowerPoint 2007 XML"
FORBIDDEN_CONVERTERS = frozenset(
    {"antiword", "catdoc", "catppt", "python-docx", "python-pptx"}
)


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


class NormalizationError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


class ConversionTimeout(NormalizationError):
    def __init__(self) -> None:
        super().__init__(FailureReason.HANG)


class SofficeMissing(NormalizationError):
    def __init__(self) -> None:
        super().__init__(FailureReason.SOFFICE_MISSING)


class ConversionFailed(NormalizationError):
    def __init__(self, reason: FailureReason = FailureReason.CONVERSION_FAILED) -> None:
        super().__init__(reason)


class UnsupportedConverterError(NormalizationError):
    def __init__(self, converter: str) -> None:
        self.converter = converter
        super().__init__(FailureReason.UNSUPPORTED_CONVERTER, converter)


def modern_office_target(source_format: DocumentFormat) -> DocumentFormat:
    if source_format is DocumentFormat.DOC:
        return DocumentFormat.DOCX
    if source_format is DocumentFormat.PPT:
        return DocumentFormat.PPTX
    raise UnsupportedConverterError(source_format.value)


def soffice_filter(source_format: DocumentFormat) -> str:
    target = modern_office_target(source_format)
    if target is DocumentFormat.DOCX:
        return WORD_2007_FILTER
    return PPTX_FILTER


def has_broken_hangul(text: str) -> bool:
    return "\ufffd" in text or "□□" in text


class OfficeNormalizer(Protocol):
    def convert(
        self,
        source: Path,
        output_dir: Path,
        *,
        source_format: DocumentFormat,
        timeout_seconds: float,
    ) -> Path:
        """Convert OLE .doc/.ppt to OOXML. Must not delete source."""
        ...


@dataclass(frozen=True)
class ConversionMetadata:
    converted_from: DocumentFormat
    converter: str
    converted_at: datetime

    def __post_init__(self) -> None:
        if (
            self.converter in FORBIDDEN_CONVERTERS
            or self.converter != LIBREOFFICE_CONVERTER
        ):
            raise UnsupportedConverterError(self.converter)
        modern_office_target(self.converted_from)


@dataclass(frozen=True)
class NormalizationResult:
    source_path: Path
    derived_path: Path | None
    metadata: ConversionMetadata | None
    failure_reason: FailureReason | None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


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
