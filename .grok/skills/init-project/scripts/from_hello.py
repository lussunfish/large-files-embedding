#!/usr/bin/env python3
"""Build init/placeholders.json from hello.txt (mechanical fields)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from hello_parse import (
    cli_framework_from_hello,
    database_from_hello,
    entity_slug,
    first_value,
    has_gpu,
    infer_acceptance,
    is_fastapi_framework,
    parse_hello_env_items,
    parse_hello_features,
    parse_hello_risks,
    pascalize,
    python_package_name,
    resolved_language,
    resolved_runtime_mode,
    section,
    shared_layer_files,
    web_framework_from_hello,
)

DASH = "—"


def die(msg: str, code: int = 1) -> None:
    print(f"from_hello.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def bullets_or_dash(body: str) -> str:
    text = body.strip()
    return text if text else DASH


def python_tool_commands(pkg: str, mode: str, has_http: bool) -> dict[str, str]:
    serve = f"uv run python -m {pkg} serve" if has_http else f"uv run python -m {pkg} health"
    uv_dev = serve if mode == "uv-native" else "— (미사용)"
    uv_stop = "./scripts/stop.sh" if mode == "uv-native" else "— (미사용)"
    pre = "uv run ruff format --check && uv run ruff check && uv run mypy src && uv run pytest"
    return {
        "PACKAGE_MANAGER": "uv",
        "LOCKFILE": "uv.lock",
        "PACKAGE_ROOT": f"src/{pkg}",
        "TEST_FRAMEWORK": "pytest",
        "LINT_FORMAT": "ruff",
        "TYPECHECK": "mypy",
        "PACKAGE_INSTALL_COMMAND": "uv sync",
        "UNIT_TEST_COMMAND": "uv run pytest tests/unit",
        "INTEGRATION_TEST_COMMAND": "uv run pytest tests/integration",
        "LINT_COMMAND": "uv run ruff check",
        "FORMAT_CHECK_COMMAND": "uv run ruff format --check",
        "TYPECHECK_COMMAND": "uv run mypy src",
        "PRE_COMMIT_COMMAND": pre,
        "PRE_COMMIT_CHECKS": (
            "- `uv run ruff format --check`\n"
            "- `uv run ruff check`\n"
            "- `uv run mypy src`\n"
            "- `uv run pytest`"
        ),
        "DEV_COMMAND": "docker compose up -d",
        "STOP_COMMAND": "docker compose down",
        "UV_DEV_COMMAND": uv_dev,
        "UV_STOP_COMMAND": uv_stop,
    }


def other_tool_commands() -> dict[str, str]:
    return {
        "PACKAGE_MANAGER": DASH,
        "LOCKFILE": DASH,
        "PACKAGE_ROOT": DASH,
        "TEST_FRAMEWORK": DASH,
        "LINT_FORMAT": DASH,
        "TYPECHECK": DASH,
        "PACKAGE_INSTALL_COMMAND": DASH,
        "UNIT_TEST_COMMAND": DASH,
        "INTEGRATION_TEST_COMMAND": DASH,
        "LINT_COMMAND": DASH,
        "FORMAT_CHECK_COMMAND": DASH,
        "TYPECHECK_COMMAND": DASH,
        "PRE_COMMIT_COMMAND": DASH,
        "PRE_COMMIT_CHECKS": DASH,
        "DEV_COMMAND": "docker compose up -d",
        "STOP_COMMAND": "docker compose down",
        "UV_DEV_COMMAND": "— (미사용)",
        "UV_STOP_COMMAND": "— (미사용)",
    }


def default_uc(
    uc_id: str,
    name: str,
    pkg: str,
    language: str,
    has_http: bool,
    entity: str,
    used_apps: set[str],
) -> dict:
    gwt = infer_acceptance(name)
    layers = shared_layer_files(
        entity=entity,
        name=name,
        pkg=pkg,
        language=language,
        has_http=has_http,
        used_apps=used_apps,
    )
    return {
        "id": uc_id,
        "name": name,
        "priority": "P0",
        "desc": name,
        "given": gwt["given"],
        "when": gwt["when"],
        "then": gwt["then"],
        "failure": gwt["failure"],
        "domain": layers["domain"],
        "application": layers["application"],
        "infrastructure": layers["infrastructure"],
        "presentation": layers["presentation"],
        "port": layers["port"],
        "adapter": layers["adapter"],
        "unit_test": layers["unit_test"],
        "integration_test": layers["integration_test"],
        "red": gwt["red"],
        "infra_service": None,
    }


def project_structure(pkg: str, language: str, has_http: bool) -> str:
    if language != "Python":
        return "src/\ntests/\nprompt-log/\n  README.md\n  INDEX.md"
    http = "    http/\n" if has_http else ""
    return (
        f"src/{pkg}/\n"
        "  domain/\n"
        "  application/\n"
        "  infrastructure/\n"
        "  presentation/\n"
        f"{http}"
        "    cli/\n"
        "tests/\n"
        "  unit/\n"
        "  integration/\n"
        "prompt-log/\n"
        "  README.md\n"
        "  INDEX.md"
    )


def build_placeholders(hello: str, today: str | None = None) -> dict:
    project = first_value(section(hello, "프로젝트명"))
    if not project:
        die("hello.txt missing ## 프로젝트명")
    ucs, assigned = parse_hello_features(hello)
    if not ucs:
        die("hello.txt has no ## 기능 items")
    if assigned:
        print(
            "from_hello: assigned "
            + ", ".join(assigned)
            + " to unlabeled feature lines",
            file=sys.stderr,
        )

    language = resolved_language(hello)
    mode = resolved_runtime_mode(hello, language)
    pkg = python_package_name(project) if language == "Python" else DASH
    entity = entity_slug(pkg) if language == "Python" else DASH
    entity_pascal = pascalize(entity) if language == "Python" else project
    web = web_framework_from_hello(hello, language)
    has_http = is_fastapi_framework(web)
    one_line = first_value(section(hello, "한 줄 설명")) or project
    used_apps: set[str] = set()
    goals = bullets_or_dash(section(hello, "목표"))
    nongoals = bullets_or_dash(section(hello, "비목표"))
    grok = bullets_or_dash(section(hello, "Grok에게 추가 지시"))
    tools = (
        python_tool_commands(pkg, mode, has_http)
        if language == "Python"
        else other_tool_commands()
    )
    data: dict = {
        "PROJECT_NAME": project,
        "ONE_LINE_DESCRIPTION": one_line,
        "DATE": today or date.today().isoformat(),
        "AUTHOR": first_value(section(hello, "작성자")) or DASH,
        "LANGUAGE": language,
        "RUNTIME_VERSION": "3.12" if language == "Python" else DASH,
        "PYTHON_PACKAGE": pkg,
        "WEB_FRAMEWORK": web,
        "CLI_FRAMEWORK": cli_framework_from_hello(hello, language),
        "DATABASE": database_from_hello(hello),
        "RUNTIME_MODE": mode,
        "USE_GPU": "yes" if has_gpu(hello) else "no",
        "DEV_MACHINE": DASH,
        "ARCHITECTURE_STYLE": "Clean Architecture + DDD-lite",
        "LAYERS": "domain → application → infrastructure → presentation",
        "DOMAIN_MODELING": "DDD-lite (Entity, VO, Repository Protocol)",
        "TEST_STRATEGY": "TDD (unit + integration)",
        "PLAN_FIRST": "yes",
        "REQUIRE_PLAN_APPROVAL": "yes",
        "GIT_HOOKS": "pre-commit optional (기본 수동 검사)",
        "GOALS": goals,
        "NON_GOALS": nongoals,
        "SCOPE_INCLUDE": ", ".join(name for _id, name in ucs),
        "SCOPE_EXCLUDE": nongoals.splitlines()[0].lstrip("- ").strip()
        if nongoals != DASH
        else DASH,
        "GROK_AGENT_RULES": grok,
        "BC_01_NAME": entity_pascal,
        "BC_01_DESC": one_line,
        "BC_01_PATH": f"src/{pkg}/" if language == "Python" else DASH,
        "PROJECT_STRUCTURE": project_structure(pkg, language, has_http),
        "REFERENCES": DASH,
        "use_cases": [
            default_uc(
                uc_id,
                name,
                pkg,
                language,
                has_http,
                entity,
                used_apps,
            )
            for uc_id, name in ucs
        ],
        "env_vars": parse_hello_env_items(hello),
        "risks": parse_hello_risks(hello),
        "ubiquitous_language": (
            [
                {
                    "term": entity_pascal,
                    "definition": one_line,
                    "context": "BC-01",
                }
            ]
            if language == "Python"
            else []
        ),
        "notes": [
            "기계 필드는 from_hello.py가 hello.txt에서 채움",
            "공유 도메인·Port·UL·GWT는 스크립트가 채움 — UC별 domain 파일로 쪼개지 말 것",
        ],
    }
    if assigned:
        data["notes"].append(
            "기능 줄에 UC-ID가 없어 " + ", ".join(assigned) + " 를 순서대로 부여"
        )
    data.update(tools)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write init/placeholders.json from hello.txt"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--hello", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    root = args.root.resolve()
    hello_path = args.hello or (root / "hello.txt")
    if not hello_path.exists():
        die(f"missing {hello_path}")
    hello = hello_path.read_text(encoding="utf-8")
    data = build_placeholders(hello, today=args.date)
    out = args.out or (root / "init" / "placeholders.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
