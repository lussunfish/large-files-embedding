"""UC-08: MCP layer-1 profile/parquet tools (fake ObjectStore/Layer1Store)."""

from __future__ import annotations

import inspect
import json

import pytest

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_DIM,
    MCP_TOOL_BODY_MAX_CHARS,
    MCP_TOOL_NAMES,
    NO_EVIDENCE,
    EncodedEmbedding,
    FailureReason,
    Grain,
    Layer1SheetListing,
    Layer1Store,
    McpQueryError,
    NarrativeChunk,
    ObjectStore,
    QueryFilters,
    require_readonly_layer1_sql,
)


class FakeEncoder:
    def encode(self, texts: list[str]) -> list[EncodedEmbedding]:
        dense = tuple(0.01 for _ in range(DEFAULT_EMBEDDING_DIM))
        return [
            EncodedEmbedding(
                dense=dense, sparse=((1, 1.0),), model="qwen3-embedding:4b"
            )
            for _ in texts
        ]


class FakeChunkStore:
    def upsert(self, collection: str, records: list[object]) -> None:
        del collection, records

    def search_hybrid(
        self,
        collection: str,
        *,
        dense: list[float],
        query_text: str,
        filters: QueryFilters,
        limit: int,
    ) -> list[object]:
        del collection, dense, query_text, filters, limit
        return []

    def query_chunks(self, collection: str, **kwargs: object) -> list[NarrativeChunk]:
        del collection, kwargs
        return []


class FakeTableStore:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.inserts: list[object] = []

    def insert_facts(
        self,
        table: str,
        rows: list[dict[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        self.inserts.append((table, list(rows), grain, report_period))
        return len(rows)

    def query_readonly(
        self, sql: str, params: list[object] | None = None
    ) -> list[dict[str, object]]:
        self.executed.append((sql, tuple(params or ())))
        return []


class FakeLayer1Store:
    def __init__(
        self,
        *,
        listings: list[Layer1SheetListing] | None = None,
        profiles: dict[str, bytes] | None = None,
        rows: dict[tuple[str, str], list[dict[str, object]]] | None = None,
    ) -> None:
        self.listings = list(listings or [])
        self.profiles = dict(profiles or {})
        self.rows = dict(rows or {})
        self.queries: list[dict[str, object]] = []

    def list_profiles(self) -> list[Layer1SheetListing]:
        return list(self.listings)

    def get_profile_bytes(self, doc_id: str) -> bytes | None:
        return self.profiles.get(doc_id)

    def query_parquet(
        self,
        doc_id: str,
        *,
        sheet: str | None,
        sql: str | None,
        columns: str | None,
        group_by: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        if sql:
            require_readonly_layer1_sql(
                sql,
                allowed_tables=_allowed_sheets(self, doc_id, sheet),
                doc_id=doc_id,
            )
        self.queries.append(
            {
                "doc_id": doc_id,
                "sheet": sheet,
                "sql": sql,
                "columns": columns,
                "group_by": group_by,
                "limit": limit,
            }
        )
        key = (doc_id, sheet or _default_sheet(self, doc_id))
        return list(self.rows.get(key, []))


def _allowed_sheets(
    store: FakeLayer1Store, doc_id: str, sheet: str | None
) -> list[str]:
    names = [item.sheet_name for item in store.listings if item.doc_id == doc_id]
    if sheet:
        return [sheet, *names]
    return names or ["layer1"]


def _default_sheet(store: FakeLayer1Store, doc_id: str) -> str:
    for item in store.listings:
        if item.doc_id == doc_id:
            return item.sheet_name
    return ""


def _profile_bytes(
    *,
    source_file: str = "misc.xlsx",
    sheet: str = "원장",
    n_rows: int = 2,
    n_cols: int = 4,
) -> bytes:
    payload = {
        "source_file": source_file,
        "sheets": [
            {
                "name": sheet,
                "kind": "data",
                "n_rows": n_rows,
                "n_cols": n_cols,
                "header_candidates": ["차종", "건수"],
                "original_columns": ["차종", "건수"],
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _uc(
    layer1: FakeLayer1Store | None = None,
) -> tuple[ServeMcp, FakeLayer1Store, FakeTableStore]:
    store = layer1 or FakeLayer1Store()
    tables = FakeTableStore()
    uc = ServeMcp(FakeChunkStore(), tables, FakeEncoder(), store)
    return uc, store, tables


def test_query_layer1_rejects_drop_and_create() -> None:
    listing = Layer1SheetListing(
        doc_id="doc-a",
        source_file="misc.xlsx",
        sheet_name="원장",
        n_rows=2,
        n_cols=4,
    )
    uc, store, tables = _uc(
        FakeLayer1Store(
            listings=[listing],
            profiles={"doc-a": _profile_bytes()},
            rows={("doc-a", "원장"): [{"차종": "SUV", "건수": 3}]},
        )
    )
    for sql in (
        "DROP TABLE 원장",
        "CREATE TABLE stolen AS SELECT * FROM 원장",
        "DELETE FROM 원장",
        "INSERT INTO 원장 VALUES (1)",
        "UPDATE 원장 SET 건수=0",
        "COPY 원장 TO '/tmp/x'",
        "ATTACH 's3://other-bucket/x.parquet'",
        "SELECT * FROM read_parquet('s3://psychology-pdfs/x.parquet')",
        "SELECT * FROM '../other/layer1/원장.parquet'",
        "SELECT * FROM market-quality-docs/other-doc/layer1/원장.parquet",
    ):
        result = uc.query_layer1(doc_id="doc-a", sheet="원장", sql=sql)
        assert "거부" in result, sql
        with pytest.raises(McpQueryError) as exc:
            require_readonly_layer1_sql(sql, allowed_tables=["원장"], doc_id="doc-a")
        assert exc.value.reason in {
            FailureReason.SQL_WRITE,
            FailureReason.SQL_NOT_ALLOWED,
        }
    assert store.queries == []
    assert tables.inserts == []
    assert tables.executed == []


def test_describe_profile_returns_json_without_parquet_body() -> None:
    parquet_blob = b"PAR1" + b"\x00" * 64 + "원본CSV,차종,건수".encode()
    profile = _profile_bytes(source_file="unmapped.xlsx", sheet="요약")
    uc, _store, tables = _uc(
        FakeLayer1Store(
            listings=[
                Layer1SheetListing("doc-p", "unmapped.xlsx", "요약", 3, 5),
            ],
            profiles={"doc-p": profile},
            rows={
                ("doc-p", "요약"): [
                    {
                        "source_file": "unmapped.xlsx",
                        "sheet_name": "요약",
                        "raw": parquet_blob.decode("latin1"),
                    }
                ]
            },
        )
    )
    described = uc.describe_profile("doc-p")
    assert described != NO_EVIDENCE
    assert "unmapped.xlsx" in described
    assert "요약" in described
    assert "PAR1" not in described
    assert "원본CSV" not in described
    assert parquet_blob not in described.encode("utf-8", errors="ignore")
    assert tables.inserts == []


def test_describe_profile_missing_is_no_evidence() -> None:
    uc, _store, _tables = _uc()
    assert uc.describe_profile("missing") == NO_EVIDENCE
    assert uc.list_layer1() == NO_EVIDENCE
    assert uc.query_layer1("missing", sheet="원장") == NO_EVIDENCE


def test_list_layer1_includes_doc_id_source_file_and_sheet_stats() -> None:
    uc, _store, _tables = _uc(
        FakeLayer1Store(
            listings=[
                Layer1SheetListing("abc123", "kpi.xlsx", "월보", 12, 6),
            ],
            profiles={"abc123": _profile_bytes(source_file="kpi.xlsx", sheet="월보")},
        )
    )
    listed = uc.list_layer1()
    assert "abc123" in listed
    assert "kpi.xlsx" in listed
    assert "월보" in listed
    assert "12" in listed
    assert "6" in listed


def test_query_layer1_applies_default_limit_and_clips_body() -> None:
    huge = "가" * (MCP_TOOL_BODY_MAX_CHARS + 200)
    rows = [
        {
            "source_file": "wide.xlsx",
            "sheet_name": "원장",
            "차종": "SUV",
            "본문": huge,
        }
        for _ in range(3)
    ]
    uc, store, _tables = _uc(
        FakeLayer1Store(
            listings=[Layer1SheetListing("doc-l", "wide.xlsx", "원장", 3, 4)],
            profiles={"doc-l": _profile_bytes(source_file="wide.xlsx")},
            rows={("doc-l", "원장"): rows},
        )
    )
    result = uc.query_layer1("doc-l", sheet="원장")
    assert store.queries
    assert store.queries[0]["limit"] == 100
    assert "wide.xlsx" in result
    assert "원장" in result or "sheet=" in result
    assert "truncated" in result.lower() or "pointer=" in result
    assert len(result) <= MCP_TOOL_BODY_MAX_CHARS + 80
    uc.query_layer1("doc-l", sheet="원장", limit=10_000)
    assert store.queries[-1]["limit"] == 500


def test_query_layer1_prefers_columns_group_by_over_sql() -> None:
    uc, store, _tables = _uc(
        FakeLayer1Store(
            listings=[Layer1SheetListing("doc-g", "misc.xlsx", "원장", 2, 3)],
            profiles={"doc-g": _profile_bytes()},
            rows={
                ("doc-g", "원장"): [
                    {
                        "source_file": "misc.xlsx",
                        "sheet_name": "원장",
                        "차종": "SUV",
                        "n": 2,
                    }
                ]
            },
        )
    )
    result = uc.query_layer1(
        "doc-g",
        sheet="원장",
        sql="SELECT * FROM 원장",
        columns="차종",
        group_by="차종",
        limit=10,
    )
    assert "거부" not in result
    assert store.queries
    call = store.queries[0]
    assert call["columns"] == "차종"
    assert call["group_by"] == "차종"
    assert call["sql"] is None
    assert "misc.xlsx" in result
    assert "SUV" in result or "원장" in result


def test_query_layer1_missing_profile_or_one_col_sheet_is_no_evidence() -> None:
    uc, store, _tables = _uc(
        FakeLayer1Store(
            listings=[Layer1SheetListing("doc-q", "notes.csv", "본문", 4, 1)],
            profiles={
                "doc-q": _profile_bytes(source_file="notes.csv", sheet="본문", n_cols=1)
            },
            rows={
                ("doc-q", "본문"): [
                    {"본문": "한 열 산문 행", "source_file": "notes.csv"}
                ]
            },
        )
    )
    assert uc.query_layer1("doc-q", sheet="본문") == NO_EVIDENCE
    assert store.queries == []

    uc2, store2, _tables2 = _uc(
        FakeLayer1Store(
            rows={("doc-p", "원장"): [{"차종": "SUV", "건수": 1}]},
        )
    )
    assert uc2.query_layer1("doc-p", sheet="원장") == NO_EVIDENCE
    assert store2.queries == []


def test_query_layer1_cites_data_sheet_when_pivot_present_and_sheet_omitted() -> None:
    profile = json.dumps(
        {
            "source_file": "kpi.xlsx",
            "sheets": [
                {
                    "name": "원장",
                    "kind": "data",
                    "n_rows": 2,
                    "n_cols": 3,
                },
                {
                    "name": "피벗",
                    "kind": "pivot",
                    "n_rows": 0,
                    "n_cols": 0,
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    uc, store, _tables = _uc(
        FakeLayer1Store(
            listings=[
                Layer1SheetListing("doc-v", "kpi.xlsx", "원장", 2, 3),
                Layer1SheetListing("doc-v", "kpi.xlsx", "피벗", 0, 0),
            ],
            profiles={"doc-v": profile},
            rows={("doc-v", "원장"): [{"차종": "SUV", "n": 1}]},
        )
    )
    result = uc.query_layer1("doc-v", columns="차종", group_by="차종")
    assert "거부" not in result
    assert result != NO_EVIDENCE
    assert "kpi.xlsx" in result
    assert "원장" in result
    assert store.queries
    assert store.queries[0]["sheet"] == "원장"
    assert store.queries[0]["sql"] is None
    assert store.queries[0]["columns"] == "차종"
    assert store.queries[0]["group_by"] == "차종"


def test_query_layer1_rejects_zwsp_read_text() -> None:
    sql = "SELECT * FROM 원장 FROM\u200bread_text('/etc/passwd')"
    uc, store, _tables = _uc(
        FakeLayer1Store(
            listings=[Layer1SheetListing("doc-a", "misc.xlsx", "원장", 2, 4)],
            profiles={"doc-a": _profile_bytes()},
            rows={("doc-a", "원장"): [{"차종": "SUV"}]},
        )
    )
    result = uc.query_layer1(doc_id="doc-a", sheet="원장", sql=sql)
    assert "거부" in result
    assert "root:" not in result
    assert "/etc/passwd" not in result
    assert store.queries == []
    with pytest.raises(McpQueryError) as exc:
        require_readonly_layer1_sql(sql, allowed_tables=["원장"], doc_id="doc-a")
    assert exc.value.reason is FailureReason.SQL_NOT_ALLOWED


def test_query_layer1_without_parquet_or_prose_sheet_is_no_evidence() -> None:
    uc, _store, _tables = _uc(
        FakeLayer1Store(
            listings=[
                Layer1SheetListing("doc-z", "notes.csv", "본문", 4, 1),
            ],
            profiles={"doc-z": _profile_bytes(sheet="본문", n_cols=1)},
        )
    )
    assert uc.query_layer1("doc-z", sheet="피벗") == NO_EVIDENCE
    listed = uc.list_layer1()
    assert listed == NO_EVIDENCE or "본문" not in listed


def test_layer1_tools_are_registered_and_closed_list_has_no_search() -> None:
    uc, _store, _tables = _uc()
    names = [spec.name for spec in uc.tool_specs()]
    assert names == list(MCP_TOOL_NAMES)
    for name in ("list_layer1", "describe_profile", "query_layer1"):
        assert name in names
    assert "search" not in names
    assert "ingest" not in names
    assert "delete" not in names
    by_name = {spec.name: spec.description for spec in uc.tool_specs()}
    joined = " ".join(by_name.values())
    assert "query_tables" in joined
    assert "describe_profile" in joined
    assert "query_layer1" in joined
    assert "get_section" in joined
    assert "search_passages" in joined
    assert "doc_id" in by_name["describe_profile"].lower() or "doc_id" in str(
        uc.tool_specs()
    )
    assert (
        "sql" in by_name["query_layer1"]
        or "sql" in ServeMcp.query_layer1.__code__.co_varnames
    )


def test_query_layer1_does_not_create_mariadb_tables() -> None:
    from large_files_embedding.infrastructure.duckdb_layer1 import DuckDbLayer1Store
    from large_files_embedding.infrastructure.mariadb_table_store import (
        MariaDbTableStore,
    )

    uc, _store, tables = _uc(
        FakeLayer1Store(
            listings=[Layer1SheetListing("doc-m", "a.xlsx", "원장", 1, 2)],
            profiles={"doc-m": _profile_bytes()},
            rows={
                ("doc-m", "원장"): [
                    {"source_file": "a.xlsx", "sheet_name": "원장", "차종": "SUV"}
                ]
            },
        )
    )
    result = uc.query_layer1("doc-m", sheet="원장")
    assert "거부" not in result
    assert tables.inserts == []
    src = inspect.getsource(DuckDbLayer1Store)
    assert "CREATE TABLE" not in src.upper()
    assert "insert_facts" not in src
    assert "MariaDb" not in src
    module = inspect.getmodule(DuckDbLayer1Store)
    assert module is not None
    module_src = inspect.getsource(module)
    assert "enable_external_access=false" in module_src
    assert "lock_configuration=true" in module_src
    assert "download_to" in module_src
    query_src = inspect.getsource(MariaDbTableStore.query_readonly)
    assert "_ensure_schema" not in query_src


def test_object_store_and_layer1_ports_expose_reads() -> None:
    assert callable(getattr(ObjectStore, "get_bytes"))
    assert callable(getattr(ObjectStore, "list_prefix"))
    assert callable(getattr(ObjectStore, "download_to"))
    assert callable(getattr(Layer1Store, "list_profiles"))
    assert callable(getattr(Layer1Store, "get_profile_bytes"))
    assert callable(getattr(Layer1Store, "query_parquet"))


def test_mcp_server_registers_layer1_tools_without_ingest() -> None:
    from large_files_embedding.presentation.mcp.server import StdioMcpServer

    module = inspect.getmodule(StdioMcpServer)
    assert module is not None
    src = inspect.getsource(module)
    assert "list_layer1" in src
    assert "describe_profile" in src
    assert "query_layer1" in src
    assert "ingest(" not in src
    assert "CREATE TABLE" not in src.upper()
