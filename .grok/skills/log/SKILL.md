---
name: log
description: >-
  Update prompt-log topic/decision markdown (not a chat transcript dump).
  Creates or revises prompt-log/<slug>.md and INDEX.md only when invoked.
  Use for /log, "결정 로그", "prompt-log에 남겨".
when-to-use: >-
  User says /log, "로그 남겨", "결정 기록", "prompt-log",
  or explicitly asks to capture a design/product decision in markdown.
argument-hint: "[topic-slug | \"topic title\"] [open|decided|superseded]"
disable-model-invocation: false
---

# log (prompt-log)

대화 전문을 덤프하지 않는다. **주제/결정 단위 md**를 짧게 생성·갱신한다.

## 인자

| 형태 | 예 |
|------|-----|
| 없음 | 직전 대화에서 주제·결정을 추론. 모호하면 슬러그·상태를 확인 |
| 슬러그 | `auth-jwt-vs-session` |
| 제목 | `"Repository를 Protocol로 둔 이유"` → 슬러그 추론 |
| 상태 | `open` \| `decided` \| `superseded` (기본: 맥락상 결정이면 `decided`, 아니면 `open`) |

## 전제

1. 워크스페이스 루트에 `prompt-log/`가 있어야 한다.
2. 없으면: init 미실행이거나 삭제된 상태 → `prompt-log/README.md`, `INDEX.md`를 템플릿 수준으로 생성한 뒤 진행할지 **사용자에게 확인**.
3. 시크릿·API 키·토큰·개인정보를 쓰지 않는다.

## Step 0 — 주제 확정

1. 슬러그: `kebab-case`, 영문 권장, 기존 파일과 충돌 시 기존 파일을 갱신할지 확인.
2. 제목: 한 줄.
3. 상태: `open` / `decided` / `superseded`.
4. 관련: UC-ID, PLAN 섹션, 이슈 등 (없으면 `—`).
5. 기록할 내용이 “남길 가치 없음”(오타·포맷만)이면 **파일을 만들지 않고** 이유를 짧게 알린 뒤 종료.

## Step 1 — 본문 작성/갱신

경로: `prompt-log/<slug>.md`

### 신규

`prompt-log/_topic.md.template`이 있으면 그 형식을 따르고, 없으면 아래 골격:

```markdown
# <Title>

| 항목 | 값 |
|------|-----|
| 슬러그 | `<slug>` |
| 상태 | open \| decided \| superseded |
| 관련 | UC-01, … |
| 최종 갱신 | YYYY-MM-DD |

## 요약

(2–4문장)

## 결정

(결정문 1–3문장. open이면 “아직 미결정”과 후보)

## 근거

- …

## 기각한 대안

| 대안 | 기각 이유 |
|------|-----------|
| … | … |

## 히스토리

### YYYY-MM-DD

- …
```

### 기존 파일

- 표 메타(상태·관련·최종 갱신) 갱신
- 요약/결정/근거/기각 대안을 **덮어쓰거나 보강** (대화 전문 append 금지)
- `## 히스토리`에 오늘 날짜 섹션을 **앞에 추가** (최신이 위)

작성 원칙:

- 대화 복붙 ❌ → 압축된 결정·근거만
- 한 주제 파일은 대체로 한 화면 안(대략 80줄 이하) 유지. 길어지면 하위 주제로 분리 제안
- 최종 결정이 구현 범위에 영향을 주면 PLAN/AGENTS 반영 필요 여부를 보고에 명시

## Step 2 — INDEX 갱신

`prompt-log/INDEX.md` 표에 행 추가 또는 수정:

| 열 | 내용 |
|----|------|
| 주제 | 제목 |
| 파일 | `[slug](./slug.md)` |
| 상태 | open / decided / superseded |
| 한 줄 요약 | 결정 한 줄 |
| 관련 | UC 등 |
| 최종 갱신 | YYYY-MM-DD |

플레이스홀더 행(`_(없음 — …)_`)이 있으면 첫 실항목 추가 시 제거.

## Step 3 — 보고

- 생성/수정한 파일 경로
- 상태·한 줄 요약
- PLAN/AGENTS 동기화 필요 여부 (필요하면 제안만; 사용자가 요청하기 전 대규모 PLAN 수정 금지)
- 커밋은 사용자가 요청할 때만

## 하지 말 것

- `/log` 없이 매 응답마다 prompt-log 자동 갱신
- 날짜별 롤링 파일로 대화를 통째로 저장
- prompt-log 전체를 매 턴 컨텍스트에 로드 (INDEX → 필요 주제만)
- 시크릿·`.env` 내용 기록
- git commit (명시 요청 시에만)
