"""UC-07 integration: MariaDB ingest_manifest skip (01-stable or skip)."""

from __future__ import annotations

import hashlib
import inspect
import socket
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pymysql
import pytest
from typer.testing import CliRunner

from large_files_embedding.application.skip_unchanged_ingest import SkipUnchangedIngest
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_PIPELINE_VERSION,
    MANIFEST_STATUS_COMPLETE,
    SKIP_REASON_UNCHANGED,
    Document,
    DocumentFamily,
    DocumentFormat,
    FailureReason,
    FileSignature,
    IngestFingerprint,
    ManifestRecord,
    ManifestStoreError,
    SignatureKind,
    TabularIngestResult,
    fingerprint_for,
)
from large_files_embedding.infrastructure.mariadb_manifest_store import (
    MariaDbManifestStore,
)
from large_files_embedding.presentation.cli.ingest import ingest
from large_files_embedding.presentation.cli.main import app


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _require_mariadb() -> MariaDbManifestStore:
    if not _port_open("127.0.0.1", 3306):
        pytest.skip("01-stable down: mariadb")
    try:
        store = MariaDbManifestStore.from_env()
        store.ensure_schema()
    except Exception as exc:
        pytest.skip(f"mariadb: {exc}")
    return store


def _document(path: Path) -> Document:
    return Document.from_signature(
        path, FileSignature(SignatureKind.CSV, csv_column_count=2)
    )


def _ingest_ok(document: Document) -> TabularIngestResult:
    return TabularIngestResult(
        source_path=document.path,
        doc_id="t1",
        sheet_count=1,
        profile_key="p",
        parquet_keys=("k",),
        fact_table=None,
        fact_row_count=0,
        failure_reason=None,
    )


def test_same_bytes_skip_across_paths(tmp_path: Path) -> None:
    store = _require_mariadb()
    payload = f"uc07-{uuid.uuid4()}".encode()
    first = tmp_path / "one" / "a.csv"
    second = tmp_path / "two" / "b.csv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(payload)
    second.write_bytes(payload)
    skipper = SkipUnchangedIngest(store)
    calls: list[Path] = []

    def ingest_fn(document: Document) -> TabularIngestResult:
        calls.append(document.path)
        return _ingest_ok(document)

    first_result = skipper.execute(_document(first), ingest=ingest_fn)
    second_result = skipper.execute(_document(second), ingest=ingest_fn)
    sha = hashlib.sha256(payload).hexdigest()

    assert first_result.skipped is False
    assert second_result.skipped is True
    assert second_result.skip_reason == SKIP_REASON_UNCHANGED
    assert second_result.content_sha256 == sha
    assert calls == [first]
    decision = _document(first).decision
    assert decision is not None
    record = store.find(
        fingerprint_for(
            decision.family,
            sha,
            encoder_model=DEFAULT_EMBEDDING_MODEL,
            pipeline_version=DEFAULT_PIPELINE_VERSION,
        )
    )
    assert record is not None
    assert record.status == MANIFEST_STATUS_COMPLETE
    assert record.fingerprint.encoder_model == ""
    assert not hasattr(record, "path")


def test_force_reingests_and_updates_ledger(tmp_path: Path) -> None:
    store = _require_mariadb()
    path = tmp_path / "force.csv"
    path.write_bytes(f"force-{uuid.uuid4()}".encode())
    skipper = SkipUnchangedIngest(store)
    calls: list[Path] = []

    def ingest_fn(document: Document) -> TabularIngestResult:
        calls.append(document.path)
        return _ingest_ok(document)

    skipper.execute(_document(path), ingest=ingest_fn)
    skipper.execute(_document(path), ingest=ingest_fn, force=True)
    skipped = skipper.execute(_document(path), ingest=ingest_fn)

    assert len(calls) == 2
    assert skipped.skipped is True


def test_cli_force_flag_exists() -> None:
    source = inspect.getsource(ingest)
    assert "--force" in source
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.stdout


def test_upsert_connect_failure_is_write_failed() -> None:
    store = MariaDbManifestStore("127.0.0.1", 1, "market_quality", "u", "p")

    def boom(database: str) -> object:
        del database
        raise pymysql.err.OperationalError(2003, "down")

    store._open = boom  # type: ignore[method-assign]
    record = ManifestRecord(
        fingerprint=IngestFingerprint("a" * 64, "", DEFAULT_PIPELINE_VERSION),
        family=DocumentFamily.C,
        detected_format=DocumentFormat.CSV,
        byte_size=1,
        status=MANIFEST_STATUS_COMPLETE,
        chunk_count=0,
        ingested_at=datetime.now(UTC),
    )
    with pytest.raises(ManifestStoreError) as exc:
        store.upsert(record)
    assert exc.value.reason is FailureReason.MANIFEST_WRITE_FAILED

    with pytest.raises(ManifestStoreError) as find_exc:
        store.find(record.fingerprint)
    assert find_exc.value.reason is FailureReason.MANIFEST_LOOKUP_FAILED


def test_manifest_adapter_has_no_path_skip_key() -> None:
    import large_files_embedding.infrastructure.mariadb_manifest_store as module

    source = inspect.getsource(module)
    assert "ingest_manifest" in source
    assert "PRIMARY KEY (content_sha256, encoder_model, pipeline_version)" in source
    assert "aliases" not in source
    assert "source_path" not in source
    assert "file_name" not in source
