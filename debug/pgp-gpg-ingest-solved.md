# PGP - GPG.pdf ingest 디버그

| 항목 | 값 |
|------|-----|
| 파일 | `sample-input/pdf/PGP - GPG.pdf` (당시 `sample-input/PGP - GPG.pdf`) |
| 크기 | 3.6MB, PDF 1.6, 216페이지 (디지털 텍스트층) |
| 일시 | 2026-09-06 발생, 2026-09-07 재확인 |
| 상태 | **solved** — CLI 입고 `chunks=317`, 동일 바이트 재입고는 스킵 |

## 증상

첫 CLI 입고:

```text
uv run python -m large_files_embedding ingest "sample-input/PGP - GPG.pdf"
→ sample-input/PGP - GPG.pdf family=B format=pdf normalize=false
→ (Docling MatchingPostProcessor WARNING 다수, ~2분)
→ sample-input/PGP - GPG.pdf FAIL reason=parse_failed
```

로그: `debug/ingest-pgp-gpg.log`

라우팅은 정상(가족 B, 정규화 없음). 실제 예외 문자열은 CLI가 삼켜서 보이지 않았다.

## 조사

단계별로 나눠 재현 (`debug/ingest-traceback.log`, `debug/ingest-stage2.log`).

| 단계 | 결과 |
|------|------|
| 라우팅 | family=B, pdf |
| Docling parse | 317 청크, json 2.2MB, pipeline=`standard_pdf`, OCR 없음 |
| validate | 통과 (text 309 / table 8) |
| 임베딩 1건 | 0.16s, dim 2560 |
| 임베딩 최장 청크 (16066자) | 5.16s |
| 임베딩 317건 **한 요청** | 71.37s (httpx timeout 120s에 근접) |
| MinIO | 자격 없으면 빈 키 → S3 실패. 테스트/01-stable 기본값은 `minioadmin` |
| Milvus upsert 317건 | 한 번에 넣으면 gRPC 메시지 한도에 걸릴 수 있음 |

파싱 자체는 실패가 아니었다. `parse_failed`는 Ollama/MinIO/Milvus 예외와 CLI `except Exception`이 모두 같은 코드로 매핑된 결과였다.

## 원인

1. **원인 은닉**  
   `IngestNarrative`가 `NarrativeIngestError`의 `__cause__`를 버리고, CLI는 나머지 예외를 traceback 없이 `PARSE_FAILED`로 바꿈.

2. **임베딩 한 방 전송**  
   317개 텍스트를 `/api/embed` 한 번에 넣고 timeout 120s. 이 책에서 71s가 나와 한도에 붙는다. 첫 실행(콜드/부하)에서 timeout → `parse_failed`.

3. **MinIO 자격 폴백 없음**  
   MariaDB는 `01-stable` `.env`를 읽는데 MinIO는 환경 변수가 비면 빈 키로 붙는다. 로컬 compose 기본은 `minioadmin`.

4. **Milvus upsert 일괄**  
   2560-dim × 317 + 긴 본문은 메시지 한 건이 커진다. 64건 단위로 나눔.

Docling `Orphan pdf_cell` 경고는 표 셀 복구 로그일 뿐 실패 조건이 아니다.

## 해결

| 파일 | 변경 |
|------|------|
| `infrastructure/embedding_encoder.py` | 배치 8, timeout 180s. `EMBEDDING_BATCH_SIZE` / `EMBEDDING_TIMEOUT_SEC` |
| `infrastructure/minio_object_store.py` | `01-stable/local-minio/.env` 또는 `minioadmin` 폴백 |
| `infrastructure/milvus_chunk_store.py` | upsert 64건 배치 |
| `application/ingest_narrative.py` | 실패 시 `logging.exception`으로 cause 유지 |
| `presentation/cli/ingest.py` | 예외 traceback을 stderr로 출력 |

테스트: `test_encoder_batches_large_inputs`, `test_minio_from_env_does_not_leave_empty_keys`.

UC-07(커밋 `0dbc127`): 성공 입고 후 같은 파일 바이트는 MariaDB `ingest_manifest`로 스킵. `--force`로만 재처리.

## 검증

MinIO 환경 변수 없이 공식 CLI 재실행 (`debug/ingest-cli-retry.log`, 2026-09-06):

```text
sample-input/PGP - GPG.pdf chunks=317 collection=market_quality_chunks_hybrid json=196e1204f9b5d2da/docling.json
```

앱 재시작 후 경로 이동분 재입고 (2026-09-07):

```text
sample-input/pdf/PGP - GPG.pdf family=B format=pdf normalize=false
sample-input/pdf/PGP - GPG.pdf chunks=317 collection=market_quality_chunks_hybrid json=56af0d8ce3a644ec/docling.json
```

같은 파일 즉시 재실행:

```text
sample-input/pdf/PGP - GPG.pdf SKIP reason=unchanged_content sha256=7d90c6b73ccc26f823ec17bbdcc7e100ebd2653ed065abf6c1b7d6fb8917d056
```

| 저장소 | 확인 |
|--------|------|
| Milvus `market_quality_chunks_hybrid` | doc_id `56af0d8ce3a644ec`, 317 청크, 169 페이지, text+table |
| MinIO `market-quality-docs` | 원본 3.6MB, `docling.json` 2.2MB |

## 남은 관찰 (입고를 막지는 않음)

- 216페이지 중 청크가 있는 페이지는 169. 빈 페이지·짧은 페이지는 정상적으로 빠짐.
- 최장 청크 ~16k자. HybridChunker `max_tokens=8192` 근방. 검색 품질은 후속 튜닝.
- Docling 표 복구 경고가 많다. 표 8개는 `chunk_type=table`로 분리됨.
