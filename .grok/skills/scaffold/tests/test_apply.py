from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import apply  # noqa: E402

TEMPLATES = SKILL / "templates" / "python"


def values(**overrides: object) -> dict:
    data: dict = {
        "PROJECT_NAME": "Demo",
        "ONE_LINE_DESCRIPTION": "demo",
        "LANGUAGE": "Python",
        "RUNTIME_VERSION": "3.12",
        "PYTHON_PACKAGE": "demo",
        "PACKAGE_ROOT": "src/demo",
        "RUNTIME_MODE": "docker-compose",
        "WEB_FRAMEWORK": "FastAPI",
        "CLI_FRAMEWORK": "Typer",
        "HAS_HTTP": True,
    }
    data.update(overrides)
    return data


class ApplyTests(unittest.TestCase):
    def _apply(self, data: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".grok").mkdir()
        (root / ".grok" / "scaffold-values.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        apply.apply_python(root, TEMPLATES, data, force=True)
        return root

    def test_http_compose_binds_all_interfaces_and_includes_typer(self) -> None:
        root = self._apply(values())
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "demo"', pyproject)
        self.assertIn("typer", pyproject)
        self.assertIn("fastapi", pyproject)
        docker = (root / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("0.0.0.0", docker)
        self.assertIn("serve", docker)
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("8000:8000", compose)
        self.assertTrue((root / "tests" / "unit" / "test_import.py").exists())
        self.assertTrue((root / ".github" / "workflows" / "ci.yml").exists())
        self.assertTrue(
            (root / "src" / "demo" / "presentation" / "http" / "app.py").exists()
        )

    def test_cli_only_docker_cmd_is_health(self) -> None:
        root = self._apply(
            values(
                WEB_FRAMEWORK="—",
                CLI_FRAMEWORK="—",
                HAS_HTTP=False,
                PROJECT_NAME="할일 API",
                PYTHON_PACKAGE="app",
                PACKAGE_ROOT="src/app",
            )
        )
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "app"', pyproject)
        self.assertIn("typer", pyproject)
        self.assertNotIn("fastapi", pyproject)
        docker = (root / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("health", docker)
        self.assertNotIn("serve", docker)
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("8000:8000", compose)
        self.assertFalse(
            (root / "src" / "app" / "presentation" / "http" / "app.py").exists()
        )

    def test_flask_does_not_write_fastapi_files(self) -> None:
        root = self._apply(
            values(WEB_FRAMEWORK="Flask", HAS_HTTP=True, PYTHON_PACKAGE="flask_app")
        )
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "flask-app"', pyproject)
        self.assertNotIn("fastapi", pyproject)
        self.assertIn("flask", pyproject)
        self.assertIn("typer", pyproject)
        self.assertFalse(
            (
                root
                / "src"
                / "flask_app"
                / "presentation"
                / "http"
                / "app.py"
            ).exists()
        )

    def test_compose_env_comes_from_values(self) -> None:
        root = self._apply(
            values(
                ENV_VARS=[
                    {"name": "LOG_LEVEL", "example": "info"},
                    {"name": "MODEL_PATH", "example": ""},
                ]
            )
        )
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('LOG_LEVEL: "${LOG_LEVEL:-info}"', compose)
        self.assertIn('MODEL_PATH: "${MODEL_PATH:-}"', compose)

    def test_compose_quotes_url_defaults(self) -> None:
        root = self._apply(
            values(
                ENV_VARS=[
                    {
                        "name": "DATABASE_URL",
                        "example": "postgresql://localhost/db",
                    }
                ]
            )
        )
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn(
            'DATABASE_URL: "${DATABASE_URL:-postgresql://localhost/db}"',
            compose,
        )

    def test_empty_existing_file_is_overwritten_without_force(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".grok").mkdir()
        (root / ".grok" / "scaffold-values.json").write_text(
            json.dumps(values()), encoding="utf-8"
        )
        (root / "pyproject.toml").write_text("  \n", encoding="utf-8")
        apply.apply_python(root, TEMPLATES, values(), force=False)
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[project]", text)

    def test_non_empty_existing_file_is_skipped_without_force(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".grok").mkdir()
        (root / ".grok" / "scaffold-values.json").write_text(
            json.dumps(values()), encoding="utf-8"
        )
        (root / "pyproject.toml").write_text("[project]\nname = \"keep\"\n", encoding="utf-8")
        apply.apply_python(root, TEMPLATES, values(), force=False)
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "keep"', text)
        self.assertNotIn("demo", text)

    def test_uv_native_skips_compose(self) -> None:
        root = self._apply(values(RUNTIME_MODE="uv-native"))
        self.assertFalse((root / "Dockerfile").exists())
        self.assertTrue((root / "scripts" / "stop.sh").exists())

    def test_pep508_name(self) -> None:
        self.assertEqual(apply.pep508_name("todo_api"), "todo-api")
        self.assertEqual(apply.pep508_name(""), "app")


if __name__ == "__main__":
    unittest.main()
