"""Skip re-ingest when original file bytes and pipeline fingerprint match."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PIPELINE_VERSION,
    MANIFEST_STATUS_COMPLETE,
    SKIP_REASON_UNCHANGED,
    Document,
    FailureReason,
    ManifestRecord,
    ManifestStore,
    ManifestStoreError,
    NarrativeIngestResult,
    TabularIngestResult,
    fingerprint_for,
    hash_file_sha256,
)

IngestOutcome = NarrativeIngestResult | TabularIngestResult
IngestFn = Callable[[Document], IngestOutcome]


@dataclass(frozen=True)
class SkipIngestResult:
    source_path: Path
    content_sha256: str
    byte_size: int
    skipped: bool
    skip_reason: str | None
    failure_reason: FailureReason | None
    ingest_result: IngestOutcome | None = None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


class SkipUnchangedIngest:
    def __init__(
        self,
        manifests: ManifestStore,
        *,
        encoder_model: str = DEFAULT_EMBEDDING_MODEL,
        pipeline_version: str = DEFAULT_PIPELINE_VERSION,
    ) -> None:
        self._manifests = manifests
        self._encoder_model = encoder_model
        self._pipeline_version = pipeline_version

    def execute(
        self,
        document: Document,
        *,
        ingest: IngestFn,
        force: bool = False,
    ) -> SkipIngestResult:
        if document.decision is None:
            reason = document.failure_reason or FailureReason.UNKNOWN_SIGNATURE
            return SkipIngestResult(document.path, "", 0, False, None, reason)
        try:
            sha256, byte_size = hash_file_sha256(document.path)
        except OSError:
            return SkipIngestResult(
                document.path, "", 0, False, None, FailureReason.CONTENT_HASH_FAILED
            )
        fingerprint = fingerprint_for(
            document.decision.family,
            sha256,
            encoder_model=self._encoder_model,
            pipeline_version=self._pipeline_version,
        )
        try:
            existing = self._manifests.find(fingerprint)
        except ManifestStoreError as exc:
            return SkipIngestResult(
                document.path, sha256, byte_size, False, None, exc.reason
            )
        except Exception:
            return SkipIngestResult(
                document.path,
                sha256,
                byte_size,
                False,
                None,
                FailureReason.MANIFEST_LOOKUP_FAILED,
            )
        if (
            not force
            and existing is not None
            and existing.status == MANIFEST_STATUS_COMPLETE
        ):
            return SkipIngestResult(
                document.path,
                sha256,
                byte_size,
                True,
                SKIP_REASON_UNCHANGED,
                None,
            )
        outcome = ingest(document)
        if outcome.failed:
            reason = outcome.failure_reason or FailureReason.PARSE_FAILED
            return SkipIngestResult(
                document.path, sha256, byte_size, False, None, reason, outcome
            )
        record = ManifestRecord(
            fingerprint=fingerprint,
            family=document.decision.family,
            detected_format=document.decision.detected_format,
            byte_size=byte_size,
            status=MANIFEST_STATUS_COMPLETE,
            chunk_count=_stored_count(outcome),
            ingested_at=datetime.now(UTC),
        )
        try:
            self._manifests.upsert(record)
        except ManifestStoreError as exc:
            return SkipIngestResult(
                document.path, sha256, byte_size, False, None, exc.reason, outcome
            )
        except Exception:
            return SkipIngestResult(
                document.path,
                sha256,
                byte_size,
                False,
                None,
                FailureReason.MANIFEST_WRITE_FAILED,
                outcome,
            )
        return SkipIngestResult(
            document.path, sha256, byte_size, False, None, None, outcome
        )


def _stored_count(outcome: IngestOutcome) -> int:
    if isinstance(outcome, NarrativeIngestResult):
        return outcome.chunk_count
    return outcome.sheet_count
