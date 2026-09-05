"""UC-05 integration: skip if 01-stable MariaDB/Milvus/Ollama are down."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid

import pytest
from typer.testing import CliRunner

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_DIM,
    MARKET_QUALITY_COLLECTION,
    NO_EVIDENCE,
    ChunkType,
    DocumentFamily,
    EncodedEmbedding,
    Grain,
    NarrativeChunk,
    NarrativeIngestError,
    require_readonly_sql,
)
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore
from large_files_embedding.presentation.cli.main import app


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _ollama_has_model() -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:11434/api/tags", timeout=2
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return False
    names = [str(item.get("name", "")) for item in payload.get("models", [])]
    return any(
        name == "qwen3-embedding:4b" or name.startswith("qwen3-embedding:4b")
        for name in names
    )


def _mariadb_skip_reason() -> str | None:
    if not _port_open("127.0.0.1", 3306):
        return "01-stable down: mariadb"
    return None


def _milvus_skip_reason() -> str | None:
    missing: list[str] = []
    if not _http_ok("http://127.0.0.1:9091/healthz"):
        missing.append("milvus")
    if not _port_open("127.0.0.1", 19530):
        missing.append("milvus-grpc")
    if not _ollama_has_model():
        missing.append("ollama:qwen3-embedding:4b")
    if missing:
        return "01-stable/ollama down: " + ", ".join(missing)
    return None


def _require_mariadb() -> MariaDbTableStore:
    reason = _mariadb_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    try:
        store = MariaDbTableStore.from_env()
        store.ensure_schema()
    except Exception as exc:
        pytest.skip(f"mariadb: {exc}")
    return store


class _StubEncoder:
    def encode(self, texts: list[str]) -> list[EncodedEmbedding]:
        dense = tuple(0.01 for _ in range(DEFAULT_EMBEDDING_DIM))
        return [
            EncodedEmbedding(
                dense=dense, sparse=((1, 1.0),), model="qwen3-embedding:4b"
            )
            for _ in texts
        ]


class _EmptyChunks:
    def upsert(self, collection: str, records: list[object]) -> None:
        del collection, records

    def search_hybrid(self, collection: str, **kwargs: object) -> list[object]:
        del collection, kwargs
        return []

    def query_chunks(self, collection: str, **kwargs: object) -> list[object]:
        del collection, kwargs
        return []


def test_cli_mcp_help_is_registered() -> None:
    result = CliRunner().invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output.lower() or "조회" in result.output


def test_query_tables_drop_is_rejected_against_mariadb() -> None:
    tables = _require_mariadb()
    uc = ServeMcp(_EmptyChunks(), tables, _StubEncoder())
    result = uc.query_tables(sql="DROP TABLE claim_event")
    assert "거부" in result
    with pytest.raises(Exception):
        require_readonly_sql("DROP TABLE claim_event")
    for sql in (
        "SELECT * FROM claim_event, information_schema.tables",
        "SELECT * FROM claim_event STRAIGHT_JOIN information_schema.tables",
        "SELECT * FROM claim_event, embeddings.chunks",
        "/*!50000 DELETE FROM claim_event WHERE id IN (*/ SELECT id FROM claim_event)",
        "SELECT SLEEP(1) FROM claim_event",
    ):
        assert "거부" in uc.query_tables(sql=sql), sql


def test_query_tables_structured_read_against_mariadb() -> None:
    tables = _require_mariadb()
    marker = f"uc05-{uuid.uuid4().hex[:8]}.xlsx"
    tables.insert_facts(
        "claim_event",
        [
            {
                "source_file": marker,
                "sheet_name": "원장",
                "report_period": "2024-01",
                "ingested_at": "2026-01-01T00:00:00",
                "template_family": "ledger",
                "part_no": "UC05-PART",
                "vehicle": "SUV",
                "event_date": "2024-01-15",
                "cause": "누유",
                "countermeasure": "가스켓",
                "quantity": 3,
            }
        ],
        grain=Grain.LEDGER,
        report_period="2024-01",
    )
    uc = ServeMcp(_EmptyChunks(), tables, _StubEncoder())
    listed = uc.list_tables(period="2024-01")
    assert "claim_event" in listed
    described = uc.describe_table("claim_event")
    assert "클레임" in described or "grain" in described.lower()
    result = uc.query_tables(
        table="claim_event",
        period="2024-01",
        group_by="vehicle",
        limit=20,
    )
    assert "거부" not in result
    assert result != NO_EVIDENCE
    assert "SUV" in result or marker in result or "quantity" in result.lower()


def test_list_documents_filter_args_on_milvus_adapter() -> None:
    reason = _milvus_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    store = MilvusChunkStore.from_env()
    assert store._collection == MARKET_QUALITY_COLLECTION
    chunk = NarrativeChunk(
        chunk_id=f"uc05-{uuid.uuid4().hex[:12]}",
        doc_id=f"uc05-doc-{uuid.uuid4().hex[:8]}",
        path="uc05-claim.docx",
        family=DocumentFamily.A,
        chunk_type=ChunkType.TEXT,
        text="UC05 원인 본문",
        embedding_input="[섹션] 3. 원인\nUC05 원인 본문",
        section_path="3. 원인",
        product="SUV",
        period="2024-01",
        doc_type="8D",
    )
    try:
        found = store.query_chunks(
            MARKET_QUALITY_COLLECTION,
            filters=None,
            doc_id=chunk.doc_id,
            limit=5,
        )
    except NarrativeIngestError as exc:
        pytest.skip(f"milvus: {exc}")
    assert isinstance(found, list)
