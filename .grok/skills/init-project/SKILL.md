---
name: init-project
description: >-
  Bootstrap a new project from hello.txt using init/ templates.
  from_hello.py writes init/placeholders.json from hello.txt, then render.py
  generates AGENTS.md, PLAN.md, README.md, .grok/rules/, and prompt-log/.
  Use when starting from grok-template, or when asked to init / bootstrap project rules.
when-to-use: >-
  User says /init-project, "프로젝트 초기화", "hello.txt로 init",
  "AGENTS.md 생성", or copies grok-template and wants Step 1–2 done.
argument-hint: "[--keep-init] [path-to-hello.txt]"
disable-model-invocation: true
---

# init-project

`grok-template` 워크플로우 Step 1–2. **생성 파일은 `render.py`가 쓴다.** AGENTS/PLAN/README를 손으로 만들지 말 것.

값 기본: `init/GENERATION_RULES.md`. JSON 모양: `.grok/skills/init-project/scripts/SCHEMA.md`.

## 입력

1. `hello.txt` (기본: 워크스페이스 루트; 인자로 경로 지정 가능)
2. `init/GENERATION_RULES.md`
3. `init/*.template`, `init/.grok/rules/*.template`

`hello.txt`가 없으면 `hello.txt.example`을 알리고 복사·편집을 안내한 뒤 **중단**.

## Step A — 사전 확인

1. 워크스페이스 루트인지 확인.
2. `init/`와 `init/GENERATION_RULES.md`가 없으면 이 스킬 대상이 아님 → 안내 후 중단.
3. 이미 `AGENTS.md` + `PLAN.md`가 있고 덮어쓰기를 원하지 않으면 확인 후 중단 가능.
4. `hello.txt` 읽기.

## Step B — placeholders.json

기계 필드는 스크립트가 채운다. LLM이 JSON을 처음부터 쓰지 말 것.

```bash
python3 .grok/skills/init-project/scripts/from_hello.py
# 옵션: --hello path/to/hello.txt
```

`init/placeholders.json`이 생긴 뒤 **보강만** 한다.

1. SCHEMA.md와 GENERATION_RULES.md를 읽는다. `init/init.txt`는 필드 설명용 — **채우지 않음**.
2. `from_hello.py`가 채운 값: 프로젝트명, 언어, 실행 모드, GPU, UC id/이름, env, uv 명령, **공유 도메인·Port·UL·GWT**. **덮어쓰지 말 것** (잘못 파싱된 경우만 수정).
3. hello `## 기능` 항목만 `use_cases`. `UC-0N:`이 없는 줄은 `from_hello.py`가 순서대로 ID를 부여한다. 없는 기능을 만들지 말 것.
4. hello `## 환경 변수`에 있는 것만 `env_vars`. 없으면 `[]`.
5. hello에 리스크가 있을 때만 `risks`. 없으면 `[]` (지어내지 말 것).
6. 레이어는 **BC 공유 domain + UC별 application**이다. `domain`/`port`/`adapter`를 UC마다 다른 파일로 쪼개지 말 것. hello에 필드명(제목 등)이 있을 때만 GWT를 구체화. 빈 GWT는 금지.
7. **RUNTIME_MODE:** Python + 비어 있지 않은 `## GPU` → `uv-native` (**`## 실행 모드`보다 우선**). GPU가 없으면 hello 실행 모드(없으면 `docker-compose`). GPU여도 비Python → hello 실행 모드(없으면 `docker-compose`). 본문·비목표·주석에서 GPU/Metal을 찾지 말 것.
8. FastAPI HTTP 레시피는 `WEB_FRAMEWORK`가 FastAPI/Starlette일 때만. Flask/Django는 FastAPI 골격으로 바꾸지 말 것.
9. `RUNTIME_ACTIVE_BLOCK`, `COMMANDS_TABLE`, `DEV_COMMAND_OR_UV`, `TEMPLATE_VERSION` 은 JSON에 넣지 않음 (render가 계산).
10. 추측은 `notes` 배열. `init/` 템플릿 파일은 수정하지 않음.

골든 예: `init/fixtures/todo-api/placeholders.json` (`hello.txt.example` 기준).

## Step C — render

루트에서:

```bash
python3 .grok/skills/init-project/scripts/render.py
```

실패하면 JSON을 고치고 다시 실행. 생성 파일을 손으로 고쳐서 통과시키지 말 것.

## Step D — validate

```bash
python3 .grok/skills/init-project/scripts/validate.py
```

실패하면 JSON을 고치고 **render부터** 다시. validate가 통과할 때까지 생성 파일을 직접 패치하지 말 것.

추가로 확인:

- `.grok/agents/{planner,coder,reviewer,security-reviewer}.md` 존재 (init 비생성). 없으면 경고. `--effort 3`용 `tests.md`도 권장.
- 사용자에게 `grok inspect` 권장.

## Step E — 정리

- `--keep-init`이면 유지하고 Step F로.
- 없으면 `init/`, 루트 `TEMPLATE.md`, `.grok/skills/init-project/`, `scripts/new-project.py`를 삭제해도 되는지 **확인** 후 승인 시 삭제.
- **삭제하지 말 것**: `.grok/skills/scaffold`, `implement-uc`, `log`; `.grok/agents/`; `.grok/roles/`; `.grok/rules/`(생성본); `AGENTS.md`; `PLAN.md`; `README.md`; `prompt-log/`; `.grok/scaffold-values.json`; `hello.txt`(사용자 선택).
- `hello.txt` 삭제는 제안만 (기본 유지).

## Step F — 다음 단계

1. `PLAN.md` 검토
2. `/scaffold` — 앱 골격. `/implement-uc`는 스캐폴드 마커 없이 시작하지 않음
3. PLAN 승인 상태를 `approved`로 변경
4. `/implement-uc UC-01` 또는 `/implement-uc all`
5. 모호하면 `/design` 먼저, 결과를 PLAN에 반영
6. 결정 기록: `/log`

## 규칙

- hello에 없는 UC·env·리스크를 지어내지 말 것.
- 생성 파일은 render.py만 기록한다.
- 이 스킬은 규칙/계획/프로젝트 README 생성만. 앱 골격은 `/scaffold`. domain은 `/implement-uc`.
- hello에 언어가 없으면 Python/uv **권장 기본**. 다른 언어면 중단하지 말고 JSON 명령을 치환. 비Python 스캐폴드는 실험적.
