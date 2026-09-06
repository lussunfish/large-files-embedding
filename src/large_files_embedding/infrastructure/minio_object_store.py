"""MinIO adapter for original files and Docling JSON."""

from __future__ import annotations

import io
import os
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio

from large_files_embedding.domain.document import (
    FailureReason,
    NarrativeIngestError,
    require_bucket,
)


class MinioObjectStore:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = require_bucket(bucket)
        self._client: Minio | None = None

    @classmethod
    def from_env(cls) -> MinioObjectStore:
        extras = _stable_minio_env()
        endpoint = os.environ.get("MINIO_ENDPOINT") or extras.get(
            "MINIO_ENDPOINT", "http://127.0.0.1:9000"
        )
        access_key = (
            os.environ.get("MINIO_ACCESS_KEY")
            or os.environ.get("MINIO_ROOT_USER")
            or extras.get("MINIO_ACCESS_KEY")
            or extras.get("MINIO_ROOT_USER")
            or "minioadmin"
        )
        secret_key = (
            os.environ.get("MINIO_SECRET_KEY")
            or os.environ.get("MINIO_ROOT_PASSWORD")
            or extras.get("MINIO_SECRET_KEY")
            or extras.get("MINIO_ROOT_PASSWORD")
            or "minioadmin"
        )
        bucket = os.environ.get("MINIO_BUCKET", "market-quality-docs")
        return cls(endpoint, access_key, secret_key, bucket)

    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        client = self._client_or_connect()
        try:
            client.put_object(
                self._bucket,
                key,
                io.BytesIO(body),
                length=len(body),
                content_type=content_type,
            )
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED) from exc

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        client = self._client_or_connect()
        try:
            client.fput_object(
                self._bucket,
                key,
                str(path),
                content_type=content_type,
            )
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED) from exc

    def _client_or_connect(self) -> Minio:
        if self._client is None:
            parsed = urlparse(
                self._endpoint
                if "://" in self._endpoint
                else f"http://{self._endpoint}"
            )
            host = parsed.netloc or parsed.path
            self._client = Minio(
                host,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=parsed.scheme == "https",
            )
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        return self._client


_STABLE_MINIO_KEYS = frozenset(
    {
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    }
)


def _stable_minio_env() -> dict[str, str]:
    path = Path.home() / "dev" / "00.workspace" / "01-stable" / "local-minio" / ".env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if key not in _STABLE_MINIO_KEYS:
            continue
        values[key] = raw.strip().strip("'").strip('"')
    return values
