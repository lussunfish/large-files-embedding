from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import uc_policy  # noqa: E402
import write_uc_plan  # noqa: E402

PLAN = """# demo

## Use Case

| UC-ID | Use Case | Context | 우선순위 | 상태 | Red 테스트 |
|-------|----------|---------|----------|------|------------|
| UC-01 | 할 일 생성 | BC-01 | P0 | `planned` | `tests/unit/todo_api/test_create_todo.py` |
| UC-02 | 할 일 목록 조회 | BC-01 | P0 | `planned` | `tests/unit/todo_api/test_list_todos.py` |
| UC-03 | 할 일 완료 처리 | BC-01 | P0 | `planned` | `tests/unit/todo_api/test_complete_todo.py` |

### UC 수용 기준 (Given/When/Then)

#### UC-01 — 할 일 생성

- **Given**: 유효한 제목
- **When**: 생성 요청을 보낸다
- **Then**: 할 일이 저장되고 id가 반환된다
- **실패/경계**: 빈 제목은 거부한다

#### UC-02 — 할 일 목록 조회

- **Given**: 할 일이 여러 개 있다
- **When**: 목록을 요청한다
- **Then**: 필터에 맞는 항목만 반환된다
- **실패/경계**: 알 수 없는 필터 값은 거부한다

#### UC-03 — 할 일 완료 처리

- **Given**: 미완료 할 일이 있다
- **When**: 완료 요청을 보낸다
- **Then**: 상태가 완료로 바뀐다
- **실패/경계**: 없는 id는 거부한다

## 아키텍처 설계

### 레이어 배치

| UC-ID | Domain | Application | Infrastructure | Presentation |
|-------|--------|-------------|----------------|--------------|
| UC-01 | `todo.py` | `create_todo.py` | `in_memory_todo_repository.py` | `http/todos.py` |
| UC-02 | `todo.py` | `list_todos.py` | `in_memory_todo_repository.py` | `http/todos.py` |
| UC-03 | `todo.py` | `complete_todo.py` | `in_memory_todo_repository.py` | `http/todos.py` |

### Port & Adapter

| Port | Adapter | UC-ID |
|------|---------|-------|
| TodoRepository | InMemoryTodoRepository | UC-01 |
| TodoRepository | InMemoryTodoRepository | UC-02 |
| TodoRepository | InMemoryTodoRepository | UC-03 |

## TDD 테스트 계획

| UC-ID | 단위 | 통합 | Red 시나리오 |
|-------|------|------|--------------|
| UC-01 | `tests/unit/todo_api/test_create_todo.py` | `tests/integration/todo_api/test_create_todo.py` | 빈 제목이면 도메인 예외 |
| UC-02 | `tests/unit/todo_api/test_list_todos.py` | `tests/integration/todo_api/test_list_todos.py` | 필터 |
| UC-03 | `tests/unit/todo_api/test_complete_todo.py` | `tests/integration/todo_api/test_complete_todo.py` | 없는 id |
"""

INCOMPLETE = """# demo

## Use Case

| UC-ID | Use Case | Context | 우선순위 | 상태 | Red 테스트 |
|-------|----------|---------|----------|------|------------|
| UC-01 | ping | BC-01 | P0 | `planned` | — |

### UC 수용 기준 (Given/When/Then)

#### UC-01 — ping

- **Given**:
- **When**:
- **Then**:
- **실패/경계**:

## 아키텍처 설계

### 레이어 배치

| UC-ID | Domain | Application | Infrastructure | Presentation |
|-------|--------|-------------|----------------|--------------|
| UC-01 | — | — | — | — |
"""


def _root(plan: str = PLAN) -> Path:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    # unittest will clean via caller addCleanup
    (root / "PLAN.md").write_text(plan, encoding="utf-8")
    grok = root / ".grok"
    grok.mkdir()
    (grok / "scaffold-values.json").write_text(
        json.dumps({"PACKAGE_ROOT": "src/todo_api", "LANGUAGE": "Python"}),
        encoding="utf-8",
    )
    return root, tmp


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root, self._tmp = _root()
        self.addCleanup(self._tmp.cleanup)

    def test_skip_planner_when_plan_complete(self) -> None:
        decision = uc_policy.decide(self.root, "UC-01", 2, ["UC-01", "UC-02", "UC-03"])
        self.assertFalse(decision["need_planner"])
        self.assertFalse(decision["need_security"])
        self.assertEqual(decision["presentation"], "http/todos.py")

    def test_security_only_on_last_shared_presentation(self) -> None:
        last = uc_policy.decide(self.root, "UC-03", 2, ["UC-01", "UC-02", "UC-03"])
        self.assertTrue(last["need_security"])
        single = uc_policy.decide(self.root, "UC-01", 2, ["UC-01"])
        self.assertFalse(single["need_security"])

    def test_security_skipped_if_already_recorded(self) -> None:
        uc_policy.record_security(self.root, "http/todos.py")
        last = uc_policy.decide(self.root, "UC-03", 2, ["UC-03"])
        self.assertFalse(last["need_security"])

    def test_planner_when_gwt_empty(self) -> None:
        root, tmp = _root(INCOMPLETE)
        self.addCleanup(tmp.cleanup)
        decision = uc_policy.decide(root, "UC-01", 2, ["UC-01"])
        self.assertTrue(decision["need_planner"])
        self.assertTrue(decision["need_security"])

    def test_open_reviews_rerun_only_files_with_open_issues(self) -> None:
        review = self.root / "r.md"
        security = self.root / "s.md"
        review.write_text(
            "### Issue 1 -- Severity: bug\nFile a.py:1\nStatus: open\n",
            encoding="utf-8",
        )
        security.write_text(
            "### Issue 1 -- Severity: bug\nFile b.py:1\nStatus: fixed\n",
            encoding="utf-8",
        )
        rerun = uc_policy.files_with_open_issues([review, security])
        self.assertEqual([item["file"] for item in rerun], [str(review)])
        self.assertEqual(rerun[0]["bug"], 1)


class WritePlanTests(unittest.TestCase):
    def test_mechanical_plan_lists_shared_domain(self) -> None:
        root, tmp = _root()
        self.addCleanup(tmp.cleanup)
        out = root / ".grok" / "uc-plans" / "UC-01.md"
        argv = sys.argv
        sys.argv = ["write_uc_plan.py", "--root", str(root), "--uc", "UC-01"]
        try:
            self.assertEqual(write_uc_plan.main(), 0)
        finally:
            sys.argv = argv
        text = out.read_text(encoding="utf-8")
        self.assertIn("## PLAN revision needed", text)
        self.assertIn("todo.py", text)
        self.assertIn("create_todo.py", text)
        self.assertIn("Do not replace shared", text)
        self.assertTrue((root / ".grok" / "uc-plans" / "_bc-plan.md").is_file())
        import check_uc_plan

        self.assertEqual(check_uc_plan.missing_sections(text), [])


if __name__ == "__main__":
    unittest.main()
