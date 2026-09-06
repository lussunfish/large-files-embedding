"""UC-03: ingest PDF/DOCX/PPTX narrative chunks into Milvus (fake Ports)."""

from __future__ import annotations

from pathlib import Path

import pytest

from large_files_embedding.application.ingest_narrative import IngestNarrative
from large_files_embedding.domain.document import (
    DEFAULT_EMBEDDING_DIM,
    MARKET_QUALITY_BUCKET,
    MARKET_QUALITY_COLLECTION,
    ChunkOrigin,
    ChunkType,
    Document,
    DocumentFamily,
    EncodedEmbedding,
    FailureReason,
    FileSignature,
    NarrativeChunk,
    NarrativeIngestError,
    ParsedNarrative,
    SignatureKind,
    StoredChunk,
    clip_varchar,
    metadata_from_header_footer,
    require_bucket,
    require_collection,
    require_milvus_uri,
    require_nonzero_embedding,
    validate_narrative_chunks,
)


class FakeNarrativeParser:
    def __init__(
        self,
        result: ParsedNarrative | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[Path, DocumentFamily, str]] = []

    def parse(
        self, path: Path, *, family: DocumentFamily, doc_id: str
    ) -> ParsedNarrative:
        self.calls.append((path, family, doc_id))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FakeEncoder:
    def __init__(
        self,
        *,
        zeros: bool = False,
        empty_sparse: bool = False,
        dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self.zeros = zeros
        self.empty_sparse = empty_sparse
        self.dim = dim
        self.texts: list[str] = []

    def encode(self, texts: list[str]) -> list[EncodedEmbedding]:
        self.texts.extend(texts)
        dense = tuple(0.0 if self.zeros else 0.01 for _ in range(self.dim))
        sparse: tuple[tuple[int, float], ...] = () if self.empty_sparse else ((1, 1.0),)
        return [
            EncodedEmbedding(dense=dense, sparse=sparse, model="qwen3-embedding:4b")
            for _ in texts
        ]


class FakeChunkStore:
    def __init__(self) -> None:
        self.records: list[StoredChunk] = []
        self.collections: list[str] = []

    def upsert(self, collection: str, records: list[StoredChunk]) -> None:
        require_collection(collection)
        self.collections.append(collection)
        self.records.extend(records)


class FakeObjectStore:
    def __init__(self) -> None:
        self.bytes_objects: dict[str, bytes] = {}
        self.file_objects: dict[str, Path] = {}

    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        self.bytes_objects[key] = body

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        self.file_objects[key] = path


def _document(path: Path, kind: SignatureKind) -> Document:
    return Document.from_signature(path, FileSignature(kind))


def _chunk(
    *,
    family: DocumentFamily = DocumentFamily.A,
    chunk_type: ChunkType = ChunkType.TEXT,
    text: str = "근본원인 본문",
    embedding_input: str | None = None,
    origin: ChunkOrigin = ChunkOrigin.JSON,
    section_path: str | None = "3. 원인",
    slide_index: int | None = None,
    page: int | None = None,
    parent_id: str | None = "parent-원인",
    speaker_notes: str | None = None,
    chunk_id: str = "c1",
    doc_id: str = "doc-1",
    path: str = "claim.docx",
) -> NarrativeChunk:
    return NarrativeChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        path=path,
        family=family,
        chunk_type=chunk_type,
        text=text,
        embedding_input=embedding_input if embedding_input is not None else text,
        origin=origin,
        section_path=section_path,
        slide_index=slide_index,
        page=page,
        parent_id=parent_id,
        speaker_notes=speaker_notes,
        product=None,
        period=None,
        doc_type=None,
        vehicle=None,
        part_no=None,
    )


def _parsed(
    chunks: list[NarrativeChunk],
    *,
    family: DocumentFamily = DocumentFamily.A,
    json_bytes: bytes = b'{"schema_name":"DoclingDocument"}',
    path: Path = Path("claim.docx"),
    pipeline: str = "simple",
) -> ParsedNarrative:
    return ParsedNarrative(
        doc_id=chunks[0].doc_id if chunks else "doc-1",
        path=path,
        family=family,
        json_bytes=json_bytes,
        chunks=tuple(chunks),
        pipeline=pipeline,
    )


def _uc(
    parser: FakeNarrativeParser,
    encoder: FakeEncoder | None = None,
    chunks: FakeChunkStore | None = None,
    objects: FakeObjectStore | None = None,
) -> tuple[IngestNarrative, FakeEncoder, FakeChunkStore, FakeObjectStore]:
    encoder = encoder or FakeEncoder()
    chunks = chunks or FakeChunkStore()
    objects = objects or FakeObjectStore()
    return (
        IngestNarrative(parser, encoder, chunks, objects),
        encoder,
        chunks,
        objects,
    )


def test_markdown_dump_only_chunks_are_rejected() -> None:
    path = Path("claim.docx")
    parser = FakeNarrativeParser(
        _parsed(
            [
                _chunk(
                    origin=ChunkOrigin.MARKDOWN_DUMP,
                    text="# 원인\n\n마크다운 dump",
                    embedding_input="# 원인\n\n마크다운 dump",
                )
            ]
        )
    )
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.OOXML_WORD))

    assert result.failed is True
    assert result.failure_reason is FailureReason.MARKDOWN_DUMP
    assert store.records == []
    assert objects.bytes_objects == {}
    assert objects.file_objects == {}
    assert encoder.texts == []


def test_fixed_length_chunks_are_rejected() -> None:
    path = Path("scan.pdf")
    parser = FakeNarrativeParser(
        _parsed(
            [
                _chunk(
                    family=DocumentFamily.B,
                    origin=ChunkOrigin.FIXED_LENGTH,
                    text="x" * 512,
                    embedding_input="x" * 512,
                    section_path=None,
                    page=1,
                )
            ],
            family=DocumentFamily.B,
            path=path,
            pipeline="standard_pdf",
        )
    )
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.PDF))

    assert result.failed is True
    assert result.failure_reason is FailureReason.FIXED_LENGTH_CHUNK
    assert store.records == []
    assert objects.file_objects == {}
    assert encoder.texts == []


def test_pptx_is_slide_level_including_notes() -> None:
    path = Path("review.pptx")
    chunks = [
        _chunk(
            family=DocumentFamily.D,
            chunk_id="s1",
            text="누유 현상",
            embedding_input="[슬라이드 1] 누유 현상\n노트: 현장 오일 누유",
            section_path=None,
            parent_id=None,
            slide_index=1,
            speaker_notes="현장 오일 누유",
            path="review.pptx",
        ),
        _chunk(
            family=DocumentFamily.D,
            chunk_id="s2",
            text="대책",
            embedding_input="[슬라이드 2] 대책\n노트: 가스켓 교체",
            section_path=None,
            parent_id=None,
            slide_index=2,
            speaker_notes="가스켓 교체",
            path="review.pptx",
        ),
    ]
    parser = FakeNarrativeParser(
        _parsed(chunks, family=DocumentFamily.D, path=path, pipeline="slide")
    )
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.OOXML_SLIDE))

    assert result.failed is False
    assert [record.chunk.slide_index for record in store.records] == [1, 2]
    assert "현장 오일 누유" in store.records[0].chunk.embedding_input
    assert "가스켓 교체" in store.records[1].chunk.embedding_input
    assert encoder.texts == [
        chunks[0].embedding_input,
        chunks[1].embedding_input,
    ]
    assert chunks[0].text not in encoder.texts
    assert objects.file_objects
    assert any(key.endswith("docling.json") for key in objects.bytes_objects)


def test_flattened_pptx_blob_is_rejected() -> None:
    path = Path("review.pptx")
    parser = FakeNarrativeParser(
        _parsed(
            [
                _chunk(
                    family=DocumentFamily.D,
                    text="슬라이드1 슬라이드2 전체 blob",
                    embedding_input="슬라이드1 슬라이드2 전체 blob",
                    slide_index=None,
                    speaker_notes=None,
                    section_path=None,
                    parent_id=None,
                    path="review.pptx",
                )
            ],
            family=DocumentFamily.D,
            path=path,
            pipeline="slide",
        )
    )
    uc, _encoder, store, objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.OOXML_SLIDE))

    assert result.failed is True
    assert result.failure_reason is FailureReason.PARSE_FAILED
    assert store.records == []
    assert objects.file_objects == {}


def test_pptx_table_chunk_without_notes_ingests_alongside_slide_notes() -> None:
    path = Path("review.pptx")
    chunks = [
        _chunk(
            family=DocumentFamily.D,
            chunk_id="s1",
            text="누유 현상",
            embedding_input="[슬라이드 1] 누유 현상\n노트: 현장 오일 누유",
            section_path=None,
            parent_id=None,
            slide_index=1,
            speaker_notes="현장 오일 누유",
            path="review.pptx",
        ),
        _chunk(
            family=DocumentFamily.D,
            chunk_id="tbl1",
            chunk_type=ChunkType.TABLE,
            text="품번,수량\nA-1,3",
            embedding_input="[슬라이드 1]\n품번,수량\nA-1,3",
            section_path=None,
            parent_id=None,
            slide_index=1,
            speaker_notes=None,
            path="review.pptx",
        ),
    ]
    parser = FakeNarrativeParser(
        _parsed(chunks, family=DocumentFamily.D, path=path, pipeline="slide")
    )
    uc, encoder, store, _objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.OOXML_SLIDE))

    assert result.failed is False
    assert [record.chunk.chunk_type for record in store.records] == [
        ChunkType.TEXT,
        ChunkType.TABLE,
    ]
    assert store.records[1].chunk.speaker_notes is None
    assert "현장 오일 누유" in store.records[0].chunk.embedding_input
    assert encoder.texts == [chunks[0].embedding_input, chunks[1].embedding_input]


def test_pptx_table_with_notes_missing_from_embedding_is_rejected() -> None:
    mixed = _chunk(
        family=DocumentFamily.D,
        chunk_type=ChunkType.TABLE,
        text="품번,수량",
        embedding_input="[슬라이드 1]\n품번,수량",
        slide_index=1,
        speaker_notes="현장 오일 누유",
        section_path=None,
        parent_id=None,
        path="review.pptx",
    )
    with pytest.raises(NarrativeIngestError) as exc:
        validate_narrative_chunks(
            [mixed], json_bytes=b'{"schema_name":"DoclingDocument"}'
        )
    assert exc.value.reason is FailureReason.PARSE_FAILED


def test_pptx_notes_dropped_from_embedding_input_are_rejected() -> None:
    path = Path("review.pptx")
    parser = FakeNarrativeParser(
        _parsed(
            [
                _chunk(
                    family=DocumentFamily.D,
                    text="제목",
                    embedding_input="제목",
                    slide_index=1,
                    speaker_notes="발표자 노트 본문",
                    section_path=None,
                    parent_id=None,
                    path="review.pptx",
                )
            ],
            family=DocumentFamily.D,
            path=path,
            pipeline="slide",
        )
    )
    uc, _encoder, store, _objects = _uc(parser)

    result = uc.execute(_document(path, SignatureKind.OOXML_SLIDE))

    assert result.failed is True
    assert store.records == []


def test_tables_mixed_into_prose_are_rejected() -> None:
    mixed = (
        "원인은 다음과 같다. | 품번 | 수량 |\n| --- | --- |\n| A-1 | 3 | "
        "대책을 본문 문장에 섞는다."
    )
    parser = FakeNarrativeParser(
        _parsed(
            [
                _chunk(
                    chunk_type=ChunkType.TEXT,
                    text=mixed,
                    embedding_input=mixed,
                )
            ]
        )
    )
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is True
    assert result.failure_reason is FailureReason.MIXED_TABLE_PROSE
    assert store.records == []
    assert objects.file_objects == {}
    assert encoder.texts == []


def test_docx_keeps_section_path_parent_child_and_separate_tables() -> None:
    text_chunk = _chunk(
        chunk_id="t1",
        chunk_type=ChunkType.TEXT,
        text="공정 조건 이탈",
        embedding_input="[섹션] 3. 원인 > 3.2 공정\n공정 조건 이탈",
        section_path="3. 원인 > 3.2 공정",
        parent_id="sec-3.원인",
    )
    table_chunk = _chunk(
        chunk_id="tbl1",
        chunk_type=ChunkType.TABLE,
        text="품번,수량\nA-1,3",
        embedding_input="[섹션] 3. 원인 > 3.2 공정\n품번,수량\nA-1,3",
        section_path="3. 원인 > 3.2 공정",
        parent_id="sec-3.원인",
    )
    parser = FakeNarrativeParser(_parsed([text_chunk, table_chunk]))
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is False
    assert [record.chunk.chunk_type for record in store.records] == [
        ChunkType.TEXT,
        ChunkType.TABLE,
    ]
    assert store.records[0].chunk.section_path == "3. 원인 > 3.2 공정"
    assert store.records[0].chunk.parent_id == "sec-3.원인"
    assert store.records[1].chunk.chunk_type is ChunkType.TABLE
    assert encoder.texts == [text_chunk.embedding_input, table_chunk.embedding_input]
    assert text_chunk.text not in encoder.texts
    assert objects.file_objects
    assert any(key.endswith("docling.json") for key in objects.bytes_objects)


def test_embedding_uses_contextualize_not_raw_chunk_text() -> None:
    chunk = _chunk(
        text="본문만",
        embedding_input="[문서] 8D\n[섹션] 대책\n본문만",
    )
    parser = FakeNarrativeParser(_parsed([chunk]))
    uc, encoder, store, _objects = _uc(parser)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is False
    assert encoder.texts == [chunk.embedding_input]
    assert store.records[0].embedding.dense[0] != 0.0
    assert store.records[0].embedding.sparse


def test_empty_docling_json_is_treated_as_markdown_dump() -> None:
    parser = FakeNarrativeParser(_parsed([_chunk()], json_bytes=b""))
    uc, _encoder, store, objects = _uc(parser)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is True
    assert result.failure_reason is FailureReason.MARKDOWN_DUMP
    assert store.records == []
    assert objects.file_objects == {}


def test_encrypted_pdf_goes_to_failure_queue_and_is_not_indexed() -> None:
    from large_files_embedding.domain.document import NarrativeParseError

    parser = FakeNarrativeParser(error=NarrativeParseError(FailureReason.ENCRYPTED_PDF))
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(Path("secret.pdf"), SignatureKind.PDF))

    assert result.failed is True
    assert result.failure_reason is FailureReason.ENCRYPTED_PDF
    assert store.records == []
    assert objects.file_objects == {}
    assert encoder.texts == []


def test_broken_xref_and_empty_document_are_not_indexed() -> None:
    from large_files_embedding.domain.document import NarrativeParseError

    parser = FakeNarrativeParser(error=NarrativeParseError(FailureReason.BROKEN_XREF))
    uc, _encoder, store, _objects = _uc(parser)
    broken = uc.execute(_document(Path("bad.pdf"), SignatureKind.PDF))
    assert broken.failure_reason is FailureReason.BROKEN_XREF
    assert store.records == []

    empty_parser = FakeNarrativeParser(
        error=NarrativeParseError(FailureReason.EMPTY_DOCUMENT)
    )
    uc2, _e2, store2, _o2 = _uc(empty_parser)
    empty = uc2.execute(_document(Path("empty.pdf"), SignatureKind.PDF))
    assert empty.failure_reason is FailureReason.EMPTY_DOCUMENT
    assert store2.records == []


def test_dummy_zero_vectors_are_rejected() -> None:
    parser = FakeNarrativeParser(_parsed([_chunk()]))
    uc, encoder, store, objects = _uc(parser, encoder=FakeEncoder(zeros=True))

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is True
    assert result.failure_reason is FailureReason.DUMMY_VECTOR
    assert store.records == []
    assert objects.file_objects == {}
    assert encoder.texts == [_chunk().embedding_input]


def test_family_c_is_not_narrative_ingested() -> None:
    parser = FakeNarrativeParser()
    uc, encoder, store, objects = _uc(parser)

    result = uc.execute(_document(Path("ledger.xlsx"), SignatureKind.OOXML_SHEET))

    assert result.failed is True
    assert result.failure_reason is FailureReason.TABULAR_NOT_NARRATIVE
    assert parser.calls == []
    assert encoder.texts == []
    assert store.records == []
    assert objects.file_objects == {}


def test_payload_has_filterable_metadata() -> None:
    chunk = _chunk(page=2, section_path="2. 대책", parent_id="sec-2")
    parser = FakeNarrativeParser(_parsed([chunk]))
    uc, _encoder, store, _objects = _uc(parser)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is False
    stored = store.records[0].chunk
    assert stored.doc_id
    assert stored.path
    assert stored.family is DocumentFamily.A
    assert stored.chunk_type in {ChunkType.TEXT, ChunkType.TABLE}
    assert stored.section_path == "2. 대책"
    assert stored.page == 2
    assert stored.product is None
    assert stored.period is None
    assert stored.doc_type is None
    assert stored.vehicle is None
    assert stored.part_no is None
    assert store.collections == [MARKET_QUALITY_COLLECTION]


def test_require_collection_rejects_psychology_and_ebook() -> None:
    assert require_collection(MARKET_QUALITY_COLLECTION) == MARKET_QUALITY_COLLECTION
    with pytest.raises(NarrativeIngestError) as psychology:
        require_collection("psychology_chunks_hybrid")
    assert psychology.value.reason is FailureReason.FORBIDDEN_COLLECTION
    with pytest.raises(NarrativeIngestError) as ebook:
        require_collection("ebook_chunks_hybrid")
    assert ebook.value.reason is FailureReason.FORBIDDEN_COLLECTION


def test_require_bucket_rejects_other_buckets() -> None:
    assert require_bucket(MARKET_QUALITY_BUCKET) == MARKET_QUALITY_BUCKET
    with pytest.raises(NarrativeIngestError) as psy:
        require_bucket("psychology-pdfs")
    assert psy.value.reason is FailureReason.FORBIDDEN_BUCKET
    with pytest.raises(NarrativeIngestError):
        require_bucket("ebook-pdfs")


def test_require_milvus_uri_rejects_lite() -> None:
    assert require_milvus_uri("http://127.0.0.1:19530") == "http://127.0.0.1:19530"
    with pytest.raises(NarrativeIngestError) as lite:
        require_milvus_uri("./milvus.db")
    assert lite.value.reason is FailureReason.FORBIDDEN_COLLECTION


def test_header_footer_promotes_part_no_and_vehicle() -> None:
    part_no, vehicle = metadata_from_header_footer(
        "품번 ABC-1234 | 차종 소나타 | CONFIDENTIAL"
    )
    assert part_no == "ABC-1234"
    assert vehicle == "소나타"
    empty_part, empty_vehicle = metadata_from_header_footer("  ")
    assert empty_part is None
    assert empty_vehicle is None


def test_long_parent_id_is_clipped_to_field_limit() -> None:
    section = "3. 근본원인 > " + ("공정조건세부항목-" * 30)
    parent = f"abcdefghijklmnop:{section}"
    clipped = clip_varchar(parent, max_length=256)
    assert 0 < len(clipped.encode("utf-8")) <= 256
    assert parent.startswith(clipped)
    chunk = _chunk(section_path=section, parent_id=parent)
    parser = FakeNarrativeParser(_parsed([chunk]))
    uc, _encoder, store, _objects = _uc(parser)
    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))
    assert result.failed is False
    assert store.records[0].chunk.parent_id == parent


def test_require_nonzero_embedding_rejects_zeros() -> None:
    zeros = EncodedEmbedding(
        dense=tuple(0.0 for _ in range(DEFAULT_EMBEDDING_DIM)),
        sparse=((1, 1.0),),
        model="qwen3-embedding:4b",
    )
    with pytest.raises(NarrativeIngestError) as exc:
        require_nonzero_embedding(zeros)
    assert exc.value.reason is FailureReason.DUMMY_VECTOR


class _FakeEmbedResponse:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.status_code = 200
        self._embeddings = embeddings

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[list[float]]]:
        return {"embeddings": self._embeddings}


class _FakeEmbedClient:
    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dim = dim
        self.payloads: list[list[str]] = []

    def post(self, url: str, json: dict[str, object]) -> _FakeEmbedResponse:
        raw = json.get("input", [])
        texts = [str(item) for item in raw] if isinstance(raw, list) else []
        self.payloads.append(texts)
        vector = [0.01] * self.dim
        return _FakeEmbedResponse([vector for _ in texts])


def test_encoder_batches_large_inputs() -> None:
    from large_files_embedding.infrastructure.embedding_encoder import (
        DenseSparseEncoder,
    )

    client = _FakeEmbedClient()
    encoder = DenseSparseEncoder(
        "http://127.0.0.1:11434",
        "qwen3-embedding:4b",
        DEFAULT_EMBEDDING_DIM,
        client=client,
        batch_size=4,
    )
    texts = [f"chunk {index} token" for index in range(9)]
    encoded = encoder.encode(texts)
    assert len(encoded) == 9
    assert [len(payload) for payload in client.payloads] == [4, 4, 1]
    assert all(len(item.dense) == DEFAULT_EMBEDDING_DIM for item in encoded)


def test_minio_from_env_does_not_leave_empty_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from large_files_embedding.infrastructure.minio_object_store import (
        MinioObjectStore,
    )

    for key in (
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    store = MinioObjectStore.from_env()
    assert store._access_key
    assert store._secret_key
