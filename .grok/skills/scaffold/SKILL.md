---
name: scaffold
description: >-
  Create the app skeleton from AGENTS.md (Python/uv default: pyproject, presentation
  shell, e2e smoke, compose or stop script). No domain/UC implementation.
  Use for /scaffold after /init-project and before /implement-uc.
when-to-use: >-
  User says /scaffold, "스캐폴드",
  or implement-uc stopped because the scaffold marker is missing.
argument-hint: "[--force]"
disable-model-invocation: true
---

# scaffold

`/init-project` 다음, `/implement-uc` 전에 **앱 골격만** 만든다. PLAN `approved`는 필요 없다.

완료 판정 SSOT: **`AGENTS.md` `### 스캐폴드 마커`의 게이트 표**. 파일 이름을 이 스킬에 복제하지 않는다.

Python(권장 기본)은 `.grok/skills/scaffold/templates/python/` 레시피를 `apply.py`가 적용한다. HTTP 골격은 **FastAPI/Starlette만**. Flask/Django는 FastAPI 파일로 바꾸지 않고, 해당 패키지 의존성만 넣는다 (HTTP 앱 모듈은 없음). 엔트리포인트는 항상 Typer라 typer 의존성을 넣는다. uv가 있으면 `uv.lock`과 생성 프로젝트 CI(`.github/workflows/ci.yml`)를 만든다. 비Python은 **실험적** — 1급 레시피 없음.

## 인자

- `--force`: 게이트가 완료여도 레시피를 다시 적용한다. 도메인·UC 테스트는 여전히 금지.

## 완료 판정

1. `AGENTS.md`에서 `### 스캐폴드 마커`를 찾는다. 없으면 `/init-project`를 안내하고 **중단**.
2. 그 섹션의 **게이트** 표를 행마다 검사한다 (존재 + 비어 있지 않음 + 섹션이 적은 추가 조건).
3. 하나라도 빠지면 **미완료**. 마커만 있고 게이트 파일이 없으면 `--force` 없이 이어서 생성한다.

게이트가 아닌 산출(앱 셸, Dockerfile, stop.sh, HTTP일 때만 e2e, `tests/unit/test_import.py`, 생성 CI)은 스캐폴드가 만들지만, 없어도 implement-uc를 막지 않는다.

## Step 0 — 게이트

1. 루트 `AGENTS.md`, `PLAN.md`를 읽는다. 없으면 `/init-project`를 안내하고 **중단**.
2. `.grok/scaffold-values.json`을 읽는다. 없으면 `/init-project` 안내 후 중단.
3. `.grok/rules/architecture.md`, `testing.md`, `python.md`(있으면)를 읽는다.
4. 완료 판정은 스크립트다. 성공이고 `--force`가 아니면: 이미 스캐폴드됨 → `/implement-uc`는 PLAN `approved` 필요함을 안내하고 **중단**.

   ```bash
   python3 .grok/skills/implement-uc/scripts/check_gates.py --scaffold-only
   ```

## Step 1 — 레시피 적용

부모가 앱 파일을 `write` / `search_replace`로 짜지 않는다. **스크립트를 실행**한다.

```bash
python3 .grok/skills/scaffold/scripts/apply.py
# --force 가 있으면 같은 인자를 붙인다
```

| 종료 코드 | 의미 | 다음 |
|-----------|------|------|
| 0 | Python 레시피 적용 | Step 2 |
| 2 | 비Python (실험적) | coder가 **게이트 매니페스트만** 생성. 도메인·UC 테스트 금지. 레시피를 발명하지 말 것 |
| 그 외 | 실패 | 에러 보고 후 중단 |

비Python coder 프롬프트 (exit 2일 때만 spawn):

```
앱 스캐폴드만 만든다. UC 도메인 구현과 UC별 tests/unit 은 금지.
이 언어는 1급 레시피가 없다 (실험적).
AGENTS.md ### 스캐폴드 마커 게이트 표의 매니페스트만 최소로 만든다.
domain / application / infrastructure 비즈니스 로직, UC별 tests/unit,
PLAN 승인 변경, git commit, README를 템플릿 사용 설명서로 덮어쓰기 금지.
```

`subagent_type`: `coder`. 같은 응답에서 `spawn_subagent`를 호출한 뒤에만 “띄웠다”고 쓴다.

## Step 2 — 검증

부모가 **실행만** 한다.

1. 완료 판정: `python3 .grok/skills/implement-uc/scripts/check_gates.py --scaffold-only`. 실패면 `--force`로 apply를 다시 하거나, 비Python이면 coder `resume_from`.
2. AGENTS 의존성 설치 명령이 있으면 실행. Python 기본은 `uv sync`. `uv` 없으면 설치를 안내하고 파일 생성은 성공으로 둔다.

## Step 3 — 보고

- 생성·수정 파일
- 설치 명령 결과
- 비Python이면 실험적 스캐폴드임을 명시
- 다음: PLAN `approved` 후 `/implement-uc UC-01` (이미 approved면 바로)

## 규칙

- Python 골격을 손으로 다시 짜지 않음 — `templates/python/` + `apply.py`
- `/implement-uc`로 도메인을 구현하지 않음
- 시크릿·`.env` 커밋 금지
