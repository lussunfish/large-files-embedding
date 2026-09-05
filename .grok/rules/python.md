# Python / uv 규칙 — large-files-embedding

> Python일 때만 생성. 다른 언어면 이 파일을 만들지 않음.

## 패키지·환경

- 의존성·venv: **uv만** (`pip install`, `python -m venv`, poetry 직접 사용 금지)
- 잠금: `uv.lock` 커밋 필수 (`/scaffold`가 uv가 있으면 `uv lock`으로 생성)
- 설치: `uv sync`
- 실행: `uv run <cmd>`

## 품질 도구

| 도구 | 용도 | 명령 |
|------|------|------|
| ruff | 린트·포맷 | `uv run ruff check`, `uv run ruff format --check` |
| mypy | 타입 | `uv run mypy src` |
| pytest | 테스트 | `uv run pytest` |

커밋 전: `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest`

## 코드 스타일

- 공개 함수·Use Case에 타입 힌트
- `Any` 남용 금지; 경계(외부 JSON 등)에서만 좁혀서 사용
- 예외: 도메인/유스케이스 의미 있는 예외, presentation에서 HTTP/CLI로 매핑
- 설정: 시크릿은 환경 변수 (코드·커밋 금지)

## 레이아웃

- 패키지 루트: `src/large_files_embedding/`
- 테스트는 `tests/` (src 레이아웃 유지)

## 금지

- 컨테이너 안에서 ruff/mypy/pytest를 “정식 검사”로 대체 (호스트 `uv run`이 SSOT)
- `requirements.txt`를 잠금 파일 대신 사용 (필요 시 export는 부가)
