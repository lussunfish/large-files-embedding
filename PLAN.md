# large-files-embedding — 구현 계획

> **구현 SSOT.** `approved` 전 프로덕션·UC별 테스트 코드 작성 금지.
> 스캐폴드는 `AGENTS.md` 참조.
> Grok 세션 `plan.md`(`/plan`)와 별개 — **이 파일이 우선.**
> 조사 산출물 `survey/` 는 앱 소스가 아니다. **포맷 처리 SSOT:** `survey/format-pipelines/README.md` + `01-pdf.md` … `08-ppt.md`. 상위: `survey/market-quality-rag-improvement.md`, `survey/excel-to-sql-decision.md`, `survey/xlsx-20-samples-layer1.md`, `survey/docx-pipeline.md`, `survey/doc-format-handling.md`. 09+는 이번 UC 범위가 아니며, 라우터 확장 지점만 열어 둔다.

## 계획 승인

| 항목 | 값 |
|------|-----|
| 상태 | `draft` |
| 승인자 | — |
| 승인일 | — |

**상태**: `draft` · `approved` · `revised` (재승인 필요)

승인 전 체크:

- [ ] 목표·비목표 합의 (스캔 OCR은 UC-03에 포함. 09+·행 임베딩·ColQwen 전체는 비목표)
- [ ] UC 우선순위·수용 기준 명확 (MCP 도구 목록이 닫혀 있음)
- [ ] 표는 프로파일 JSON + Parquet 1층, MariaDB 2층은 매핑된 팩트만
- [ ] 실행 모드·명령어 확인 (`01-stable` 공유 스택)
- [ ] Phase 완료 조건이 검증 가능 (어댑터가 인메모리가 아님)

---

## 목표

- 01–08 포맷을 시그니처 기준으로 라우팅해 서술 문서는 벡터, 표는 SQL로 입고한다
- HybridChunker JSON 청크를 **공유 Milvus**(`127.0.0.1:19530`)에 넣고, 엑셀/CSV는 Parquet 랜딩 후 **MariaDB**로 조회한다
- 원본·파생 객체는 **공유 MinIO**(`127.0.0.1:9000`) 버킷에 둔다
- Codex CLI에 stdio MCP를 연동해 담당자가 근거 있는 인사이트를 얻는다
- Clean Architecture + TDD, 호스트 uv로 개발·실행

## 비목표

- 09번 이후 포맷(HWP, MD/TXT/HTML, 메일, CAD 등)의 이번 범위 구현. 감지되면 실패 큐
- 엑셀/CSV 행을 Milvus에 임베딩. Docling XLSX/CSV 백엔드로 행을 처리하기
- GraphRAG, ColQwen 전체 재인덱스. 디지털 PDF 텍스트 인덱스를 ColPali/VLM으로 대체
- 엑셀 시트마다 MariaDB 테이블을 1:1로 만드는 전량 적재. xlsx를 MariaDB BLOB로 넣기
- 3,100개를 처음부터 curated SQL에 밀어 넣기. 100MB 원본을 LLM 컨텍스트/채팅에 올리기
- Anthropic contextual retrieval(청크마다 LLM 설명)을 1차 경로로 쓰기
- antiword/catdoc/catppt, python-docx로 `.doc`, python-pptx로 `.ppt`, xlrd
- 이 레포에서 Milvus/MinIO/MariaDB compose를 새로 띄우기 (`01-stable` 공유 스택을 쓴다)
- 공유 MariaDB의 `embeddings.chunks` VECTOR 테이블에 서술 청크를 넣기 (벡터는 Milvus)
- 웹 UI, 클라우드 전용 파서·변환 API
- 사용자 홈의 `~/.codex/config.toml`을 직접 덮어쓰기 (스니펫만 생성)
- ColQwen/ColPali 페이지 비전 인덱스 (후속)

## 범위

### 포함

- UC-01: 시그니처로 가족 A/B/C/D 라우팅
- UC-02: `.doc`/`.ppt` LibreOffice 정규화 (원본 보존)
- UC-03: PDF/DOCX/PPTX 서술 입고 (Docling JSON, 공유 Milvus 컬렉션, 임베딩)
- UC-04: XLSX/XLS/CSV 표 입고 (calamine/polars, 프로파일 JSON, Parquet 1층→MinIO, 조회용 팩트는 MariaDB). 행 임베딩 금지
- UC-05: MCP 조회 전용 도구 (목록은 UC-05 수용 기준)
- UC-06: Codex용 stdio MCP `config.toml` **스니펫 생성** (홈 파일 미수정)

### 제외

- 09번 이후 포맷 (가족 E/F/G/H 포함). 라우터 미등록이면 실패 큐
- 엑셀/CSV 행 임베딩, Docling 표 백엔드로 SQL 경로
- GraphRAG, ColQwen 전체 재인덱스, 시트 1:1 MariaDB 테이블, 원본 BLOB 적재
- `01-stable` 밖 인프라 중복 기동
- 웹 UI, 클라우드 전용 파서 API, antiword/xlrd

---

## Bounded Context

| ID | 이름 | 설명 | 경로 |
|----|------|------|------|
| BC-01 | Document | 01–08 포맷 입고(서술=공유 Milvus, 표=MariaDB, 객체=MinIO)와 MCP 조회 | `src/large_files_embedding/` |

### Ubiquitous Language

| 용어 | 정의 | Context |
|------|------|---------|
| Document | 입고 대상 시장품질 파일. 가족 A/B/D는 서술, C는 표 | BC-01 |
| 가족 | A Word형, B PDF형, C 정형 표, D 슬라이드. 조사의 E~H(가벼운 텍스트·이미지·컨테이너·도면)는 이번 UC 밖 | 라우팅 |
| 서술 청크 | Milvus에 넣는 텍스트/표 객체. C 가족 행이 아님. 임베딩 입력은 `chunker.contextualize` | UC-03, UC-05 |
| 표 카탈로그 | MariaDB 스키마·팩트 + Milvus에 넣는 **시트/테이블 설명 문장**(행 데이터 아님) | UC-04, UC-05 |
| 프로파일 JSON | 표 파일당 2~10KB 지문(시트·헤더·타입·샘플). LLM에는 이것만. 원본 워크북은 넣지 않음 | UC-04 |
| 1층 / 2층 | 1층=Parquet 랜딩(원본 컬럼 유지). 2층=curated 팩트 SQL. 정규화는 2층만 | UC-04 |
| 원장 | 한 행=사건 1건. UNION이 맞음 | UC-04 |
| 스냅샷 | 월보처럼 파일 단위 시점. `report_period` 없이 UNION 하면 중복 집계 | UC-04 |
| TAG | Table-Augmented Generation. 숫자 질문은 RAG가 아니라 `query_tables` | UC-05 |
| 실패 큐 | 파싱·변환 실패·미등록 포맷. 빈 문서로 인덱싱하지 않음. 배치는 계속 | UC-01~04 |
| parent-child | 검색은 작은 청크, 답변은 부모 섹션(`get_section`) | UC-03, UC-05 |

---

## Use Case

| UC-ID | Use Case | Context | 우선순위 | 상태 | Red 테스트 |
|-------|----------|---------|----------|------|------------|
| UC-01 | 파일 시그니처로 포맷을 판별하고 가족(A/B/C/D)으로 라우팅한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_route_file.py` |
| UC-02 | .doc/.ppt를 LibreOffice로 현대 포맷으로 정규화한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_normalize_office.py` |
| UC-03 | PDF/DOCX/PPTX를 Docling JSON·HybridChunker로 청크해 Milvus에 넣는다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_ingest_narrative.py` |
| UC-04 | XLSX/XLS/CSV를 calamine/polars로 Parquet 1층·MariaDB 2층에 넣는다 (행 임베딩 금지) | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_ingest_tabular.py` |
| UC-05 | MCP 조회 도구(search_passages, get_section, query_tables 등)를 제공한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_serve_mcp.py` |
| UC-06 | Codex용 stdio MCP config.toml 스니펫을 생성한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_configure_codex.py` |

상태: `planned` · `in_progress` · `done` · `deferred` · `cancelled`

의존: UC-02는 라우팅 결과(정규화 대상)가 필요하다. UC-03/04는 UC-01 뒤에. UC-05는 UC-03·04가 저장한 인덱스를 읽는다. UC-06은 UC-05 엔트리포인트가 있어야 한다.

### UC 수용 기준 (Given/When/Then)

#### UC-01 — 파일 시그니처로 포맷을 판별하고 가족(A/B/C/D)으로 라우팅한다

- **Given**: PDF/OOXML/OLE/CSV 시그니처를 가진 파일이 있다
- **When**: 입고 라우터에 경로를 넘긴다
- **Then**: 가족 A/B/C/D와 정규화 대상 여부(`.doc`/`.ppt`만 soffice)가 반환된다. `.xls`는 가족 C이며 1순위는 calamine이다. 핸들러 레지스트리에 없는 포맷(09+, 가족 E/F/G/H)은 실패 큐로 보내고, `search_hwp` 같은 포맷별 MCP 도구를 만들지 않는다
- **실패/경계**: 알 수 없는 시그니처는 실패 큐로 보내고 배치를 멈추지 않는다. 확장자만 `.doc`인 OOXML은 가족 A로, 확장자만 `.xls`인 ZIP은 가족 C(xlsx)로, 확장자만 `.ppt`인 OOXML은 가족 D로 재분류한다. `{\rtf` 위장 `.doc`는 16(범위 밖)이라 실패 큐. CSV가 한 열 산문이면 표가 아니므로 실패 큐(15는 범위 밖). 매크로는 실행하지 않는다. antiword/catdoc/python-docx(`.doc`)/python-pptx(`.ppt`)로 우회하지 않는다

#### UC-02 — .doc/.ppt를 LibreOffice로 현대 포맷으로 정규화한다

- **Given**: OLE `.doc` 또는 `.ppt`와 soffice가 있다
- **When**: 정규화를 요청한다
- **Then**: 원본은 유지하고 `.docx`/`.pptx` 파생물과 메타(`converted_from`, `converter=libreoffice`, `converted_at`)가 생긴다. 필터는 `docx:"MS Word 2007 XML"` / pptx. 호출은 timeout과 파일별 `UserInstallation`을 쓴다. Docling 내장 `convert_to_modern_format`만 쓰고 soffice를 숨기지 않는다. 동시 변환은 워커 하나(또는 프로필 격리)로 제한한다
- **실패/경계**: timeout·soffice 부재·한글 `□□`/모지바케는 failed로 남기고 원본을 삭제하지 않는다. antiword/catdoc/catppt, python-docx로 `.doc`, python-pptx로 `.ppt`는 거부한다. PDF로 먼저 변환하지 않는다. 웹 변환 API에 올리지 않는다

#### UC-03 — PDF/DOCX/PPTX를 Docling JSON·HybridChunker로 청크해 Milvus에 넣는다

- **Given**: PDF 또는 DOCX 또는 PPTX가 있다. 임베딩 인코더(다국어 dense)가 설정되어 있다
- **When**: 서술 입고를 실행한다
- **Then**:
  - 원본과 Docling JSON을 둘 다 보관한다. 청크만 남기지 않는다. 마크다운 dump만으로 인덱싱하지 않는다. 고정 길이 슬라이딩 윈도우는 쓰지 않는다. 임베딩 입력은 `chunk.text`가 아니라 `chunker.contextualize(chunk)`다 (`merge_peers=True`, `repeat_table_header=True`). Anthropic contextual retrieval(청크마다 LLM 설명)은 1차가 아니다
  - **DOCX (가족 A)**: SimplePipeline + HybridChunker. 청크 키는 섹션 경로. 표는 `chunk_type=table`로 본문과 분리. **parent-child**: 검색용 작은 청크 + 답변용 부모 섹션. DOCX를 PDF로 바꿔 StandardPdfPipeline 하지 않는다. LibreOffice는 DrawingML 렌더에만 (켜면 timeout+UserInstallation)
  - **PDF (가족 B)**: 텍스트 층이 있으면 StandardPdfPipeline. 희소/스캔 페이지는 RapidOCR `lang=["korean"]` (기본 lang `chinese` 금지. PP-OCR v6 korean 별칭만 있는 경로는 쓰지 않음). 표는 별도 청크. 막대/원/선은 `--enrich-chart-extraction`을 켜면 표로 넣고, 없어도 UC를 막지 않는다. 100MB는 페이지 스트림으로 읽고 파일을 통째로 메모리에 올리지 않는다. 반복 헤더/푸터는 메타로 빼고 본문 청크에 매 페이지 반복하지 않는다. PDF→DOCX 변환은 기본이 아니다. VlmPipeline은 난해 페이지만 선택이며 디지털 본문 전체를 대체하지 않는다
  - **PPTX (가족 D)**: 슬라이드 1장 = 청크 1개 (제목+본문+**발표자 노트**+차트 캡션/표). 전 슬라이드를 한 blob으로 붙이지 않는다. HybridChunker 섹션 분할로 슬라이드를 쪼개지 않는다. PPTX를 PDF 파이프라인으로 보내지 않는다. bar/pie/line은 Docling 차트 추출(없어도 UC를 막지 않음). 사진·공정 이미지는 캡션이 있으면 캡션, VLM은 후속(`USE_GPU=no`)
  - Milvus payload 메타(필터 가능): `doc_id`, `path`, `family`, `chunk_type(text|table)`, `section_path` 또는 `slide_index`, `page`, `product`, `period`, `doc_type`. 있으면 `vehicle`(차종), `part_no`(품번). 없으면 필드를 null로 두고 3100건 전체를 매번 검색하지 않게 필터 인자를 연다
  - 각 청크는 dense 벡터로 **공유 Milvus** `127.0.0.1:19530` 컬렉션 `market_quality_chunks_hybrid`에 들어간다. psychology/ebook 컬렉션과 섞지 않는다. 품번·코드를 위해 sparse/BM25를 같이 넣는다. 더미 영벡터 금지. JSON/원본은 MinIO 버킷 `market-quality-docs`에도 올린다
- **실패/경계**: 암호 PDF·깨진 xref·빈 문서·변환 실패는 실패 큐. 인덱싱하지 않는다. 마크다운 dump만 있는 청크, 표를 본문 문장에 섞은 청크는 거부한다

#### UC-04 — XLSX/XLS/CSV를 calamine/polars로 Parquet 1층·MariaDB 2층에 넣는다 (행 임베딩 금지)

- **Given**: xlsx/xls/csv 파일이 있다
- **When**: 표 입고를 실행한다
- **Then**:
  - 추출은 fastexcel/calamine(polars 기본 엔진) 시트 단위 스트리밍. 워크북 전체 메모리 로드 금지. Docling XLSX/CSV 백엔드는 SQL 경로에 쓰지 않는다(내부 openpyxl). openpyxl은 차트·정의된 이름·병합 수리 폴백만. pandas 통째 로드·xlrd 금지
  - 파일당 **프로파일 JSON**(2~10KB: 시트명, 행/열, 헤더 후보, 타입, null, 샘플 5행)을 남긴다. 100MB 원본을 LLM 컨텍스트/채팅에 넣지 않는다. 스키마 정렬은 이 프로필로 한다
  - **1층** 시트 단위 Parquet를 MinIO(`market-quality-docs`)에 올린다. **원본 컬럼을 유지**한다. 정규화는 2층. 메타: `source_file`, `sheet_name`, `report_period`, `ingested_at`, `template_family`. 날짜는 엑셀 시리얼을 변환한다
  - **2층** 조회는 **MariaDB** `127.0.0.1:3306` (앱 DB `market_quality`, **팩트** 예: `claim_event` / `monthly_quality_kpi`). 파일/시트당 테이블 1개는 금지. 매핑이 없는 파일은 1층만 두고 전량 curated 적재하지 않는다. 공유 서버 `embeddings.chunks` VECTOR·xlsx BLOB는 쓰지 않는다
  - **원장**은 UNION이 맞고, **월보 스냅샷**은 `report_period` 없이 UNION하지 않는다
  - CSV는 utf-8-sig 또는 cp949, 구분자 `,`/`;`/`\t`. polars `scan_csv`. 한 열 산문은 표가 아니므로 실패 큐
  - 피벗·차트·매크로·빈 시트는 건너뛰고 메타만. 원인/대책처럼 긴 칸은 **테이블에서 삭제하지 않고**, **설명 문장만** 카탈로그 청크로 Milvus에 넣을 수 있다 (행 전체 임베딩 아님)
- **실패/경계**: 행을 벡터 컬렉션에 넣으려 하면 도메인 예외. `.xls` calamine 실패만 LibreOffice 폴백. VBA/매크로는 실행하지 않는다. 원인/대책 칸을 SQL에서 지우고 RAG만 남기는 경로를 두지 않는다

#### UC-05 — MCP 조회 도구(search_passages, get_section, query_tables 등)를 제공한다

- **Given**: 서술 청크(공유 Milvus)와 표 카탈로그(MariaDB)가 있다
- **When**: 아래 도구를 호출한다
- **Then**: 각 응답에 파일명과 페이지 또는 시트 또는 섹션 경로가 붙고, 본문은 짧게 자른다. 도구 description에 **숫자 집계→`query_tables`(TAG/Text-to-SQL), 대책/원인→`get_section`, 코드/품번→`search_passages`(sparse+필터), 모호한 검색→`search_passages`** 를 적는다. `search` 하나만 두지 않는다. `list_documents`/`search_passages`/`list_tables`는 `product`, `period`, `doc_type` 필터 인자를 받는다. 근거가 없으면 “근거 없음”을 반환한다 (지어내지 않음). 표 숫자를 서술 청크에서 지어내지 않는다. `get_section`은 parent 섹션을 돌려 주고 잘린 자식 청크만으로 답하지 않는다. DOCX 인용은 페이지보다 `파일명+섹션 경로`가 우선이다
- **필수 도구 (이 목록이 닫힌 수용 기준이다)**:
  - `list_documents(product?, period?, doc_type?)`
  - `search_passages(query, filters?)` — dense+sparse, 가능하면 rerank top 50→5
  - `get_outline(doc_id)`
  - `get_section(doc_id, heading_path)`
  - `get_table(doc_id, table_id)` — 문서 안 표 청크
  - `get_page(doc_id, page)` — PDF 텍스트/저장된 페이지. ColQwen 아님
  - `list_slides` / `get_slide` — PPTX
  - `list_tables` / `describe_table` (grain·단위·한 행의 의미) / `query_tables` — MariaDB **읽기 전용**, LIMIT. 가능하면 임의 SQL보다 filters+group_by
- **실패/경계**: 허용 스키마 밖 SQL·쓰기(`DROP`/`DELETE`/`INSERT`/`UPDATE`)는 거부한다. 입고·삭제는 MCP에 두지 않는다. 도구 출력이 길면 잘라서 포인터만 남긴다

#### UC-06 — Codex용 stdio MCP config.toml 스니펫을 생성한다

- **Given**: UC-05 stdio MCP 엔트리포인트가 있다
- **When**: 연동 설정을 생성한다
- **Then**: 저장소 안 스니펫(예: `deploy/codex-mcp.toml`)이 나온다. 키: `command`, `args`, `cwd`, `startup_timeout_sec`(≥30), `tool_timeout_sec`. **홈 디렉터리 `~/.codex/config.toml`을 수정하지 않는다**
- **실패/경계**: command가 비면 거부한다

---

## 아키텍처 설계

도메인은 UC마다 쪼개지 않는다. `domain/document.py`에 가족·시그니처·청크/표 레코드 규칙을 둔다. 저장 Port는 역할별로 나눈다. **인메모리 어댑터는 단위 테스트 더블일 뿐, PLAN Infrastructure 열이 아니다.**

입고는 `ingest(path) → detect → normalize → extract(narrative|tabular)` 레지스트리다. 09+ 추가는 핸들러 한 개이며 MCP 도구를 포맷마다 늘리지 않는다. 컨테이너(메일/zip)·가족 E(MD/TXT/HTML)는 이번 범위에서 실패 큐. 표 추출기는 프로파일 JSON을 같이 낸다(별도 Port 없음).

질문 유형과 도구: 코드/키워드 → `search_passages`(sparse+필터), 수치/집계 → `query_tables`(TAG), 원인·대책 → `get_section`, 차트 페이지 → `get_page`(비전 인덱스는 후속).

### 레이어 배치

| UC-ID | Domain | Application | Infrastructure | Presentation |
|-------|--------|-------------|----------------|--------------|
| UC-01 | `document.py` | `route_file.py` | `format_detector.py` | `cli/ingest.py` |
| UC-02 | `document.py` | `normalize_office.py` | `libreoffice_normalizer.py` | `cli/ingest.py` |
| UC-03 | `document.py` | `ingest_narrative.py` | `docling_adapter.py`, `embedding_encoder.py`, `milvus_chunk_store.py`, `minio_object_store.py` | `cli/ingest.py` |
| UC-04 | `document.py` | `ingest_tabular.py` | `calamine_extractor.py`, `mariadb_table_store.py`, `minio_object_store.py` | `cli/ingest.py` |
| UC-05 | `document.py` | `serve_mcp.py` | `milvus_chunk_store.py`, `mariadb_table_store.py` (읽기) | `mcp/server.py` |
| UC-06 | `document.py` | `configure_codex.py` | `codex_snippet_writer.py` | `cli/configure.py` |

### Port & Adapter

| Port | Adapter | UC-ID | 비고 |
|------|---------|-------|------|
| `FormatDetector` | `MagicFormatDetector` | UC-01 | 확장자가 아니라 시그니처 |
| `OfficeNormalizer` | `LibreOfficeNormalizer` | UC-02 | timeout + `UserInstallation`. 동시성 제한. antiword 아님 |
| `NarrativeParser` | `DoclingNarrativeParser` | UC-03 | JSON 보관. 가족 A/B/D 분기. 고정 길이 청크 아님 |
| `EmbeddingEncoder` | `DenseSparseEncoder` | UC-03, UC-05 | 더미 벡터 금지. 다국어 dense + sparse/BM25 |
| `ChunkStore` | `MilvusChunkStore` | UC-03, UC-05 | `127.0.0.1:19530`, 컬렉션 `market_quality_chunks_hybrid`. C 행 금지. Lite 파일 백엔드 아님 |
| `ObjectStore` | `MinioObjectStore` | UC-03, UC-04 | `127.0.0.1:9000`, 버킷 `market-quality-docs`. Milvus 내부 MinIO와 합치지 않음 |
| `TabularExtractor` | `CalamineTabularExtractor` | UC-04 | polars/fastexcel. 프로파일 JSON 포함. Docling XLSX 백엔드 아님 |
| `TableStore` | `MariaDbTableStore` | UC-04, UC-05 | `127.0.0.1:3306`. 단위 테스트 더블만 DuckDB/in-memory |
| `McpServer` | `StdioMcpServer` | UC-05 | 조회 전용 |
| `CodexConfigExporter` | `TomlSnippetWriter` | UC-06 | 홈 설정 파일을 덮지 않음 |

단위 테스트는 위 Port의 가짜 구현(in-memory/fake)을 써도 된다. 통합 테스트는 표의 Adapter와 **이미 떠 있는** `01-stable` 컨테이너를 쓴다. 이 레포에서 compose로 인프라를 올리지 않는다. 포트가 닫혀 있으면 skip 마크로 명시.

---

## 실행 환경

| 항목 | 값 |
|------|-----|
| RUNTIME_MODE | `uv-native` |
| USE_GPU | `no` (PDF 레이아웃은 CPU. GPU는 후속) |
| 패키지 관리 | uv |
| 입고 CLI | `uv run python -m large_files_embedding ingest <path>` |
| MCP stdio | `uv run python -m large_files_embedding mcp` |
| 설정 스니펫 | `uv run python -m large_files_embedding configure-codex` |
| 스모크 | `uv run python -m large_files_embedding health` |
| 앱 중지 | `./scripts/stop.sh` |

실행 정책 상세: `AGENTS.md`. 앱은 uv-native. **인프라는 OrbStack/`orbctl`로 기동한 공유 스택** `~/dev/00.workspace/01-stable/{local-mariadb,local-milvus,local-minio}` 이다. 자격 증명은 그 디렉터리 `.env` / README를 따른다. 시크릿을 이 레포에 커밋하지 않는다.

---

## 인프라 서비스

공유 스택 정의: `~/dev/00.workspace/01-stable/`. 2026-09-05 점검 시 세 서비스 모두 `healthy`, 포트는 `127.0.0.1` only.

| UC-ID | 서비스 | 설정 | 포트 | 비고 |
|-------|--------|------|------|------|
| UC-02 | LibreOffice soffice | `DOCLING_LIBREOFFICE_CMD` 또는 PATH | — | OS 패키지. 한글 폰트 필요 |
| UC-03 | **Milvus standalone** `local-milvus` | `MILVUS_URI=http://127.0.0.1:19530` | 19530 gRPC, 9091 health, 8001 Attu | 컬렉션 `market_quality_chunks_hybrid`. Lite(`milvus.db`) 아님. 내부 `local-milvus-minio`는 호스트 포트 없음 |
| UC-03 | 임베딩 모델 | 다국어 dense (예: BGE-M3) | — | 로컬 가중치 또는 합의된 API. 더미 금지. MariaDB README의 `qwen3-embedding:4b`/VECTOR(2560) 스키마는 이 프로젝트 서술 경로가 아님 |
| UC-03/04 | **MinIO** `local-minio` | `MINIO_ENDPOINT=http://127.0.0.1:9000` | 9000 S3, 9001 콘솔 | 버킷 `market-quality-docs` (앱이 없으면 생성). `psychology-pdfs`/`ebook-pdfs`와 분리 |
| UC-04 | **MariaDB 11.8** `local-mariadb` | `127.0.0.1:3306`, DB는 앱 스키마 | 3306 | 표 2층. `embeddings.chunks` VECTOR에 서술 청크를 넣지 않음 |
| UC-05 | (없음) | UC-03/04 인덱스 읽기 | — | 입고 워커와 프로세스 분리 |

헬스 (구현 전·통합 테스트 전):

```bash
curl -fsS http://127.0.0.1:9091/healthz          # milvus → OK
curl -fsS http://127.0.0.1:9000/minio/health/live
nc -z 127.0.0.1 3306
```

기동/중지는 이 레포가 아니라 01-stable compose (OrbStack). 끄면 다른 워크스페이스(psychology, ebook)도 멈춘다.

---

## TDD 테스트 계획

| UC-ID | 단위 | 통합 | Red 시나리오 |
|-------|------|------|--------------|
| UC-01 | `tests/unit/large_files_embedding/test_route_file.py` | `tests/integration/large_files_embedding/test_route_file.py` | 확장자만 .doc인 OOXML은 가족 A. `{\rtf` 위장은 실패 큐 |
| UC-02 | `tests/unit/large_files_embedding/test_normalize_office.py` | `tests/integration/large_files_embedding/test_normalize_office.py` | timeout이 나면 hang으로 간주하고 실패한다. 원본은 남는다 |
| UC-03 | `tests/unit/large_files_embedding/test_ingest_narrative.py` | `tests/integration/large_files_embedding/test_ingest_narrative.py` | 마크다운 dump만 있는 청크는 거부. PPTX는 슬라이드 단위(노트 포함). 고정 길이 청크 거부 |
| UC-04 | `tests/unit/large_files_embedding/test_ingest_tabular.py` | `tests/integration/large_files_embedding/test_ingest_tabular.py` | xlsx 행 임베딩 요청은 도메인 예외. 원인/대책 칸 삭제는 거부 |
| UC-05 | `tests/unit/large_files_embedding/test_serve_mcp.py` | `tests/integration/large_files_embedding/test_serve_mcp.py` | query_tables에 DROP이 있으면 거부한다. 필터 인자 존재 |
| UC-06 | `tests/unit/large_files_embedding/test_configure_codex.py` | `tests/integration/large_files_embedding/test_configure_codex.py` | 빈 command면 예외. 홈 config.toml을 건드리지 않는다 |

순서: Red → Green → Refactor. 세부 규칙: `.grok/rules/testing.md`.

---

## 구현 Phase

| Phase | UC-ID | 작업 | 완료 조건 |
|-------|-------|------|-----------|
| 0 | — | `/scaffold` (pyproject, stop.sh, app shell, `health`) | `uv sync` + health 스모크. 게이트 파일 존재 |
| 1 | UC-01 | 시그니처 라우터 TDD | 단위·통합 Green. 가짜 확장자 재분류 |
| 2 | UC-02 | LibreOffice 정규화 TDD | timeout 테스트 Green. 원본 보존 |
| 3 | UC-03 | 서술 입고 (Docling JSON, 가족별 청크, 임베딩, Milvus) | DOCX 섹션 / PDF OCR 분기 / PPTX 슬라이드+노트 각각 검증. contextualize. 더미 벡터 없음 |
| 4 | UC-04 | 표 입고 (calamine, 프로파일 JSON, Parquet 1층→MinIO, MariaDB 2층) | Milvus에 행이 없음. 1층 원본 컬럼. 차트시트 스킵. 스냅샷 UNION 없음 |
| 5 | UC-05 | MCP 조회 서버 (필수 도구 전부) | 쓰기 SQL 거부. 인용 필드 존재 |
| 6 | UC-06 | Codex toml 스니펫 | 홈 파일을 수정하지 않음. `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest` 통과 |

`/implement-uc`는 UC 안에서 domain → application → infrastructure → presentation 순서를 지킨다. PLAN Phase를 UC당 3줄로 쪼개지 않는다.

---

## Definition of Done (UC)

- [ ] UC 상태 `done`
- [ ] 단위·통합 테스트 Green
- [ ] `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest` 통과
- [ ] PLAN 레이어 배치·Port 표와 구현 경로가 일치
- [ ] C 가족 행이 `ChunkStore`에 없음 (UC-04, UC-05). 카탈로그 설명 청크만 허용. 1층 원본 컬럼 유지
- [ ] 서술 청크는 `contextualize`. 고정 길이 dump·마크다운-only 인덱스 없음
- [ ] MCP 응답에 파일명+위치. 근거 없으면 없다고 답함. 표 숫자를 서술에서 지어내지 않음
- [ ] `/implement-uc` reviewer **bug 0**
- [ ] `/implement-uc` security-reviewer **bug 0** — presentation이 끝나는 UC: CLI는 UC-06, MCP는 UC-05 (`--effort` ≥ 2). `--effort 1`은 security 생략

---

## Grok 구현 가이드

PLAN `approved` 후. 부모는 코딩하지 않는다.

```text
/scaffold
# AGENTS.md 스캐폴드 마커 완료 후. implement-uc는 미완료면 시작하지 않음

/implement-uc UC-01
# 기본: write_uc_plan.py → coder → reviewer
# planner는 PLAN GWT/레이어가 비었을 때만. security는 presentation이 끝나는 UC
# /implement-uc all
# /implement-uc UC-01 --effort 3
```

구현 계획 산출: `.grok/uc-plans/UC-01.md` (`write_uc_plan.py`, Git ignore).

coder는 이 파일의 Port/Adapter 표를 따른다. `InMemory*`는 테스트 더블 이름이지 프로덕션 Infrastructure가 아니다.

대규모·모호하면 먼저:

```text
/design <기능 설명 — PLAN.md 참조>
```

설계 결과를 이 PLAN에 반영하고 `revised` → `approved` 후 `/implement-uc`.

---

## 리스크 & 의존성

| 항목 | 영향 | 대응 |
|------|------|------|
| 공유 인프라 다운 | 입고·MCP 전부 실패 | 헬스 URL을 health 커맨드에 포함. 이 레포에서 재기동하지 않고 01-stable을 안내 |
| 컬렉션/버킷 충돌 | psychology·ebook 데이터 오염 | 전용 컬렉션·버킷 이름만 사용 |
| soffice hang·프로필 락 (Docling #3819) | `.doc`/`.ppt` 입고가 멈춤 | timeout + 파일별 `UserInstallation`. 동시성 제한 |
| Docling 레이아웃/OCR 모델 최초 다운로드 | CI·오프라인 실패, 첫 실행 지연 | 모델 캐시 경로 문서화. 통합 테스트는 없으면 skip |
| 100MB xlsx/PDF 메모리 폭주 | 워커 OOM | calamine/polars 스트리밍. PDF는 페이지 스트림. openpyxl 전체 로드 금지 |
| 한글 폰트 없는 headless | 변환 본문 `□□` | Noto CJK/Nanum을 설치 전제로 두고 깨짐 검사 |
| 스캔 PDF를 디지털 경로에 넣음 | 검색 공백 | 텍스트 층 밀도로 OCR 분기 (UC-03) |
| 반복 헤더/푸터를 본문에 넣음 | 품번이 모든 페이지에 나와 검색 오염 | 헤더/푸터는 메타, 본문에서 제거 |
| 월보 스냅샷 UNION | 건수 중복 집계 | `report_period` 필수. 원장만 UNION |
| 양식 매핑 없이 MariaDB 전량 적재 | 숫자는 들어가고 의미가 틀림 | 1층 Parquet+프로필만. 2층은 매핑된 팩트 |
| RapidOCR 기본 lang / v6 korean 별칭 | 한글 스캔 깨짐 | `lang=["korean"]` PP-OCR v4/v5 |

---

## 변경 이력

| 날짜 | 버전 | 변경 | 승인 |
|------|------|------|------|
| 2026-09-05 | 0.1 | 초안 (init-project) | `draft` |
| 2026-09-05 | 0.2 | 리뷰 반영: Port/Adapter 실스토어, MCP 도구 목록 고정, UC-03 가족별 청크·임베딩, UC-06 스니펫만, Phase UC 단위, 리스크 | `draft` |
| 2026-09-05 | 0.3 | 공유 인프라: orbctl/01-stable MariaDB·Milvus·MinIO. Lite/DuckDB는 테스트 더블. 객체 스토어 Port 추가 | `draft` |
| 2026-09-05 | 0.4 | survey 대조: 메타 필터, parent-child, 표 카탈로그 청크, 스냅샷, 실패 큐, MCP 도구 라우팅·근거 없음 | `draft` |
| 2026-09-05 | 0.5 | survey 재대조: UC-04 제목 MariaDB, 프로파일 JSON·1층 원본 컬럼, contextualize, 헤더/푸터, RTF/한 열 CSV 실패 큐, antiword/xlrd/Docling XLSX 금지, PPTX 노트, TAG | `draft` |
