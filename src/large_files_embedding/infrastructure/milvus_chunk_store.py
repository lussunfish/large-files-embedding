"""Milvus standalone adapter for hybrid narrative chunks."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from pymilvus import (
    AnnSearchRequest,
    DataType,
    Function,
    FunctionType,
    MilvusClient,
    RRFRanker,
)

from large_files_embedding.domain.document import (
    PARENT_ID_MAX_LENGTH,
    SECTION_PATH_MAX_LENGTH,
    ChunkType,
    DocumentFamily,
    FailureReason,
    NarrativeChunk,
    NarrativeIngestError,
    PassageHit,
    QueryFilters,
    StoredChunk,
    clip_varchar,
    require_collection,
    require_milvus_uri,
)

_UPSERT_BATCH = 64
_OUTPUT_FIELDS = (
    "chunk_id",
    "doc_id",
    "path",
    "family",
    "chunk_type",
    "section_path",
    "slide_index",
    "page",
    "product",
    "period",
    "doc_type",
    "vehicle",
    "part_no",
    "parent_id",
    "text",
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
            for start in range(0, len(rows), _UPSERT_BATCH):
                client.upsert(
                    collection_name=self._collection,
                    data=rows[start : start + _UPSERT_BATCH],
                )
            client.flush(self._collection)
            client.load_collection(self._collection)
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED) from exc

    def search_hybrid(
        self,
        collection: str,
        *,
        dense: Sequence[float],
        query_text: str,
        filters: QueryFilters,
        limit: int,
    ) -> list[PassageHit]:
        name = require_collection(collection)
        if name != self._collection:
            raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, name)
        client = self._client_or_connect()
        self._load_collection(client)
        expr = _filter_expr(filters=filters)
        dense_req = AnnSearchRequest(
            data=[list(dense)],
            anns_field="dense",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=expr or None,
        )
        sparse_req = AnnSearchRequest(
            data=[query_text],
            anns_field="sparse",
            param={"metric_type": "BM25"},
            limit=limit,
            expr=expr or None,
        )
        hits: list[object]
        try:
            results = client.hybrid_search(
                collection_name=self._collection,
                reqs=[dense_req, sparse_req],
                ranker=RRFRanker(),
                limit=limit,
                output_fields=list(_OUTPUT_FIELDS),
            )
            hits = results[0] if results else []
        except Exception:
            try:
                results = client.search(
                    collection_name=self._collection,
                    data=[list(dense)],
                    anns_field="dense",
                    limit=limit,
                    filter=expr,
                    output_fields=list(_OUTPUT_FIELDS),
                    search_params={"metric_type": "COSINE", "params": {"ef": 64}},
                )
                hits = results[0] if results else []
            except Exception as exc:
                raise NarrativeIngestError(FailureReason.QUERY_FAILED) from exc
        out: list[PassageHit] = []
        for hit in hits:
            chunk = _mapping_to_chunk(_hit_mapping(hit))
            if chunk is None:
                continue
            score = _hit_score(hit)
            out.append(PassageHit(chunk=chunk, score=score))
        return out

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
        name = require_collection(collection)
        if name != self._collection:
            raise NarrativeIngestError(FailureReason.FORBIDDEN_COLLECTION, name)
        client = self._client_or_connect()
        self._load_collection(client)
        expr = (
            _filter_expr(
                filters=filters,
                doc_id=doc_id,
                chunk_id=chunk_id,
                parent_id=parent_id,
                chunk_type=chunk_type,
                heading_path=heading_path,
                page=page,
                slide_index=slide_index,
                family=family,
            )
            or 'chunk_id != ""'
        )
        try:
            rows = client.query(
                collection_name=self._collection,
                filter=expr,
                output_fields=list(_OUTPUT_FIELDS),
                limit=max(1, min(int(limit), 16384)),
            )
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.QUERY_FAILED) from exc
        chunks: list[NarrativeChunk] = []
        for row in rows:
            chunk = _mapping_to_chunk(row if isinstance(row, Mapping) else {})
            if chunk is not None:
                chunks.append(chunk)
        return chunks

    def _client_or_connect(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(uri=self._uri)
        return self._client

    def _load_collection(self, client: MilvusClient) -> None:
        try:
            exists = client.has_collection(self._collection)
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.QUERY_FAILED) from exc
        if not exists:
            raise NarrativeIngestError(FailureReason.QUERY_FAILED, self._collection)
        try:
            client.load_collection(self._collection)
        except Exception as exc:
            raise NarrativeIngestError(FailureReason.QUERY_FAILED) from exc

    def _ensure_collection(self, client: MilvusClient) -> None:
        if client.has_collection(self._collection):
            client.load_collection(self._collection)
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


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _filter_expr(
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
) -> str:
    parts: list[str] = []
    if filters is not None:
        if filters.product:
            parts.append(f"product == {_quote(filters.product)}")
        if filters.period:
            parts.append(f"period == {_quote(filters.period)}")
        if filters.doc_type:
            parts.append(f"doc_type == {_quote(filters.doc_type)}")
    if doc_id:
        parts.append(f"doc_id == {_quote(doc_id)}")
    if chunk_id:
        parts.append(f"chunk_id == {_quote(chunk_id)}")
    if parent_id:
        parts.append(f"parent_id == {_quote(parent_id)}")
    if chunk_type is not None:
        parts.append(f"chunk_type == {_quote(chunk_type.value)}")
    if family is not None:
        parts.append(f"family == {_quote(family.value)}")
    if heading_path:
        exact = f"section_path == {_quote(heading_path)}"
        prefix = f"section_path like {_quote(heading_path + ' >%')}"
        parts.append(f"({exact} or {prefix})")
    if page is not None:
        parts.append(f"page == {int(page)}")
    if slide_index is not None:
        parts.append(f"slide_index == {int(slide_index)}")
    return " and ".join(parts)


def _hit_mapping(hit: object) -> Mapping[str, object]:
    if isinstance(hit, Mapping):
        entity = hit.get("entity")
        if isinstance(entity, Mapping):
            merged = dict(entity)
            if "distance" in hit:
                merged["distance"] = hit["distance"]
            if "score" in hit:
                merged["score"] = hit["score"]
            return merged
        return hit
    entity = getattr(hit, "entity", None)
    data: dict[str, object] = {}
    if isinstance(entity, Mapping):
        data.update(entity)
    elif entity is not None:
        for field in _OUTPUT_FIELDS:
            getter = getattr(entity, "get", None)
            if callable(getter):
                data[field] = getter(field)
    if not data:
        getter = getattr(hit, "get", None)
        if callable(getter):
            for field in _OUTPUT_FIELDS:
                data[field] = getter(field)
    data.setdefault("distance", getattr(hit, "distance", 0.0))
    return data


def _hit_score(hit: object) -> float:
    if isinstance(hit, Mapping):
        value = hit.get("score", hit.get("distance", 0.0))
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
    value = getattr(hit, "score", None)
    if value is None:
        value = getattr(hit, "distance", 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _mapping_to_chunk(row: Mapping[str, object]) -> NarrativeChunk | None:
    try:
        family = DocumentFamily(str(row.get("family") or ""))
        chunk_type = ChunkType(str(row.get("chunk_type") or ChunkType.TEXT.value))
    except ValueError:
        return None
    chunk_id = str(row.get("chunk_id") or "")
    doc_id = str(row.get("doc_id") or "")
    if not chunk_id or not doc_id:
        return None
    page = _as_int(row.get("page"), -1)
    slide = _as_int(row.get("slide_index"), -1)
    text = str(row.get("text") or "")
    return NarrativeChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        path=str(row.get("path") or ""),
        family=family,
        chunk_type=chunk_type,
        text=text,
        embedding_input=text,
        section_path=str(row.get("section_path") or "") or None,
        slide_index=None if slide < 0 else slide,
        page=None if page < 0 else page,
        parent_id=str(row.get("parent_id") or "") or None,
        product=str(row.get("product") or "") or None,
        period=str(row.get("period") or "") or None,
        doc_type=str(row.get("doc_type") or "") or None,
        vehicle=str(row.get("vehicle") or "") or None,
        part_no=str(row.get("part_no") or "") or None,
    )


def _as_int(value: object, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
