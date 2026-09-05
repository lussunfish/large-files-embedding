from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import check_gates  # noqa: E402

AGENTS = """# demo

### 스캐폴드 마커

**게이트 (모두: 존재 + 비어 있지 않음):**

| 조건 | 파일 |
|------|------|
| LANGUAGE=Python | `pyproject.toml` (`[project]` 또는 `[tool.` 포함) |
| Node / TypeScript | `package.json` |
| Go | `go.mod` |
| Rust | `Cargo.toml` |
| 그 외 | 패키지 관리 매니페스트 1개 |
| 실행 모드 `docker-compose` | `docker-compose.yml` |

### 계획 파일 우선순위
"""


def plan(status: str) -> str:
    return (
        "# demo\n\n"
        "## 계획 승인\n\n"
        "| 항목 | 값 |\n"
        "|------|-----|\n"
        f"| 상태 | `{status}` |\n"
        "| 승인자 | — |\n\n"
        "## 목표\n\n"
        "- x\n"
    )


class CheckGatesTests(unittest.TestCase):
    def _project(
        self,
        *,
        status: str = "approved",
        language: str = "Python",
        mode: str = "docker-compose",
        pyproject: str | None = "[project]\nname = 'demo'\n",
        compose: str | None = "services: {}\n",
        agents: str = AGENTS,
    ) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "PLAN.md").write_text(plan(status), encoding="utf-8")
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
        grok = root / ".grok"
        grok.mkdir()
        (grok / "scaffold-values.json").write_text(
            json.dumps({"LANGUAGE": language, "RUNTIME_MODE": mode}),
            encoding="utf-8",
        )
        if pyproject is not None:
            (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
        if compose is not None:
            (root / "docker-compose.yml").write_text(compose, encoding="utf-8")
        return root

    def test_approved_python_compose_passes(self) -> None:
        root = self._project()
        self.assertEqual(check_gates.collect_errors(root), [])

    def test_draft_fails_but_scaffold_only_passes(self) -> None:
        root = self._project(status="draft")
        errors = check_gates.collect_errors(root)
        self.assertTrue(any("approved" in e for e in errors))
        self.assertEqual(check_gates.collect_errors(root, scaffold_only=True), [])

    def test_empty_pyproject_fails(self) -> None:
        root = self._project(pyproject="  \n")
        errors = check_gates.collect_errors(root, scaffold_only=True)
        self.assertTrue(any("empty pyproject.toml" in e for e in errors))

    def test_missing_compose_fails_only_in_compose_mode(self) -> None:
        root = self._project(compose=None)
        errors = check_gates.collect_errors(root, scaffold_only=True)
        self.assertTrue(any("docker-compose.yml" in e for e in errors))
        native = self._project(mode="uv-native", compose=None)
        self.assertEqual(check_gates.collect_errors(native, scaffold_only=True), [])

    def test_go_checks_go_mod_not_pyproject(self) -> None:
        root = self._project(language="Go", pyproject=None)
        errors = check_gates.collect_errors(root, scaffold_only=True)
        self.assertTrue(any("go.mod" in e for e in errors))
        self.assertFalse(any("pyproject.toml" in e for e in errors))
        (root / "go.mod").write_text("module demo\n", encoding="utf-8")
        self.assertEqual(check_gates.collect_errors(root, scaffold_only=True), [])


class CheckUcPlanTests(unittest.TestCase):
    def test_missing_sections(self) -> None:
        import check_uc_plan

        self.assertEqual(
            check_uc_plan.missing_sections("## Scope\n"),
            [
                "## PLAN revision needed",
                "## Critical files",
                "## TDD",
                "## Layers",
            ],
        )
        complete = "\n".join(
            [
                "## PLAN revision needed\nno",
                "## Scope\n- In:",
                "## Critical files\n- x",
                "## TDD\n- Red:",
                "## Layers\n- Domain:",
                "## Existing reuse\n- none",
                "## Risks\n- none",
            ]
        )
        self.assertEqual(check_uc_plan.missing_sections(complete), [])


if __name__ == "__main__":
    unittest.main()
