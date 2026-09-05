from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

import from_hello  # noqa: E402
import hello_parse  # noqa: E402


class FromHelloTests(unittest.TestCase):
    def test_example_todo_api(self) -> None:
        hello = (ROOT / "hello.txt.example").read_text(encoding="utf-8")
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["PROJECT_NAME"], "todo-api")
        self.assertEqual(data["LANGUAGE"], "Python")
        self.assertEqual(data["RUNTIME_MODE"], "docker-compose")
        self.assertEqual(data["WEB_FRAMEWORK"], "FastAPI")
        self.assertEqual(data["CLI_FRAMEWORK"], "Typer")
        self.assertEqual(data["PYTHON_PACKAGE"], "todo_api")
        self.assertEqual([u["id"] for u in data["use_cases"]], ["UC-01", "UC-02", "UC-03"])
        self.assertEqual([e["name"] for e in data["env_vars"]], ["LOG_LEVEL"])
        self.assertEqual(data["risks"], [])
        self.assertEqual(data["DATE"], "2026-09-05")
        ucs = {u["id"]: u for u in data["use_cases"]}
        self.assertEqual(ucs["UC-01"]["failure"], "빈 필수 값은 거부한다")
        self.assertEqual(ucs["UC-02"]["failure"], "알 수 없는 필터 값은 거부한다")
        self.assertEqual(ucs["UC-03"]["failure"], "없는 id는 거부한다")
        self.assertEqual(ucs["UC-01"]["port"], "TodoRepository")
        self.assertEqual(ucs["UC-01"]["adapter"], "InMemoryTodoRepository")
        self.assertEqual(ucs["UC-01"]["domain"], "todo.py")
        self.assertEqual(ucs["UC-02"]["domain"], "todo.py")
        self.assertEqual(ucs["UC-03"]["domain"], "todo.py")
        self.assertEqual(ucs["UC-01"]["application"], "create_todo.py")
        self.assertEqual(ucs["UC-02"]["application"], "list_todos.py")
        self.assertEqual(ucs["UC-03"]["application"], "complete_todo.py")
        self.assertEqual(ucs["UC-01"]["infrastructure"], "in_memory_todo_repository.py")
        self.assertEqual(ucs["UC-01"]["presentation"], "http/todos.py")
        self.assertEqual(ucs["UC-03"]["presentation"], "http/todos.py")
        self.assertEqual(data["BC_01_NAME"], "Todo")
        self.assertEqual(data["ubiquitous_language"][0]["term"], "Todo")
        self.assertNotEqual(ucs["UC-01"]["given"], "할 일 생성 요청이 가능하다")

    def test_gpu_example_is_uv_native(self) -> None:
        hello = (ROOT / "hello.txt.gpu.example").read_text(encoding="utf-8")
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["RUNTIME_MODE"], "uv-native")
        self.assertEqual(data["USE_GPU"], "yes")
        self.assertIn("local_llm_chat", data["UV_DEV_COMMAND"])
        self.assertEqual(
            [e["name"] for e in data["env_vars"]],
            ["MODEL_PATH", "OLLAMA_BASE_URL"],
        )
        ucs = {u["id"]: u for u in data["use_cases"]}
        self.assertIn("스트리밍", ucs["UC-01"]["then"])
        self.assertIn("경로", ucs["UC-02"]["failure"])
        self.assertEqual(ucs["UC-01"]["domain"], "chat.py")
        self.assertEqual(ucs["UC-02"]["domain"], "chat.py")
        self.assertEqual(ucs["UC-01"]["application"], "stream_chat.py")
        self.assertEqual(ucs["UC-02"]["application"], "load_chat.py")
        self.assertEqual(ucs["UC-01"]["port"], "ChatRepository")
        model_path = next(e for e in data["env_vars"] if e["name"] == "MODEL_PATH")
        self.assertEqual(model_path["example"], "")
        ollama = next(e for e in data["env_vars"] if e["name"] == "OLLAMA_BASE_URL")
        self.assertEqual(ollama["example"], "http://127.0.0.1:11434")

    def test_gpu_section_wins_over_compose_mode(self) -> None:
        hello = """## 프로젝트명
demo
## 한 줄 설명
x
## 기술 스택
- Python 3.12, FastAPI
## 실행 모드
docker-compose
## GPU
- MPS
## 기능
- UC-01: ping
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["RUNTIME_MODE"], "uv-native")

    def test_korean_project_name_gets_safe_package(self) -> None:
        self.assertEqual(hello_parse.python_package_name("할일 API"), "api")
        self.assertEqual(hello_parse.python_package_name("할일관리"), "app")
        self.assertEqual(hello_parse.pep508_name("todo_api"), "todo-api")
        self.assertEqual(hello_parse.pep508_name("app"), "app")

    def test_typer_only_is_not_fastapi(self) -> None:
        hello = """## 프로젝트명
cli-tool
## 한 줄 설명
파일 변환 CLI
## 기술 스택
- Python 3.12, uv, Typer, pytest
## 실행 모드
docker-compose
## 기능
- UC-01: 파일 변환
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["WEB_FRAMEWORK"], "—")
        self.assertEqual(data["CLI_FRAMEWORK"], "Typer")

    def test_english_section_aliases(self) -> None:
        hello = """## Project name
demo
## One-line description
A demo
## Tech stack
- Python 3.12, FastAPI
## Features
- UC-01: ping
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["PROJECT_NAME"], "demo")
        self.assertEqual(data["use_cases"][0]["id"], "UC-01")
        self.assertEqual(data["WEB_FRAMEWORK"], "FastAPI")

    def test_flask_is_not_rewritten_to_fastapi(self) -> None:
        hello = """## 프로젝트명
flask-app
## 한 줄 설명
웹
## 기술 스택
- Python 3.12, Flask
## 기능
- UC-01: ping
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(data["WEB_FRAMEWORK"], "Flask")

    def test_unlabeled_features_get_uc_ids(self) -> None:
        hello = """## 프로젝트명
demo
## 한 줄 설명
x
## 기술 스택
- Python 3.12
## 기능
- 로그인
- UC-03: 로그아웃
- 프로필 조회
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        self.assertEqual(
            [(u["id"], u["name"]) for u in data["use_cases"]],
            [("UC-01", "로그인"), ("UC-03", "로그아웃"), ("UC-02", "프로필 조회")],
        )
        self.assertTrue(
            any("UC-01" in note and "UC-02" in note for note in data["notes"])
        )

    def test_shared_entity_from_package_suffix(self) -> None:
        self.assertEqual(hello_parse.entity_slug("todo_api"), "todo")
        self.assertEqual(hello_parse.entity_slug("local_llm_chat"), "chat")
        self.assertEqual(hello_parse.entity_slug("app"), "app")
        self.assertEqual(hello_parse.verb_from_name("할 일 목록 조회 (완료/미완료 필터)"), "list")
        self.assertEqual(hello_parse.verb_from_name("할 일 완료 처리"), "complete")

    def test_env_example_skips_korean_description(self) -> None:
        hello = """## 프로젝트명
demo
## 기술 스택
- Python
## 기능
- UC-01: ping
## 환경 변수
- LOG_LEVEL: info (기본)
- MODEL_PATH: 로컬 모델 경로
- TIMEOUT_MS: 5000
"""
        data = from_hello.build_placeholders(hello, today="2026-09-05")
        by_name = {e["name"]: e["example"] for e in data["env_vars"]}
        self.assertEqual(by_name["LOG_LEVEL"], "info")
        self.assertEqual(by_name["MODEL_PATH"], "")
        self.assertEqual(by_name["TIMEOUT_MS"], "5000")


if __name__ == "__main__":
    unittest.main()
