"""Stdio MCP adapter. Query-only; no ingest or delete tools."""

from __future__ import annotations

from collections.abc import Callable

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import MCP_TOOL_SPECS, McpToolSpec
from large_files_embedding.infrastructure.duckdb_layer1 import DuckDbLayer1Store
from large_files_embedding.infrastructure.embedding_encoder import DenseSparseEncoder
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore


class StdioMcpServer:
    def __init__(self, use_case: ServeMcp) -> None:
        self._use_case = use_case

    def serve_stdio(self) -> None:
        server = _build_server(self._use_case)
        runner = getattr(server, "run")
        try:
            runner(transport="stdio")
        except TypeError:
            runner()


def run_stdio() -> None:
    use_case = ServeMcp(
        MilvusChunkStore.from_env(),
        MariaDbTableStore.from_env(),
        DenseSparseEncoder.from_env(),
        DuckDbLayer1Store(MinioObjectStore.from_env()),
    )
    StdioMcpServer(use_case).serve_stdio()


def _build_server(use_case: ServeMcp) -> object:
    server = _mcp_ctor()("market-quality")
    handlers = _tool_handlers(use_case)
    specs = {spec.name: spec for spec in MCP_TOOL_SPECS}
    for name, fn in handlers.items():
        _add_tool(server, specs[name], fn)
    return server


def _mcp_ctor() -> Callable[..., object]:
    try:
        from mcp.server import MCPServer

        return MCPServer
    except ImportError:
        module = __import__("mcp.server.fastmcp", fromlist=["FastMCP"])
        return getattr(module, "FastMCP")


def _add_tool(server: object, spec: McpToolSpec, fn: Callable[..., str]) -> None:
    add_tool = getattr(server, "add_tool", None)
    if callable(add_tool):
        try:
            add_tool(fn, name=spec.name, description=spec.description)
            return
        except TypeError:
            add_tool(fn)
            return
    decorator = getattr(server, "tool")
    try:
        decorator(name=spec.name, description=spec.description)(fn)
    except TypeError:
        decorator()(fn)


def _tool_handlers(use_case: ServeMcp) -> dict[str, Callable[..., str]]:
    def list_documents(
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        """문서 목록. 팩트 숫자→query_tables, 1층 숫자→query_layer1."""
        return use_case.list_documents(
            product=product, period=period, doc_type=doc_type
        )

    def search_passages(
        query: str,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        """모호한 검색·품번/코드. 숫자는 query_tables 또는 query_layer1."""
        return use_case.search_passages(
            query, product=product, period=period, doc_type=doc_type
        )

    def get_outline(doc_id: str) -> str:
        """문서 목차. 원인/대책은 get_section."""
        return use_case.get_outline(doc_id)

    def get_section(doc_id: str, heading_path: str) -> str:
        """원인/대책 등 parent 섹션. DOCX는 파일명+섹션 경로로 인용."""
        return use_case.get_section(doc_id, heading_path)

    def get_table(doc_id: str, table_id: str) -> str:
        """문서 안 표 청크. 집계는 query_tables 또는 query_layer1."""
        return use_case.get_table(doc_id, table_id)

    def get_page(doc_id: str, page: int) -> str:
        """PDF 저장된 페이지 텍스트. ColQwen 아님."""
        return use_case.get_page(doc_id, page)

    def list_slides(doc_id: str) -> str:
        """PPTX 슬라이드 목록."""
        return use_case.list_slides(doc_id)

    def get_slide(doc_id: str, slide_index: int) -> str:
        """PPTX 슬라이드 본문+노트."""
        return use_case.get_slide(doc_id, slide_index)

    def list_tables(
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        """MariaDB 팩트 표 목록. 숫자는 query_tables. 1층은 describe_profile."""
        return use_case.list_tables(product=product, period=period, doc_type=doc_type)

    def describe_table(name: str) -> str:
        """표 grain·단위·한 행의 의미."""
        return use_case.describe_table(name)

    def query_tables(
        sql: str | None = None,
        table: str | None = None,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
        group_by: str | None = None,
        limit: int | None = None,
    ) -> str:
        """숫자 집계 TAG. 읽기 전용. DROP/DELETE/INSERT/UPDATE 거부."""
        return use_case.query_tables(
            sql=sql,
            table=table,
            product=product,
            period=period,
            doc_type=doc_type,
            group_by=group_by,
            limit=limit,
        )

    def list_layer1() -> str:
        """MinIO 1층 프로필 목록. 1층 숫자는 describe_profile 후 query_layer1."""
        return use_case.list_layer1()

    def describe_profile(doc_id: str) -> str:
        """1층 profile.json만. Parquet 본문을 붙이지 않음."""
        return use_case.describe_profile(doc_id)

    def query_layer1(
        doc_id: str,
        sheet: str | None = None,
        sql: str | None = None,
        columns: str | None = None,
        group_by: str | None = None,
        limit: int | None = None,
    ) -> str:
        """1층 Parquet 조회. 읽기 전용. DROP/CREATE/COPY/ATTACH 거부."""
        return use_case.query_layer1(
            doc_id,
            sheet=sheet,
            sql=sql,
            columns=columns,
            group_by=group_by,
            limit=limit,
        )

    return {
        "list_documents": list_documents,
        "search_passages": search_passages,
        "get_outline": get_outline,
        "get_section": get_section,
        "get_table": get_table,
        "get_page": get_page,
        "list_slides": list_slides,
        "get_slide": get_slide,
        "list_tables": list_tables,
        "describe_table": describe_table,
        "query_tables": query_tables,
        "list_layer1": list_layer1,
        "describe_profile": describe_profile,
        "query_layer1": query_layer1,
    }
