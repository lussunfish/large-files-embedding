#!/usr/bin/env python3
"""Render golden fixtures into a temp dir, validate, and apply the Python scaffold."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parents[3]  # repo root (…/grok-template)
TEST_DIRS = (
    HERE.parent / "tests",
    TEMPLATE / ".grok" / "skills" / "scaffold" / "tests",
    TEMPLATE / ".grok" / "skills" / "implement-uc" / "tests",
)
sys.path.insert(0, str(HERE))
import from_hello  # noqa: E402

MECHANICAL_KEYS = (
    "PROJECT_NAME",
    "LANGUAGE",
    "RUNTIME_VERSION",
    "PYTHON_PACKAGE",
    "PACKAGE_MANAGER",
    "LOCKFILE",
    "PACKAGE_ROOT",
    "WEB_FRAMEWORK",
    "CLI_FRAMEWORK",
    "RUNTIME_MODE",
    "USE_GPU",
    "PACKAGE_INSTALL_COMMAND",
    "UNIT_TEST_COMMAND",
    "PRE_COMMIT_COMMAND",
    "UV_DEV_COMMAND",
    "UV_STOP_COMMAND",
)


def run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)


def bootstrap(dest: Path, hello_src: Path, fixture: Path | None) -> None:
    dest.mkdir()
    shutil.copytree(TEMPLATE / "init", dest / "init")
    shutil.copy2(TEMPLATE / ".gitignore", dest / ".gitignore")
    grok = dest / ".grok"
    grok.mkdir()
    shutil.copy2(TEMPLATE / ".grok" / "template-version", grok / "template-version")
    shutil.copy2(hello_src, dest / "hello.txt")
    if fixture is not None:
        shutil.copy2(fixture, dest / "init" / "placeholders.json")
    else:
        run(
            [
                sys.executable,
                str(HERE / "from_hello.py"),
                "--root",
                str(dest),
                "--hello",
                str(dest / "hello.txt"),
                "--date",
                "2026-09-05",
            ],
            cwd=HERE,
        )
    run([sys.executable, str(HERE / "render.py"), "--root", str(dest)], cwd=HERE)
    run(
        [
            sys.executable,
            str(HERE / "validate.py"),
            "--root",
            str(dest),
            "--hello",
            str(dest / "hello.txt"),
        ],
        cwd=HERE,
    )


def apply_python(dest: Path) -> None:
    apply = TEMPLATE / ".grok" / "skills" / "scaffold" / "scripts" / "apply.py"
    if not apply.exists():
        print("missing apply.py", file=sys.stderr)
        raise SystemExit(1)
    run([sys.executable, str(apply), "--root", str(dest)], cwd=dest)


def maybe_uv_check(dest: Path) -> None:
    uv = shutil.which("uv")
    if not uv:
        if os.environ.get("CI"):
            print("uv not on PATH (required in CI)", file=sys.stderr)
            raise SystemExit(1)
        print("uv not on PATH — skip host tool check")
        return
    run([uv, "sync"], cwd=dest)
    run([uv, "run", "ruff", "check"], cwd=dest)
    run([uv, "run", "ruff", "format", "--check"], cwd=dest)
    run([uv, "run", "mypy", "src"], cwd=dest)
    run([uv, "run", "pytest"], cwd=dest)


def check_todo_api(dest: Path) -> None:
    pyproject = dest / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.exists() else ""
    if "[project]" not in text:
        print("scaffold apply did not write pyproject.toml [project]", file=sys.stderr)
        raise SystemExit(1)
    if 'name = "todo-api"' not in text:
        print("pyproject name must be PEP 508 todo-api", file=sys.stderr)
        raise SystemExit(1)
    if "typer" not in text:
        print("pyproject must include typer (CLI entrypoint)", file=sys.stderr)
        raise SystemExit(1)
    dockerfile = dest / "Dockerfile"
    docker = dockerfile.read_text(encoding="utf-8")
    if "README.md" not in docker:
        print("Dockerfile must COPY README.md", file=sys.stderr)
        raise SystemExit(1)
    if "--host" not in docker or "0.0.0.0" not in docker:
        print("Dockerfile CMD must bind 0.0.0.0", file=sys.stderr)
        raise SystemExit(1)
    if not (dest / ".dockerignore").exists():
        print("missing .dockerignore", file=sys.stderr)
        raise SystemExit(1)
    if not (dest / "tests" / "unit" / "test_import.py").exists():
        print("missing tests/unit/test_import.py", file=sys.stderr)
        raise SystemExit(1)
    if not (dest / ".github" / "workflows" / "ci.yml").exists():
        print("missing generated CI workflow", file=sys.stderr)
        raise SystemExit(1)
    compose = (dest / "docker-compose.yml").read_text(encoding="utf-8")
    if "8000:8000" not in compose:
        print("HTTP compose must publish 8000", file=sys.stderr)
        raise SystemExit(1)
    if "${LOG_LEVEL:-info}" not in compose:
        print("compose must pass LOG_LEVEL from the environment", file=sys.stderr)
        raise SystemExit(1)
    cli = (dest / "src" / "todo_api" / "presentation" / "cli" / "main.py").read_text(
        encoding="utf-8"
    )
    if 'host: str = "127.0.0.1"' not in cli:
        print("CLI serve default host must be 127.0.0.1", file=sys.stderr)
        raise SystemExit(1)
    env = dest / ".env.example"
    if env.exists() and "DATABASE_URL" in env.read_text(encoding="utf-8"):
        print("todo-api .env.example must not include unused DATABASE_URL", file=sys.stderr)
        raise SystemExit(1)
    plan = (dest / "PLAN.md").read_text(encoding="utf-8")
    if "CRUD" in plan:
        print("PLAN.md still says CRUD — hello/fixture mismatch", file=sys.stderr)
        raise SystemExit(1)
    maybe_uv_check(dest)


def check_gpu(dest: Path) -> None:
    if not (dest / "scripts" / "stop.sh").exists():
        print("uv-native scaffold missing scripts/stop.sh", file=sys.stderr)
        raise SystemExit(1)
    if (dest / "docker-compose.yml").exists() or (dest / "Dockerfile").exists():
        print("uv-native scaffold must not write compose/Dockerfile", file=sys.stderr)
        raise SystemExit(1)
    agents = (dest / "AGENTS.md").read_text(encoding="utf-8")
    if "uv-native" not in agents:
        print("GPU project AGENTS.md missing uv-native", file=sys.stderr)
        raise SystemExit(1)
    if not (dest / ".github" / "workflows" / "ci.yml").exists():
        print("missing generated CI workflow", file=sys.stderr)
        raise SystemExit(1)


def compare_mechanical(got: dict, golden: dict, label: str) -> None:
    for key in MECHANICAL_KEYS:
        if got.get(key) != golden.get(key):
            print(
                f"{label}: from_hello {key}={got.get(key)!r} != golden {golden.get(key)!r}",
                file=sys.stderr,
            )
            raise SystemExit(1)
    got_ucs = [(u.get("id"), u.get("name")) for u in got.get("use_cases") or []]
    gold_ucs = [(u.get("id"), u.get("name")) for u in golden.get("use_cases") or []]
    if got_ucs != gold_ucs:
        print(f"{label}: use_cases {got_ucs} != golden {gold_ucs}", file=sys.stderr)
        raise SystemExit(1)
    got_env = [e.get("name") for e in got.get("env_vars") or []]
    gold_env = [e.get("name") for e in golden.get("env_vars") or []]
    if got_env != gold_env:
        print(f"{label}: env_vars {got_env} != golden {gold_env}", file=sys.stderr)
        raise SystemExit(1)


def run_unittests() -> None:
    for tests_dir in TEST_DIRS:
        if not tests_dir.exists():
            continue
        run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(tests_dir),
                "-q",
            ],
            cwd=TEMPLATE,
        )


def main() -> int:
    run_unittests()

    todo_hello = TEMPLATE / "hello.txt.example"
    todo_fixture = TEMPLATE / "init" / "fixtures" / "todo-api" / "placeholders.json"
    gpu_hello = TEMPLATE / "hello.txt.gpu.example"
    gpu_fixture = TEMPLATE / "init" / "fixtures" / "local-llm-chat" / "placeholders.json"
    for path in (todo_hello, todo_fixture, gpu_hello, gpu_fixture):
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 1

    with tempfile.TemporaryDirectory(prefix="grok-template-fixture-") as tmp:
        root = Path(tmp)
        todo = root / "todo"
        bootstrap(todo, todo_hello, todo_fixture)
        apply_python(todo)
        check_todo_api(todo)

        gpu = root / "gpu"
        bootstrap(gpu, gpu_hello, gpu_fixture)
        apply_python(gpu)
        check_gpu(gpu)

        generated = root / "from-hello"
        bootstrap(generated, todo_hello, fixture=None)
        payload = json.loads(
            (generated / ".grok" / "scaffold-values.json").read_text(encoding="utf-8")
        )
        if payload.get("HAS_HTTP") is not True:
            print("from_hello todo-api must set HAS_HTTP true", file=sys.stderr)
            raise SystemExit(1)
        if payload.get("RUNTIME_MODE") != "docker-compose":
            print("from_hello todo-api RUNTIME_MODE must be docker-compose", file=sys.stderr)
            raise SystemExit(1)
        env_names = [e.get("name") for e in payload.get("ENV_VARS") or []]
        if "LOG_LEVEL" not in env_names:
            print("scaffold-values ENV_VARS must include LOG_LEVEL", file=sys.stderr)
            raise SystemExit(1)

        compare_mechanical(
            from_hello.build_placeholders(
                todo_hello.read_text(encoding="utf-8"), today="2026-09-05"
            ),
            json.loads(todo_fixture.read_text(encoding="utf-8")),
            "todo-api",
        )
        compare_mechanical(
            from_hello.build_placeholders(
                gpu_hello.read_text(encoding="utf-8"), today="2026-09-05"
            ),
            json.loads(gpu_fixture.read_text(encoding="utf-8")),
            "local-llm-chat",
        )

        print("check_fixture.py: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
