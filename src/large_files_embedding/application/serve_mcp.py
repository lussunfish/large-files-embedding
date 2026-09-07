"""MCP query-only use case over ChunkStore, TableStore, and Layer1Store."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from large_files_embedding.domain.document import (
    ALLOWED_FACT_TABLES,
    FACT_TABLE_CATALOG,
    FORBIDDEN_MCP_TOOLS,
    MARKET_QUALITY_COLLECTION,
    MCP_QUERY_LIMIT,
    MCP_QUERY_LIMIT_MAX,
    MCP_SEARCH_CANDIDATES,
    MCP_SEARCH_TOP_K,
    MCP_TOOL_SPECS,
    NO_EVIDENCE,
    ChunkStore,
    ChunkType,
    DocumentFamily,
    EmbeddingEncoder,
    FailureReason,
    Layer1Store,
    McpQueryError,
    McpToolSpec,
    PassageHit,
    QueryFilters,
    TableStore,
    TabularIngestError,
    clip_tool_text,
    ensure_sql_limit,
    format_citation,
    format_table_citation,
    parent_section_path,
    require_collection,
    require_fact_table,
    require_layer1_doc_id,
    require_readonly_layer1_sql,
    require_readonly_sql,
    require_sql_ident,
)


class ServeMcp:
    def __init__(
        self,
        chunks: ChunkStore,
        tables: TableStore,
        encoder: EmbeddingEncoder,
        layer1: Layer1Store | None = None,
        *,
        collection: str = MARKET_QUALITY_COLLECTION,
    ) -> None:
        self._chunks = chunks
        self._tables = tables
        self._encoder = encoder
        self._layer1 = layer1
        self._collection = require_collection(collection)

    def tool_specs(self) -> tuple[McpToolSpec, ...]:
        return MCP_TOOL_SPECS

    def execute(self, tool: str, arguments: Mapping[str, object] | None = None) -> str:
        if tool in FORBIDDEN_MCP_TOOLS or tool not in {
            spec.name for spec in MCP_TOOL_SPECS
        }:
            raise McpQueryError(FailureReason.UNKNOWN_MCP_TOOL, tool)
        args = dict(arguments or {})
        if tool == "list_documents":
            return self.list_documents(
                product=_opt_str(args.get("product")),
                period=_opt_str(args.get("period")),
                doc_type=_opt_str(args.get("doc_type")),
            )
        if tool == "search_passages":
            return self.search_passages(
                str(args.get("query") or ""),
                product=_opt_str(args.get("product")),
                period=_opt_str(args.get("period")),
                doc_type=_opt_str(args.get("doc_type")),
            )
        if tool == "get_outline":
            return self.get_outline(str(args.get("doc_id") or ""))
        if tool == "get_section":
            return self.get_section(
                str(args.get("doc_id") or ""),
                str(args.get("heading_path") or ""),
            )
        if tool == "get_table":
            return self.get_table(
                str(args.get("doc_id") or ""),
                str(args.get("table_id") or ""),
            )
        if tool == "get_page":
            return self.get_page(
                str(args.get("doc_id") or ""), _opt_int(args.get("page")) or 0
            )
        if tool == "list_slides":
            return self.list_slides(str(args.get("doc_id") or ""))
        if tool == "get_slide":
            return self.get_slide(
                str(args.get("doc_id") or ""),
                _opt_int(args.get("slide_index")) or 0,
            )
        if tool == "list_tables":
            return self.list_tables(
                product=_opt_str(args.get("product")),
                period=_opt_str(args.get("period")),
                doc_type=_opt_str(args.get("doc_type")),
            )
        if tool == "describe_table":
            return self.describe_table(str(args.get("name") or ""))
        if tool == "list_layer1":
            return self.list_layer1()
        if tool == "describe_profile":
            return self.describe_profile(str(args.get("doc_id") or ""))
        if tool == "query_layer1":
            return self.query_layer1(
                str(args.get("doc_id") or ""),
                sheet=_opt_str(args.get("sheet")),
                sql=_opt_str(args.get("sql")),
                columns=_opt_str(args.get("columns")),
                group_by=_opt_str(args.get("group_by")),
                limit=_opt_int(args.get("limit")),
            )
        return self.query_tables(
            sql=_opt_str(args.get("sql")),
            table=_opt_str(args.get("table")),
            product=_opt_str(args.get("product")),
            period=_opt_str(args.get("period")),
            doc_type=_opt_str(args.get("doc_type")),
            group_by=_opt_str(args.get("group_by")),
            limit=_opt_int(args.get("limit")),
        )

    def list_documents(
        self,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        chunks = self._chunks.query_chunks(
            self._collection,
            filters=QueryFilters(product=product, period=period, doc_type=doc_type),
        )
        seen: dict[str, object] = {}
        lines: list[str] = []
        for chunk in chunks:
            if chunk.doc_id in seen:
                continue
            seen[chunk.doc_id] = chunk
            lines.append(
                f"{format_citation(chunk)} doc_id={chunk.doc_id} "
                f"product={chunk.product or ''} period={chunk.period or ''} "
                f"doc_type={chunk.doc_type or ''}"
            )
        if not lines:
            return NO_EVIDENCE
        return clip_tool_text("\n".join(lines), pointer="list_documents")

    def search_passages(
        self,
        query: str,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        needle = query.strip()
        if not needle:
            return NO_EVIDENCE
        encoded = self._encoder.encode([needle])
        hits = self._chunks.search_hybrid(
            self._collection,
            dense=encoded[0].dense,
            query_text=needle,
            filters=QueryFilters(product=product, period=period, doc_type=doc_type),
            limit=MCP_SEARCH_CANDIDATES,
        )
        ranked = _rerank(hits, needle, MCP_SEARCH_TOP_K)
        if not ranked:
            return NO_EVIDENCE
        blocks: list[str] = []
        for hit in ranked:
            root = parent_section_path(hit.chunk.section_path)
            pointer = f"get_section:{hit.chunk.doc_id}:{root}"
            body = clip_tool_text(hit.chunk.text, pointer=pointer)
            blocks.append(f"{format_citation(hit.chunk)}\n{body}")
        return clip_tool_text("\n\n".join(blocks), pointer="search_passages")

    def get_outline(self, doc_id: str) -> str:
        chunks = self._chunks.query_chunks(self._collection, doc_id=doc_id)
        if not chunks:
            return NO_EVIDENCE
        filename = Path(chunks[0].path).name
        seen: set[str] = set()
        lines = [filename]
        for chunk in chunks:
            label = chunk.section_path
            if not label and chunk.slide_index is not None:
                label = f"slide={chunk.slide_index}"
            if not label and chunk.page is not None:
                label = f"page={chunk.page}"
            if not label or label in seen:
                continue
            seen.add(label)
            lines.append(f"- {label}")
        if len(lines) == 1:
            return NO_EVIDENCE
        return clip_tool_text("\n".join(lines), pointer=f"get_outline:{doc_id}")

    def get_section(self, doc_id: str, heading_path: str) -> str:
        root = parent_section_path(heading_path)
        if not root:
            return NO_EVIDENCE
        chunks = self._chunks.query_chunks(
            self._collection, doc_id=doc_id, heading_path=root
        )
        if not chunks:
            return NO_EVIDENCE
        blocks = [f"{format_citation(chunk)}\n{chunk.text}" for chunk in chunks]
        return clip_tool_text(
            "\n\n".join(blocks),
            pointer=f"get_section:{doc_id}:{root}",
        )

    def get_table(self, doc_id: str, table_id: str) -> str:
        chunks = self._chunks.query_chunks(
            self._collection,
            doc_id=doc_id,
            chunk_id=table_id,
            chunk_type=ChunkType.TABLE,
        )
        if not chunks:
            return NO_EVIDENCE
        chunk = chunks[0]
        return clip_tool_text(
            f"{format_citation(chunk)}\n{chunk.text}",
            pointer=f"get_table:{doc_id}:{table_id}",
        )

    def get_page(self, doc_id: str, page: int) -> str:
        chunks = self._chunks.query_chunks(
            self._collection, doc_id=doc_id, page=int(page)
        )
        if not chunks:
            return NO_EVIDENCE
        blocks = [f"{format_citation(chunk)}\n{chunk.text}" for chunk in chunks]
        return clip_tool_text("\n\n".join(blocks), pointer=f"get_page:{doc_id}:{page}")

    def list_slides(self, doc_id: str) -> str:
        chunks = self._chunks.query_chunks(
            self._collection, doc_id=doc_id, family=DocumentFamily.D
        )
        if not chunks:
            return NO_EVIDENCE
        seen: set[int] = set()
        lines: list[str] = []
        for chunk in chunks:
            if chunk.slide_index is None or chunk.slide_index in seen:
                continue
            seen.add(chunk.slide_index)
            title = chunk.section_path or ""
            lines.append(f"{format_citation(chunk)} {title}".rstrip())
        return (
            clip_tool_text("\n".join(lines), pointer=f"list_slides:{doc_id}")
            if lines
            else NO_EVIDENCE
        )

    def get_slide(self, doc_id: str, slide_index: int) -> str:
        chunks = self._chunks.query_chunks(
            self._collection,
            doc_id=doc_id,
            slide_index=int(slide_index),
            family=DocumentFamily.D,
        )
        if not chunks:
            return NO_EVIDENCE
        blocks = [f"{format_citation(chunk)}\n{chunk.text}" for chunk in chunks]
        return clip_tool_text(
            "\n\n".join(blocks),
            pointer=f"get_slide:{doc_id}:{slide_index}",
        )

    def list_tables(
        self,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
    ) -> str:
        lines: list[str] = []
        filtered = bool(product or period or doc_type)
        for name, entry in FACT_TABLE_CATALOG.items():
            sql, params = structured_table_sql(
                name,
                product=product,
                period=period,
                doc_type=doc_type,
                group_by=None,
                limit=20,
            )
            try:
                rows = self._tables.query_readonly(sql, params)
            except (McpQueryError, TabularIngestError):
                rows = []
            if filtered and not rows:
                continue
            cites = " ".join(format_table_citation(row) for row in rows[:3])
            extra = f" {cites}" if cites else ""
            lines.append(
                f"{name} grain={entry.grain.value} 한 행={entry.one_row_meaning}{extra}"
            )
        if not lines:
            return NO_EVIDENCE
        return clip_tool_text("\n".join(lines), pointer="list_tables")

    def describe_table(self, name: str) -> str:
        entry = FACT_TABLE_CATALOG.get(name)
        if entry is None:
            return NO_EVIDENCE
        return (
            f"{entry.name} grain={entry.grain.value} units={entry.units} "
            f"한 행={entry.one_row_meaning} columns={','.join(entry.columns)}"
        )

    def query_tables(
        self,
        sql: str | None = None,
        table: str | None = None,
        product: str | None = None,
        period: str | None = None,
        doc_type: str | None = None,
        group_by: str | None = None,
        limit: int | None = None,
    ) -> str:
        cap = limit if limit is not None else 100
        try:
            if sql:
                validated = require_readonly_sql(sql)
                limited = ensure_sql_limit(validated, cap)
                rows = self._tables.query_readonly(limited)
            else:
                if not table:
                    return NO_EVIDENCE
                require_fact_table(table)
                built, params = structured_table_sql(
                    table,
                    product=product,
                    period=period,
                    doc_type=doc_type,
                    group_by=group_by,
                    limit=cap,
                )
                require_readonly_sql(built)
                rows = self._tables.query_readonly(built, params)
        except (McpQueryError, TabularIngestError) as exc:
            return f"거부: {exc.reason.value}"
        if not rows:
            return NO_EVIDENCE
        return clip_tool_text(_format_rows(rows), pointer="query_tables")

    def list_layer1(self) -> str:
        if self._layer1 is None:
            return NO_EVIDENCE
        lines: list[str] = []
        for item in self._layer1.list_profiles():
            if item.n_cols < 2:
                continue
            lines.append(
                f"doc_id={item.doc_id} source_file={item.source_file} "
                f"sheet={item.sheet_name} n_rows={item.n_rows} n_cols={item.n_cols}"
            )
        if not lines:
            return NO_EVIDENCE
        return clip_tool_text("\n".join(lines), pointer="list_layer1")

    def describe_profile(self, doc_id: str) -> str:
        if self._layer1 is None:
            return NO_EVIDENCE
        try:
            key = require_layer1_doc_id(doc_id)
        except McpQueryError:
            return NO_EVIDENCE
        raw = self._layer1.get_profile_bytes(key)
        if not raw:
            return NO_EVIDENCE
        text = raw.decode("utf-8", errors="replace")
        return clip_tool_text(text, pointer=f"describe_profile:{key}")

    def query_layer1(
        self,
        doc_id: str,
        sheet: str | None = None,
        sql: str | None = None,
        columns: str | None = None,
        group_by: str | None = None,
        limit: int | None = None,
    ) -> str:
        if self._layer1 is None:
            return NO_EVIDENCE
        try:
            key = require_layer1_doc_id(doc_id)
        except McpQueryError as exc:
            return f"거부: {exc.reason.value}"
        cap = (
            MCP_QUERY_LIMIT
            if limit is None
            else max(1, min(int(limit), MCP_QUERY_LIMIT_MAX))
        )
        raw = self._layer1.get_profile_bytes(key)
        if not raw:
            return NO_EVIDENCE
        source_file, queryable = _layer1_queryable_sheets(raw)
        if sheet:
            if sheet not in queryable:
                return NO_EVIDENCE
            resolved_sheet = sheet
        elif len(queryable) == 1:
            resolved_sheet = queryable[0]
        elif not queryable:
            return NO_EVIDENCE
        else:
            resolved_sheet = None
        structured = bool(columns or group_by)
        bound_sql = None if structured else sql
        if bound_sql:
            allowed = list(queryable)
            if resolved_sheet:
                allowed.insert(0, resolved_sheet)
            allowed.append("layer1")
            try:
                require_readonly_layer1_sql(
                    bound_sql, allowed_tables=allowed, doc_id=key
                )
            except McpQueryError as exc:
                return f"거부: {exc.reason.value}"
        try:
            rows = self._layer1.query_parquet(
                key,
                sheet=resolved_sheet,
                sql=bound_sql,
                columns=columns if structured else None,
                group_by=group_by if structured else None,
                limit=cap,
            )
        except (McpQueryError, TabularIngestError) as exc:
            return f"거부: {exc.reason.value}"
        if not rows:
            return NO_EVIDENCE
        cited = [
            _with_layer1_citation(
                row, source_file=source_file, sheet_name=resolved_sheet or ""
            )
            for row in rows
        ]
        return clip_tool_text(_format_rows(cited), pointer="query_layer1")


def _layer1_queryable_sheets(raw: bytes) -> tuple[str, list[str]]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", []
    if not isinstance(payload, dict):
        return "", []
    source_file = str(payload.get("source_file") or "")
    sheets = payload.get("sheets")
    if not isinstance(sheets, list):
        return source_file, []
    names: list[str] = []
    for item in sheets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name or _as_profile_int(item.get("n_cols")) < 2:
            continue
        names.append(name)
    return source_file, names


def _as_profile_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _with_layer1_citation(
    row: Mapping[str, object], *, source_file: str, sheet_name: str
) -> dict[str, object]:
    merged = dict(row)
    if source_file:
        merged.setdefault("source_file", source_file)
    if sheet_name:
        merged.setdefault("sheet_name", sheet_name)
    return merged


def structured_table_sql(
    table: str,
    *,
    product: str | None,
    period: str | None,
    doc_type: str | None,
    group_by: str | None,
    limit: int,
) -> tuple[str, list[object]]:
    name = require_fact_table(table)
    if name not in ALLOWED_FACT_TABLES:
        raise McpQueryError(FailureReason.SQL_NOT_ALLOWED, table)
    where: list[str] = []
    params: list[object] = []
    if period:
        where.append("`report_period` = %s")
        params.append(period)
    if product:
        where.append("`vehicle` = %s")
        params.append(product)
    if doc_type:
        where.append("`template_family` = %s")
        params.append(doc_type)
    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    capped = max(1, min(int(limit), 500))
    if group_by:
        col = require_sql_ident(group_by)
        metric = "quantity" if name == "claim_event" else "claim_count"
        extra = ""
        if name == "monthly_quality_kpi":
            extra = ", SUM(`ppm`) AS ppm"
        sql = (
            f"SELECT `{col}` AS `{col}`, COUNT(*) AS n, "
            f"SUM(`{metric}`) AS `{metric}`{extra} "
            f"FROM `{name}`{where_sql} GROUP BY `{col}` LIMIT {capped}"
        )
        return sql, params
    sql = f"SELECT * FROM `{name}`{where_sql} LIMIT {capped}"
    return sql, params


def _format_rows(rows: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []
    for row in rows:
        citation = format_table_citation(row)
        body = " ".join(f"{key}={row[key]}" for key in row)
        lines.append(f"{citation} {body}".strip())
    return "\n".join(lines)


def _rerank(hits: Sequence[PassageHit], query: str, top_k: int) -> list[PassageHit]:
    tokens = set(_tokens(query))
    scored: list[PassageHit] = []
    for hit in hits:
        overlap = len(tokens & set(_tokens(hit.chunk.text)))
        scored.append(PassageHit(chunk=hit.chunk, score=hit.score + overlap))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def _tokens(text: str) -> list[str]:
    return [part for part in text.lower().replace(",", " ").split() if part]


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
