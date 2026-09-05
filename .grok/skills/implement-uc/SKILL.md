---
name: implement-uc
description: >-
  Implement PLAN.md Use Cases via coder → reviewer, with planner/security only
  when policy says so. One UC-ID, or all remaining UCs sequentially.
  Parent orchestrates only.
when-to-use: >-
  User says /implement-uc, "UC 구현", "implement UC-01", "/implement-uc all",
  "전체 UC 구현", or asks to build use cases from PLAN.md after approval.
argument-hint: "UC-ID | all [--effort N]"
disable-model-invocation: false
---

# implement-uc

**PLAN.md SSOT + TDD**로 UC를 구현한다. 부모는 오케스트레이터다. 소스·테스트는 **coder 서브에이전트만** 수정한다.

한 번에 여러 UC를 띄우지 않는다. `all`이어도 **한 UC가 done된 뒤에만** 다음 UC로 간다. 깊이 1이라 `all`을 자식 파이프라인으로 감쌀 수 없다. 대신 **UC 경계에서 부모 컨텍스트를 비운다** (아래 `all` 규칙).

역할 정의: `.grok/agents/{planner,coder,reviewer,security-reviewer}.md` (effort ≥ 3이면 `tests.md`)

| 역할 | `subagent_type` | 산출 |
|------|-----------------|------|
| planner | `planner` | UC 구현 계획 (읽기 전용) |
| coder | `coder` | 코드·테스트·summary |
| reviewer | `reviewer` | 리뷰 파일 |
| security-reviewer | `security-reviewer` | 보안 리뷰 파일 |
| tests (effort ≥ 3) | `tests` | 테스트 리뷰 파일 |

서브에이전트 깊이 1 — 자식은 spawn하지 못한다. 부모가 planner·coder·리뷰어를 띄운다.

## 인자

- 필수: `UC-ID` (예: `UC-01`) 또는 `all`
- 선택: `--effort N` (1–3, **기본 2**)

| 호출 | 동작 |
|------|------|
| `/implement-uc UC-01` | 그 UC만 |
| `/implement-uc all` | 남은 UC를 PLAN 순서로 **순차** 실행 |

`all` 대기열: 상태가 `planned` 또는 `in_progress`인 행. `done` / `cancelled` / `deferred`는 건너뜀. 정렬: Phase 표 순서 → 우선순위(P0이 앞) → UC-ID.

`all`에서 한 UC가 실패하면 **거기서 멈춘다**. 나머지 UC는 시작하지 않는다. 재개는 `/implement-uc all` (남은 것만) 또는 `/implement-uc UC-0N`.

병렬 `all` 금지 (공유 워크트리, UC 의존).

| Effort | 리뷰 |
|--------|------|
| 1 | reviewer만 |
| 2 | reviewer. security는 **같은 presentation의 마지막 남은 UC만** (기본) |
| 3 | reviewer + security(정책 동일) + tests specialist |

## 부모 금지 / 허용

금지: `src/`, `tests/`, 앱 코드에 `write` / `search_replace`. 구현·수정 서술만 하고 spawn하지 않는 것. 스캐폴드는 `/scaffold`.

허용:

- `PLAN.md` UC 상태·Phase 체크만
- `.grok/uc-plans/` 산출물
- `uc_policy.py` / `write_uc_plan.py` / `check_uc_plan.py` / `check_gates.py` 실행
- 읽기, grep, 커밋 전 검사 **실행**(수정 없이)
- `spawn_subagent`

## 산출 경로

워크스페이스 상대 경로. 런 동안 바꾸지 않음.

- `plan_file`: `.grok/uc-plans/<UC-ID>.md`
- `summary_file`: `.grok/uc-plans/<UC-ID>-summary.md`
- `review_file`: `.grok/uc-plans/<UC-ID>-review.md`
- `security_file`: `.grok/uc-plans/<UC-ID>-security.md` (`need_security`일 때)
- `tests_file`: `.grok/uc-plans/<UC-ID>-tests.md` (effort ≥ 3)
- `merged_file`: `.grok/uc-plans/<UC-ID>-review-merged.md`

`.grok/uc-plans/`는 Git ignore. 없으면 디렉터리 생성.

## Tool-call

`spawn_subagent`를 **같은 응답에서** 호출한 뒤에만 “띄웠다”고 과거형으로 보고한다. 서술만 하고 호출하지 말 것.

`description` 접두: `[planner]`, `[coder]`, `[reviewer]`, `[security]`, `[tests]`.

커스텀 타입이 없으면(알 수 없는 type):

| 원래 | fallback | 프롬프트 |
|------|----------|----------|
| `planner` | `plan` | `.grok/agents/planner.md` 본문을 앞에 붙임 |
| 나머지 | `general-purpose` | 해당 `.grok/agents/*.md` 본문을 앞에 붙임 |

시작 시 에이전트 파일 4개(effort ≥ 3이면 `tests.md`까지)를 `read_file`로 읽어 둔다. fallback에 쓴다.

`resume_from` 시 페르소나/에이전트 본문은 다시 붙이지 않는다. description 태그는 유지.

---

## Step 0 — 게이트

1. 루트 `PLAN.md`, `AGENTS.md`를 읽는다.
2. `.grok/rules/architecture.md`, `testing.md`, `python.md`(있으면)를 읽는다. AGENTS에서 커밋 전 검사 명령을 기억한다.
3. 게이트는 스크립트로 **한꺼번에** 검사한다. 실패하면 stderr를 모두 보고하고 **중단** (승인만 말하고 스캐폴드 누락을 숨기지 않음). 파일 목록을 이 스킬에 적지 말 것.

   ```bash
   python3 .grok/skills/implement-uc/scripts/check_gates.py
   ```

   - PLAN `## 계획 승인`이 `approved`가 아님 → 승인 방법 안내.
   - 스캐폴드 미완료 → `/scaffold`. `### 스캐폴드 마커`가 없으면 `/init-project`.
   - 스크립트가 없으면(구버전 복사본) 같은 규칙을 수동으로: 승인 표 + AGENTS 게이트 표.
4. 대기열을 만든다.
   - 단일: 해당 `UC-ID` 행. 없으면 중단. `done` / `cancelled` / `deferred`이면 재구현하지 말고 안내 후 중단.
   - `all`: 위 규칙으로 큐를 짠다. 비어 있으면 “남은 UC 없음” 보고 후 중단. 큐를 사용자에게 한 줄로 알린 뒤 첫 UC부터 진행 (승인 질문 없이). `todo_write`로 큐의 UC-ID를 적어 compaction 후에도 순서를 유지.

이후 Step 1–8을 **큐의 UC마다** 반복한다. UC가 바뀔 때마다 coder/reviewer/security는 **새로 spawn** (`resume_from`은 그 UC 안에서만). 산출 경로의 `<UC-ID>`를 현재 UC로 바꾼다.

`all` 실패 시: 해당 UC는 `in_progress`로 두고, 한 줄 원인 + 남은 큐를 보고 중단. 성공한 UC는 `done` 유지.

### `all` — 부모 컨텍스트

플랫폼이 서브에이전트 깊이 1이라 UC 워커를 중첩할 수 없다. 부모가 큐를 들고 순차 spawn하되:

1. 이전 UC의 plan/review/summary **본문을 다음 UC 프롬프트에 넣지 않는다.**
2. 이전 UC 판정은 `uc_policy.py --open-reviews`와 PLAN 상태 한 줄만 사용한다.
3. 다음 UC 프롬프트는 해당 UC-ID, PLAN·AGENTS 경로, `plan_file` 경로만.
4. 큐는 `todo_write` + PLAN.md. 이전 리뷰를 요약해서 들고 가지 말 것.
5. compaction 후 복구: PLAN + todo 큐 + `uc_policy.py`. 이전 리뷰 파일을 다시 읽지 말 것.

## Step 1 — 범위

구현 범위는 다음만:

- PLAN의 해당 UC 수용 기준·레이어·TDD 표·Phase
- AGENTS 명령어·커밋 전 검사
- `plan_file` (`write_uc_plan.py` 또는 planner)

범위 밖 파일·UC·리팩터 금지. **예외:** PLAN이 이 UC에 적은 공유 `domain/`·Port·Adapter는 범위 안 (확장만, `domain/uc_NN.py`로 쪼개지 않음). 필요하면 PLAN `revised` → 재승인을 안내하고 **코딩하지 않음**.

## Step 2 — 상태

PLAN.md에서 해당 UC 상태를 `in_progress`로 갱신 (아직이면). 다른 PLAN 섹션은 건드리지 않음.

`.grok/uc-plans/` 디렉터리가 없으면 만든다.

## Step 3 — 계획 (기본: 스크립트)

큐의 이 UC에 대해 정책을 한 번 읽는다. 이후 Step 5도 이 JSON을 쓴다.

```bash
python3 .grok/skills/implement-uc/scripts/uc_policy.py --uc <UC-ID> --effort N --queue <큐를 쉼표로>
```

- `need_planner: false` (기본, PLAN에 GWT·레이어가 있을 때):

  ```bash
  python3 .grok/skills/implement-uc/scripts/write_uc_plan.py --uc <UC-ID>
  python3 .grok/skills/implement-uc/scripts/check_uc_plan.py <plan_file>
  ```

  planner를 spawn하지 않는다.

- `need_planner: true` (GWT/레이어 공백): `spawn_subagent` planner (`background: false`, `[planner] Plan <UC-ID>`).

프롬프트 (planner를 띄울 때만):

```
PLAN.md의 <UC-ID>만 구현 계획으로 짠다. 공유 domain/Port를 UC별 파일로 쪼개지 말 것.

읽을 것: PLAN.md (해당 UC·레이어·TDD·Phase), AGENTS.md,
.grok/rules/architecture.md, testing.md, python.md(있으면), 관련 소스.

- 프로젝트 PLAN.md가 SSOT (세션 plan.md 무시)
- TDD: 실패 테스트 → 최소 구현 → 리팩터
- 레이어: Domain → Application → Infrastructure → Presentation
- 범위 밖 UC·파일을 계획에 넣지 말 것
- 소스를 수정하지 말 것

최종 응답에 스킬이 요구한 섹션을 그대로 포함할 것:
PLAN revision needed / Scope / Critical files / TDD / Layers / Existing reuse / Risks
```

완료 후 응답에서 계획 본문을 추출해 `plan_file`에 **부모가** `write`한다 (planner는 읽기 전용). 이어서 `check_uc_plan.py`. 필수 섹션이 없으면 planner를 `resume_from`으로 한 번 더. 그래도 실패하면 중단.

`PLAN revision needed`가 `yes`이면: 이유 보고, PLAN 수정·재승인 안내, **Step 4로 가지 않고 중단**. UC 상태는 `in_progress`로 두거나 사용자에게 되돌릴지 묻는다.

## Step 4 — Coder

`spawn_subagent`:

- `subagent_type`: `coder`
- `background`: `false`
- `description`: `[coder] Implement <UC-ID>`

프롬프트:

```
PLAN.md의 <UC-ID>만 구현한다.

- 구현 계획: <plan_file>
- PLAN.md가 SSOT (세션 plan.md 무시)
- TDD: 실패 테스트 → 최소 구현 → 리팩터
- 레이어: Domain → Application → Infrastructure → Presentation
- AGENTS.md 커밋 전 검사 통과
- 범위 밖 변경 금지. PLAN이 적은 공유 domain/Port/Adapter는 범위 안 (확장만)
- git commit 하지 말 것 (사용자가 요청한 경우만 프롬프트에 명시됨)

완료 후 요약을 <summary_file>에 쓴다: 변경 파일, 추가/수정 내용, 설계 결정.
```

실패하면 에러 보고 후 중단. `subagent_id`를 저장해 수정 라운드에 `resume_from`.

완료 후 부모가 커밋 전 검사 명령을 **실행**한다 (코드는 안 고친다). 실패하면 리뷰로 가지 않고 coder를 `resume_from`으로 고쳐 재실행한다. 통과한 뒤에만 Step 5.

## Step 5 — Reviewers

effort에 따라 병렬 (`background: true`).

공통: summary와 변경을 읽고, 각자 파일에 이슈를 쓴다. 소스 수정 금지.

### reviewer

- `subagent_type`: `reviewer`
- `description`: `[reviewer] Review <UC-ID>`

```
coder가 <UC-ID>를 구현했다.

구현 계획: <plan_file>
요약: <summary_file>
PLAN.md의 해당 UC 수용 기준과 계획이 지켜졌는지, TDD·레이어·버그를 본다.

리뷰를 <review_file>에 쓴다.
형식: ## Summary, ## Issues, 각 Issue는 Severity bug|suggestion|nit, File path:line, Description, Suggestion, Status: open.
이슈가 없으면 Issues를 비운다.
```

### security-reviewer (`need_security: true`일 때만)

effort ≥ 2이어도 같은 presentation의 마지막 남은 UC가 아니면 건너뛴다 (`uc_policy.py`).

- `subagent_type`: `security-reviewer`
- `description`: `[security] Review <UC-ID>`

```
coder가 <UC-ID>를 구현했다. 보안만 본다.

요약: <summary_file>
입력 경계, 인증/인가, 인젝션, 시크릿, 로그 노출.

리뷰를 <security_file>에 쓴다.
Severity는 bug|suggestion|nit 만 사용 (critical/high → bug).
형식은 reviewer와 동일. 소스 수정 금지.
```

### tests (effort ≥ 3만)

- `subagent_type`: `tests`
- `description`: `[tests] Review <UC-ID>`
- 에이전트: `.grok/agents/tests.md` (없으면 fallback `general-purpose` + 본문 prepend)

```
테스트 커버리지·품질만 리뷰한다. 스타일·보안은 다른 리뷰어가 본다.
요약: <summary_file>
PLAN Red 시나리오와 경계/에러 경로가 테스트됐는지.
리뷰를 <tests_file>에 쓴다. 형식은 reviewer와 동일 (bug|suggestion|nit, Status: open).
소스 수정 금지.
```

모두 끝나면 `get_command_or_subagent_output`으로 대기. reviewer 실패는 중단. 이 UC에서 security를 띄웠으면 실패도 중단 (DoD). 건너뛴 security는 bug 0으로 치지 않고 기록만 한다. tests 실패는 경고 후 나머지 진행.

각 `subagent_id` 저장 (재리뷰 `resume_from`).

## Step 6 — 병합·종료 판정

각 리뷰 파일을 읽는다. 이슈 제목이 `### Issue N -- Severity: (bug|suggestion|nit)` 인 것만 센다.

security를 띄웠거나 tests가 있으면 `merged_file`에 합친다. 태그: `[Reviewer]`, `[Security]`, `[Tests]`. 같은 파일·줄·원인 중복은 하나 남긴다.

`bug` = 이 라운드에 있는 리뷰 파일의 bug 합.

판정:

1. **bug == 0** (첫 리뷰부터 또는 수정 후): Step 7.
2. **bug > 0**: Step 6b (coder resume).
3. **stalemate**: 직전 라운드 `wontfix`를 리뷰어가 다시 `open` — 사용자에게 묻고, 결정을 coder 프롬프트에 넣어 재개.
4. **라운드 4 초과**이고 bug 남음: UC를 `done`으로 올리지 말고 남은 bug를 보고 중단.

suggestion/nit는 coder에게 넘긴다. **2라운드 이후** suggestion/nit만 남으면 막지 않고 Step 7 (최종 보고에 남김).

### Step 6b — Fix

`spawn_subagent`:

- `subagent_type`: `coder`
- `resume_from`: coder id
- `description`: `[coder] Fix <UC-ID> review`

```
리뷰 이슈를 고친다. 병합 파일: <merged_file> (effort 1이면 <review_file>)

Status: open 인 항목을 다룬다. 동의 → 수정 후 Status: fixed + Response.
반대 → Status: wontfix + 기술 근거. 사용자 결정은 최종이다.

커밋 전 검사를 다시 통과할 것. git commit 하지 말 것.
```

완료 후 **open 이슈가 남은 리뷰 파일만** 재리뷰:

```bash
python3 .grok/skills/implement-uc/scripts/uc_policy.py --open-reviews <review_file> [security_file] [tests_file]
```

`rerun` 목록의 리뷰어만 `resume_from` (병렬). security가 이 UC에서 이미 clean이면 다시 돌리지 않는다.

- 고친 이슈는 재목록하지 않음
- 미해결·회귀는 `Status: open`
- 범위는 초기 리뷰와 동일

다시 Step 6.

## Step 7 — PLAN·검증

bug == 0일 때만:

1. 커밋 전 검사 명령을 부모가 다시 실행. 실패하면 coder resume 후 Step 6으로.
2. PLAN: 해당 UC `done`, 관련 Phase·DoD 체크. 레이어/Port 표는 coder가 이미 갱신했으면 중복 수정하지 않음. 비어 있으면 구현 요약 기준으로 **표만** 채움 (서술 장문 금지).

이 UC에서 security를 돌렸고 bug 0이면:

```bash
python3 .grok/skills/implement-uc/scripts/uc_policy.py --record-security <presentation>
```

`git commit`은 사용자가 요청한 경우만.

## Step 8 — 보고

- 변경 파일
- 테스트·커밋 전 검사 결과
- 리뷰: 라운드 수, bug/suggestion/nit, security 실행/연기 여부 (`uc_policy` 이유)
- 남은 suggestion/nit (있으면)
- PLAN 갱신
- 산출 경로 (`plan_file`, 리뷰 파일)
- 다음 UC (PLAN 우선순위). `all`이면 큐 전체 표: UC-ID / 결과(done·stopped·skipped) / bug 수
- 커밋하지 않았으면 그 사실
- `all`이고 큐가 남았으면 재개 명령: `/implement-uc all` 또는 실패한 `/implement-uc <UC-ID>`

## 규칙

- `approved` 전 UC 구현 금지. 스캐폴드는 `/scaffold` (이 스킬이 하지 않음)
- AGENTS `### 스캐폴드 마커` 게이트 미완료면 구현 시작 금지
- 시크릿·`.env` 커밋 금지
- `/implement` 내장 루프로 대체하지 말 것. 이 스킬이 planner와 프로젝트 에이전트 타입을 쓴다.
- 부모 최종 메시지에 “내가 구현했다”고 쓰지 말 것. coder가 구현했다.
