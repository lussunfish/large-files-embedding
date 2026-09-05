"""Ingest family C tabular files into Parquet (MinIO) and MariaDB facts."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from large_files_embedding.domain.document import (
    DEFAULT_OFFICE_TIMEOUT_SECONDS,
    Document,
    DocumentFamily,
    DocumentFormat,
    ExtractedTabular,
    FailureReason,
    Grain,
    NarrativeIngestError,
    NormalizationError,
    ObjectStore,
    OfficeNormalizer,
    SheetKind,
    TableStore,
    TabularExtractor,
    TabularIngestError,
    TabularIngestResult,
    validate_extracted_tabular,
)

_UNSAFE_SHEET_RE = re.compile(r"[/\\]+")


class IngestTabular:
    def __init__(
        self,
        extractor: TabularExtractor,
        tables: TableStore,
        objects: ObjectStore,
        *,
        xls_fallback: OfficeNormalizer | None = None,
    ) -> None:
        self._extractor = extractor
        self._tables = tables
        self._objects = objects
        self._xls_fallback = xls_fallback
        self.failure_queue: list[TabularIngestResult] = []

    def execute(
        self, document: Document, *, ingest_path: Path | None = None
    ) -> TabularIngestResult:
        source = ingest_path or document.path
        if document.decision is None:
            reason = document.failure_reason or FailureReason.UNKNOWN_SIGNATURE
            return self._fail(document.path, reason)
        if document.decision.family is not DocumentFamily.C:
            return self._fail(document.path, FailureReason.NARRATIVE_NOT_TABULAR)
        doc_id = _doc_id(source)
        extracted: ExtractedTabular | None = None
        try:
            extracted = self._extract_with_xls_fallback(document, source, doc_id)
            validate_extracted_tabular(extracted)
            profile_key = f"{doc_id}/profile.json"
            self._objects.put_bytes(
                profile_key,
                extracted.profile.to_json_bytes(),
                content_type="application/json",
            )
            original_key: str | None = None
            if source.exists():
                original_key = f"{doc_id}/original/{source.name}"
                self._objects.put_file(
                    original_key,
                    source,
                    content_type=_content_type(source),
                )
            parquet_keys = self._store_layer1(doc_id, extracted)
            fact_table, fact_count = self._store_facts(extracted)
            return TabularIngestResult(
                source_path=document.path,
                doc_id=doc_id,
                sheet_count=len(parquet_keys),
                profile_key=profile_key,
                parquet_keys=parquet_keys,
                fact_table=fact_table,
                fact_row_count=fact_count,
                failure_reason=None,
                original_key=original_key,
            )
        except TabularIngestError as exc:
            return self._fail(document.path, exc.reason)
        except NarrativeIngestError as exc:
            return self._fail(document.path, exc.reason)
        finally:
            if extracted is not None:
                for sheet in extracted.sheets:
                    if sheet.parquet_path is not None:
                        sheet.parquet_path.unlink(missing_ok=True)

    def _extract_with_xls_fallback(
        self, document: Document, source: Path, doc_id: str
    ) -> ExtractedTabular:
        try:
            return self._extractor.extract(source, doc_id=doc_id)
        except TabularIngestError as exc:
            decision = document.decision
            if (
                exc.reason is not FailureReason.EXTRACT_FAILED
                or decision is None
                or decision.detected_format is not DocumentFormat.XLS
                or self._xls_fallback is None
            ):
                raise
            tmpdir = Path(tempfile.mkdtemp(prefix="xls-fallback-"))
            try:
                derived = self._xls_fallback.convert(
                    source,
                    tmpdir,
                    source_format=DocumentFormat.XLS,
                    timeout_seconds=DEFAULT_OFFICE_TIMEOUT_SECONDS,
                )
            except NormalizationError as norm_exc:
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise TabularIngestError(norm_exc.reason) from norm_exc
            try:
                return self._extractor.extract(derived, doc_id=doc_id)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def _store_layer1(
        self, doc_id: str, extracted: ExtractedTabular
    ) -> tuple[str, ...]:
        keys: list[str] = []
        for sheet in extracted.sheets:
            if sheet.kind is not SheetKind.DATA:
                continue
            key = f"{doc_id}/layer1/{_safe_sheet(sheet.sheet_name)}.parquet"
            if sheet.parquet_path is not None:
                self._objects.put_file(
                    key,
                    sheet.parquet_path,
                    content_type="application/vnd.apache.parquet",
                )
            elif sheet.parquet_bytes is not None:
                self._objects.put_bytes(
                    key,
                    sheet.parquet_bytes,
                    content_type="application/vnd.apache.parquet",
                )
            keys.append(key)
        return tuple(keys)

    def _store_facts(self, extracted: ExtractedTabular) -> tuple[str | None, int]:
        stored: list[str] = []
        total = 0
        for batch in extracted.fact_batches:
            period = batch.report_period
            if batch.grain is Grain.SNAPSHOT and not period:
                continue
            inserted = False
            for chunk in self._extractor.iter_fact_slices(batch):
                rows = list(chunk)
                if batch.table == "claim_event":
                    rows = [row for row in rows if _has_cause_fields(row)]
                if not rows:
                    continue
                total += self._tables.insert_facts(
                    batch.table,
                    rows,
                    grain=batch.grain,
                    report_period=period,
                )
                inserted = True
            if inserted:
                stored.append(batch.table)
        if not stored:
            return None, 0
        unique = list(dict.fromkeys(stored))
        label = unique[0] if len(unique) == 1 else ",".join(unique)
        return label, total

    def _fail(self, source: Path, reason: FailureReason) -> TabularIngestResult:
        result = TabularIngestResult(source, None, 0, None, (), None, 0, reason)
        self.failure_queue.append(result)
        return result


def _doc_id(path: Path) -> str:
    resolved = str(path.resolve()) if path.exists() else str(path)
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


def _safe_sheet(name: str) -> str:
    cleaned = _UNSAFE_SHEET_RE.sub("_", name).strip() or "sheet"
    return cleaned


def _has_cause_fields(row: Mapping[str, object]) -> bool:
    names = {str(key).lower() for key in row}
    has_cause = "cause" in names or "원인" in names
    has_counter = "countermeasure" in names or "대책" in names
    return has_cause and has_counter


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".xls":
        return "application/vnd.ms-excel"
    return "application/octet-stream"
