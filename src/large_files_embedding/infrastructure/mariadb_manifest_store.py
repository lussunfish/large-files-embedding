"""MariaDB adapter for content-hash ingest skip ledger (ingest_manifest)."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from large_files_embedding.domain.document import (
    DEFAULT_MARIADB_DATABASE,
    DEFAULT_MARIADB_HOST,
    DEFAULT_MARIADB_PORT,
    DocumentFamily,
    DocumentFormat,
    FailureReason,
    IngestFingerprint,
    ManifestRecord,
    ManifestStoreError,
)

_DDL = """
CREATE TABLE IF NOT EXISTS ingest_manifest (
  content_sha256 CHAR(64) NOT NULL,
  encoder_model VARCHAR(128) NOT NULL,
  pipeline_version VARCHAR(64) NOT NULL,
  family CHAR(1) NOT NULL,
  detected_format VARCHAR(16) NOT NULL,
  byte_size BIGINT NOT NULL,
  status VARCHAR(16) NOT NULL,
  chunk_count INT NOT NULL,
  ingested_at DATETIME NOT NULL,
  PRIMARY KEY (content_sha256, encoder_model, pipeline_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
_SELECT = """
SELECT content_sha256, encoder_model, pipeline_version, family, detected_format,
       byte_size, status, chunk_count, ingested_at
FROM ingest_manifest
WHERE content_sha256=%s AND encoder_model=%s AND pipeline_version=%s
"""
_UPSERT = """
INSERT INTO ingest_manifest (
  content_sha256, encoder_model, pipeline_version, family, detected_format,
  byte_size, status, chunk_count, ingested_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  family=VALUES(family),
  detected_format=VALUES(detected_format),
  byte_size=VALUES(byte_size),
  status=VALUES(status),
  chunk_count=VALUES(chunk_count),
  ingested_at=VALUES(ingested_at)
"""


class MariaDbManifestStore:
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
    def from_env(cls) -> MariaDbManifestStore:
        extras = _stable_mariadb_env()
        database = os.environ.get("MARIADB_DATABASE", DEFAULT_MARIADB_DATABASE)
        if database != DEFAULT_MARIADB_DATABASE:
            raise ManifestStoreError(FailureReason.MANIFEST_LOOKUP_FAILED, database)
        return cls(
            host=os.environ.get("MARIADB_HOST", DEFAULT_MARIADB_HOST),
            port=int(os.environ.get("MARIADB_PORT", str(DEFAULT_MARIADB_PORT))),
            database=database,
            user=os.environ.get("MARIADB_USER")
            or extras.get("MARIADB_USER", "embed_user"),
            password=os.environ.get("MARIADB_PASSWORD")
            or extras.get("MARIADB_PASSWORD", ""),
        )

    def find(self, fingerprint: IngestFingerprint) -> ManifestRecord | None:
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    _SELECT,
                    (
                        fingerprint.content_sha256,
                        fingerprint.encoder_model,
                        fingerprint.pipeline_version,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        except ManifestStoreError:
            raise
        except Exception as exc:
            raise ManifestStoreError(FailureReason.MANIFEST_LOOKUP_FAILED) from exc
        if row is None:
            return None
        return _to_record(row)

    def upsert(self, record: ManifestRecord) -> None:
        fingerprint = record.fingerprint
        ingested_at = record.ingested_at
        if ingested_at.tzinfo is not None:
            ingested_at = ingested_at.replace(tzinfo=None)
        try:
            connection = self._connect(FailureReason.MANIFEST_WRITE_FAILED)
            self._ensure_schema(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    _UPSERT,
                    (
                        fingerprint.content_sha256,
                        fingerprint.encoder_model,
                        fingerprint.pipeline_version,
                        record.family.value,
                        record.detected_format.value,
                        record.byte_size,
                        record.status,
                        record.chunk_count,
                        ingested_at,
                    ),
                )
            connection.commit()
        except ManifestStoreError:
            raise
        except Exception as exc:
            raise ManifestStoreError(FailureReason.MANIFEST_WRITE_FAILED) from exc

    def ensure_schema(self) -> None:
        self._ensure_schema(self._connect())

    def _connect(
        self,
        reason: FailureReason = FailureReason.MANIFEST_LOOKUP_FAILED,
    ) -> pymysql.connections.Connection[Any]:
        if self._connection is not None:
            try:
                self._connection.ping()
                return self._connection
            except Exception:
                self._connection = None
        try:
            self._connection = self._open(self._database)
        except pymysql.err.OperationalError as exc:
            raise ManifestStoreError(reason) from exc
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
            cursor.execute(_DDL)
        connection.commit()


def _to_record(row: dict[str, object]) -> ManifestRecord:
    ingested = row["ingested_at"]
    if isinstance(ingested, datetime):
        ingested_at = ingested
    elif isinstance(ingested, date):
        ingested_at = datetime.combine(ingested, datetime.min.time())
    else:
        ingested_at = datetime.fromisoformat(str(ingested))
    return ManifestRecord(
        fingerprint=IngestFingerprint(
            content_sha256=str(row["content_sha256"]),
            encoder_model=str(row["encoder_model"]),
            pipeline_version=str(row["pipeline_version"]),
        ),
        family=DocumentFamily(str(row["family"])),
        detected_format=DocumentFormat(str(row["detected_format"])),
        byte_size=_as_int(row["byte_size"]),
        status=str(row["status"]),
        chunk_count=_as_int(row["chunk_count"]),
        ingested_at=ingested_at,
    )


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return int(str(value))
    return value


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
