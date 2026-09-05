# large-files-embedding

시장품질 문서(PDF/DOCX/DOC/XLSX/XLS/CSV/PPTX/PPT)를 입고하고 Codex CLI MCP로 조회하는 로컬 서비스

| 항목 | 값 |
|------|-----|
| 언어 | Python 3.12 |
| 패키지 | uv |
| 실행 모드 | `uv-native` |
| 구현 범위 | [`PLAN.md`](PLAN.md) |

## 요구 사항

- Python 3.12+
- uv
- `docker-compose` 모드면 Docker Compose

## 실행

### 앱 워크로드 (uv-native)

| 작업 | 명령어 |
|------|--------|
| 실행 | `uv run python -m large_files_embedding health` |
| 중지 | `./scripts/stop.sh` |

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

커밋 전: `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest`

구현 절차는 [`AGENTS.md`](AGENTS.md) (`/scaffold` → PLAN `approved` → `/implement-uc`). 결정 기록: `/log`.
