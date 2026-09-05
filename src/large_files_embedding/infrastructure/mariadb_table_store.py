"""MariaDB adapter for curated fact tables (claim_event, monthly_quality_kpi)."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymysql

from large_files_embedding.domain.document import (
    DEFAULT_MARIADB_DATABASE,
    DEFAULT_MARIADB_HOST,
    DEFAULT_MARIADB_PORT,
    FailureReason,
    Grain,
    TabularIngestError,
    require_fact_table,
    require_snapshot_period,
)

_CLAIM_COLUMNS = (
    "source_file",
    "sheet_name",
    "report_period",
    "ingested_at",
    "template_family",
    "part_no",
    "vehicle",
    "event_date",
    "cause",
    "countermeasure",
    "quantity",
)
_KPI_COLUMNS = (
    "source_file",
    "sheet_name",
    "report_period",
    "ingested_at",
    "template_family",
    "vehicle",
    "claim_count",
    "ppm",
)
_CLAIM_DDL = """
CREATE TABLE IF NOT EXISTS claim_event (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_file VARCHAR(512) NOT NULL,
  sheet_name VARCHAR(255) NOT NULL,
  report_period VARCHAR(32) NULL,
  ingested_at DATETIME NOT NULL,
  template_family VARCHAR(64) NOT NULL,
  part_no VARCHAR(128) NULL,
  vehicle VARCHAR(128) NULL,
  event_date DATE NULL,
  cause TEXT NULL,
  countermeasure TEXT NULL,
  quantity DOUBLE NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
_KPI_DDL = """
CREATE TABLE IF NOT EXISTS monthly_quality_kpi (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_file VARCHAR(512) NOT NULL,
  sheet_name VARCHAR(255) NOT NULL,
  report_period VARCHAR(32) NOT NULL,
  ingested_at DATETIME NOT NULL,
  template_family VARCHAR(64) NOT NULL,
  vehicle VARCHAR(128) NULL,
  claim_count DOUBLE NULL,
  ppm DOUBLE NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


class MariaDbTableStore:
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._connection: pymysql.connections.Connection[Any] | None = None

    @classmethod
    def from_env(cls) -> MariaDbTableStore:
        extras = _stable_mariadb_env()
        database = os.environ.get("MARIADB_DATABASE", DEFAULT_MARIADB_DATABASE)
        if database != DEFAULT_MARIADB_DATABASE:
            raise TabularIngestError(FailureReason.TABLE_PER_FILE, database)
        return cls(
            host=os.environ.get("MARIADB_HOST", DEFAULT_MARIADB_HOST),
            port=int(os.environ.get("MARIADB_PORT", str(DEFAULT_MARIADB_PORT))),
            database=database,
            user=os.environ.get("MARIADB_USER")
            or extras.get("MARIADB_USER", "embed_user"),
            password=os.environ.get("MARIADB_PASSWORD")
            or extras.get("MARIADB_PASSWORD", ""),
        )

    def insert_facts(
        self,
        table: str,
        rows: Sequence[Mapping[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        require_fact_table(table)
        if grain is Grain.SNAPSHOT:
            require_snapshot_period(report_period)
        if not rows:
            return 0
        columns = _CLAIM_COLUMNS if table == "claim_event" else _KPI_COLUMNS
        payload: list[tuple[object, ...]] = []
        for row in rows:
            values = dict(row)
            if report_period and not values.get("report_period"):
                values["report_period"] = report_period
            if grain is Grain.SNAPSHOT and not values.get("report_period"):
                raise TabularIngestError(FailureReason.SNAPSHOT_UNION)
            payload.append(tuple(_sql_value(values.get(column)) for column in columns))
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            placeholders = ", ".join(["%s"] * len(columns))
            col_sql = ", ".join(f"`{column}`" for column in columns)
            sql = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
            with connection.cursor() as cursor:
                cursor.executemany(sql, payload)
            connection.commit()
        except TabularIngestError:
            raise
        except Exception as exc:
            raise TabularIngestError(FailureReason.EXTRACT_FAILED) from exc
        return len(payload)

    def ensure_schema(self) -> None:
        self._ensure_schema(self._connect())

    def _connect(self) -> pymysql.connections.Connection[Any]:
        if self._connection is not None:
            try:
                self._connection.ping()
                return self._connection
            except Exception:
                self._connection = None
        try:
            self._connection = self._open(self._database)
        except pymysql.err.OperationalError as exc:
            raise TabularIngestError(FailureReason.EXTRACT_FAILED) from exc
        return self._connection

    def _open(self, database: str) -> pymysql.connections.Connection[Any]:
        return pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=database,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=5,
        )

    def _ensure_schema(self, connection: pymysql.connections.Connection[Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(_CLAIM_DDL)
            cursor.execute(_KPI_DDL)
        connection.commit()


def _stable_mariadb_env() -> dict[str, str]:
    path = Path.home() / "dev" / "00.workspace" / "01-stable" / "local-mariadb" / ".env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if key not in {"MARIADB_USER", "MARIADB_PASSWORD"}:
            continue
        values[key] = raw.strip().strip("'").strip('"')
    return values


def _sql_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return value
    if isinstance(value, str) and "T" in value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None)
        except ValueError:
            return value
    return value
