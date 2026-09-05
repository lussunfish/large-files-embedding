# placeholders.json

`/init-project` Step B 산출. **기계 필드는 `from_hello.py`가 쓴다** (공유 도메인·Port·UL·GWT 포함). LLM은 hello에 있는 필드명으로 GWT를 구체화할 때만 보강한다. UC별 `domain/uc_01.py`로 쪼개지 말 것. `render.py`가 프로젝트 파일을 만든다. `init/init.txt`는 필드 설명용이며 채우지 않는다.

위치: `init/placeholders.json`

hello에 없는 UC·환경 변수·리스크를 넣지 말 것. 없으면 빈 배열.

## 최상위 (문자열, 필수)

| 키 | 기본 (Python) | 비고 |
|----|----------------|------|
| `PROJECT_NAME` | hello 프로젝트명 | |
| `ONE_LINE_DESCRIPTION` | hello 한 줄 | |
| `DATE` | 오늘 `YYYY-MM-DD` | |
| `AUTHOR` | hello 없으면 `—` | |
| `LANGUAGE` | 미명시 시 `Python` | |
| `RUNTIME_VERSION` | Python `3.12` | |
| `PYTHON_PACKAGE` | 프로젝트명 snake_case (`todo-api` → `todo_api`). 한글만 있으면 `app` | 비Python이면 `—`. ASCII identifier |
| `PACKAGE_MANAGER` | `uv` | |
| `LOCKFILE` | `uv.lock` | |
| `PACKAGE_ROOT` | `src/<PYTHON_PACKAGE>` | |
| `WEB_FRAMEWORK` | FastAPI/Starlette/Flask/Django는 스택 그대로. Python HTTP면 FastAPI. Typer-only면 `—` | |
| `CLI_FRAMEWORK` | Python은 Typer (엔트리포인트) | |
| `TEST_FRAMEWORK` | Python만 pytest | |
| `LINT_FORMAT` | Python만 ruff | |
| `TYPECHECK` | Python만 mypy | |
| `DATABASE` | hello 스택, 없으면 `—` | UC에 없으면 인프라 행을 만들지 않음 |
| `RUNTIME_MODE` | Python+`## GPU`면 항상 `uv-native` (실행 모드보다 우선). 아니면 hello 실행 모드 / `docker-compose` | |
| `USE_GPU` | `no` / `yes` | |
| `DEV_MACHINE` | 없으면 `—` | |
| `ARCHITECTURE_STYLE` | Clean Architecture + DDD-lite | |
| `LAYERS` | domain → application → infrastructure → presentation | |
| `DOMAIN_MODELING` | DDD-lite (Entity, VO, Repository Protocol) | |
| `TEST_STRATEGY` | TDD (unit + integration) | |
| `PLAN_FIRST` | `yes` | |
| `REQUIRE_PLAN_APPROVAL` | `yes` | |
| `GIT_HOOKS` | `pre-commit optional (기본 수동 검사)` | |
| `PACKAGE_INSTALL_COMMAND` | `uv sync` | |
| `UNIT_TEST_COMMAND` | `uv run pytest tests/unit` | 비Python: hello, 없으면 `—` |
| `INTEGRATION_TEST_COMMAND` | `uv run pytest tests/integration` | 비Python: hello, 없으면 `—` |
| `LINT_COMMAND` | `uv run ruff check` | |
| `FORMAT_CHECK_COMMAND` | `uv run ruff format --check` | |
| `TYPECHECK_COMMAND` | `uv run mypy src` | |
| `PRE_COMMIT_COMMAND` | ruff + mypy + pytest | 비Python: hello, 없으면 `—` |
| `PRE_COMMIT_CHECKS` | 커밋 전 검사 목록 (markdown) | |
| `DEV_COMMAND` | `docker compose up -d` | |
| `STOP_COMMAND` | `docker compose down` | |
| `UV_DEV_COMMAND` | compose면 `— (미사용)` | |
| `UV_STOP_COMMAND` | compose면 `— (미사용)` | |
| `GOALS` | markdown 불릿 | |
| `NON_GOALS` | markdown 불릿 | |
| `SCOPE_INCLUDE` | 목표·기능 한 줄 요약 | |
| `SCOPE_EXCLUDE` | 비목표 한 줄 요약 | |
| `GROK_AGENT_RULES` | hello 추가 지시 (markdown) | 없으면 `—` |
| `BC_01_NAME` | 한 도메인이면 그 이름 | 추측이면 `notes`에 기록 |
| `BC_01_DESC` | | |
| `BC_01_PATH` | `PACKAGE_ROOT/` | |
| `PROJECT_STRUCTURE` | 예상 트리 코드블록 본문 (백틱 없이) | |
| `REFERENCES` | 없으면 `—` | |

`DEV_COMMAND_OR_UV` / `STOP_COMMAND_OR_UV` / `RUNTIME_ACTIVE_BLOCK` / `COMMANDS_TABLE` 은 **넣지 않음** — render가 `RUNTIME_MODE`로 만든다.

`TEMPLATE_VERSION` 도 넣지 않음 — `.grok/template-version`에서 읽는다.

## `use_cases` (배열, hello 기능과 1:1)

hello `## 기능` 항목 수와 같아야 한다. 없는 UC를 만들지 말 것. `UC-0N:` 없는 기능 줄은 from_hello가 빈 번호를 순서대로 부여한다.

```json
{
  "id": "UC-01",
  "name": "할 일 생성",
  "priority": "P0",
  "desc": "제목으로 할 일을 만든다",
  "given": "유효한 제목과 생성 API",
  "when": "생성 요청을 보낸다",
  "then": "할 일이 저장되고 id가 반환된다",
  "failure": "빈 제목은 거부한다",
  "domain": "todo.py",
  "application": "create_todo.py",
  "infrastructure": "in_memory_todo_repository.py",
  "presentation": "http/todos.py",
  "port": "TodoRepository",
  "adapter": "InMemoryTodoRepository",
  "unit_test": "tests/unit/todo_api/test_create_todo.py",
  "integration_test": "tests/integration/todo_api/test_create_todo.py",
  "red": "빈 제목이면 도메인 예외",
  "infra_service": null
}
```

`port` / `adapter` / `infra_service` 는 없으면 `null`. 전부 null이면 PLAN에 표 대신 한 줄.

테스트 경로를 비우면 render가 Python일 때 `tests/unit/<pkg>/test_<id>.py` 로 채운다. GWT(`given`/`when`/`then`/`failure`)는 비우지 말 것. hello에 없으면 기능 설명으로 쓰고 `notes`에 추측이라고 적는다.

## `env_vars` (배열)

hello `## 환경 변수`에 **있는 것만**. 섹션이 없거나 비면 `[]`.

```json
{
  "name": "LOG_LEVEL",
  "desc": "로그 수준",
  "required": "no",
  "example": "info"
}
```

## `risks` (배열)

hello에 리스크가 있을 때만. 없으면 `[]` (지어내지 말 것).

```json
{
  "item": "…",
  "impact": "…",
  "mitigation": "…"
}
```

## `ubiquitous_language` (배열, 선택)

Python이면 from_hello가 엔티티 한 줄을 넣는다. 없으면 `[]`. `{ "term", "definition", "context" }`.

## `notes` (배열, 선택)

추측한 키/값. 예: `["BC_01_NAME 은 프로젝트명에서 추론"]`.
