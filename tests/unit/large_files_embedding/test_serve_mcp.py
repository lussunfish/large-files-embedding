"""UC-05: MCP query tools (fake ChunkStore/TableStore)."""

from __future__ import annotations

import inspect

import pytest

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import (
    ALLOWED_FACT_TABLES,
    DEFAULT_EMBEDDING_DIM,
    MARKET_QUALITY_COLLECTION,
    MCP_TOOL_NAMES,
    NO_EVIDENCE,
    ChunkStore,
    ChunkType,
    DocumentFamily,
    EncodedEmbedding,
    FailureReason,
    Grain,
    McpQueryError,
    NarrativeChunk,
    NarrativeIngestError,
    QueryFilters,
    TableStore,
    ensure_sql_limit,
    format_citation,
    require_readonly_sql,
)


class FakeEncoder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def encode(self, texts: list[str]) -> list[EncodedEmbedding]:
        self.texts.extend(texts)
        dense = tuple(0.01 for _ in range(DEFAULT_EMBEDDING_DIM))
        return [
            EncodedEmbedding(
                dense=dense, sparse=((1, 1.0),), model="qwen3-embedding:4b"
            )
            for _ in texts
        ]


class FakeChunkStore:
    def __init__(self, chunks: list[NarrativeChunk] | None = None) -> None:
        self.chunks = list(chunks or [])
        self.search_calls: list[tuple[str, QueryFilters, int]] = []
        self.upserts: list[object] = []

    def upsert(self, collection: str, records: list[object]) -> None:
        from large_files_embedding.domain.document import require_collection

        require_collection(collection)
        self.upserts.extend(records)

    def search_hybrid(
        self,
        collection: str,
        *,
        dense: list[float],
        query_text: str,
        filters: QueryFilters,
        limit: int,
    ) -> list[tuple[NarrativeChunk, float]]:
        from large_files_embedding.domain.document import PassageHit, require_collection

        del dense
        require_collection(collection)
        self.search_calls.append((query_text, filters, limit))
        hits: list[PassageHit] = []
        needle = query_text.lower()
        for chunk in self.chunks:
            if not _match_filters(chunk, filters):
                continue
            haystack = f"{chunk.text} {chunk.embedding_input} {chunk.part_no or ''}"
            if needle and needle not in haystack.lower():
                continue
            hits.append(PassageHit(chunk=chunk, score=1.0))
        return hits[:limit]

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
    ) -> list[NarrativeChunk]:
        from large_files_embedding.domain.document import require_collection

        require_collection(collection)
        out: list[NarrativeChunk] = []
        for chunk in self.chunks:
            if filters is not None and not _match_filters(chunk, filters):
                continue
            if doc_id is not None and chunk.doc_id != doc_id:
                continue
            if chunk_id is not None and chunk.chunk_id != chunk_id:
                continue
            if parent_id is not None and chunk.parent_id != parent_id:
                continue
            if chunk_type is not None and chunk.chunk_type is not chunk_type:
                continue
            if family is not None and chunk.family is not family:
                continue
            if page is not None and chunk.page != page:
                continue
            if slide_index is not None and chunk.slide_index != slide_index:
                continue
            if heading_path is not None and not _under_heading(chunk, heading_path):
                continue
            out.append(chunk)
            if len(out) >= limit:
                break
        return out


class FakeTableStore:
    def __init__(self) -> None:
        self.claim_rows: list[dict[str, object]] = []
        self.kpi_rows: list[dict[str, object]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def insert_facts(
        self,
        table: str,
        rows: list[dict[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        from large_files_embedding.domain.document import require_fact_table

        require_fact_table(table)
        del grain, report_period
        target = self.claim_rows if table == "claim_event" else self.kpi_rows
        target.extend(rows)
        return len(rows)

    def query_readonly(
        self, sql: str, params: list[object] | None = None
    ) -> list[dict[str, object]]:
        require_readonly_sql(sql)
        bound = tuple(params or ())
        self.executed.append((sql, bound))
        lowered = sql.lower()
        if "monthly_quality_kpi" in lowered:
            return list(self.kpi_rows)
        return list(self.claim_rows)


def _match_filters(chunk: NarrativeChunk, filters: QueryFilters) -> bool:
    if filters.product and (chunk.product or "") != filters.product:
        return False
    if filters.period and (chunk.period or "") != filters.period:
        return False
    if filters.doc_type and (chunk.doc_type or "") != filters.doc_type:
        return False
    return True


def _under_heading(chunk: NarrativeChunk, heading_path: str) -> bool:
    path = chunk.section_path or ""
    if path == heading_path:
        return True
    return path.startswith(f"{heading_path} >") or path.startswith(f"{heading_path}/")


def _chunk(
    *,
    chunk_id: str = "c1",
    doc_id: str = "doc-1",
    path: str = "claim.docx",
    family: DocumentFamily = DocumentFamily.A,
    chunk_type: ChunkType = ChunkType.TEXT,
    text: str = "근본원인 본문",
    section_path: str | None = "3. 원인",
    slide_index: int | None = None,
    page: int | None = None,
    parent_id: str | None = "doc-1:3. 원인",
    product: str | None = "SUV",
    period: str | None = "2024-01",
    doc_type: str | None = "8D",
    part_no: str | None = "A-1",
) -> NarrativeChunk:
    return NarrativeChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        path=path,
        family=family,
        chunk_type=chunk_type,
        text=text,
        embedding_input=f"[섹션] {section_path or ''}\n{text}",
        section_path=section_path,
        slide_index=slide_index,
        page=page,
        parent_id=parent_id,
        product=product,
        period=period,
        doc_type=doc_type,
        part_no=part_no,
    )


def _uc(
    chunks: list[NarrativeChunk] | None = None,
    tables: FakeTableStore | None = None,
) -> tuple[ServeMcp, FakeChunkStore, FakeTableStore, FakeEncoder]:
    store = FakeChunkStore(chunks)
    table_store = tables or FakeTableStore()
    encoder = FakeEncoder()
    return ServeMcp(store, table_store, encoder), store, table_store, encoder


def test_query_tables_rejects_drop() -> None:
    uc, _chunks, tables, _encoder = _uc()
    result = uc.query_tables(sql="DROP TABLE claim_event")
    assert "거부" in result
    assert tables.executed == []
    with pytest.raises(McpQueryError) as exc:
        require_readonly_sql("DROP TABLE claim_event")
    assert exc.value.reason is FailureReason.SQL_WRITE


def test_query_tables_rejects_writes_and_forbidden_schema() -> None:
    uc, _chunks, tables, _encoder = _uc()
    for sql in (
        "DELETE FROM claim_event",
        "INSERT INTO claim_event (part_no) VALUES ('x')",
        "UPDATE claim_event SET quantity=0",
        "SELECT * FROM embeddings.chunks",
        "SELECT * FROM secret_xlsx_blob",
        "SELECT * FROM claim_event, information_schema.tables",
        "SELECT * FROM claim_event STRAIGHT_JOIN information_schema.tables",
        "SELECT * FROM claim_event, embeddings.chunks",
        "SELECT * FROM otherdb.claim_event",
        "SELECT * FROM claim_event /*!50000 , information_schema.tables */",
        "/*!50000 DELETE FROM claim_event WHERE id IN (*/ SELECT id FROM claim_event)",
        "/*!50000 INSERT INTO claim_event (part_no) */ SELECT part_no FROM claim_event",
        "SELECT * FROM claim_event /*!50000 INTO OUTFILE '/tmp/pwn' */",
        "SELECT SLEEP(5) FROM claim_event",
        "SELECT LOAD_FILE('/etc/passwd') FROM claim_event",
    ):
        result = uc.query_tables(sql=sql)
        assert "거부" in result, sql
        with pytest.raises(McpQueryError):
            require_readonly_sql(sql)
    assert tables.executed == []


def test_query_tables_rejects_index_hint_comma_joins() -> None:
    uc, _chunks, tables, _encoder = _uc()
    payloads = (
        (
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM claim_event "
            "USE INDEX (), information_schema.tables"
        ),
        (
            "SELECT SCHEMA_NAME FROM claim_event IGNORE INDEX (PRIMARY), "
            "information_schema.SCHEMATA"
        ),
        ("SELECT * FROM claim_event FORCE INDEX (PRIMARY), information_schema.tables"),
        ("SELECT * FROM claim_event IGNORE KEY (PRIMARY), information_schema.tables"),
        ("SELECT * FROM claim_event AS t USE INDEX (PRIMARY), embeddings.chunks"),
        (
            "SELECT * FROM claim_event USE INDEX FOR JOIN (PRIMARY), "
            "information_schema.tables"
        ),
        ("SELECT * FROM claim_event PARTITION (p0), information_schema.tables"),
    )
    for sql in payloads:
        result = uc.query_tables(sql=sql)
        assert "거부" in result, sql
        with pytest.raises(McpQueryError) as exc:
            require_readonly_sql(sql)
        assert exc.value.reason in {
            FailureReason.SQL_NOT_ALLOWED,
            FailureReason.EMBEDDINGS_VECTOR,
        }
    require_readonly_sql("SELECT * FROM claim_event USE INDEX (PRIMARY)")
    assert tables.executed == []


def test_filter_args_exist_on_list_documents_search_passages_list_tables() -> None:
    uc, _chunks, _tables, _encoder = _uc()
    specs = {spec.name: spec for spec in uc.tool_specs()}
    for name in ("list_documents", "search_passages", "list_tables"):
        assert name in specs
        for arg in ("product", "period", "doc_type"):
            assert arg in specs[name].parameters
        sig = inspect.signature(getattr(uc, name))
        assert "product" in sig.parameters
        assert "period" in sig.parameters
        assert "doc_type" in sig.parameters


def test_closed_tool_list_has_no_search_or_ingest() -> None:
    uc, _chunks, _tables, _encoder = _uc()
    names = [spec.name for spec in uc.tool_specs()]
    assert names == list(MCP_TOOL_NAMES)
    assert "search" not in names
    assert "ingest" not in names
    assert "delete" not in names
    assert "search_hwp" not in names


def test_tool_descriptions_route_question_types() -> None:
    uc, _chunks, _tables, _encoder = _uc()
    by_name = {spec.name: spec.description for spec in uc.tool_specs()}
    assert "query_tables" in by_name["query_tables"]
    assert "숫자" in by_name["query_tables"] or "집계" in by_name["query_tables"]
    assert "get_section" in by_name["get_section"]
    assert "원인" in by_name["get_section"] or "대책" in by_name["get_section"]
    assert "search_passages" in by_name["search_passages"]
    assert "품번" in by_name["search_passages"] or "코드" in by_name["search_passages"]
    assert "search_passages" in by_name["list_documents"]
    joined = " ".join(by_name.values())
    assert "query_tables" in joined
    assert "get_section" in joined
    assert "search_passages" in joined


def test_missing_evidence_returns_no_evidence() -> None:
    uc, _chunks, _tables, _encoder = _uc()
    assert uc.search_passages("없는품번ZZZ") == NO_EVIDENCE
    assert uc.get_section("missing", "3. 원인") == NO_EVIDENCE
    assert uc.get_page("missing", 9) == NO_EVIDENCE
    assert uc.get_slide("missing", 1) == NO_EVIDENCE
    assert uc.get_table("missing", "t1") == NO_EVIDENCE
    assert uc.list_documents(product="없는제품") == NO_EVIDENCE


def test_search_passages_cites_filename_and_location() -> None:
    chunk = _chunk(text="품번 A-1 누유", path="8D_SUV.docx", section_path="3. 원인")
    uc, store, _tables, encoder = _uc([chunk])
    result = uc.search_passages("A-1", product="SUV", period="2024-01", doc_type="8D")
    assert "8D_SUV.docx" in result
    assert "3. 원인" in result
    assert "누유" in result
    assert encoder.texts == ["A-1"]
    assert store.search_calls
    assert store.search_calls[0][2] >= 50


def test_docx_citation_prefers_section_path_over_page() -> None:
    chunk = _chunk(
        path="report.docx",
        family=DocumentFamily.A,
        section_path="4. 대책",
        page=12,
    )
    citation = format_citation(chunk)
    assert "report.docx" in citation
    assert "4. 대책" in citation
    assert "page=" not in citation


def test_pdf_and_slide_citations_include_page_or_slide() -> None:
    pdf = _chunk(
        path="scan.pdf",
        family=DocumentFamily.B,
        section_path=None,
        page=3,
        parent_id=None,
    )
    slide = _chunk(
        path="monthly.pptx",
        family=DocumentFamily.D,
        section_path="원인분석",
        slide_index=12,
        page=None,
        parent_id=None,
    )
    assert "scan.pdf" in format_citation(pdf)
    assert "page=3" in format_citation(pdf)
    assert "monthly.pptx" in format_citation(slide)
    assert "slide=12" in format_citation(slide)


def test_get_section_returns_parent_not_only_child() -> None:
    child = _chunk(
        chunk_id="child",
        text="짧은 자식",
        section_path="3. 원인 > 3.2 공정",
        parent_id="doc-1:3. 원인",
    )
    sibling = _chunk(
        chunk_id="sib",
        text="형제 본문",
        section_path="3. 원인 > 3.1 설계",
        parent_id="doc-1:3. 원인",
    )
    parent = _chunk(
        chunk_id="parent",
        text="부모 섹션 전체: 근본원인과 대책 맥락",
        section_path="3. 원인",
        parent_id="doc-1:3. 원인",
    )
    uc, _store, _tables, _encoder = _uc([child, sibling, parent])
    result = uc.get_section("doc-1", "3. 원인")
    assert "부모 섹션 전체" in result
    assert "짧은 자식" in result
    assert "claim.docx" in result
    assert "3. 원인" in result
    child_call = uc.get_section("doc-1", "3. 원인 > 3.2 공정")
    assert "부모 섹션 전체" in child_call
    assert "짧은 자식" in child_call
    assert "형제 본문" in child_call


def test_long_tool_output_is_truncated_with_pointer() -> None:
    body = "대책 " + ("가" * 8000)
    chunk = _chunk(text=body, section_path="4. 대책")
    uc, _store, _tables, _encoder = _uc([chunk])
    result = uc.get_section("doc-1", "4. 대책")
    assert "truncated" in result.lower() or "pointer=" in result
    assert len(result) < len(body)


def test_search_passages_does_not_invent_table_numbers() -> None:
    chunk = _chunk(text="누유 현상이 반복된다.", part_no="A-1")
    uc, _store, _tables, _encoder = _uc([chunk])
    result = uc.search_passages("건수 합계")
    assert "42" not in result
    assert "1,234" not in result
    assert result == NO_EVIDENCE or "누유" in result


def test_list_documents_applies_product_period_doc_type_filters() -> None:
    keep = _chunk(path="keep.docx", product="SUV", period="2024-01", doc_type="8D")
    drop = _chunk(
        chunk_id="c2",
        doc_id="doc-2",
        path="other.docx",
        product="SEDAN",
        period="2023-12",
        doc_type="월보",
    )
    uc, _store, _tables, _encoder = _uc([keep, drop])
    result = uc.list_documents(product="SUV", period="2024-01", doc_type="8D")
    assert "keep.docx" in result
    assert "other.docx" not in result


def test_get_page_returns_stored_text_not_vision() -> None:
    page = _chunk(
        path="scan.pdf",
        family=DocumentFamily.B,
        text="페이지에 저장된 OCR 텍스트",
        section_path=None,
        page=2,
        parent_id=None,
    )
    uc, _store, _tables, _encoder = _uc([page])
    result = uc.get_page("doc-1", 2)
    assert "scan.pdf" in result
    assert "page=2" in result
    assert "OCR 텍스트" in result


def test_list_and_get_slide() -> None:
    slide = _chunk(
        path="deck.pptx",
        family=DocumentFamily.D,
        text="[슬라이드 2] 원인분석\n노트: 가스켓",
        section_path="원인분석",
        slide_index=2,
        page=None,
        parent_id=None,
    )
    uc, _store, _tables, _encoder = _uc([slide])
    listed = uc.list_slides("doc-1")
    assert "deck.pptx" in listed
    assert "slide=2" in listed
    got = uc.get_slide("doc-1", 2)
    assert "가스켓" in got
    assert "deck.pptx" in got


def test_get_table_returns_table_chunk_with_citation() -> None:
    table = _chunk(
        chunk_id="tbl-1",
        chunk_type=ChunkType.TABLE,
        text="품번,수량\nA-1,3",
        section_path="3. 원인 > 표",
    )
    uc, _store, _tables, _encoder = _uc([table])
    result = uc.get_table("doc-1", "tbl-1")
    assert "A-1" in result
    assert "claim.docx" in result


def test_list_tables_and_describe_table() -> None:
    tables = FakeTableStore()
    tables.claim_rows.append(
        {
            "source_file": "ledger.xlsx",
            "sheet_name": "원장",
            "report_period": "2024-01",
            "template_family": "ledger",
            "vehicle": "SUV",
            "part_no": "A-1",
            "quantity": 3,
        }
    )
    uc, _chunks, _tables, _encoder = _uc(tables=tables)
    listed = uc.list_tables(product="SUV", period="2024-01", doc_type="ledger")
    assert "claim_event" in listed
    assert "ledger.xlsx" in listed or "원장" in listed
    described = uc.describe_table("claim_event")
    assert "grain" in described.lower() or "원장" in described or "ledger" in described
    assert "한 행" in described or "클레임" in described


def test_query_tables_prefers_filters_and_group_by() -> None:
    tables = FakeTableStore()
    tables.claim_rows.append(
        {
            "source_file": "ledger.xlsx",
            "sheet_name": "원장",
            "report_period": "2024-01",
            "vehicle": "SUV",
            "quantity": 3,
        }
    )
    uc, _chunks, store, _encoder = _uc(tables=tables)
    result = uc.query_tables(
        table="claim_event",
        product="SUV",
        period="2024-01",
        group_by="vehicle",
        limit=10,
    )
    assert "거부" not in result
    assert store.executed
    sql = store.executed[0][0].upper()
    assert "SELECT" in sql
    assert "GROUP BY" in sql
    assert "LIMIT" in sql
    assert "ledger.xlsx" in result or "SUV" in result


def test_pdf_outline_uses_page_when_no_section_path() -> None:
    page = _chunk(
        path="scan.pdf",
        family=DocumentFamily.B,
        text="페이지 본문",
        section_path=None,
        page=3,
        parent_id=None,
    )
    uc, _store, _tables, _encoder = _uc([page])
    result = uc.get_outline("doc-1")
    assert result != NO_EVIDENCE
    assert "scan.pdf" in result
    assert "page=3" in result


def test_ensure_sql_limit_handles_offset_without_double_limit() -> None:
    out = ensure_sql_limit("SELECT * FROM claim_event LIMIT 10 OFFSET 5", 100)
    assert out.upper().count("LIMIT") == 1
    assert "OFFSET 5" in out.upper()
    assert "LIMIT 10 OFFSET 5 LIMIT" not in out.upper()
    comma = ensure_sql_limit("SELECT * FROM claim_event LIMIT 0, 1000000", 100)
    assert comma.upper().count("LIMIT") == 1
    assert "1000000" not in comma


def test_infra_error_is_not_returned_as_no_evidence() -> None:
    class BoomStore(FakeChunkStore):
        def query_chunks(self, *args: object, **kwargs: object) -> list[NarrativeChunk]:
            raise NarrativeIngestError(FailureReason.QUERY_FAILED)

    uc = ServeMcp(BoomStore(), FakeTableStore(), FakeEncoder())
    with pytest.raises(NarrativeIngestError) as exc:
        uc.get_section("doc-1", "3. 원인")
    assert exc.value.reason is FailureReason.QUERY_FAILED


def test_mariadb_query_path_does_not_ensure_schema() -> None:
    from large_files_embedding.infrastructure.mariadb_table_store import (
        MariaDbTableStore,
    )

    src = inspect.getsource(MariaDbTableStore.query_readonly)
    assert "_ensure_schema" not in src
    assert "commit(" not in src


def test_milvus_read_loads_collection() -> None:
    from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore

    search_src = inspect.getsource(MilvusChunkStore.search_hybrid)
    query_src = inspect.getsource(MilvusChunkStore.query_chunks)
    load_src = inspect.getsource(MilvusChunkStore._load_collection)
    assert "_load_collection" in search_src
    assert "_load_collection" in query_src
    assert "load_collection" in load_src
    assert "return []" not in search_src
    assert "return []" not in query_src


def test_chunk_and_table_store_ports_are_extended_for_reads() -> None:
    assert callable(getattr(ChunkStore, "search_hybrid"))
    assert callable(getattr(ChunkStore, "query_chunks"))
    assert callable(getattr(TableStore, "query_readonly"))
    assert callable(getattr(ChunkStore, "upsert"))
    assert callable(getattr(TableStore, "insert_facts"))


def test_mcp_cli_command_exists_without_home_config() -> None:
    from large_files_embedding.presentation.cli import main as cli_main
    from large_files_embedding.presentation.mcp.server import StdioMcpServer

    src = inspect.getsource(cli_main)
    assert "def mcp" in src
    assert "~/.grok/config.toml" not in src
    names = {
        spec.name
        for spec in ServeMcp(
            FakeChunkStore(), FakeTableStore(), FakeEncoder()
        ).tool_specs()
    }
    assert names == set(MCP_TOOL_NAMES)
    assert inspect.isclass(StdioMcpServer)
    module = inspect.getmodule(StdioMcpServer)
    assert module is not None
    server_src = inspect.getsource(module)
    assert "ingest(" not in server_src
    assert MARKET_QUALITY_COLLECTION
    assert ALLOWED_FACT_TABLES == frozenset({"claim_event", "monthly_quality_kpi"})
