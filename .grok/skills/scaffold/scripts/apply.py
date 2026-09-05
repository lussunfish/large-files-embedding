#!/usr/bin/env python3
"""Apply first-class Python scaffold recipes. Non-Python is experimental (manifest only)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
PY_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
FASTAPI_FRAMEWORKS = {"fastapi", "starlette"}


def die(msg: str, code: int = 1) -> None:
    print(f"apply.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def sub(text: str, ctx: dict[str, str], source: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            die(f"{source}: unknown placeholder {{{{{key}}}}}")
        return ctx[key]

    out = PLACEHOLDER_RE.sub(repl, text)
    leftover = PLACEHOLDER_RE.findall(out)
    if leftover:
        die(f"{source}: leftover placeholders: {', '.join(leftover)}")
    return out


def load_values(root: Path) -> dict:
    path = root / ".grok" / "scaffold-values.json"
    if not path.exists():
        die(f"missing {path} — run /init-project first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        die("scaffold-values.json must be an object")
    return data


def is_blank_file(path: Path) -> bool:
    try:
        return not path.read_text(encoding="utf-8").strip()
    except OSError:
        return True


def write_file(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force and not is_blank_file(path):
        return "skip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if path.suffix == ".sh":
        path.chmod(path.stat().st_mode | 0o111)
    return "write"


def major_minor(version: str) -> str:
    match = re.match(r"(\d+)\.(\d+)", (version or "").strip())
    return f"{match.group(1)}.{match.group(2)}" if match else "3.12"


def pep508_name(python_package: str) -> str:
    raw = (python_package or "app").strip().lower().replace("_", "-")
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-.")
    if not raw or not re.match(r"^[a-z0-9]", raw):
        return "app"
    return raw


def uses_fastapi(values: dict) -> bool:
    web = (values.get("WEB_FRAMEWORK") or "").strip().lower()
    return web in FASTAPI_FRAMEWORKS


def web_framework(values: dict) -> str:
    return (values.get("WEB_FRAMEWORK") or "").strip().lower()


def compose_default(example: str) -> str:
    ex = (example or "").strip()
    if not ex or re.search(r"\s", ex) or re.search(r"[가-힣]", ex):
        return ""
    return ex


def compose_extra(values: dict, has_http: bool) -> str:
    parts: list[str] = []
    if has_http:
        parts.append('    ports:\n      - "8000:8000"')
    raw = values.get("ENV_VARS") or []
    env_lines: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            name = str(item["name"]).strip()
            default = compose_default(str(item.get("example") or ""))
        elif isinstance(item, str) and item.strip():
            name, default = item.strip(), ""
        else:
            continue
        if not name:
            continue
        env_lines.append(f'      {name}: "${{{name}:-{default}}}"')
    if env_lines:
        parts.append("    environment:\n" + "\n".join(env_lines))
    if not parts:
        return ""
    return "\n".join(parts) + "\n"


def python_ctx(values: dict) -> dict[str, str]:
    pkg = values["PYTHON_PACKAGE"]
    if not PY_IDENT.match(pkg or ""):
        die(f"PYTHON_PACKAGE {pkg!r} is not a Python identifier")
    has_http = uses_fastapi(values)
    web = web_framework(values)
    deps: list[str] = []
    if has_http:
        deps.extend(['    "fastapi>=0.115"', '    "uvicorn[standard]>=0.32"'])
    elif web == "flask":
        deps.append('    "flask>=3.0"')
    elif web == "django":
        deps.append('    "django>=5.0"')
    deps.append('    "typer>=0.15"')
    dev = ['    "pytest>=8.3"', '    "ruff>=0.8"', '    "mypy>=1.13"']
    if has_http:
        dev.append('    "httpx>=0.27"')
    runtime = major_minor(values.get("RUNTIME_VERSION") or "3.12")
    major, minor = runtime.split(".")
    docker_cmd = (
        f'["python", "-m", "{pkg}", "serve", "--host", "0.0.0.0"]'
        if has_http
        else f'["python", "-m", "{pkg}", "health"]'
    )
    return {
        "PROJECT_NAME": values["PROJECT_NAME"],
        "ONE_LINE_DESCRIPTION": values["ONE_LINE_DESCRIPTION"],
        "PYTHON_PACKAGE": pkg,
        "PYPROJECT_NAME": pep508_name(pkg),
        "PACKAGE_ROOT": values["PACKAGE_ROOT"],
        "RUNTIME_VERSION": runtime,
        "RUFF_TARGET": f"py{major}{minor}",
        "APP_DEPENDENCIES": ",\n".join(deps),
        "DEV_DEPENDENCIES": ",\n".join(dev),
        "HAS_HTTP": "true" if has_http else "false",
        "DOCKER_CMD": docker_cmd,
        "COMPOSE_EXTRA": compose_extra(values, has_http),
        "DOCKER_UV_SYNC": "RUN uv sync --no-dev",
    }


def apply_files(
    root: Path,
    templates: Path,
    mapping: list[tuple[str, str, bool]],
    ctx: dict[str, str],
    force: bool,
) -> list[str]:
    log: list[str] = []
    for src_rel, dest_rel, enabled in mapping:
        if not enabled:
            continue
        src = templates / src_rel
        if not src.exists():
            die(f"missing recipe {src}")
        dest = root / dest_rel
        action = write_file(dest, sub(src.read_text(encoding="utf-8"), ctx, src_rel), force)
        log.append(f"{action} {dest_rel}")
    return log


def maybe_uv_lock(root: Path) -> str:
    uv = shutil.which("uv")
    if not uv:
        return "skip uv.lock (uv not on PATH)"
    proc = subprocess.run([uv, "lock"], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"uv lock failed:\n{proc.stderr or proc.stdout}")
    return "write uv.lock"


def warn_non_fastapi_web(values: dict) -> None:
    web = web_framework(values)
    if web in {"flask", "django"}:
        print(
            f"apply.py: WEB_FRAMEWORK={values.get('WEB_FRAMEWORK')!s} has no HTTP "
            "recipe (no presentation/http, no FastAPI files). Dependency is added; "
            "first-class HTTP scaffold is FastAPI/Starlette only.",
            file=sys.stderr,
        )


def apply_python(root: Path, templates: Path, values: dict, force: bool) -> list[str]:
    warn_non_fastapi_web(values)
    ctx = python_ctx(values)
    pkg = ctx["PYTHON_PACKAGE"]
    mode = values["RUNTIME_MODE"]
    has_http = uses_fastapi(values)
    app_mapping: list[tuple[str, str, bool]] = [
        ("pyproject.toml", "pyproject.toml", True),
        ("src/package/__init__.py", f"src/{pkg}/__init__.py", True),
        ("src/package/__main__.py", f"src/{pkg}/__main__.py", True),
        ("src/package/presentation/__init__.py", f"src/{pkg}/presentation/__init__.py", True),
        (
            "src/package/presentation/cli/__init__.py",
            f"src/{pkg}/presentation/cli/__init__.py",
            True,
        ),
        (
            "src/package/presentation/cli/main.py"
            if has_http
            else "src/package/presentation/cli/main_nohttp.py",
            f"src/{pkg}/presentation/cli/main.py",
            True,
        ),
        (
            "src/package/presentation/http/__init__.py",
            f"src/{pkg}/presentation/http/__init__.py",
            has_http,
        ),
        (
            "src/package/presentation/http/app.py",
            f"src/{pkg}/presentation/http/app.py",
            has_http,
        ),
        ("tests/unit/test_import.py", "tests/unit/test_import.py", True),
        ("tests/integration/test_app_e2e.py", "tests/integration/test_app_e2e.py", has_http),
        (".github/workflows/ci.yml", ".github/workflows/ci.yml", True),
        ("scripts/stop.sh", "scripts/stop.sh", mode == "uv-native"),
    ]
    log = apply_files(root, templates, app_mapping, ctx, force)
    if any(item.startswith("write pyproject.toml") for item in log):
        log.append(maybe_uv_lock(root))
    else:
        log.append("skip uv.lock (pyproject.toml unchanged)")
    if (root / "uv.lock").exists():
        ctx["DOCKER_UV_SYNC"] = "COPY uv.lock ./\nRUN uv sync --frozen --no-dev"
    docker_mapping: list[tuple[str, str, bool]] = [
        ("docker-compose.yml", "docker-compose.yml", mode == "docker-compose"),
        ("Dockerfile", "Dockerfile", mode == "docker-compose"),
        (".dockerignore", ".dockerignore", mode == "docker-compose"),
    ]
    log.extend(apply_files(root, templates, docker_mapping, ctx, force))
    return log


def apply_experimental(root: Path, values: dict) -> list[str]:
    lang = values.get("LANGUAGE") or "unknown"
    print(
        f"apply.py: LANGUAGE={lang} has no first-class recipe. "
        "Create only the AGENTS.md scaffold-marker gate manifest. "
        "Non-Python scaffold is experimental.",
        file=sys.stderr,
    )
    return [f"experimental:{lang}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply grok-template scaffold recipes")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    values = load_values(root)
    lang = (values.get("LANGUAGE") or "").strip()
    templates = Path(__file__).resolve().parent.parent / "templates" / "python"
    if lang.lower() == "python":
        log = apply_python(root, templates, values, args.force)
    else:
        log = apply_experimental(root, values)
        return 2
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
