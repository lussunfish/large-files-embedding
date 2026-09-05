# 테스트 규칙 — large-files-embedding

> TDD·테스트 배치 전용. PLAN의 TDD 표가 UC별 Red 시나리오 SSOT.

## TDD (`PLAN` approved 후)

1. **Red** — PLAN Red 시나리오에 맞는 실패 테스트
2. **Green** — 최소 구현
3. **Refactor** — 테스트 유지하며 정리
4. PLAN.md UC 상태 갱신

## 배치

| 종류 | 경로 | 대상 |
|------|------|------|
| 단위 | `tests/unit/` | domain, application (가짜 Port) |
| 통합 | `tests/integration/` | infrastructure + 실제/테스트 컨테이너 |
| e2e 스모크 | `tests/integration/test_app_e2e.py` | 앱 기동·health (스캐폴드 허용) |

## 규칙

- 새 동작 = 새(또는 갱신) 테스트 없이 머지하지 않음
- 단위 테스트는 프레임워크·DB 없이 빠르게
- 통합 테스트는 외부 의존을 명시적으로 준비 (`docker compose up` 등)
- 테스트 이름: 동작·조건이 드러나게 (`test_create_todo_rejects_empty_title`)
- 과도한 mock 지양 — domain은 실객체, Port 경계에서만 대체

## 명령

- 단위: `uv run pytest tests/unit`
- 통합: `uv run pytest tests/integration`
- 전체(커밋 전): `uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest`

## 금지

- `approved` 전 UC별 테스트 추가 (e2e 스캐폴드 제외)
- “일단 구현하고 테스트는 나중에”
- flaky 테스트 방치 (재시도로 숨기지 말 것)
