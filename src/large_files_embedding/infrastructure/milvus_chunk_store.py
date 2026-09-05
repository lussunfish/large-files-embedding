"""Milvus standalone adapter for hybrid narrative chunks."""

from __future__ import annotations

import os
from collections.abc import Sequence

from pymilvus import DataType, Function, FunctionType, MilvusClient

from large_files_embedding.domain.document import (
    PARENT_ID_MAX_LENGTH,
    SECTION_PATH_MAX_LENGTH,
    FailureReason,
    NarrativeIngestError,
    StoredChunk,
    clip_varchar,
    require_collection,
    require_milvus_uri,
)


class MilvusChunkStore:
    def __init__(self, uri: str, collection: str, dim: int = 2560) -> None:
        self._uri = require_milvus_uri(uri)
        self._collection = require_collection(collection)
        self._dim = dim
        self._client: MilvusClient | None = None

    @classmethod
    def from_env(cls) -> MilvusChunkStore:
        uri = os.environ.get("MILVUS_URI", "http://127.0.0.1:19530")
        collection = os.environ.get("MILVUS_COLLECTION", "market_quality_chunks_hybrid")
        dim = int(os.environ.get("EMBEDDING_DIM", "2560"))
        return cls(uri=uri, collection=collection, dim=dim)

    def upsert(self, collection: str, records: Sequence[StoredChunk]) -> None:
        name = require_collection(collection)
        if name != self._collection:
            raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, name)
        if not records:
            return
        client = self._client_or_connect()
        self._ensure_collection(client)
        parent_id_max = _field_max_length(
            client, self._collection, "parent_id", default=256
        )
        section_max = _field_max_length(
            client, self._collection, "section_path", default=SECTION_PATH_MAX_LENGTH
        )
        rows = [
            _row(
                record,
                dim=self._dim,
                parent_id_max=parent_id_max,
                section_path_max=section_max,
            )
            for record in records
        ]
        try:
            client.upsert(collection_name=self._collection, data=rows)
            client.flush(self._collection)
            client.load_collection(self._collection)
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED) from exc

    def _client_or_connect(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(uri=self._uri)
        return self._client

    def _ensure_collection(self, client: MilvusClient) -> None:
        if client.has_collection(self._collection):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
        schema.add_field("path", DataType.VARCHAR, max_length=1024)
        schema.add_field("family", DataType.VARCHAR, max_length=8)
        schema.add_field("chunk_type", DataType.VARCHAR, max_length=16)
        schema.add_field("section_path", DataType.VARCHAR, max_length=1024)
        schema.add_field("slide_index", DataType.INT64)
        schema.add_field("page", DataType.INT64)
        schema.add_field("product", DataType.VARCHAR, max_length=256)
        schema.add_field("period", DataType.VARCHAR, max_length=64)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=64)
        schema.add_field("vehicle", DataType.VARCHAR, max_length=256)
        schema.add_field("part_no", DataType.VARCHAR, max_length=256)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=PARENT_ID_MAX_LENGTH)
        schema.add_field(
            "text",
            DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
        )
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self._dim)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(
            Function(
                name="text_bm25_emb",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )
        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="dense",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        index_params.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        client.create_collection(
            collection_name=self._collection,
            schema=schema,
            index_params=index_params,
        )
        client.load_collection(self._collection)


def _field_max_length(
    client: MilvusClient, collection: str, field: str, default: int
) -> int:
    try:
        description = client.describe_collection(collection)
        fields = (
            description.get("fields", [])
            if isinstance(description, dict)
            else getattr(description, "fields", []) or []
        )
        for item in fields:
            name = (
                item.get("name")
                if isinstance(item, dict)
                else getattr(item, "name", None)
            )
            if name != field:
                continue
            params = (
                item.get("params")
                if isinstance(item, dict)
                else getattr(item, "params", None)
            ) or {}
            return int(params.get("max_length", default))
    except (TypeError, ValueError, AttributeError, KeyError):
        return default
    return default


def _row(
    record: StoredChunk,
    *,
    dim: int,
    parent_id_max: int,
    section_path_max: int,
) -> dict[str, object]:
    chunk = record.chunk
    dense = list(record.embedding.dense)
    if len(dense) != dim:
        raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
    text = chunk.embedding_input[:65535]
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "path": chunk.path,
        "family": chunk.family.value,
        "chunk_type": chunk.chunk_type.value,
        "section_path": clip_varchar(chunk.section_path, section_path_max),
        "slide_index": chunk.slide_index if chunk.slide_index is not None else -1,
        "page": chunk.page if chunk.page is not None else -1,
        "product": chunk.product or "",
        "period": chunk.period or "",
        "doc_type": chunk.doc_type or "",
        "vehicle": chunk.vehicle or "",
        "part_no": chunk.part_no or "",
        "parent_id": clip_varchar(chunk.parent_id, parent_id_max),
        "text": text,
        "dense": dense,
    }
