# large-files-embedding — 구현 계획

> **구현 SSOT.** `approved` 전 프로덕션·UC별 테스트 코드 작성 금지.
> 스캐폴드는 `AGENTS.md` 참조.
> Grok 세션 `plan.md`(`/plan`)와 별개 — **이 파일이 우선.**
> 조사 산출물 `survey/` 는 앱 소스가 아니다. 범위 해석이 막히면 `survey/format-pipelines/01-pdf.md` … `08-ppt.md`를 읽는다.

## 계획 승인

| 항목 | 값 |
|------|-----|
| 상태 | `draft` |
| 승인자 | — |
| 승인일 | — |

**상태**: `draft` · `approved` · `revised` (재승인 필요)

승인 전 체크:

- [ ] 목표·비목표 합의 (스캔 OCR은 UC-03에 포함)
- [ ] UC 우선순위·수용 기준 명확 (MCP 도구 목록이 닫혀 있음)
- [ ] 실행 모드·명령어 확인
- [ ] Phase 완료 조건이 검증 가능 (어댑터가 인메모리가 아님)

---

## 목표

- 01–08 포맷을 시그니처 기준으로 라우팅해 서술 문서는 벡터, 표는 SQL로 입고한다
- HybridChunker JSON 청크를 **공유 Milvus**(`127.0.0.1:19530`)에 넣고, 엑셀/CSV는 Parquet 랜딩 후 **MariaDB**로 조회한다
- 원본·파생 객체는 **공유 MinIO**(`127.0.0.1:9000`) 버킷에 둔다
- Codex CLI에 stdio MCP를 연동해 담당자가 근거 있는 인사이트를 얻는다
- Clean Architecture + TDD, 호스트 uv로 개발·실행

## 비목표

- 09번 이후 포맷(HWP, 메일, CAD 등)의 이번 범위 구현
- 엑셀/CSV 행을 Milvus에 임베딩
- GraphRAG, ColQwen 전체 재인덱스
- 엑셀 시트마다 MariaDB 테이블을 1:1로 만드는 전량 적재
- 이 레포에서 Milvus/MinIO/MariaDB compose를 새로 띄우기 (`01-stable` 공유 스택을 쓴다)
- 공유 MariaDB의 `embeddings.chunks` VECTOR 테이블에 서술 청크를 넣기 (벡터는 Milvus)
- 웹 UI, 클라우드 전용 파서 API
- 사용자 홈의 `~/.codex/config.toml`을 직접 덮어쓰기 (스니펫만 생성)
- ColQwen/ColPali 페이지 비전 인덱스 (후속)

## 범위

### 포함

- UC-01: 시그니처로 가족 A/B/C/D 라우팅
- UC-02: `.doc`/`.ppt` LibreOffice 정규화 (원본 보존)
- UC-03: PDF/DOCX/PPTX 서술 입고 (Docling JSON, 공유 Milvus 컬렉션, 임베딩)
- UC-04: XLSX/XLS/CSV 표 입고 (calamine/polars, Parquet→MinIO, 조회는 MariaDB). 행 임베딩 금지
- UC-05: MCP 조회 전용 도구 (목록은 UC-05 수용 기준)
- UC-06: Codex용 stdio MCP `config.toml` **스니펫 생성**

### 제외

- 09번 이후 포맷
- 엑셀/CSV 행 임베딩
- GraphRAG, ColQwen 전체 재인덱스, 시트 1:1 MariaDB 테이블
- `01-stable` 밖 인프라 중복 기동
- 웹 UI, 클라우드 전용 파서 API

---

## Bounded Context

| ID | 이름 | 설명 | 경로 |
|----|------|------|------|
| BC-01 | Document | 01–08 포맷 입고(서술=공유 Milvus, 표=MariaDB, 객체=MinIO)와 MCP 조회 | `src/large_files_embedding/` |

### Ubiquitous Language

| 용어 | 정의 | Context |
|------|------|---------|
| Document | 입고 대상 시장품질 파일. 가족 A/B/D는 서술, C는 표 | BC-01 |
| 가족 | A Word형, B PDF형, C 정형 표, D 슬라이드 | 라우팅 |
| 서술 청크 | Milvus에 넣는 텍스트/표 객체. C 가족 행이 아님 | UC-03, UC-05 |
| 표 카탈로그 | MariaDB에 적재된 시트 스키마·팩트. 1층 행은 Parquet(MinIO) | UC-04, UC-05 |

---

## Use Case

| UC-ID | Use Case | Context | 우선순위 | 상태 | Red 테스트 |
|-------|----------|---------|----------|------|------------|
| UC-01 | 파일 시그니처로 포맷을 판별하고 가족(A/B/C/D)으로 라우팅한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_route_file.py` |
| UC-02 | .doc/.ppt를 LibreOffice로 현대 포맷으로 정규화한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_normalize_office.py` |
| UC-03 | PDF/DOCX/PPTX를 Docling JSON·HybridChunker로 청크해 Milvus에 넣는다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_ingest_narrative.py` |
| UC-04 | XLSX/XLS/CSV를 calamine/polars로 Parquet·DuckDB에 넣는다 (행 임베딩 금지) | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_ingest_tabular.py` |
| UC-05 | MCP 조회 도구(search_passages, get_section, query_tables 등)를 제공한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_serve_mcp.py` |
| UC-06 | Codex CLI config.toml에 stdio MCP를 연동한다 | BC-01 | P0 | `planned` | `tests/unit/large_files_embedding/test_configure_codex.py` |

상태: `planned` · `in_progress` · `done` · `deferred` · `cancelled`

의존: UC-02는 라우팅 결과(정규화 대상)가 필요하다. UC-03/04는 UC-01 뒤에. UC-05는 UC-03·04가 저장한 인덱스를 읽는다. UC-06은 UC-05 엔트리포인트가 있어야 한다.

### UC 수용 기준 (Given/When/Then)

#### UC-01 — 파일 시그니처로 포맷을 판별하고 가족(A/B/C/D)으로 라우팅한다

- **Given**: PDF/OOXML/OLE/CSV 시그니처를 가진 파일이 있다
- **When**: 입고 라우터에 경로를 넘긴다
- **Then**: 가족 A/B/C/D와 정규화 대상 여부(`.doc`/`.ppt`만 soffice)가 반환된다. `.xls`는 가족 C이며 1순위는 calamine이다
- **실패/경계**: 알 수 없는 시그니처는 실패 큐로 보내고 배치를 멈추지 않는다. 확장자만 `.doc`인 OOXML은 가족 A로 재분류한다

#### UC-02 — .doc/.ppt를 LibreOffice로 현대 포맷으로 정규화한다

- **Given**: OLE `.doc` 또는 `.ppt`와 soffice가 있다
- **When**: 정규화를 요청한다
- **Then**: 원본은 유지하고 `.docx`/`.pptx` 파생물과 메타(`converted_from`, `converter=libreoffice`)가 생긴다. 호출은 timeout과 파일별 `UserInstallation`을 쓴다
- **실패/경계**: timeout·soffice 부재는 failed로 남기고 원본을 삭제하지 않는다

#### UC-03 — PDF/DOCX/PPTX를 Docling JSON·HybridChunker로 청크해 Milvus에 넣는다

- **Given**: PDF 또는 DOCX 또는 PPTX가 있다. 임베딩 인코더(다국어 dense)가 설정되어 있다
- **When**: 서술 입고를 실행한다
- **Then**:
  - 원본 옆에 Docling JSON을 보관한다. 마크다운 dump만으로 인덱싱하지 않는다
  - **DOCX (가족 A)**: SimplePipeline + HybridChunker(`contextualize`, `repeat_table_header=True`). 청크 키는 섹션 경로
  - **PDF (가족 B)**: 텍스트 층이 있으면 StandardPdfPipeline. 희소/스캔 페이지는 RapidOCR `lang=["korean"]`. 표는 별도 청크. (차트 추출 `--enrich-chart-extraction`은 있으면 켜고, 없어도 UC를 막지 않는다)
  - **PPTX (가족 D)**: 슬라이드 1장 = 청크 1개 (제목+본문+노트). HybridChunker 섹션 분할로 슬라이드를 쪼개지 않는다
  - 각 청크는 dense 벡터로 **공유 Milvus** `127.0.0.1:19530` 컬렉션 `market_quality_chunks_hybrid`에 들어간다. psychology/ebook 컬렉션과 섞지 않는다. 품번·코드를 위해 sparse/BM25를 같이 넣는다. 더미 영벡터 금지. JSON/원본은 MinIO 버킷 `market-quality-docs`에도 올린다
- **실패/경계**: 암호 PDF·빈 문서는 인덱싱하지 않는다. 마크다운 dump만 있는 청크는 거부한다

#### UC-04 — XLSX/XLS/CSV를 calamine/polars로 Parquet·DuckDB에 넣는다 (행 임베딩 금지)

- **Given**: xlsx/xls/csv 파일이 있다
- **When**: 표 입고를 실행한다
- **Then**: 시트 단위 Parquet 1층을 MinIO(`market-quality-docs`)에 올리고, 조회용 2층은 **MariaDB** `127.0.0.1:3306` (앱이 만드는 DB/스키마, 예: `market_quality`). 공유 서버의 `embeddings.chunks` VECTOR 테이블은 쓰지 않는다. 메타에 `source_file`, `sheet_name`, `report_period`(알 수 있으면), `ingested_at`을 넣는다. CSV는 utf-8-sig 또는 cp949. 피벗·차트시트는 적재하지 않는다. **Milvus 청크는 없다**
- **실패/경계**: 행을 벡터 컬렉션에 넣으려 하면 도메인 예외. 시트마다 테이블 1개로 전량 적재하지 않는다. openpyxl로 100MB 전체를 로드하지 않는다. `.xls` calamine 실패만 LibreOffice 폴백

#### UC-05 — MCP 조회 도구(search_passages, get_section, query_tables 등)를 제공한다

- **Given**: 서술 청크(공유 Milvus)와 표 카탈로그(MariaDB)가 있다
- **When**: 아래 도구를 호출한다
- **Then**: 각 응답에 파일명과 페이지 또는 시트 또는 섹션 경로가 붙고, 본문은 짧게 자른다
- **필수 도구 (이 목록이 닫힌 수용 기준이다)**:
  - `list_documents`
  - `search_passages` (하이브리드 + 가능하면 rerank)
  - `get_outline`
  - `get_section`
  - `get_table` (문서 안 표 청크)
  - `get_page` (PDF)
  - `list_slides` / `get_slide` (PPTX)
  - `list_tables` / `describe_table` / `query_tables` (MariaDB, **읽기 전용**, LIMIT 강제)
- **실패/경계**: 허용 스키마 밖 SQL·쓰기(`DROP`/`DELETE`/`INSERT`/`UPDATE`)는 거부한다. 입고·삭제는 MCP에 두지 않는다

#### UC-06 — Codex CLI config.toml에 stdio MCP를 연동한다

- **Given**: UC-05 stdio MCP 엔트리포인트가 있다
- **When**: 연동 설정을 생성한다
- **Then**: 저장소 안 스니펫(예: `deploy/codex-mcp.toml`)이 나온다. 키: `command`, `args`, `cwd`, `startup_timeout_sec`(≥30), `tool_timeout_sec`. **홈 디렉터리 `~/.codex/config.toml`을 수정하지 않는다**
- **실패/경계**: command가 비면 거부한다

---

## 아키텍처 설계

도메인은 UC마다 쪼개지 않는다. `domain/document.py`에 가족·시그니처·청크/표 레코드 규칙을 둔다. 저장 Port는 역할별로 나눈다. **인메모리 어댑터는 단위 테스트 더블일 뿐, PLAN Infrastructure 열이 아니다.**

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
| `OfficeNormalizer` | `LibreOfficeNormalizer` | UC-02 | timeout + `UserInstallation` |
| `NarrativeParser` | `DoclingNarrativeParser` | UC-03 | JSON 보관. 가족 A/B/D 분기 |
| `EmbeddingEncoder` | `DenseSparseEncoder` | UC-03, UC-05 | 더미 벡터 금지. 다국어 dense + sparse/BM25 |
| `ChunkStore` | `MilvusChunkStore` | UC-03, UC-05 | `127.0.0.1:19530`, 컬렉션 `market_quality_chunks_hybrid`. C 행 금지. Lite 파일 백엔드 아님 |
| `ObjectStore` | `MinioObjectStore` | UC-03, UC-04 | `127.0.0.1:9000`, 버킷 `market-quality-docs`. Milvus 내부 MinIO와 합치지 않음 |
| `TabularExtractor` | `CalamineTabularExtractor` | UC-04 | polars/fastexcel |
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
| UC-01 | `tests/unit/large_files_embedding/test_route_file.py` | `tests/integration/large_files_embedding/test_route_file.py` | 확장자만 .doc인 OOXML은 가족 A로 재분류한다 |
| UC-02 | `tests/unit/large_files_embedding/test_normalize_office.py` | `tests/integration/large_files_embedding/test_normalize_office.py` | timeout이 나면 hang으로 간주하고 실패한다 |
| UC-03 | `tests/unit/large_files_embedding/test_ingest_narrative.py` | `tests/integration/large_files_embedding/test_ingest_narrative.py` | 마크다운 dump만 있는 청크는 거부한다. PPTX는 슬라이드 단위 |
| UC-04 | `tests/unit/large_files_embedding/test_ingest_tabular.py` | `tests/integration/large_files_embedding/test_ingest_tabular.py` | xlsx 행 임베딩 요청은 도메인 예외 |
| UC-05 | `tests/unit/large_files_embedding/test_serve_mcp.py` | `tests/integration/large_files_embedding/test_serve_mcp.py` | query_tables에 DROP이 있으면 거부한다 |
| UC-06 | `tests/unit/large_files_embedding/test_configure_codex.py` | `tests/integration/large_files_embedding/test_configure_codex.py` | 빈 command면 예외. 홈 config.toml을 건드리지 않는다 |

순서: Red → Green → Refactor. 세부 규칙: `.grok/rules/testing.md`.

---

## 구현 Phase

| Phase | UC-ID | 작업 | 완료 조건 |
|-------|-------|------|-----------|
| 0 | — | `/scaffold` (pyproject, stop.sh, app shell, `health`) | `uv sync` + health 스모크. 게이트 파일 존재 |
| 1 | UC-01 | 시그니처 라우터 TDD | 단위·통합 Green. 가짜 확장자 재분류 |
| 2 | UC-02 | LibreOffice 정규화 TDD | timeout 테스트 Green. 원본 보존 |
| 3 | UC-03 | 서술 입고 (Docling JSON, 가족별 청크, 임베딩, Milvus) | DOCX 섹션 / PDF OCR 분기 / PPTX 슬라이드 각각 검증. 더미 벡터 없음 |
| 4 | UC-04 | 표 입고 (calamine, Parquet→MinIO, MariaDB) | Milvus에 행이 없음. 인코딩·차트시트 스킵 |
| 5 | UC-05 | MCP 조회 서버 (필수 도구 전부) | 쓰기 SQL 거부. 인용 필드 존재 |
| 6 | UC-06 | Codex toml 스니펫 | 홈 파일을 수정하지 않음. `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest` 통과 |

`/implement-uc`는 UC 안에서 domain → application → infrastructure → presentation 순서를 지킨다. PLAN Phase를 UC당 3줄로 쪼개지 않는다.

---

## Definition of Done (UC)

- [ ] UC 상태 `done`
- [ ] 단위·통합 테스트 Green
- [ ] `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest` 통과
- [ ] PLAN 레이어 배치·Port 표와 구현 경로가 일치
- [ ] C 가족 행이 `ChunkStore`에 없음 (UC-04, UC-05)
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
| 100MB xlsx 메모리 폭주 | 워커 OOM | calamine/polars 스트리밍. openpyxl 전체 로드 금지 |
| 한글 폰트 없는 headless | 변환 본문 `□□` | Noto CJK/Nanum을 설치 전제로 두고 깨짐 검사 |
| 스캔 PDF를 디지털 경로에 넣음 | 검색 공백 | 텍스트 층 밀도로 OCR 분기 (UC-03) |

---

## 변경 이력

| 날짜 | 버전 | 변경 | 승인 |
|------|------|------|------|
| 2026-09-05 | 0.1 | 초안 (init-project) | `draft` |
| 2026-09-05 | 0.2 | 리뷰 반영: Port/Adapter 실스토어, MCP 도구 목록 고정, UC-03 가족별 청크·임베딩, UC-06 스니펫만, Phase UC 단위, 리스크 | `draft` |
| 2026-09-05 | 0.3 | 공유 인프라: orbctl/01-stable MariaDB·Milvus·MinIO. Lite/DuckDB는 테스트 더블. 객체 스토어 Port 추가 | `draft` |
