"""Ingest family A/B/D narrative documents into Milvus + MinIO."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from large_files_embedding.domain.document import (
    MARKET_QUALITY_COLLECTION,
    ChunkStore,
    Document,
    DocumentFamily,
    EmbeddingEncoder,
    FailureReason,
    NarrativeIngestError,
    NarrativeIngestResult,
    NarrativeParser,
    ObjectStore,
    StoredChunk,
    require_collection,
    require_nonzero_embedding,
    validate_narrative_chunks,
)


class IngestNarrative:
    def __init__(
        self,
        parser: NarrativeParser,
        encoder: EmbeddingEncoder,
        chunks: ChunkStore,
        objects: ObjectStore,
        *,
        collection: str = MARKET_QUALITY_COLLECTION,
    ) -> None:
        self._parser = parser
        self._encoder = encoder
        self._chunks = chunks
        self._objects = objects
        self._collection = require_collection(collection)
        self.failure_queue: list[NarrativeIngestResult] = []

    def execute(
        self, document: Document, *, ingest_path: Path | None = None
    ) -> NarrativeIngestResult:
        source = ingest_path or document.path
        if document.decision is None:
            return self._fail(document.path, FailureReason.UNKNOWN_SIGNATURE)
        if document.decision.family is DocumentFamily.C:
            return self._fail(document.path, FailureReason.TABULAR_NOT_NARRATIVE)
        family = document.decision.family
        doc_id = _doc_id(source)
        try:
            parsed = self._parser.parse(source, family=family, doc_id=doc_id)
            validate_narrative_chunks(parsed.chunks, json_bytes=parsed.json_bytes)
            embeddings = self._encoder.encode(
                [chunk.embedding_input for chunk in parsed.chunks]
            )
            if len(embeddings) != len(parsed.chunks):
                return self._fail(document.path, FailureReason.PARSE_FAILED)
            for embedding in embeddings:
                require_nonzero_embedding(embedding)
            original_key = f"{parsed.doc_id}/original/{source.name}"
            json_key = f"{parsed.doc_id}/docling.json"
            self._objects.put_file(
                original_key,
                source,
                content_type=_content_type(source),
            )
            self._objects.put_bytes(
                json_key,
                parsed.json_bytes,
                content_type="application/json",
            )
            records = [
                StoredChunk(chunk=chunk, embedding=embedding)
                for chunk, embedding in zip(parsed.chunks, embeddings, strict=True)
            ]
            self._chunks.upsert(self._collection, records)
            return NarrativeIngestResult(
                source_path=document.path,
                doc_id=parsed.doc_id,
                chunk_count=len(records),
                json_key=json_key,
                original_key=original_key,
                failure_reason=None,
            )
        except NarrativeIngestError as exc:
            logging.getLogger(__name__).exception(
                "narrative ingest failed (%s) for %s",
                exc.reason.value,
                document.path,
            )
            return self._fail(document.path, exc.reason)

    def _fail(self, source: Path, reason: FailureReason) -> NarrativeIngestResult:
        result = NarrativeIngestResult(source, None, 0, None, None, reason)
        self.failure_queue.append(result)
        return result


def _doc_id(path: Path) -> str:
    resolved = str(path.resolve()) if path.exists() else str(path)
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".pptx":
        return (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    return "application/octet-stream"
