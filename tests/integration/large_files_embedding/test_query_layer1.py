"""UC-08 integration: skip if 01-stable MinIO is down."""

from __future__ import annotations

import inspect
import json
import urllib.error
import urllib.request
import uuid
from io import BytesIO

import polars as pl
import pytest

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_DIM,
    MARKET_QUALITY_BUCKET,
    NO_EVIDENCE,
    EncodedEmbedding,
    Grain,
)
from large_files_embedding.infrastructure.duckdb_layer1 import DuckDbLayer1Store
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _require_minio() -> MinioObjectStore:
    if not _http_ok("http://127.0.0.1:9000/minio/health/live"):
        pytest.skip("01-stable down: minio")
    try:
        return MinioObjectStore.from_env()
    except Exception as exc:
        pytest.skip(f"minio: {exc}")


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


class _EmptyTables:
    def insert_facts(
        self,
        table: str,
        rows: list[dict[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        del table, rows, grain, report_period
        raise AssertionError("layer1 must not insert MariaDB facts")

    def query_readonly(
        self, sql: str, params: list[object] | None = None
    ) -> list[dict[str, object]]:
        del sql, params
        raise AssertionError("layer1 must not query MariaDB")


def _put_layer1(objects: MinioObjectStore, doc_id: str) -> None:
    profile = {
        "source_file": "uc08-misc.xlsx",
        "sheets": [
            {
                "name": "원장",
                "kind": "data",
                "n_rows": 2,
                "n_cols": 3,
                "header_candidates": ["차종", "건수"],
                "original_columns": ["차종", "건수"],
            },
            {
                "name": "피벗",
                "kind": "pivot",
                "n_rows": 0,
                "n_cols": 0,
                "header_candidates": [],
                "original_columns": [],
            },
        ],
    }
    objects.put_bytes(
        f"{doc_id}/profile.json",
        json.dumps(profile, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )
    frame = pl.DataFrame(
        {
            "차종": ["SUV", "SEDAN"],
            "건수": [3, 1],
            "source_file": ["uc08-misc.xlsx", "uc08-misc.xlsx"],
            "sheet_name": ["원장", "원장"],
        }
    )
    buffer = BytesIO()
    frame.write_parquet(buffer)
    objects.put_bytes(
        f"{doc_id}/layer1/원장.parquet",
        buffer.getvalue(),
        content_type="application/vnd.apache.parquet",
    )


def test_layer1_tools_against_minio_parquet() -> None:
    objects = _require_minio()
    assert objects._bucket == MARKET_QUALITY_BUCKET
    doc_id = f"uc08-{uuid.uuid4().hex[:12]}"
    _put_layer1(objects, doc_id)
    store = DuckDbLayer1Store(objects)
    uc = ServeMcp(
        _EmptyChunks(),
        _EmptyTables(),
        _StubEncoder(),
        store,
    )
    listed = uc.list_layer1()
    assert listed != NO_EVIDENCE
    assert "doc_id=" in listed
    assert "source_file=" in listed
    assert any(item.doc_id == doc_id for item in store.list_profiles())
    described = uc.describe_profile(doc_id)
    assert "uc08-misc.xlsx" in described
    assert "PAR1" not in described
    assert "원본CSV" not in described
    result = uc.query_layer1(doc_id, sheet="원장", columns="차종", group_by="차종")
    assert "거부" not in result
    assert result != NO_EVIDENCE
    assert "uc08-misc.xlsx" in result
    assert "SUV" in result or "차종" in result
    omitted = uc.query_layer1(doc_id, columns="차종", group_by="차종")
    assert "거부" not in omitted
    assert "uc08-misc.xlsx" in omitted
    assert "원장" in omitted
    assert "거부" in uc.query_layer1(doc_id, sheet="원장", sql="DROP TABLE 원장")
    assert "거부" in uc.query_layer1(
        doc_id, sheet="원장", sql="CREATE TABLE x AS SELECT * FROM 원장"
    )
    assert uc.query_layer1(doc_id, sheet="피벗") == NO_EVIDENCE


def test_duckdb_adapter_scans_parquet_without_mariadb_ddl() -> None:
    from large_files_embedding.infrastructure.duckdb_layer1 import DuckDbLayer1Store
    from large_files_embedding.infrastructure.minio_object_store import (
        MinioObjectStore,
    )

    module = inspect.getmodule(DuckDbLayer1Store)
    assert module is not None
    src = inspect.getsource(module)
    assert "read_parquet" in src or "scan_parquet" in src
    assert "CREATE TABLE" not in src.upper()
    assert "insert_facts" not in src
    get_src = inspect.getsource(MinioObjectStore)
    assert "def get_bytes" in get_src
    assert "def list_prefix" in get_src
    assert "def download_to" in get_src
    assert "fget_object" in get_src
    assert "enable_external_access=false" in src
    assert "lock_configuration=true" in src
