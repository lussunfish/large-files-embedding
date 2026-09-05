"""Shared document identity, signature, and family routing rules."""

from __future__ import annotations

import re
from collections.abc import Sequence
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
    ENCRYPTED_PDF = "encrypted_pdf"
    BROKEN_XREF = "broken_xref"
    EMPTY_DOCUMENT = "empty_document"
    PARSE_FAILED = "parse_failed"
    MARKDOWN_DUMP = "markdown_dump"
    MIXED_TABLE_PROSE = "mixed_table_prose"
    FIXED_LENGTH_CHUNK = "fixed_length_chunk"
    DUMMY_VECTOR = "dummy_vector"
    FORBIDDEN_COLLECTION = "forbidden_collection"
    FORBIDDEN_BUCKET = "forbidden_bucket"
    TABULAR_NOT_NARRATIVE = "tabular_not_narrative"


CALAMINE_ENGINE = "calamine"
LIBREOFFICE_CONVERTER = "libreoffice"
DEFAULT_OFFICE_TIMEOUT_SECONDS = 120.0
WORD_2007_FILTER = "docx:MS Word 2007 XML"
PPTX_FILTER = "pptx:Impress MS PowerPoint 2007 XML"
FORBIDDEN_CONVERTERS = frozenset(
    {"antiword", "catdoc", "catppt", "python-docx", "python-pptx"}
)
MARKET_QUALITY_COLLECTION = "market_quality_chunks_hybrid"
FORBIDDEN_COLLECTIONS = frozenset({"psychology_chunks_hybrid", "ebook_chunks_hybrid"})
MARKET_QUALITY_BUCKET = "market-quality-docs"
FORBIDDEN_BUCKETS = frozenset({"psychology-pdfs", "ebook-pdfs"})
DEFAULT_EMBEDDING_DIM = 2560
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:4b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_MILVUS_URI = "http://127.0.0.1:19530"
DEFAULT_MINIO_ENDPOINT = "http://127.0.0.1:9000"
SECTION_PATH_MAX_LENGTH = 1024
PARENT_ID_MAX_LENGTH = 2048
_PART_NO_RE = re.compile(
    r"(?:품번|part[\s_-]?no)[:\s]*([A-Z0-9][A-Z0-9._/-]{1,})",
    re.IGNORECASE,
)
_VEHICLE_RE = re.compile(r"(?:차종|vehicle)[:\s]*([A-Za-z0-9가-힣_-]+)", re.IGNORECASE)


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


class ChunkType(StrEnum):
    TEXT = "text"
    TABLE = "table"


class ChunkOrigin(StrEnum):
    JSON = "json"
    MARKDOWN_DUMP = "markdown_dump"
    FIXED_LENGTH = "fixed_length"


class NarrativeIngestError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


class NarrativeParseError(NarrativeIngestError):
    pass


@dataclass(frozen=True)
class NarrativeChunk:
    chunk_id: str
    doc_id: str
    path: str
    family: DocumentFamily
    chunk_type: ChunkType
    text: str
    embedding_input: str
    origin: ChunkOrigin = ChunkOrigin.JSON
    section_path: str | None = None
    slide_index: int | None = None
    page: int | None = None
    parent_id: str | None = None
    speaker_notes: str | None = None
    product: str | None = None
    period: str | None = None
    doc_type: str | None = None
    vehicle: str | None = None
    part_no: str | None = None


@dataclass(frozen=True)
class ParsedNarrative:
    doc_id: str
    path: Path
    family: DocumentFamily
    json_bytes: bytes
    chunks: tuple[NarrativeChunk, ...]
    pipeline: str
    ocr_lang: tuple[str, ...] | None = None
    header_footer: str | None = None


@dataclass(frozen=True)
class EncodedEmbedding:
    dense: tuple[float, ...]
    sparse: tuple[tuple[int, float], ...]
    model: str


@dataclass(frozen=True)
class StoredChunk:
    chunk: NarrativeChunk
    embedding: EncodedEmbedding


@dataclass(frozen=True)
class NarrativeIngestResult:
    source_path: Path
    doc_id: str | None
    chunk_count: int
    json_key: str | None
    original_key: str | None
    failure_reason: FailureReason | None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


class NarrativeParser(Protocol):
    def parse(
        self, path: Path, *, family: DocumentFamily, doc_id: str
    ) -> ParsedNarrative:
        """Parse a narrative file into Docling JSON and structure-aware chunks."""
        ...


class EmbeddingEncoder(Protocol):
    def encode(self, texts: Sequence[str]) -> list[EncodedEmbedding]:
        """Encode contextualized chunk texts. Dense must be non-zero."""
        ...


class ChunkStore(Protocol):
    def upsert(self, collection: str, records: Sequence[StoredChunk]) -> None:
        """Upsert narrative chunks into the shared Milvus collection."""
        ...


class ObjectStore(Protocol):
    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        """Store bytes (Docling JSON)."""
        ...

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        """Store a file without requiring the caller to load it fully."""
        ...


def require_collection(name: str) -> str:
    if name in FORBIDDEN_COLLECTIONS or name != MARKET_QUALITY_COLLECTION:
        raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, name)
    return name


def require_bucket(name: str) -> str:
    if name in FORBIDDEN_BUCKETS or name != MARKET_QUALITY_BUCKET:
        raise NarrativeIngestError(FailureReason.FORBIDDEN_BUCKET, name)
    return name


def require_milvus_uri(uri: str) -> str:
    lowered = uri.strip().lower()
    if lowered.endswith(".db") or "milvus.db" in lowered or lowered.startswith("file:"):
        raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, uri)
    return uri


def require_nonzero_embedding(embedding: EncodedEmbedding) -> EncodedEmbedding:
    if len(embedding.dense) != DEFAULT_EMBEDDING_DIM:
        raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
    if all(abs(value) < 1e-15 for value in embedding.dense):
        raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
    if not embedding.sparse:
        raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
    return embedding


def validate_narrative_chunks(
    chunks: Sequence[NarrativeChunk], *, json_bytes: bytes
) -> None:
    if not json_bytes:
        raise NarrativeIngestError(FailureReason.MARKDOWN_DUMP)
    if not chunks:
        raise NarrativeIngestError(FailureReason.EMPTY_DOCUMENT)
    for chunk in chunks:
        _validate_chunk(chunk)


def _validate_chunk(chunk: NarrativeChunk) -> None:
    if chunk.origin is ChunkOrigin.MARKDOWN_DUMP:
        raise NarrativeIngestError(FailureReason.MARKDOWN_DUMP)
    if chunk.origin is ChunkOrigin.FIXED_LENGTH:
        raise NarrativeIngestError(FailureReason.FIXED_LENGTH_CHUNK)
    if chunk.family is DocumentFamily.C:
        raise NarrativeIngestError(FailureReason.TABULAR_NOT_NARRATIVE)
    if chunk.family is DocumentFamily.D:
        if chunk.slide_index is None:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED)
        notes = chunk.speaker_notes
        if notes and notes not in chunk.embedding_input:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED)
    if chunk.chunk_type is ChunkType.TEXT and _mixed_table_prose(chunk.text):
        raise NarrativeIngestError(FailureReason.MIXED_TABLE_PROSE)


def _mixed_table_prose(text: str) -> bool:
    has_pipe_table = "|" in text and "---" in text
    has_sentence = any(marker in text for marker in (". ", "。", "다."))
    return has_pipe_table and has_sentence


def clip_varchar(value: str | None, max_length: int) -> str:
    text = value or ""
    if max_length <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_length:
        return text
    clipped = encoded[:max_length]
    while clipped:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return ""


def metadata_from_header_footer(text: str) -> tuple[str | None, str | None]:
    if not text.strip():
        return None, None
    part = _PART_NO_RE.search(text)
    vehicle = _VEHICLE_RE.search(text)
    return (
        part.group(1) if part else None,
        vehicle.group(1) if vehicle else None,
    )
