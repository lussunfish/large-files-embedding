"""UC-07: skip re-ingest when file bytes and fingerprint match (path-independent)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from large_files_embedding.application.ingest_narrative import IngestNarrative
from large_files_embedding.application.skip_unchanged_ingest import SkipUnchangedIngest
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PIPELINE_VERSION,
    MANIFEST_STATUS_COMPLETE,
    SKIP_REASON_UNCHANGED,
    ChunkOrigin,
    ChunkType,
    Document,
    DocumentFamily,
    EncodedEmbedding,
    FailureReason,
    FileSignature,
    IngestFingerprint,
    ManifestRecord,
    ManifestStoreError,
    NarrativeChunk,
    NarrativeIngestError,
    ParsedNarrative,
    SignatureKind,
    StoredChunk,
    TabularIngestResult,
    hash_file_sha256,
    require_collection,
)


class FakeNarrativeParser:
    def __init__(
        self,
        result: ParsedNarrative | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[Path, DocumentFamily, str]] = []

    def parse(
        self, path: Path, *, family: DocumentFamily, doc_id: str
    ) -> ParsedNarrative:
        self.calls.append((path, family, doc_id))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FakeEncoder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def encode(self, texts: list[str]) -> list[EncodedEmbedding]:
        self.texts.extend(texts)
        dense = tuple(0.01 for _ in range(DEFAULT_EMBEDDING_DIM))
        return [
            EncodedEmbedding(
                dense=dense, sparse=((1, 1.0),), model=DEFAULT_EMBEDDING_MODEL
            )
            for _ in texts
        ]


class FakeChunkStore:
    def __init__(self) -> None:
        self.records: list[StoredChunk] = []

    def upsert(self, collection: str, records: list[StoredChunk]) -> None:
        require_collection(collection)
        self.records.extend(records)


class FakeObjectStore:
    def __init__(self) -> None:
        self.bytes_objects: dict[str, bytes] = {}
        self.file_objects: dict[str, Path] = {}

    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        del content_type
        self.bytes_objects[key] = body

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        del content_type
        self.file_objects[key] = path


class FakeManifestStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], ManifestRecord] = {}
        self.find_calls: list[IngestFingerprint] = []
        self.upsert_calls: list[ManifestRecord] = []
        self.fail_find = False

    def find(self, fingerprint: IngestFingerprint) -> ManifestRecord | None:
        if self.fail_find:
            raise ManifestStoreError(FailureReason.MANIFEST_LOOKUP_FAILED)
        self.find_calls.append(fingerprint)
        key = (
            fingerprint.content_sha256,
            fingerprint.encoder_model,
            fingerprint.pipeline_version,
        )
        return self.records.get(key)

    def upsert(self, record: ManifestRecord) -> None:
        key = (
            record.fingerprint.content_sha256,
            record.fingerprint.encoder_model,
            record.fingerprint.pipeline_version,
        )
        self.records[key] = record
        self.upsert_calls.append(record)


def _document(path: Path, kind: SignatureKind = SignatureKind.OOXML_WORD) -> Document:
    return Document.from_signature(path, FileSignature(kind))


def _chunk(*, path: str = "claim.docx") -> NarrativeChunk:
    return NarrativeChunk(
        chunk_id="c1",
        doc_id="doc-1",
        path=path,
        family=DocumentFamily.A,
        chunk_type=ChunkType.TEXT,
        text="근본원인 본문",
        embedding_input="근본원인 본문",
        origin=ChunkOrigin.JSON,
        section_path="3. 원인",
        parent_id="parent-원인",
    )


def _parsed(path: Path) -> ParsedNarrative:
    chunk = _chunk(path=str(path))
    return ParsedNarrative(
        doc_id=chunk.doc_id,
        path=path,
        family=DocumentFamily.A,
        json_bytes=b'{"schema_name":"DoclingDocument"}',
        chunks=(chunk,),
        pipeline="simple",
    )


def _pipeline(
    path: Path,
) -> tuple[
    SkipUnchangedIngest,
    FakeManifestStore,
    FakeNarrativeParser,
    FakeEncoder,
    IngestNarrative,
]:
    parser = FakeNarrativeParser(_parsed(path))
    encoder = FakeEncoder()
    narrative = IngestNarrative(parser, encoder, FakeChunkStore(), FakeObjectStore())
    manifests = FakeManifestStore()
    skipper = SkipUnchangedIngest(manifests)
    return skipper, manifests, parser, encoder, narrative


def test_second_ingest_same_bytes_skips_parser_and_encoder(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"same-docx-bytes")
    skipper, manifests, parser, encoder, narrative = _pipeline(path)
    document = _document(path)

    first = skipper.execute(document, ingest=narrative.execute)
    second = skipper.execute(document, ingest=narrative.execute)

    assert first.skipped is False
    assert first.failure_reason is None
    assert len(parser.calls) == 1
    assert encoder.texts
    assert second.skipped is True
    assert second.skip_reason == SKIP_REASON_UNCHANGED
    assert second.content_sha256 == hashlib.sha256(b"same-docx-bytes").hexdigest()
    assert len(parser.calls) == 1
    assert len(encoder.texts) == 1
    assert len(manifests.upsert_calls) == 1


def test_same_bytes_different_path_skips(tmp_path: Path) -> None:
    first_path = tmp_path / "a" / "claim.docx"
    second_path = tmp_path / "b" / "copy.docx"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    payload = b"identical-payload"
    first_path.write_bytes(payload)
    second_path.write_bytes(payload)
    skipper, manifests, parser, encoder, narrative = _pipeline(first_path)

    skipper.execute(_document(first_path), ingest=narrative.execute)
    parser.calls.clear()
    encoder.texts.clear()
    other_parser = FakeNarrativeParser(_parsed(second_path))
    other_narrative = IngestNarrative(
        other_parser, FakeEncoder(), FakeChunkStore(), FakeObjectStore()
    )

    result = skipper.execute(_document(second_path), ingest=other_narrative.execute)

    assert result.skipped is True
    assert result.skip_reason == SKIP_REASON_UNCHANGED
    assert other_parser.calls == []
    assert (
        manifests.find_calls[-1].content_sha256 == hashlib.sha256(payload).hexdigest()
    )


def test_changed_bytes_reingest(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"version-one")
    skipper, _manifests, parser, encoder, narrative = _pipeline(path)

    skipper.execute(_document(path), ingest=narrative.execute)
    path.write_bytes(b"version-two")
    parser.calls.clear()
    encoder.texts.clear()

    result = skipper.execute(_document(path), ingest=narrative.execute)

    assert result.skipped is False
    assert len(parser.calls) == 1
    assert encoder.texts


def test_failed_manifest_does_not_skip(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"failed-once")
    skipper, manifests, parser, encoder, narrative = _pipeline(path)
    sha, size = hash_file_sha256(path)
    fingerprint = IngestFingerprint(
        content_sha256=sha,
        encoder_model=DEFAULT_EMBEDDING_MODEL,
        pipeline_version=DEFAULT_PIPELINE_VERSION,
    )
    decision = _document(path).decision
    assert decision is not None
    manifests.upsert(
        ManifestRecord(
            fingerprint=fingerprint,
            family=DocumentFamily.A,
            detected_format=decision.detected_format,
            byte_size=size,
            status="failed",
            chunk_count=0,
            ingested_at=datetime.now(UTC),
        )
    )

    result = skipper.execute(_document(path), ingest=narrative.execute)

    assert result.skipped is False
    assert len(parser.calls) == 1
    assert encoder.texts
    assert manifests.upsert_calls[-1].status == MANIFEST_STATUS_COMPLETE


def test_failed_ingest_does_not_write_manifest(tmp_path: Path) -> None:
    path = tmp_path / "empty.docx"
    path.write_bytes(b"empty-doc")
    parser = FakeNarrativeParser(
        error=NarrativeIngestError(FailureReason.EMPTY_DOCUMENT)
    )
    narrative = IngestNarrative(
        parser, FakeEncoder(), FakeChunkStore(), FakeObjectStore()
    )
    manifests = FakeManifestStore()
    skipper = SkipUnchangedIngest(manifests)

    result = skipper.execute(_document(path), ingest=narrative.execute)

    assert result.skipped is False
    assert result.failure_reason is FailureReason.EMPTY_DOCUMENT
    assert manifests.records == {}
    assert manifests.upsert_calls == []


def test_force_ignores_skip_and_records_again(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"force-me")
    skipper, manifests, parser, encoder, narrative = _pipeline(path)
    skipper.execute(_document(path), ingest=narrative.execute)
    parser.calls.clear()
    encoder.texts.clear()

    result = skipper.execute(_document(path), ingest=narrative.execute, force=True)

    assert result.skipped is False
    assert len(parser.calls) == 1
    assert encoder.texts
    assert len(manifests.upsert_calls) == 2


def test_lookup_failure_does_not_skip_or_ingest(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"lookup-down")
    skipper, manifests, parser, encoder, narrative = _pipeline(path)
    manifests.fail_find = True

    result = skipper.execute(_document(path), ingest=narrative.execute)

    assert result.skipped is False
    assert result.failure_reason is FailureReason.MANIFEST_LOOKUP_FAILED
    assert parser.calls == []
    assert encoder.texts == []
    assert manifests.upsert_calls == []


def test_different_fingerprint_does_not_skip(tmp_path: Path) -> None:
    path = tmp_path / "claim.docx"
    path.write_bytes(b"same-bytes")
    skipper, manifests, parser, _encoder, narrative = _pipeline(path)
    skipper.execute(_document(path), ingest=narrative.execute)
    parser.calls.clear()
    other = SkipUnchangedIngest(manifests, pipeline_version="2")
    other_parser = FakeNarrativeParser(_parsed(path))
    other_narrative = IngestNarrative(
        other_parser, FakeEncoder(), FakeChunkStore(), FakeObjectStore()
    )

    result = other.execute(_document(path), ingest=other_narrative.execute)

    assert result.skipped is False
    assert len(other_parser.calls) == 1


def test_family_c_uses_empty_encoder_model(tmp_path: Path) -> None:
    path = tmp_path / "ledger.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    manifests = FakeManifestStore()
    skipper = SkipUnchangedIngest(manifests)
    document = Document.from_signature(
        path, FileSignature(SignatureKind.CSV, csv_column_count=2)
    )
    calls: list[Path] = []

    def ingest(doc: Document) -> TabularIngestResult:
        calls.append(doc.path)
        return TabularIngestResult(
            source_path=doc.path,
            doc_id="t1",
            sheet_count=1,
            profile_key="p",
            parquet_keys=("k",),
            fact_table="claim_event",
            fact_row_count=1,
            failure_reason=None,
        )

    first = skipper.execute(document, ingest=ingest)
    second = skipper.execute(document, ingest=ingest)

    assert first.skipped is False
    assert second.skipped is True
    assert len(calls) == 1
    stored = manifests.upsert_calls[0]
    assert stored.fingerprint.encoder_model == ""
    assert stored.family is DocumentFamily.C
    assert stored.chunk_count == 1


def test_hash_is_streaming_bytes_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = tmp_path / "dir-a" / "alpha.docx"
    two = tmp_path / "dir-b" / "beta.docx"
    one.parent.mkdir()
    two.parent.mkdir()
    payload = b"xyz" * 1000
    one.write_bytes(payload)
    two.write_bytes(payload)

    def boom(self: Path) -> bytes:
        raise AssertionError("whole-file load is forbidden")

    monkeypatch.setattr(Path, "read_bytes", boom)
    sha_one, size_one = hash_file_sha256(one)
    sha_two, size_two = hash_file_sha256(two)

    assert sha_one == sha_two == hashlib.sha256(payload).hexdigest()
    assert size_one == size_two == len(payload)
    assert len(sha_one) == 64
