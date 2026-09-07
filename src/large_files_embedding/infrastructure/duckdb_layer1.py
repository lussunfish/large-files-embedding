"""DuckDB adapter that scans MinIO layer-1 parquet without loading workbooks."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

import duckdb

from large_files_embedding.domain.document import (
    FailureReason,
    Layer1SheetListing,
    McpQueryError,
    ObjectStore,
    ensure_sql_limit,
    layer1_parquet_key,
    layer1_parquet_prefix,
    layer1_profile_key,
    quote_sql_ident,
    require_layer1_doc_id,
    require_layer1_ident,
    require_readonly_layer1_sql,
)

_PROFILE_SUFFIX = "/profile.json"


class DuckDbLayer1Store:
    def __init__(self, objects: ObjectStore) -> None:
        self._objects = objects

    def list_profiles(self) -> list[Layer1SheetListing]:
        listings: list[Layer1SheetListing] = []
        for key in self._objects.list_prefix(""):
            if not key.endswith(_PROFILE_SUFFIX):
                continue
            doc_id = key[: -len(_PROFILE_SUFFIX)]
            try:
                require_layer1_doc_id(doc_id)
            except McpQueryError:
                continue
            raw = self._objects.get_bytes(key)
            if not raw:
                continue
            listings.extend(_listings_from_profile(doc_id, raw))
        return listings

    def get_profile_bytes(self, doc_id: str) -> bytes | None:
        return self._objects.get_bytes(layer1_profile_key(doc_id))

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
        key = require_layer1_doc_id(doc_id)
        parquet_key, sheet_name = self._resolve_parquet(key, sheet)
        if parquet_key is None or sheet_name is None:
            return []
        cap = max(1, min(int(limit), 500))
        allowed = [sheet_name, "layer1"]
        if sql:
            require_readonly_layer1_sql(sql, allowed_tables=allowed, doc_id=key)
        handle, tmp = tempfile.mkstemp(prefix="layer1-scan-", suffix=".parquet")
        os.close(handle)
        tmp_path = Path(tmp)
        try:
            if not self._objects.download_to(parquet_key, tmp_path):
                return []
            if tmp_path.stat().st_size == 0:
                return []
            return _scan_parquet(
                str(tmp_path),
                sheet_name=sheet_name,
                sql=sql,
                columns=columns,
                group_by=group_by,
                limit=cap,
                allowed_tables=allowed,
                doc_id=key,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def _resolve_parquet(
        self, doc_id: str, sheet: str | None
    ) -> tuple[str | None, str | None]:
        if sheet:
            return layer1_parquet_key(doc_id, sheet), sheet
        prefix = layer1_parquet_prefix(doc_id)
        keys = [
            name
            for name in self._objects.list_prefix(prefix)
            if name.endswith(".parquet")
        ]
        if len(keys) != 1:
            return None, None
        found = keys[0]
        stem = Path(found).stem
        return found, stem


def _listings_from_profile(doc_id: str, raw: bytes) -> list[Layer1SheetListing]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    source_file = str(payload.get("source_file") or "")
    sheets = payload.get("sheets")
    if not isinstance(sheets, list):
        return []
    listings: list[Layer1SheetListing] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        name = str(sheet.get("name") or "")
        if not name:
            continue
        listings.append(
            Layer1SheetListing(
                doc_id=doc_id,
                source_file=source_file,
                sheet_name=name,
                n_rows=_as_int(sheet.get("n_rows")),
                n_cols=_as_int(sheet.get("n_cols")),
            )
        )
    return listings


def _as_int(value: object) -> int:
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


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scan_parquet(
    path: str,
    *,
    sheet_name: str,
    sql: str | None,
    columns: str | None,
    group_by: str | None,
    limit: int,
    allowed_tables: Sequence[str],
    doc_id: str,
) -> list[dict[str, object]]:
    view = quote_sql_ident(sheet_name)
    parquet = _quote_sql_string(path)
    source = f"read_parquet({parquet})"
    built = _layer1_select_sql(
        sheet_name,
        sql=sql,
        columns=columns,
        group_by=group_by,
        limit=limit,
        allowed_tables=allowed_tables,
        doc_id=doc_id,
    )
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE TEMPORARY TABLE layer1 AS SELECT * FROM {source}")
        connection.execute(f"CREATE TEMPORARY VIEW {view} AS SELECT * FROM layer1")
        try:
            connection.execute("SET enable_external_access=false")
            connection.execute("SET lock_configuration=true")
        except Exception as exc:
            raise McpQueryError(FailureReason.QUERY_FAILED) from exc
        result = connection.execute(built)
        description = result.description or []
        names = [str(col[0]) for col in description]
        rows: list[dict[str, object]] = []
        for values in result.fetchall():
            rows.append({names[index]: values[index] for index in range(len(names))})
        return rows
    except McpQueryError:
        raise
    except Exception as exc:
        raise McpQueryError(FailureReason.QUERY_FAILED) from exc
    finally:
        connection.close()


def _layer1_select_sql(
    sheet_name: str,
    *,
    sql: str | None,
    columns: str | None,
    group_by: str | None,
    limit: int,
    allowed_tables: Sequence[str],
    doc_id: str,
) -> str:
    view = quote_sql_ident(sheet_name)
    if columns or group_by:
        return _structured_layer1_sql(
            view, columns=columns, group_by=group_by, limit=limit
        )
    if sql:
        validated = require_readonly_layer1_sql(
            sql, allowed_tables=allowed_tables, doc_id=doc_id
        )
        return ensure_sql_limit(validated, limit)
    return f"SELECT * FROM {view} LIMIT {limit}"


def _structured_layer1_sql(
    view: str,
    *,
    columns: str | None,
    group_by: str | None,
    limit: int,
) -> str:
    if group_by:
        col = quote_sql_ident(require_layer1_ident(group_by))
        extra = ""
        if columns:
            selected = [
                quote_sql_ident(require_layer1_ident(part))
                for part in columns.split(",")
                if part.strip()
            ]
            extras = [item for item in selected if item != col]
            if extras:
                extra = ", " + ", ".join(extras)
        return (
            f"SELECT {col} AS {col}{extra}, COUNT(*) AS n "
            f"FROM {view} GROUP BY {col} LIMIT {limit}"
        )
    if columns:
        selected = [
            quote_sql_ident(require_layer1_ident(part))
            for part in columns.split(",")
            if part.strip()
        ]
        if not selected:
            return f"SELECT * FROM {view} LIMIT {limit}"
        return f"SELECT {', '.join(selected)} FROM {view} LIMIT {limit}"
    return f"SELECT * FROM {view} LIMIT {limit}"
