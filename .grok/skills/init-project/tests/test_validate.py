from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

import hello_parse  # noqa: E402
import validate  # noqa: E402

GPU_AND_COMPOSE = """## 프로젝트명
demo
## 기술 스택
- Python 3.12
## 실행 모드
docker-compose
## GPU
- Apple Silicon MPS
## 기능
- UC-01: ping
"""


class HelloParseTests(unittest.TestCase):
    def test_example_is_python_compose_without_gpu(self) -> None:
        hello = (ROOT / "hello.txt.example").read_text(encoding="utf-8")
        self.assertEqual(validate.language_from_hello(hello), "Python")
        self.assertFalse(validate.has_gpu(hello))
        self.assertEqual(validate.runtime_mode_from_hello(hello), "docker-compose")

    def test_gpu_example_uses_gpu_section(self) -> None:
        hello = (ROOT / "hello.txt.gpu.example").read_text(encoding="utf-8")
        self.assertTrue(validate.has_gpu(hello))
        self.assertEqual(validate.runtime_mode_from_hello(hello), "uv-native")
        self.assertEqual(validate.language_from_hello(hello), "Python")

    def test_gpu_false_positives_ignore_nongoal_and_comments(self) -> None:
        self.assertFalse(validate.has_gpu("## 비목표\n- GPU 학습은 하지 않음\n"))
        self.assertFalse(validate.has_gpu("# Metal 관련 없음\n## 목표\n- API\n"))
        self.assertFalse(validate.has_gpu("## 비목표\n- local LLM 연동\n"))
        self.assertTrue(validate.has_gpu("## GPU\n- Apple Silicon MPS\n"))

    def test_known_non_python_languages(self) -> None:
        self.assertEqual(
            validate.language_from_hello("## 기술 스택\n- Kotlin, Gradle\n"),
            "Kotlin",
        )
        self.assertEqual(
            validate.language_from_hello("## 기술 스택\n- Java 21, Spring\n"),
            "Java",
        )
        self.assertEqual(
            validate.language_from_hello("## 기술 스택\n- Go 1.22\n"),
            "Go",
        )
        self.assertEqual(
            validate.language_from_hello("## 기술 스택\n- TypeScript, Python backend\n"),
            "Python",
        )

    def test_unspecified_stack_has_no_language(self) -> None:
        self.assertIsNone(validate.language_from_hello("## 기술 스택\n- FastAPI\n"))

    def test_python_gpu_overrides_compose_runtime_mode(self) -> None:
        self.assertEqual(
            hello_parse.resolved_runtime_mode(GPU_AND_COMPOSE, "Python"),
            "uv-native",
        )
        data = {
            "LANGUAGE": "Python",
            "RUNTIME_MODE": "uv-native",
            "PYTHON_PACKAGE": "demo",
            "use_cases": [{"id": "UC-01", "name": "ping"}],
            "env_vars": [],
            "risks": [],
        }
        validate.check_json_vs_hello(data, GPU_AND_COMPOSE)

    def test_python_package_must_be_identifier(self) -> None:
        data = {
            "LANGUAGE": "Python",
            "RUNTIME_MODE": "docker-compose",
            "PYTHON_PACKAGE": "할일",
            "use_cases": [{"id": "UC-01", "name": "ping"}],
            "env_vars": [],
            "risks": [],
        }
        hello = (
            "## 프로젝트명\ndemo\n## 기술 스택\n- Python\n"
            "## 실행 모드\ndocker-compose\n## 기능\n- UC-01: ping\n"
        )
        with self.assertRaises(SystemExit):
            validate.check_json_vs_hello(data, hello)

    def test_non_python_requires_real_commands(self) -> None:
        data = {
            "LANGUAGE": "Go",
            "PACKAGE_INSTALL_COMMAND": "—",
            "UNIT_TEST_COMMAND": "go test ./...",
            "PRE_COMMIT_COMMAND": "go test ./...",
        }
        with self.assertRaises(SystemExit):
            validate.check_non_python_commands(data)
        data["PACKAGE_INSTALL_COMMAND"] = "go mod download"
        validate.check_non_python_commands(data)


if __name__ == "__main__":
    unittest.main()
