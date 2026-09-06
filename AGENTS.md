# large-files-embedding

> Grok Build 프로젝트 규칙. `init/`에서 생성됨. 팀 공유 시 Git 커밋.
> 규칙 로드 확인: `grok inspect`

## 프로젝트 개요

시장품질 문서(PDF/DOCX/DOC/XLSX/XLS/CSV/PPTX/PPT)를 입고하고 Grok MCP로 조회하는 로컬 서비스

| 항목 | 값 |
|------|-----|
| 언어 | Python 3.12 |
| 패키지 관리 | uv |
| 잠금 파일 | uv.lock |
| 실행 모드 | `uv-native` (앱). 인프라는 공유 OrbStack 컨테이너 |
| 아키텍처 | Clean Architecture + DDD-lite |
| 테스트 | TDD (unit + integration) |

구현 범위·UC·Phase: **`PLAN.md`** (SSOT).

## prompt-log (결정 저널)

| 항목 | 정책 |
|------|------|
| 위치 | `prompt-log/` (README, INDEX, 주제별 `*.md`) |
| 용도 | 설계·제품 결정의 **근거·히스토리** (대화 전문 아카이브 아님) |
| 갱신 | **`/log` 또는 사용자가 로그 기록을 명시한 때만** — 매 턴 자동 갱신 금지 |
| Git | **추적함** (`.gitignore`에 넣지 않음) |
| SSOT | 범위·구현 권위는 `PLAN.md` / 이 파일. 결정이 범위에 영향 주면 PLAN·AGENTS에도 반영 |
| 읽기 | 매 턴 전체 로드 금지. `INDEX.md` → 관련 주제 파일만 |
| 금지 | 시크릿·API 키, 오타/포맷만 있는 잡음, 대화 복붙 |

스킬: `.grok/skills/log/SKILL.md` (`/log`).

## PLAN-first (필수)

`PLAN.md`의 `## 계획 승인`이 **`approved`**일 때만 UC 구현·UC별 테스트 시작.

| 시점 | 허용 | 금지 |
|------|------|------|
| `approved` 전 | PLAN 작성·갱신, `/scaffold`¹ | `domain/` `application/` `infrastructure/`, UC별 tests |
| `approved` 후 | TDD (Red → Green → Refactor) | PLAN 범위 밖 UC |

### 스캐폴드 마커

`/scaffold` 완료 · `/implement-uc` 시작 조건. **이 섹션이 권위.** 스킬은 여기 적힌 파일만 검사하고 목록을 다시 적지 않는다.

**게이트 (모두: 존재 + 비어 있지 않음):**

| 조건 | 파일 |
|------|------|
| LANGUAGE=Python | `pyproject.toml` (`[project]` 또는 `[tool.` 포함) |
| Node / TypeScript | `package.json` |
| Go | `go.mod` |
| Rust | `Cargo.toml` |
| 그 외 | 패키지 관리 매니페스트 1개 |
| 실행 모드 `docker-compose` | `docker-compose.yml` |

**게이트가 아닌 스캐폴드 산출** (없으면 `/scaffold`가 채움, implement-uc는 막지 않음): 앱 셸, compose면 `Dockerfile`, `uv-native`면 `scripts/stop.sh`. HTTP presentation이 있을 때만 `tests/integration/test_app_e2e.py`. Python HTTP 골격은 FastAPI/Starlette만 (Flask/Django는 FastAPI로 치환하지 않음). `[project].name`은 패키지명의 PEP 508 형식.

¹ `/scaffold`: 위 게이트 파일 + 게이트 아닌 산출. 마커만 있고 게이트 파일이 빠졌으면 `--force` 없이 이어서 채움.

범위 변경: PLAN 수정 → 상태 `revised` → 재승인(`approved`) → 구현.

### 계획 파일 우선순위

1. **프로젝트 `PLAN.md`** — 구현 범위의 최종 권위
2. `.grok/uc-plans/<UC-ID>.md` — `/implement-uc` planner 산출 (how, Git ignore)
3. `/design` 산출 설계 문서 — 대규모·모호한 기능 (PLAN에 반영 후 구현)
4. 세션 `plan.md` (`/plan`) — 임시 설계안, 세션 한정

## 필수 개발 방식

- PLAN approved 전 domain/ 신규 코드 금지
- 커밋 전 ruff + mypy + pytest
- `survey/` 는 조사 산출물이며 앱 소스와 섞지 말 것. 포맷 SSOT: `survey/format-pipelines/README.md` + `01`–`08`. 상위: `survey/market-quality-rag-improvement.md`, `survey/excel-to-sql-decision.md`, `survey/xlsx-20-samples-layer1.md`, `survey/docx-pipeline.md`, `survey/doc-format-handling.md`
- 09+ (HWP, MD/TXT/HTML, 메일, CAD 등 가족 E/F/G/H)는 PLAN 밖. 라우터에 없으면 실패 큐. `search_hwp` 같은 포맷별 MCP 도구 금지
- MCP는 조회만, 입고는 CLI. 클라이언트는 **Grok**(stdio). `search` 하나만 두지 말 것. 숫자→`query_tables`(TAG), 대책/원인→`get_section`, 품번/코드→`search_passages`(sparse+필터)
- `~/.grok/config.toml`과 `~/.codex/config.toml`을 덮어쓰지 말 것. 연동은 저장소 스니펫(`deploy/grok-mcp.toml`) 또는 프로젝트 `.grok/config.toml`의 `[mcp_servers.*]`
- 도구 인자 `product`/`period`/`doc_type`. 모델이 자연어에서만 뽑게 두지 말 것
- 응답에 파일명+페이지/시트/섹션. 근거 없으면 “근거 없음”. 표 숫자를 서술 청크에서 지어내지 말 것
- VBA/매크로 실행 금지. 실패 파일은 빈 문서로 인덱싱하지 말 것
- 임베딩 입력은 `chunk.text`가 아니라 `chunker.contextualize(chunk)`. 고정 길이 슬라이딩 윈도우·마크다운 dump 인덱스 금지
- 반복 헤더/푸터는 메타. 본문 청크에 매 페이지 반복 금지
- soffice는 timeout + 파일별 `UserInstallation`. 동시 실행 제한. 원본 삭제 금지. antiword/catdoc/catppt 금지
- **인프라는 이 레포 compose가 아니다.** `~/dev/00.workspace/01-stable/{local-mariadb,local-milvus,local-minio}` (OrbStack/`orbctl`). 끄면 다른 프로젝트도 멈춘다
- Milvus 컬렉션은 `market_quality_chunks_hybrid`만. `psychology_chunks_hybrid` / `ebook_chunks_hybrid`에 쓰지 말 것
- MinIO 버킷은 `market-quality-docs`. `psychology-pdfs` / `ebook-pdfs` 및 Milvus 내부 MinIO와 합치지 말 것
- MariaDB는 표 2층(`claim_event` / `monthly_quality_kpi`)과 UC-07 입고 원장(`ingest_manifest`)만. `embeddings.chunks` VECTOR에 서술 청크를 넣지 말 것 (벡터는 Milvus). 내용 해시 스킵 인덱스를 MinIO에 두지 말 것
- 서술 dense 임베딩은 호스트 **Ollama** `qwen3-embedding:4b` (`http://127.0.0.1:11434`). sentence-transformers로 BGE-M3를 기본 경로로 두지 말 것. 같은 모델이어도 MariaDB VECTOR에 서술 청크를 넣지 말 것
- 시크릿은 `01-stable` `.env`에서 읽고 이 레포에 커밋하지 말 것

### 가족별 (01–08)

| 가족 | 하라 | 하지 말 것 |
|------|------|------------|
| A Word | SimplePipeline JSON, HybridChunker `contextualize`+`repeat_table_header`, parent-child, 표는 `chunk_type=table` | DOCX→PDF, python-docx로 `.doc`, 표를 본문에 섞기 |
| B PDF | StandardPdfPipeline, RapidOCR `lang=["korean"]`, 페이지 스트림, 차트 추출은 선택 | 마크다운 dump, lang `chinese`, 통째 메모리, PDF→DOCX, VLM으로 디지털 전체 대체 |
| C 표 | calamine/polars 스트리밍 → 프로파일 JSON + Parquet 1층(원본 컬럼) → MariaDB 팩트. `.xls`는 calamine 1순위 | 행 임베딩, 시트 1:1 테이블, Docling XLSX/CSV 백엔드, openpyxl/pandas 전체 로드, xlrd, 월보를 period 없이 UNION, 원인/대책 칸 삭제, 100MB를 LLM 컨텍스트에 |
| D 슬라이드 | 1장=1청크(제목+본문+노트), 표는 table 객체 | PPTX→PDF, 전 슬라이드 blob, HybridChunker로 슬라이드 쪼개기, python-pptx로 `.ppt` |

### 멀티에이전트 (`/implement-uc`)

부모는 오케스트레이션만 한다. 소스·테스트는 `coder`만 수정.

| 순서 | 역할 | 에이전트 |
|------|------|----------|
| 1 | UC 계획 | `write_uc_plan.py` (PLAN GWT/레이어 공백일 때만 planner) |
| 2 | TDD 구현 | `.grok/agents/coder.md` |
| 3 | 리뷰 | `.grok/agents/reviewer.md`. security는 같은 presentation의 마지막 UC |
| 4 | bug 0까지 수정 루프 | coder resume. open 이슈가 있는 리뷰어만 재실행 |

기본 `/implement-uc UC-01` = effort 2 (reviewer. security는 정책). `--effort 3`이면 `.grok/agents/tests.md` 리뷰 추가. `/implement-uc all`은 남은 UC를 **순차** 실행 (병렬 금지, 부모는 이전 UC 본문을 다음 프롬프트에 넣지 않음). 서브에이전트 깊이 1. `--effort 1`은 security를 생략한다.

모델은 모두 부모와 같음 (`grok-4.6` 등). reasoning effort: planner `high`, coder/reviewer `medium`, security-reviewer `high`.

### 구현 순서 (`approved` 후)

1. PLAN에서 UC-ID·Phase·Red 시나리오 확인
2. `write_uc_plan.py` (또는 planner)
3. coder: 실패 테스트 → Domain → Application → Infrastructure → Presentation. 공유 domain은 확장
4. reviewer. security는 같은 presentation의 마지막 남은 UC만
5. 커밋 전 검사 통과: `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest`
6. PLAN.md UC 상태 갱신 (`planned` → `in_progress` → `done`) — **reviewer bug 0** 후. security를 띄운 UC는 security bug 0도

## 실행 정책

**활성 모드: `uv-native`**

- 앱·CLI: 호스트 `uv run`
- 인프라: **이미 떠 있는** 공유 컨테이너 (아래). 이 레포에서 `docker compose up` 하지 않음
- 개발 도구: 호스트 `uv run`
- 앱 중지: `./scripts/stop.sh` (인프라 컨테이너는 중지하지 않음)

### 공유 인프라 (OrbStack)

정의: `~/dev/00.workspace/01-stable/`. 자격·기동 방법은 그 README.

| 서비스 | 컨테이너 | 호스트 | 용도 |
|--------|----------|--------|------|
| MariaDB 11.8 | `local-mariadb-mariadb-1` | `127.0.0.1:3306` | 표 2층 SQL |
| Milvus 2.5.4 | `local-milvus` | `127.0.0.1:19530` (gRPC), `:9091` health, `:8001` Attu | 서술 벡터 |
| MinIO | `local-minio` | `127.0.0.1:9000` S3, `:9001` 콘솔 | 원본·파생 객체 |

Milvus 스택 안의 `local-milvus-minio` / `local-milvus-etcd`는 내부 전용이다. 앱은 `local-minio`만 쓴다.

서술 dense는 OrbStack이 아니라 호스트 **Ollama** (`127.0.0.1:11434`, 모델 `qwen3-embedding:4b`). 이 레포에서 Ollama를 compose하지 않는다.

```bash
curl -fsS http://127.0.0.1:9091/healthz
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9000/minio/health/live
nc -z 127.0.0.1 3306
curl -fsS http://127.0.0.1:11434/api/tags   # qwen3-embedding:4b
```

## 명령어

### 앱 워크로드 (uv-native)

| 작업 | 명령어 |
|------|--------|
| 실행 | `uv run python -m large_files_embedding health` (인프라 헬스 포함) |
| 입고 | `uv run python -m large_files_embedding ingest <path>` |
| MCP | `uv run python -m large_files_embedding mcp` |
| 앱 중지 | `./scripts/stop.sh` (공유 컨테이너는 그대로) |

### 공통 (항상 호스트 uv)

| 작업 | 명령어 |
|------|--------|
| 의존성 설치 | `uv sync` |
| 단위 테스트 | `uv run pytest tests/unit` |
| 통합 테스트 | `uv run pytest tests/integration` |
| 린트 | `uv run ruff check` |
| 포맷 검사 | `uv run ruff format --check` |
| 타입 검사 | `uv run mypy src` |
| 커밋 전 검사 | `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest` |

## Git commit 전 검사

- `uv run ruff format --check`
- `uv run ruff check`
- `uv run mypy src`
- `uv run pytest`

- 위 커밋 전 검사 전체 통과 후에만 커밋
- `git commit --no-verify` 금지 (사용자가 명시 요청한 경우만 예외)

## 안전·범위

- `.env`, API 키, 시크릿 커밋 금지 (`.env.example`만 허용)
- 요청·PLAN 범위 밖 리팩터·의존성 추가 금지
- 앱 골격은 `/scaffold`, UC 구현은 `/implement-uc` — 부모는 `src/`·UC 테스트를 직접 수정하지 않음
- 파괴적 git(`reset --hard`, force-push)은 사용자 확인 후
- 공유 시스템 변경(원격 push, PR 생성) 전 확인

## 세부 규칙 (자동 로드)

| 파일 | 내용 |
|------|------|
| `.grok/rules/architecture.md` | 레이어·DDD |
| `.grok/rules/testing.md` | TDD·테스트 배치 |
| `.grok/rules/python.md` | uv·ruff·mypy |

## Grok Build 워크플로우

| 단계 | 방법 |
|------|------|
| 규칙 확인 | `grok inspect` |
| 앱 골격 | `/scaffold` (implement-uc 전 필수) |
| UC 구현 | `/implement-uc UC-01` 또는 `/implement-uc all` |
| 결정 저널 | `/log` — `prompt-log/<주제>.md` + INDEX 갱신 (명시 시에만) |
| 모호한 설계 | `/design …` → 결과를 PLAN에 반영 → 승인 |
| 다수 PR 스택 | `/design` 후 `/execute-plan <design-doc>` |
| 로컬 리뷰 (UC 파이프라인 밖) | `/review` |
| 검증 | 위 커밋 전 검사 |
| PR 모니터링 | `/pr-babysit` |

UC 구현은 `/implement-uc`가 기본 경로다. 내장 `/implement`만 쓸 때도 설명에 **`PLAN.md` + UC-ID**를 넣는다.

생성 템플릿: grok-template 0.5.0
