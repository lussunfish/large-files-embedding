"""Shared document identity, signature, and family routing rules."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
    NARRATIVE_NOT_TABULAR = "narrative_not_tabular"
    ROW_EMBEDDING = "row_embedding"
    CAUSE_COLUMN_DROPPED = "cause_column_dropped"
    SNAPSHOT_UNION = "snapshot_union"
    TABLE_PER_FILE = "table_per_file"
    XLSX_BLOB = "xlsx_blob"
    EMBEDDINGS_VECTOR = "embeddings_vector"
    EXTRACT_FAILED = "extract_failed"
    FORBIDDEN_ENGINE = "forbidden_engine"
    PROFILE_TOO_LARGE = "profile_too_large"
    ORIGINAL_COLUMN_DROPPED = "original_column_dropped"
    SQL_WRITE = "sql_write"
    SQL_NOT_ALLOWED = "sql_not_allowed"
    UNKNOWN_MCP_TOOL = "unknown_mcp_tool"
    QUERY_FAILED = "query_failed"
    EMPTY_MCP_COMMAND = "empty_mcp_command"
    PROTECTED_GROK_PATH = "protected_grok_path"
    STARTUP_TIMEOUT_TOO_SHORT = "startup_timeout_too_short"
    MANIFEST_LOOKUP_FAILED = "manifest_lookup_failed"
    MANIFEST_WRITE_FAILED = "manifest_write_failed"
    CONTENT_HASH_FAILED = "content_hash_failed"


CALAMINE_ENGINE = "calamine"
LIBREOFFICE_CONVERTER = "libreoffice"
DEFAULT_OFFICE_TIMEOUT_SECONDS = 120.0
WORD_2007_FILTER = "docx:MS Word 2007 XML"
PPTX_FILTER = "pptx:Impress MS PowerPoint 2007 XML"
XLSX_FILTER = "xlsx:Calc MS Excel 2007 XML"
FORBIDDEN_CONVERTERS = frozenset(
    {"antiword", "catdoc", "catppt", "python-docx", "python-pptx"}
)
MARKET_QUALITY_COLLECTION = "market_quality_chunks_hybrid"
FORBIDDEN_COLLECTIONS = frozenset({"psychology_chunks_hybrid", "ebook_chunks_hybrid"})
MARKET_QUALITY_BUCKET = "market-quality-docs"
FORBIDDEN_BUCKETS = frozenset({"psychology-pdfs", "ebook-pdfs"})
DEFAULT_EMBEDDING_DIM = 2560
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:4b"
DEFAULT_PIPELINE_VERSION = "1"
HASH_CHUNK_SIZE = 1024 * 1024
MANIFEST_STATUS_COMPLETE = "complete"
SKIP_REASON_UNCHANGED = "unchanged_content"
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
    if source_format is DocumentFormat.XLS:
        return DocumentFormat.XLSX
    raise UnsupportedConverterError(source_format.value)


def soffice_filter(source_format: DocumentFormat) -> str:
    target = modern_office_target(source_format)
    if target is DocumentFormat.DOCX:
        return WORD_2007_FILTER
    if target is DocumentFormat.PPTX:
        return PPTX_FILTER
    return XLSX_FILTER


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


@dataclass(frozen=True)
class QueryFilters:
    product: str | None = None
    period: str | None = None
    doc_type: str | None = None


@dataclass(frozen=True)
class PassageHit:
    chunk: NarrativeChunk
    score: float = 0.0


class ChunkStore(Protocol):
    def upsert(self, collection: str, records: Sequence[StoredChunk]) -> None:
        """Upsert narrative chunks into the shared Milvus collection."""
        ...

    def search_hybrid(
        self,
        collection: str,
        *,
        dense: Sequence[float],
        query_text: str,
        filters: QueryFilters,
        limit: int,
    ) -> Sequence[PassageHit]:
        """Dense + sparse hybrid search with metadata filters."""
        ...

    def query_chunks(
        self,
        collection: str,
        *,
        filters: QueryFilters | None = None,
        doc_id: str | None = None,
        chunk_id: str | None = None,
        parent_id: str | None = None,
        chunk_type: ChunkType | None = None,
        heading_path: str | None = None,
        page: int | None = None,
        slide_index: int | None = None,
        family: DocumentFamily | None = None,
        limit: int = 16384,
    ) -> Sequence[NarrativeChunk]:
        """Read stored chunks by id, heading, page, slide, or filters."""
        ...


class ObjectStore(Protocol):
    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        """Store bytes (Docling JSON)."""
        ...

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        """Store a file without requiring the caller to load it fully."""
        ...

    def get_bytes(self, key: str) -> bytes | None:
        """Read object bytes from this bucket. Missing keys return None."""
        ...

    def list_prefix(self, prefix: str) -> Sequence[str]:
        """List object keys under prefix in this bucket only."""
        ...

    def download_to(self, key: str, dest: Path) -> bool:
        """Stream object to dest without loading the whole body in RAM."""
        ...


def require_collection(name: str) -> str:
    if name in FORBIDDEN_COLLECTIONS or name != MARKET_QUALITY_COLLECTION:
        raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, name)
    return name


def require_bucket(name: str) -> str:
    if name in FORBIDDEN_BUCKETS or name != MARKET_QUALITY_BUCKET:
        raise NarrativeIngestError(FailureReason.FORBIDDEN_BUCKET, name)
    return name


_LAYER1_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LAYER1_UNSAFE_SHEET_RE = re.compile(r"[/\\]+")


@dataclass(frozen=True)
class Layer1SheetListing:
    doc_id: str
    source_file: str
    sheet_name: str
    n_rows: int
    n_cols: int


class Layer1Store(Protocol):
    def list_profiles(self) -> Sequence[Layer1SheetListing]:
        """List sheets from */profile.json. Skip objects without a profile."""
        ...

    def get_profile_bytes(self, doc_id: str) -> bytes | None:
        """Return profile.json only. Do not attach parquet or CSV."""
        ...

    def query_parquet(
        self,
        doc_id: str,
        *,
        sheet: str | None,
        sql: str | None,
        columns: str | None,
        group_by: str | None,
        limit: int,
    ) -> Sequence[Mapping[str, object]]:
        """Scan one doc_id's layer-1 parquet. Read-only; do not load the workbook."""
        ...


def require_layer1_doc_id(doc_id: str) -> str:
    text = (doc_id or "").strip()
    if not _LAYER1_DOC_ID_RE.fullmatch(text):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, doc_id)
    return text


def layer1_profile_key(doc_id: str) -> str:
    return f"{require_layer1_doc_id(doc_id)}/profile.json"


def layer1_parquet_prefix(doc_id: str) -> str:
    return f"{require_layer1_doc_id(doc_id)}/layer1/"


def layer1_sheet_filename(sheet: str) -> str:
    cleaned = _LAYER1_UNSAFE_SHEET_RE.sub("_", sheet).strip() or "sheet"
    return cleaned


def layer1_parquet_key(doc_id: str, sheet: str) -> str:
    return f"{layer1_parquet_prefix(doc_id)}{layer1_sheet_filename(sheet)}.parquet"


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


_MD_TABLE_SEPARATOR = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.MULTILINE,
)


def _mixed_table_prose(text: str) -> bool:
    if _MD_TABLE_SEPARATOR.search(text) is None:
        return False
    return any(marker in text for marker in (". ", "。", "다."))


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


PROFILE_JSON_MAX_BYTES = 10 * 1024
EXCEL_EPOCH = date(1899, 12, 30)
ALLOWED_FACT_TABLES = frozenset({"claim_event", "monthly_quality_kpi"})
FORBIDDEN_SQL_TABLES = frozenset({"embeddings.chunks", "embeddings"})
FORBIDDEN_TABULAR_ENGINES = frozenset(
    {"pandas", "xlrd", "openpyxl", "docling", "xlsx2csv"}
)
ALLOWED_TABULAR_ENGINES = frozenset({CALAMINE_ENGINE, "polars", "fastexcel"})
LAYER1_META_COLUMNS = (
    "source_file",
    "sheet_name",
    "report_period",
    "ingested_at",
    "template_family",
)
DEFAULT_MARIADB_HOST = "127.0.0.1"
DEFAULT_MARIADB_PORT = 3306
DEFAULT_MARIADB_DATABASE = "market_quality"
_DATE_COL_RE = re.compile(r"일|date|일자|발생|period", re.IGNORECASE)
_CAUSE_TOKENS = ("원인", "cause", "rootcause", "근본원인")
_COUNTERMEASURE_TOKENS = ("대책", "countermeasure", "조치")


class TabularIngestError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


class SheetKind(StrEnum):
    DATA = "data"
    PIVOT = "pivot"
    CHART = "chart"
    MACRO = "macro"
    EMPTY = "empty"


class Grain(StrEnum):
    LEDGER = "ledger"
    SNAPSHOT = "snapshot"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SheetProfile:
    name: str
    kind: SheetKind
    n_rows: int
    n_cols: int
    header_candidates: tuple[str, ...]
    types: tuple[tuple[str, str], ...]
    nulls: tuple[tuple[str, float], ...]
    sample_rows: tuple[tuple[str, ...], ...]
    original_columns: tuple[str, ...]


@dataclass(frozen=True)
class TabularProfile:
    source_file: str
    sheets: tuple[SheetProfile, ...]
    encoding: str | None = None
    delimiter: str | None = None

    def to_json_bytes(self) -> bytes:
        raw = _profile_json_bytes(self, sample_limit=5, value_limit=200)
        if len(raw) <= PROFILE_JSON_MAX_BYTES:
            return raw
        raw = _profile_json_bytes(self, sample_limit=1, value_limit=40)
        if len(raw) <= PROFILE_JSON_MAX_BYTES:
            return raw
        raw = _profile_json_bytes(self, sample_limit=0, value_limit=0)
        if len(raw) <= PROFILE_JSON_MAX_BYTES:
            return raw
        raw = _profile_json_bytes(self, sample_limit=0, value_limit=0, column_limit=20)
        if len(raw) <= PROFILE_JSON_MAX_BYTES:
            return raw
        return _profile_json_bytes(self, sample_limit=0, value_limit=0, column_limit=8)


@dataclass(frozen=True)
class Layer1Sheet:
    sheet_name: str
    parquet_bytes: bytes | None
    parquet_path: Path | None
    original_columns: tuple[str, ...]
    report_period: str | None
    template_family: str
    ingested_at: datetime
    source_file: str
    n_rows: int
    kind: SheetKind


@dataclass(frozen=True)
class FactBatch:
    table: str
    grain: Grain
    report_period: str | None
    rows: tuple[Mapping[str, object], ...] = ()
    parquet_path: Path | None = None


@dataclass(frozen=True)
class ExtractedTabular:
    profile: TabularProfile
    sheets: tuple[Layer1Sheet, ...]
    fact_batches: tuple[FactBatch, ...]
    engine: str
    row_embedding_texts: tuple[str, ...] = ()
    catalog_sentences: tuple[str, ...] = ()

    @property
    def fact_table(self) -> str | None:
        tables = list(dict.fromkeys(batch.table for batch in self.fact_batches))
        if not tables:
            return None
        if len(tables) == 1:
            return tables[0]
        return ",".join(tables)

    @property
    def fact_rows(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        for batch in self.fact_batches:
            rows.extend(batch.rows)
        return tuple(rows)

    @property
    def grain(self) -> Grain:
        grains = {batch.grain for batch in self.fact_batches}
        if Grain.LEDGER in grains and Grain.SNAPSHOT in grains:
            return Grain.UNKNOWN
        if Grain.LEDGER in grains:
            return Grain.LEDGER
        if Grain.SNAPSHOT in grains:
            return Grain.SNAPSHOT
        return Grain.UNKNOWN


@dataclass(frozen=True)
class TabularIngestResult:
    source_path: Path
    doc_id: str | None
    sheet_count: int
    profile_key: str | None
    parquet_keys: tuple[str, ...]
    fact_table: str | None
    fact_row_count: int
    failure_reason: FailureReason | None
    original_key: str | None = None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


class TabularExtractor(Protocol):
    def extract(self, path: Path, *, doc_id: str) -> ExtractedTabular:
        """Stream sheets into a profile, layer-1 parquet, and optional facts."""
        ...

    def iter_fact_slices(
        self, batch: FactBatch
    ) -> Iterator[Sequence[Mapping[str, object]]]:
        """Yield mapped fact rows in bounded slices. Do not materialize the sheet."""
        ...


class TableStore(Protocol):
    def insert_facts(
        self,
        table: str,
        rows: Sequence[Mapping[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        """Insert curated fact rows. Must not create a table per file."""
        ...

    def query_readonly(
        self,
        sql: str,
        params: Sequence[object] | None = None,
    ) -> Sequence[Mapping[str, object]]:
        """Run allowlisted read-only SQL. Writes must be rejected."""
        ...


class ManifestStoreError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


@dataclass(frozen=True)
class IngestFingerprint:
    content_sha256: str
    encoder_model: str
    pipeline_version: str


@dataclass(frozen=True)
class ManifestRecord:
    fingerprint: IngestFingerprint
    family: DocumentFamily
    detected_format: DocumentFormat
    byte_size: int
    status: str
    chunk_count: int
    ingested_at: datetime


class ManifestStore(Protocol):
    def find(self, fingerprint: IngestFingerprint) -> ManifestRecord | None:
        """Look up a content-hash skip row. Path is not part of the key."""
        ...

    def upsert(self, record: ManifestRecord) -> None:
        """Write a successful ingest fingerprint. Do not store path aliases."""
        ...


def encoder_model_for_family(family: DocumentFamily, configured: str) -> str:
    if family is DocumentFamily.C:
        return ""
    return configured


def fingerprint_for(
    family: DocumentFamily,
    content_sha256: str,
    *,
    encoder_model: str,
    pipeline_version: str,
) -> IngestFingerprint:
    return IngestFingerprint(
        content_sha256=content_sha256,
        encoder_model=encoder_model_for_family(family, encoder_model),
        pipeline_version=pipeline_version,
    )


def hash_file_sha256(
    path: Path, *, chunk_size: int = HASH_CHUNK_SIZE
) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
            total += len(block)
    return digest.hexdigest(), total


def forbid_row_embedding(texts: Sequence[str]) -> None:
    if texts:
        raise TabularIngestError(FailureReason.ROW_EMBEDDING)


def is_cause_column(name: str) -> bool:
    normalized = _norm_col(name)
    return any(token in normalized for token in _CAUSE_TOKENS)


def is_countermeasure_column(name: str) -> bool:
    normalized = _norm_col(name)
    return any(token in normalized for token in _COUNTERMEASURE_TOKENS)


def require_cause_columns_kept(
    original_columns: Sequence[str], landing_columns: Sequence[str]
) -> None:
    landing = set(landing_columns)
    dropped = [
        column
        for column in original_columns
        if (is_cause_column(column) or is_countermeasure_column(column))
        and column not in landing
    ]
    if dropped:
        raise TabularIngestError(FailureReason.CAUSE_COLUMN_DROPPED)


def require_original_columns(
    original_columns: Sequence[str], landing_columns: Sequence[str]
) -> None:
    missing = [column for column in original_columns if column not in landing_columns]
    if not missing:
        return
    require_cause_columns_kept(original_columns, landing_columns)
    raise TabularIngestError(FailureReason.ORIGINAL_COLUMN_DROPPED, ",".join(missing))


def require_fact_table(name: str) -> str:
    lowered = name.strip().lower()
    if lowered in FORBIDDEN_SQL_TABLES or "embeddings.chunks" in lowered:
        raise TabularIngestError(FailureReason.EMBEDDINGS_VECTOR, name)
    if lowered == "xlsx_blob" or lowered.endswith("_blob"):
        raise TabularIngestError(FailureReason.XLSX_BLOB, name)
    if name not in ALLOWED_FACT_TABLES:
        raise TabularIngestError(FailureReason.TABLE_PER_FILE, name)
    return name


def require_snapshot_period(report_period: str | None) -> str:
    if report_period is None or not str(report_period).strip():
        raise TabularIngestError(FailureReason.SNAPSHOT_UNION)
    return str(report_period)


def excel_serial_to_date(serial: int | float) -> date:
    return EXCEL_EPOCH + timedelta(days=int(serial))


def convert_excel_serial(value: object, *, column: str) -> object:
    if not _DATE_COL_RE.search(column):
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    if value < 20_000 or value > 80_000:
        return value
    return excel_serial_to_date(value).isoformat()


def infer_fact_mapping(columns: Sequence[str]) -> str | None:
    has_cause = any(is_cause_column(column) for column in columns)
    has_counter = any(is_countermeasure_column(column) for column in columns)
    if has_cause and has_counter:
        return "claim_event"
    norms = [_norm_col(column) for column in columns]
    if any("ppm" in name for name in norms) or any(
        "클레임건수" in column for column in columns
    ):
        return "monthly_quality_kpi"
    return None


_CLAIM_COLUMN_MAP = {
    "품번": "part_no",
    "partno": "part_no",
    "part_no": "part_no",
    "차종": "vehicle",
    "vehicle": "vehicle",
    "발생일": "event_date",
    "일자": "event_date",
    "건수": "quantity",
    "수량": "quantity",
}
_KPI_COLUMN_MAP = {
    "차종": "vehicle",
    "vehicle": "vehicle",
    "클레임건수": "claim_count",
    "건수": "claim_count",
    "ppm": "ppm",
    "월": "report_period",
    "기간": "report_period",
}


def map_fact_column(column: str, table: str) -> str | None:
    if table == "claim_event":
        if is_cause_column(column):
            return "cause"
        if is_countermeasure_column(column):
            return "countermeasure"
        return _CLAIM_COLUMN_MAP.get(column) or _CLAIM_COLUMN_MAP.get(column.lower())
    if table == "monthly_quality_kpi":
        return _KPI_COLUMN_MAP.get(column) or _KPI_COLUMN_MAP.get(column.lower())
    return None


def validate_extracted_tabular(extracted: ExtractedTabular) -> None:
    if extracted.engine in FORBIDDEN_TABULAR_ENGINES:
        raise TabularIngestError(FailureReason.FORBIDDEN_ENGINE, extracted.engine)
    if extracted.engine not in ALLOWED_TABULAR_ENGINES:
        raise TabularIngestError(FailureReason.FORBIDDEN_ENGINE, extracted.engine)
    forbid_row_embedding(extracted.row_embedding_texts)
    profile_bytes = extracted.profile.to_json_bytes()
    if len(profile_bytes) > PROFILE_JSON_MAX_BYTES:
        raise TabularIngestError(FailureReason.PROFILE_TOO_LARGE)
    profiles = {sheet.name: sheet for sheet in extracted.profile.sheets}
    for sheet in extracted.sheets:
        if sheet.kind is not SheetKind.DATA:
            continue
        profile = profiles.get(sheet.sheet_name)
        original = (
            profile.original_columns if profile is not None else sheet.original_columns
        )
        require_cause_columns_kept(original, sheet.original_columns)
        require_original_columns(original, sheet.original_columns)
    for batch in extracted.fact_batches:
        require_fact_table(batch.table)


def _norm_col(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("_", "")


def _profile_json_bytes(
    profile: TabularProfile,
    *,
    sample_limit: int,
    value_limit: int,
    column_limit: int | None = None,
) -> bytes:
    payload = {
        "source_file": profile.source_file,
        "encoding": profile.encoding,
        "delimiter": profile.delimiter,
        "sheet_names": [sheet.name for sheet in profile.sheets],
        "sheets": [
            _sheet_profile_payload(
                sheet,
                sample_limit=sample_limit,
                value_limit=value_limit,
                column_limit=column_limit,
            )
            for sheet in profile.sheets
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _sheet_profile_payload(
    sheet: SheetProfile,
    *,
    sample_limit: int,
    value_limit: int,
    column_limit: int | None,
) -> dict[str, object]:
    headers = list(sheet.header_candidates)
    types = list(sheet.types)
    nulls = list(sheet.nulls)
    original = list(sheet.original_columns)
    if column_limit is not None:
        headers = headers[:column_limit]
        types = types[:column_limit]
        nulls = nulls[:column_limit]
        original = original[:column_limit]
    sample_width = column_limit if column_limit is not None else None
    samples = [
        [
            _clip_profile_value(cell, value_limit)
            for cell in (row[:sample_width] if sample_width is not None else row)
        ]
        for row in sheet.sample_rows[:sample_limit]
    ]
    return {
        "name": sheet.name,
        "kind": sheet.kind.value,
        "n_rows": sheet.n_rows,
        "n_cols": sheet.n_cols,
        "header_candidates": headers,
        "types": dict(types),
        "nulls": dict(nulls),
        "sample_rows": samples,
        "original_columns": original,
    }


def _clip_profile_value(value: object, limit: int) -> str:
    text = "" if value is None else str(value)
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[:limit]


NO_EVIDENCE = "근거 없음"
MCP_QUERY_LIMIT = 100
MCP_QUERY_LIMIT_MAX = 500
MCP_SEARCH_CANDIDATES = 50
MCP_SEARCH_TOP_K = 5
MCP_TOOL_BODY_MAX_CHARS = 4000
MCP_TOOL_NAMES = (
    "list_documents",
    "search_passages",
    "get_outline",
    "get_section",
    "get_table",
    "get_page",
    "list_slides",
    "get_slide",
    "list_tables",
    "describe_table",
    "query_tables",
    "list_layer1",
    "describe_profile",
    "query_layer1",
)
FORBIDDEN_MCP_TOOLS = frozenset({"search", "ingest", "delete", "search_hwp"})
FORBIDDEN_SQL_SCHEMAS = frozenset(
    {"embeddings", "information_schema", "performance_schema", "mysql", "sys"}
)
ALLOWED_SQL_SCHEMAS = frozenset({"", DEFAULT_MARIADB_DATABASE})
_SQL_WRITE_RE = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|"
    r"REVOKE|MERGE|CALL|LOAD|HANDLER|LOCK|UNLOCK|COPY|ATTACH|DETACH|"
    r"INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)
_SQL_DANGEROUS_RE = re.compile(
    r"\b(SLEEP|BENCHMARK|LOAD_FILE|GET_LOCK|RELEASE_LOCK)\b",
    re.IGNORECASE,
)
_SQL_SELECT_HEAD_RE = re.compile(r"^\s*(WITH|SELECT)\b", re.IGNORECASE)
_SQL_FROM_JOIN_RE = re.compile(
    r"\b(?:FROM|STRAIGHT_JOIN|JOIN)\s+",
    re.IGNORECASE,
)
_SQL_TABLE_STOP_RE = re.compile(
    r"\s*(,|\b(?:WHERE|GROUP|ORDER|LIMIT|HAVING|UNION|EXCEPT|INTERSECT|"
    r"ON|USING|JOIN|STRAIGHT_JOIN|INNER|LEFT|RIGHT|CROSS|NATURAL|FULL|"
    r"OUTER|SET|WINDOW|FOR|USE|FORCE|IGNORE|PARTITION)\b)",
    re.IGNORECASE,
)
_SQL_INDEX_HINT_HEAD_RE = re.compile(
    r"^(?:USE|IGNORE|FORCE)\s+(?:INDEX|KEY)"
    r"(?:\s+FOR\s+(?:JOIN|ORDER\s+BY|GROUP\s+BY))?",
    re.IGNORECASE,
)
_SQL_PARTITION_HEAD_RE = re.compile(r"^PARTITION\b", re.IGNORECASE)
_SQL_TABLE_NAME_RE = re.compile(
    r'^["`]?(\w+)["`]?(?:\s*\.\s*["`]?(\w+)["`]?)?'
    r'(?:\s+(?:AS\s+)?["`]?\w+["`]?)?\s*$',
    re.IGNORECASE,
)
_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LAYER1_IDENT_RE = re.compile(r"^\w+$")
_LAYER1_TABLE_FUNCS = (
    "read_text",
    "read_blob",
    "read_csv",
    "read_json",
    "read_parquet",
    "read_csv_auto",
    "read_duckdb",
    "parquet_scan",
    "glob",
    "query",
    "sniff_csv",
    "excel",
    "read_xlsx",
    "read_ods",
)
_LAYER1_FORBIDDEN_SQL_RE = re.compile(
    r"(?:\.\.|://|\\|\.parquet\b|\.csv\b|\.json\b|"
    r"(?:read_text|read_blob|read_csv|read_json|read_parquet|"
    r"read_csv_auto|read_duckdb|parquet_scan|glob|query|sniff_csv|"
    r"excel|read_xlsx|read_ods)\s*\(|"
    r"psychology-pdfs|ebook-pdfs)",
    re.IGNORECASE,
)
_SQL_LIMIT_TAIL_RE = re.compile(
    r"\bLIMIT\s+(\d+)\s*(?:,\s*(\d+))?\s*(?:OFFSET\s+(\d+))?\s*$",
    re.IGNORECASE,
)


class McpQueryError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


@dataclass(frozen=True)
class McpToolSpec:
    name: str
    description: str
    parameters: tuple[str, ...]


@dataclass(frozen=True)
class TableCatalogEntry:
    name: str
    grain: Grain
    units: str
    one_row_meaning: str
    columns: tuple[str, ...]


FACT_TABLE_CATALOG: dict[str, TableCatalogEntry] = {
    "claim_event": TableCatalogEntry(
        name="claim_event",
        grain=Grain.LEDGER,
        units="quantity=건수",
        one_row_meaning="클레임 1건",
        columns=(
            "source_file",
            "sheet_name",
            "report_period",
            "ingested_at",
            "template_family",
            "part_no",
            "vehicle",
            "event_date",
            "cause",
            "countermeasure",
            "quantity",
        ),
    ),
    "monthly_quality_kpi": TableCatalogEntry(
        name="monthly_quality_kpi",
        grain=Grain.SNAPSHOT,
        units="claim_count=건, ppm",
        one_row_meaning="차종×기간 월보 KPI 1행",
        columns=(
            "source_file",
            "sheet_name",
            "report_period",
            "ingested_at",
            "template_family",
            "vehicle",
            "claim_count",
            "ppm",
        ),
    ),
}

MCP_TOOL_SPECS: tuple[McpToolSpec, ...] = (
    McpToolSpec(
        name="list_documents",
        description=(
            "문서 목록. product/period/doc_type 필터. "
            "숫자 집계(매핑 팩트)→query_tables(TAG), "
            "숫자 집계(1층만)→describe_profile 후 query_layer1, "
            "원인/대책→get_section, "
            "품번/코드→search_passages(sparse+필터). search 하나만 두지 않음."
        ),
        parameters=("product", "period", "doc_type"),
    ),
    McpToolSpec(
        name="search_passages",
        description=(
            "모호한 검색과 품번/코드/키워드는 search_passages. dense+sparse "
            "하이브리드와 product/period/doc_type 필터. "
            "숫자 집계(매핑 팩트)는 query_tables, "
            "숫자 집계(1층만)는 describe_profile 후 query_layer1, "
            "원인/대책은 get_section. 표 숫자를 서술 청크에서 지어내지 말 것."
        ),
        parameters=("query", "product", "period", "doc_type"),
    ),
    McpToolSpec(
        name="get_outline",
        description="문서 목차(섹션/슬라이드 트리). 원인/대책 장은 get_section.",
        parameters=("doc_id",),
    ),
    McpToolSpec(
        name="get_section",
        description=(
            "원인/대책은 get_section. parent 섹션을 반환하고 잘린 자식 청크만으로 "
            "답하지 않는다. DOCX 인용은 파일명+섹션 경로가 페이지보다 우선."
        ),
        parameters=("doc_id", "heading_path"),
    ),
    McpToolSpec(
        name="get_table",
        description=(
            "문서 안 표 청크. 표 숫자 집계(매핑 팩트)는 query_tables, "
            "1층만 있는 표는 describe_profile 후 query_layer1. "
            "서술 청크에서 숫자를 지어내지 말 것."
        ),
        parameters=("doc_id", "table_id"),
    ),
    McpToolSpec(
        name="get_page",
        description="PDF 저장된 페이지 텍스트. ColQwen/비전 인덱스가 아님.",
        parameters=("doc_id", "page"),
    ),
    McpToolSpec(
        name="list_slides",
        description=(
            "PPTX 슬라이드 목록. 한 장은 get_slide. 인용은 파일명+슬라이드 번호."
        ),
        parameters=("doc_id",),
    ),
    McpToolSpec(
        name="get_slide",
        description="PPTX 슬라이드 본문+노트. 인용은 파일명+슬라이드 번호.",
        parameters=("doc_id", "slide_index"),
    ),
    McpToolSpec(
        name="list_tables",
        description=(
            "MariaDB 팩트 표 목록. product/period/doc_type 필터. "
            "숫자는 query_tables, 1층만 있는 표는 describe_profile 후 "
            "query_layer1, 원인/대책은 get_section."
        ),
        parameters=("product", "period", "doc_type"),
    ),
    McpToolSpec(
        name="describe_table",
        description="표 grain·단위·한 행의 의미. 집계 전에 호출.",
        parameters=("name",),
    ),
    McpToolSpec(
        name="query_tables",
        description=(
            "숫자 집계(매핑 팩트)는 query_tables(TAG/Text-to-SQL). "
            "MariaDB 읽기 전용, LIMIT. 가능하면 sql보다 filters+group_by. "
            "1층만 있는 표 숫자는 describe_profile 후 query_layer1. "
            "DROP/DELETE/INSERT/UPDATE와 허용 스키마 밖 SQL은 거부. "
            "원인/대책은 get_section, 품번/코드는 search_passages."
        ),
        parameters=(
            "sql",
            "table",
            "product",
            "period",
            "doc_type",
            "group_by",
            "limit",
        ),
    ),
    McpToolSpec(
        name="list_layer1",
        description=(
            "MinIO 1층 profile.json 목록. 프로필 없는 객체는 건너뛴다. "
            "매핑된 팩트 숫자→query_tables, 1층만 있는 표 숫자→describe_profile "
            "후 query_layer1, 원인/대책→get_section, 품번→search_passages. "
            "표 숫자를 서술 청크에서 지어내지 말 것."
        ),
        parameters=(),
    ),
    McpToolSpec(
        name="describe_profile",
        description=(
            "1층 profile.json만 반환(2~10KB). Parquet 본문·원본 CSV를 붙이지 않음. "
            "1층 표 숫자는 describe_profile 후 query_layer1. "
            "매핑된 팩트 숫자→query_tables, 원인/대책→get_section, "
            "품번→search_passages."
        ),
        parameters=("doc_id",),
    ),
    McpToolSpec(
        name="query_layer1",
        description=(
            "1층 Parquet만 조회(DuckDB/polars scan). 가능하면 sql보다 "
            "columns/group_by. 기본 LIMIT 100 최대 500. 읽기 전용. "
            "DROP/DELETE/INSERT/UPDATE/CREATE/COPY/ATTACH 및 허용 doc_id 밖 "
            "경로는 거부. 매핑된 팩트 숫자→query_tables, 원인/대책→get_section, "
            "품번→search_passages."
        ),
        parameters=("doc_id", "sheet", "sql", "columns", "group_by", "limit"),
    ),
)


class McpServer(Protocol):
    def serve_stdio(self) -> None:
        """Serve query-only MCP over stdio. No ingest/delete tools."""
        ...


def parent_section_path(heading_path: str | None) -> str:
    text = (heading_path or "").strip()
    if not text:
        return ""
    if " > " in text:
        return text.split(" > ", 1)[0].strip()
    return text


def format_citation(chunk: NarrativeChunk) -> str:
    filename = Path(chunk.path).name if chunk.path else chunk.doc_id
    if chunk.family is DocumentFamily.A:
        if chunk.section_path:
            return f"{filename} {chunk.section_path}"
        return filename
    if chunk.family is DocumentFamily.D and chunk.slide_index is not None:
        base = f"{filename} slide={chunk.slide_index}"
        if chunk.section_path:
            return f"{base} {chunk.section_path}"
        return base
    if chunk.page is not None:
        base = f"{filename} page={chunk.page}"
        if chunk.section_path:
            return f"{base} {chunk.section_path}"
        return base
    if chunk.section_path:
        return f"{filename} {chunk.section_path}"
    return filename


def format_table_citation(row: Mapping[str, object]) -> str:
    filename = str(row.get("source_file") or "")
    sheet = str(row.get("sheet_name") or "")
    if filename and sheet:
        return f"{filename} sheet={sheet}"
    return filename or sheet or "table"


def clip_tool_text(text: str, *, pointer: str) -> str:
    if len(text) <= MCP_TOOL_BODY_MAX_CHARS:
        return text
    keep = max(32, MCP_TOOL_BODY_MAX_CHARS - 80)
    return f"{text[:keep]}\n… truncated pointer={pointer}"


def require_sql_ident(name: str) -> str:
    if not _SQL_IDENT_RE.fullmatch(name):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, name)
    return name


def require_layer1_ident(name: str) -> str:
    text = name.strip()
    if not text or not _LAYER1_IDENT_RE.fullmatch(text):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, name)
    return text


def require_readonly_sql(sql: str) -> str:
    stripped = _require_select_sql(sql)
    refs = _sql_table_refs(_strip_sql_noise(stripped))
    if not refs:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    for schema, table in refs:
        _reject_sql_table(schema, table)
    return stripped


def ensure_sql_limit(sql: str, limit: int = MCP_QUERY_LIMIT) -> str:
    capped = max(1, min(int(limit), MCP_QUERY_LIMIT_MAX))
    stripped = sql.strip()
    match = _SQL_LIMIT_TAIL_RE.search(stripped)
    if match is None:
        return f"{stripped} LIMIT {capped}"
    first = int(match.group(1))
    second = match.group(2)
    offset = match.group(3)
    prefix = stripped[: match.start()].rstrip()
    if second is not None:
        count = min(int(second), capped)
        return f"{prefix} LIMIT {first}, {count}"
    count = min(first, capped)
    if offset is not None:
        return f"{prefix} LIMIT {count} OFFSET {int(offset)}"
    return f"{prefix} LIMIT {count}"


def require_readonly_layer1_sql(
    sql: str,
    *,
    allowed_tables: Sequence[str],
    doc_id: str,
) -> str:
    normalized = _normalize_layer1_sql_chars(sql)
    stripped = _require_select_sql(normalized)
    noise_free = _strip_sql_noise(stripped)
    if _LAYER1_FORBIDDEN_SQL_RE.search(noise_free) or _LAYER1_FORBIDDEN_SQL_RE.search(
        stripped
    ):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    collapsed = re.sub(r"\s+", "", noise_free.lower())
    for func in _LAYER1_TABLE_FUNCS:
        if f"{func}(" in collapsed:
            raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    doc = require_layer1_doc_id(doc_id)
    if doc.lower() not in stripped.lower() and any(
        token in stripped.lower()
        for token in ("layer1/", "/layer1", "market-quality-docs", "s3")
    ):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    refs = _sql_table_refs(noise_free)
    if not refs:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    allowed = {_layer1_table_key(name) for name in allowed_tables if name}
    allowed.add("layer1")
    for schema, table in refs:
        if schema:
            raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, f"{schema}.{table}")
        if _layer1_table_key(table) not in allowed:
            raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, table)
    return stripped


def _normalize_layer1_sql_chars(sql: str) -> str:
    parts: list[str] = []
    for char in sql:
        category = unicodedata.category(char)
        if category in {"Cf", "Mn", "Me"}:
            continue
        if category == "Cc" and char not in "\t\n\r":
            continue
        if category.startswith("Z"):
            parts.append(" ")
            continue
        parts.append(char)
    return "".join(parts)


def quote_sql_ident(name: str) -> str:
    text = name.strip()
    if not text:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, name)
    return '"' + text.replace('"', '""') + '"'


def _layer1_table_key(name: str) -> str:
    return name.strip().strip('`"').lower()


def _require_select_sql(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    if "/*!" in stripped:
        if _SQL_WRITE_RE.search(stripped):
            raise McpQueryError(FailureReason.SQL_WRITE, sql)
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    noise_free = _strip_sql_noise(stripped)
    if _SQL_WRITE_RE.search(noise_free) or _SQL_WRITE_RE.search(stripped):
        raise McpQueryError(FailureReason.SQL_WRITE, sql)
    if _SQL_DANGEROUS_RE.search(noise_free) or _SQL_DANGEROUS_RE.search(stripped):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    if not _SQL_SELECT_HEAD_RE.search(noise_free):
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, sql)
    return stripped


def _strip_sql_noise(sql: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"#[^\n]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def _sql_table_refs(sql: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in _SQL_FROM_JOIN_RE.finditer(sql):
        rest = sql[match.end() :]
        token, rest = _next_sql_table_token(rest)
        _collect_sql_table_token(token, refs)
        rest = _skip_sql_table_hints(rest)
        while rest.lstrip().startswith(","):
            rest = rest.lstrip()[1:]
            token, rest = _next_sql_table_token(rest)
            _collect_sql_table_token(token, refs)
            rest = _skip_sql_table_hints(rest)
    return refs


def _skip_balanced_parens(rest: str) -> str:
    rest = rest.lstrip()
    if not rest.startswith("("):
        return rest
    depth = 0
    for index, char in enumerate(rest):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return rest[index + 1 :]
    return ""


def _skip_sql_table_hints(rest: str) -> str:
    while True:
        stripped = rest.lstrip()
        hint = _SQL_INDEX_HINT_HEAD_RE.match(stripped)
        if hint is not None:
            rest = _skip_balanced_parens(stripped[hint.end() :])
            continue
        partition = _SQL_PARTITION_HEAD_RE.match(stripped)
        if partition is not None:
            rest = _skip_balanced_parens(stripped[partition.end() :])
            continue
        return stripped


def _next_sql_table_token(rest: str) -> tuple[str, str]:
    rest = rest.lstrip()
    if not rest:
        return "", ""
    if rest.startswith("("):
        depth = 0
        for index, char in enumerate(rest):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return rest[: index + 1], rest[index + 1 :]
        return rest, ""
    stop = _SQL_TABLE_STOP_RE.search(rest)
    if stop is None:
        return rest.strip(), ""
    return rest[: stop.start()].strip(), rest[stop.start() :]


def _collect_sql_table_token(token: str, refs: list[tuple[str, str]]) -> None:
    token = token.strip()
    if not token:
        return
    if token.startswith("("):
        inner = token[1:-1] if token.endswith(")") else token[1:]
        refs.extend(_sql_table_refs(inner))
        return
    parsed = _parse_sql_table(token)
    if parsed is None:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, token)
    refs.append(parsed)


def _parse_sql_table(token: str) -> tuple[str, str] | None:
    match = _SQL_TABLE_NAME_RE.match(token.strip())
    if match is None:
        return None
    first = match.group(1)
    second = match.group(2)
    if second:
        return first.lower(), second
    return "", first


def _reject_sql_table(schema: str, table: str) -> None:
    schema_l = schema.lower()
    table_l = table.lower()
    qualified = f"{schema_l}.{table_l}" if schema_l else table_l
    if (
        schema_l == "embeddings"
        or table_l in FORBIDDEN_SQL_TABLES
        or qualified in FORBIDDEN_SQL_TABLES
        or table_l == "chunks"
    ):
        raise McpQueryError(FailureReason.EMBEDDINGS_VECTOR, qualified or table)
    if schema_l in FORBIDDEN_SQL_SCHEMAS:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, qualified or table)
    if schema_l and schema_l not in ALLOWED_SQL_SCHEMAS:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, qualified or table)
    if table_l.endswith("_blob") or table_l == "xlsx_blob":
        raise McpQueryError(FailureReason.XLSX_BLOB, table)
    if table not in ALLOWED_FACT_TABLES and table_l not in ALLOWED_FACT_TABLES:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, table)


DEFAULT_MCP_SERVER_NAME = "market-quality"
DEFAULT_MCP_COMMAND = "uv"
DEFAULT_MCP_ARGS = ("run", "python", "-m", "large_files_embedding", "mcp")
DEFAULT_STARTUP_TIMEOUT_SEC = 30
DEFAULT_TOOL_TIMEOUT_SEC = 60
MIN_STARTUP_TIMEOUT_SEC = 30
PROTECTED_GROK_CHILDREN = frozenset({"skills", "agents", "roles"})
_MCP_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class GrokConfigError(Exception):
    def __init__(self, reason: FailureReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason.value)


@dataclass(frozen=True)
class GrokMcpSnippet:
    server_name: str
    command: str
    args: tuple[str, ...]
    cwd: str
    enabled: bool
    startup_timeout_sec: int
    tool_timeout_sec: int

    def __post_init__(self) -> None:
        require_mcp_server_name(self.server_name)
        require_mcp_command(self.command)
        require_startup_timeout(self.startup_timeout_sec)


class GrokConfigExporter(Protocol):
    def export(self, snippet: GrokMcpSnippet, destination: Path) -> Path:
        """Write a Grok [mcp_servers.*] snippet. Must not touch home config."""
        ...


def require_mcp_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise GrokConfigError(FailureReason.EMPTY_MCP_COMMAND)
    return command.strip()


def require_mcp_server_name(name: str) -> str:
    text = name.strip()
    if not _MCP_SERVER_NAME_RE.fullmatch(text):
        raise GrokConfigError(FailureReason.EMPTY_MCP_COMMAND, name)
    return text


def require_startup_timeout(seconds: int) -> int:
    value = int(seconds)
    if value < MIN_STARTUP_TIMEOUT_SEC:
        raise GrokConfigError(FailureReason.STARTUP_TIMEOUT_TOO_SHORT)
    return value


def require_export_destination(path: Path, *, home: Path | None = None) -> Path:
    if is_protected_grok_destination(path, home=home):
        raise GrokConfigError(FailureReason.PROTECTED_GROK_PATH, str(path))
    return path


def is_protected_grok_destination(path: Path, *, home: Path | None = None) -> bool:
    home_root = home if home is not None else Path.home()
    forbidden = _path_variants(
        home_root / ".grok" / "config.toml",
        home_root / ".codex" / "config.toml",
    )
    forbidden_keys = {_normcase_key(item) for item in forbidden}
    for candidate in _path_variants(path):
        if _has_protected_grok_child(candidate):
            return True
        if _normcase_key(candidate) in forbidden_keys:
            return True
        if any(_is_same_file(candidate, item) for item in forbidden):
            return True
    return False


def _path_variants(*paths: Path) -> set[Path]:
    variants: set[Path] = set()
    for path in paths:
        variants.add(path)
        expanded = path.expanduser()
        variants.add(expanded)
        try:
            variants.add(expanded.resolve())
        except OSError:
            pass
    return variants


def _normcase_key(path: Path) -> str:
    return os.path.normcase(os.fspath(path)).casefold()


def _normcase_part(part: str) -> str:
    return os.path.normcase(part).casefold()


def _is_same_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _has_protected_grok_child(path: Path) -> bool:
    grok = _normcase_part(".grok")
    protected = {_normcase_part(name) for name in PROTECTED_GROK_CHILDREN}
    parts = path.parts
    for index, part in enumerate(parts):
        if _normcase_part(part) == grok and index + 1 < len(parts):
            if _normcase_part(parts[index + 1]) in protected:
                return True
    return False
