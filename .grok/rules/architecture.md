# 아키텍처 규칙 — large-files-embedding

> CA·DDD 전용. 실행·의존성 정책은 `AGENTS.md`, 테스트는 `testing.md`.

## 레이어 의존성

```
presentation → application → domain
infrastructure → application  (Port 구현)
```

의존 방향만 허용. **domain은 바깥을 모른다.**

| 레이어 | 책임 | 금지 |
|--------|------|------|
| domain | Entity, VO, Domain Service, **Repository Protocol** | 프레임워크·ORM·HTTP import |
| application | Use Case. domain Protocol에 의존. **외부 시스템 Port만** 여기 (메일, LLM API 등) | 구체 Adapter·프레임워크 의존 |
| infrastructure | Adapter (Repository·외부 Port 구현) | 비즈니스 규칙 |
| presentation | HTTP/CLI/Worker 어댑터 | Use Case 외 로직 |

## 패키지 배치 (권장)

```
src/large_files_embedding/
  domain/
  application/
  infrastructure/
  presentation/
    cli/
    mcp/
```

Bounded Context가 여럿이면 `src/large_files_embedding/<context>/...` 또는 패키지 분리. Python 기본 `PACKAGE_ROOT`는 `src/large_files_embedding`.

## DDD-lite

- Bounded Context 단위로 모델·용어 분리
- 용어는 `PLAN.md` Ubiquitous Language와 일치
- Anemic Domain Model 지양 (의미 있는 행위는 Entity/Domain Service)
- Repository는 Protocol(Port), 구현은 infrastructure
- **한 BC = 공유 domain 모듈 + UC별 application.** `domain/uc_01.py`처럼 UC마다 엔티티를 쪼개지 않는다. 다음 UC는 같은 엔티티·Port를 확장한다.

## Port & Adapter

- **저장 Repository Protocol은 domain.** PLAN Port 열이 비어 있지 않으면 기본이 이 계약이다.
- 메일·LLM·결제처럼 도메인 밖 시스템 Port만 application에 둔다.
- Infrastructure가 Adapter를 구현한다.
- Presentation은 Use Case만 호출 (Repo·ORM 직접 호출 금지).

## 금지

- `approved` 전 domain/application/infrastructure·UC별 tests 추가
- Presentation/Infrastructure에 비즈니스 규칙
- PLAN 범위 밖 Use Case
- 레이어 역의존 (domain → infrastructure 등)
