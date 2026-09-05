#!/usr/bin/env python3
"""Render project files from init/placeholders.json + init/ templates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
OPTIONAL_LINE_KEYS = {"PYTHON_RULES_ROW"}

REQUIRED_STR = (
    "PROJECT_NAME",
    "ONE_LINE_DESCRIPTION",
    "DATE",
    "AUTHOR",
    "LANGUAGE",
    "RUNTIME_VERSION",
    "PYTHON_PACKAGE",
    "PACKAGE_MANAGER",
    "LOCKFILE",
    "PACKAGE_ROOT",
    "WEB_FRAMEWORK",
    "CLI_FRAMEWORK",
    "TEST_FRAMEWORK",
    "LINT_FORMAT",
    "TYPECHECK",
    "DATABASE",
    "RUNTIME_MODE",
    "USE_GPU",
    "DEV_MACHINE",
    "ARCHITECTURE_STYLE",
    "LAYERS",
    "DOMAIN_MODELING",
    "TEST_STRATEGY",
    "PLAN_FIRST",
    "REQUIRE_PLAN_APPROVAL",
    "GIT_HOOKS",
    "PACKAGE_INSTALL_COMMAND",
    "UNIT_TEST_COMMAND",
    "INTEGRATION_TEST_COMMAND",
    "LINT_COMMAND",
    "FORMAT_CHECK_COMMAND",
    "TYPECHECK_COMMAND",
    "PRE_COMMIT_COMMAND",
    "PRE_COMMIT_CHECKS",
    "DEV_COMMAND",
    "STOP_COMMAND",
    "UV_DEV_COMMAND",
    "UV_STOP_COMMAND",
    "GOALS",
    "NON_GOALS",
    "SCOPE_INCLUDE",
    "SCOPE_EXCLUDE",
    "GROK_AGENT_RULES",
    "BC_01_NAME",
    "BC_01_DESC",
    "BC_01_PATH",
    "PROJECT_STRUCTURE",
    "REFERENCES",
)

GITIGNORE_EXTRA = """
.DS_Store
hello.txt
.env
.env.*
!.env.example
*.local
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
*.egg-info/
.coverage
htmlcov/
.grok/uc-plans/
.grok/reviews/
node_modules/
target/
vendor/
""".strip().splitlines()

RENDERED_BY_SCRIPT = {
    "DEV_COMMAND_OR_UV",
    "STOP_COMMAND_OR_UV",
    "RUNTIME_ACTIVE_BLOCK",
    "COMMANDS_TABLE",
    "TEMPLATE_VERSION",
    "UC_TABLE_ROWS",
    "UC_ACCEPTANCE_SECTIONS",
    "UC_LAYER_ROWS",
    "UC_TDD_ROWS",
    "UC_PHASE_ROWS",
    "PORT_BODY",
    "INFRA_BODY",
    "UL_BODY",
    "ENV_VAR_ROWS",
    "RISK_ROWS",
    "PYTHON_RULES_ROW",
}


def die(msg: str, code: int = 1) -> None:
    print(f"render.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read {path}: {exc}")
    if not isinstance(data, dict):
        die("placeholders.json must be an object")
    return data


def require_str(data: dict, key: str) -> str:
    if key not in data or not isinstance(data[key], str) or data[key] == "":
        die(f"missing or empty string key: {key}")
    return data[key]


def as_list(data: dict, key: str) -> list:
    val = data.get(key, [])
    if val is None:
        return []
    if not isinstance(val, list):
        die(f"{key} must be an array")
    return val


def is_python(data: dict) -> bool:
    return data["LANGUAGE"].strip().lower() == "python"


def snake_slug(uc_id: str, name: str) -> str:
    tail = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    num = uc_id.lower().replace("-", "_")
    return tail or num


def default_test_paths(data: dict, uc: dict) -> tuple[str, str]:
    pkg = data.get("PYTHON_PACKAGE") or "app"
    slug = snake_slug(uc["id"], uc.get("name") or uc["id"])
    if not is_python(data):
        unit = uc.get("unit_test") or "—"
        integ = uc.get("integration_test") or "—"
        return unit, integ
    unit = uc.get("unit_test") or f"tests/unit/{pkg}/test_{slug}.py"
    integ = uc.get("integration_test") or f"tests/integration/{pkg}/test_{slug}.py"
    return unit, integ


def runtime_block(data: dict) -> str:
    mode = data["RUNTIME_MODE"]
    gpu = (data.get("USE_GPU") or "").strip().lower() == "yes"
    if mode == "uv-native":
        title = (
            "**활성 모드: `uv-native` (GPU/MPS)**"
            if gpu
            else "**활성 모드: `uv-native`**"
        )
        app_line = (
            "- 앱·CLI: 호스트 `uv run` (Docker 앱 컨테이너 금지 — MPS 미지원)\n"
            if gpu
            else "- 앱·CLI: 호스트 `uv run`\n"
        )
        return (
            f"{title}\n"
            "\n"
            f"{app_line}"
            "- 인프라(DB 등 필요 시): compose **인프라만**\n"
            "- 개발 도구: 호스트 `uv run`\n"
            "- 중지: `./scripts/stop.sh` (또는 PLAN에 명시한 방식)\n"
        )
    py_tools = (
        "- 개발 도구(ruff, mypy, pytest): **항상 호스트** `uv run`\n"
        "- 컨테이너 안에서 린트·단위 테스트 실행 금지\n"
        if is_python(data)
        else "- 개발 도구: 호스트에서 패키지 매니저 명령 (아래 표)\n"
    )
    return (
        "**활성 모드: `docker-compose`**\n"
        "\n"
        "- 앱·CLI: `docker compose build` / `up -d` / `down`\n"
        "- 인프라(DB/Redis 등): 같은 compose 스택\n"
        f"{py_tools}"
    )


def commands_table(data: dict) -> str:
    mode = data["RUNTIME_MODE"]
    if mode == "uv-native":
        app = (
            "### 앱 워크로드 (uv-native)\n"
            "\n"
            "| 작업 | 명령어 |\n"
            "|------|--------|\n"
            f"| 실행 | `{data['UV_DEV_COMMAND']}` |\n"
            f"| 중지 | `{data['UV_STOP_COMMAND']}` |\n"
        )
    else:
        app = (
            "### 앱 워크로드 (docker-compose)\n"
            "\n"
            "| 작업 | 명령어 |\n"
            "|------|--------|\n"
            "| 빌드 | `docker compose build` |\n"
            f"| 실행 | `{data['DEV_COMMAND']}` |\n"
            f"| 중지 | `{data['STOP_COMMAND']}` |\n"
            "| 로그 | `docker compose logs -f` |\n"
        )
    tools_head = (
        "### 공통 (항상 호스트 uv)" if is_python(data) else "### 공통 (호스트)"
    )
    tools = (
        f"{tools_head}\n"
        "\n"
        "| 작업 | 명령어 |\n"
        "|------|--------|\n"
        f"| 의존성 설치 | `{data['PACKAGE_INSTALL_COMMAND']}` |\n"
        f"| 단위 테스트 | `{data['UNIT_TEST_COMMAND']}` |\n"
        f"| 통합 테스트 | `{data['INTEGRATION_TEST_COMMAND']}` |\n"
        f"| 린트 | `{data['LINT_COMMAND']}` |\n"
        f"| 포맷 검사 | `{data['FORMAT_CHECK_COMMAND']}` |\n"
        f"| 타입 검사 | `{data['TYPECHECK_COMMAND']}` |\n"
        f"| 커밋 전 검사 | `{data['PRE_COMMIT_COMMAND']}` |\n"
    )
    return app + "\n" + tools


def build_uc_ctx(data: dict) -> dict[str, str]:
    ucs = as_list(data, "use_cases")
    if not ucs:
        die("use_cases must have at least one item")
    table_rows = []
    acceptance = []
    layers = []
    tdd = []
    phases = [
        "| 0 | — | `/scaffold` (매니페스트, compose/Dockerfile 또는 stop.sh, app shell) "
        f"| `{data['PACKAGE_INSTALL_COMMAND']}` + health/e2e 스모크 |"
    ]
    port_rows = []
    infra_rows = []
    for i, uc in enumerate(ucs):
        if not isinstance(uc, dict):
            die(f"use_cases[{i}] must be an object")
        for key in ("id", "name", "priority", "desc", "given", "when", "then", "failure"):
            if not str(uc.get(key) or "").strip():
                die(f"use_cases[{i}].{key} is required")
        uid = uc["id"].strip()
        name = uc["name"].strip()
        unit, integ = default_test_paths(data, uc)
        red_path = uc.get("red_path") or unit
        table_rows.append(
            f"| {uid} | {name} | BC-01 | {uc['priority']} | `planned` | `{red_path}` |"
        )
        acceptance.append(
            f"#### {uid} — {name}\n"
            "\n"
            f"- **Given**: {uc['given']}\n"
            f"- **When**: {uc['when']}\n"
            f"- **Then**: {uc['then']}\n"
            f"- **실패/경계**: {uc['failure']}\n"
        )
        domain = uc.get("domain") or "—"
        application = uc.get("application") or "—"
        infrastructure = uc.get("infrastructure") or "—"
        presentation = uc.get("presentation") or "—"
        layers.append(
            f"| {uid} | `{domain}` | `{application}` | `{infrastructure}` | `{presentation}` |"
        )
        red = uc.get("red") or "실패 테스트 선행"
        tdd.append(f"| {uid} | `{unit}` | `{integ}` | {red} |")
        base = 3 * i
        phases.append(
            f"| {base + 1} | {uid} | Domain + Application (TDD) | 단위 테스트 Green |"
        )
        phases.append(
            f"| {base + 2} | {uid} | Infrastructure + 통합 | 통합 테스트 Green |"
        )
        phases.append(
            f"| {base + 3} | {uid} | Presentation | `{data['PRE_COMMIT_COMMAND']}` 통과 |"
        )
        port = uc.get("port")
        adapter = uc.get("adapter")
        if port:
            port_rows.append(f"| {port} | {adapter or '—'} | {uid} |")
        svc = uc.get("infra_service")
        if isinstance(svc, dict) and svc.get("name"):
            infra_rows.append(
                f"| {uid} | {svc.get('name')} | {svc.get('config') or '—'} | "
                f"{svc.get('port') or '—'} | {svc.get('note') or '—'} |"
            )
        elif isinstance(svc, str) and svc.strip():
            infra_rows.append(f"| {uid} | {svc.strip()} | — | — | — |")

    if port_rows:
        port_body = (
            "| Port | Adapter | UC-ID |\n"
            "|------|---------|-------|\n" + "\n".join(port_rows) + "\n"
        )
    else:
        port_body = "이 Phase에 Port 없음\n"

    if infra_rows:
        infra_body = (
            "| UC-ID | 서비스 | 설정 | 포트 | 비고 |\n"
            "|-------|--------|------|------|------|\n" + "\n".join(infra_rows) + "\n"
        )
    else:
        infra_body = "—\n"

    uls = as_list(data, "ubiquitous_language")
    ul_rows = []
    for term in uls:
        if not isinstance(term, dict):
            die("ubiquitous_language items must be objects")
        if term.get("term"):
            ul_rows.append(
                f"| {term.get('term')} | {term.get('definition') or '—'} | "
                f"{term.get('context') or 'BC-01'} |"
            )
    if ul_rows:
        ul_body = (
            "| 용어 | 정의 | Context |\n"
            "|------|------|---------|\n" + "\n".join(ul_rows) + "\n"
        )
    else:
        ul_body = "hello에 정의된 도메인 용어 없음.\n"

    env_rows = []
    for env in as_list(data, "env_vars"):
        if not isinstance(env, dict) or not env.get("name"):
            die("env_vars items need name")
        env_rows.append(
            f"| {env['name']} | {env.get('desc') or '—'} | "
            f"{env.get('required') or 'no'} | {env.get('example') or '—'} |"
        )
    risk_rows = []
    for risk in as_list(data, "risks"):
        if not isinstance(risk, dict) or not risk.get("item"):
            die("risks items need item")
        risk_rows.append(
            f"| {risk['item']} | {risk.get('impact') or '—'} | {risk.get('mitigation') or '—'} |"
        )

    return {
        "UC_TABLE_ROWS": "\n".join(table_rows),
        "UC_ACCEPTANCE_SECTIONS": "\n".join(acceptance),
        "UC_LAYER_ROWS": "\n".join(layers),
        "UC_TDD_ROWS": "\n".join(tdd),
        "UC_PHASE_ROWS": "\n".join(phases),
        "PORT_BODY": port_body,
        "INFRA_BODY": infra_body,
        "UL_BODY": ul_body,
        "ENV_VAR_ROWS": "\n".join(env_rows) if env_rows else "| — | hello에 환경 변수 없음 | — | — |",
        "RISK_ROWS": "\n".join(risk_rows) if risk_rows else "| — | hello에 명시된 리스크 없음 | — |",
    }


def substitute(text: str, ctx: dict[str, str], source: str) -> str:
    for key in OPTIONAL_LINE_KEYS:
        token = "{{" + key + "}}"
        value = ctx.get(key, "")
        if value:
            text = text.replace(token, value)
        else:
            text = re.sub(rf"^[ \t]*{re.escape(token)}[ \t]*\n", "", text, flags=re.M)
            text = text.replace(token, "")

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


def merge_gitignore(path: Path) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [
        ln
        for ln in existing.splitlines()
        if not re.match(r"^/?prompt-log/?$", ln.strip())
    ]
    have = set(lines)
    for item in GITIGNORE_EXTRA:
        if item not in have:
            lines.append(item)
            have.add(item)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_env_example(root: Path, data: dict) -> None:
    envs = as_list(data, "env_vars")
    if not envs:
        return
    lines = ["# Generated by /init-project. No secrets.\n"]
    for env in envs:
        desc = env.get("desc") or env["name"]
        example = env.get("example") or ""
        lines.append(f"# {desc}")
        lines.append(f"{env['name']}={example}")
        lines.append("")
    (root / ".env.example").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def is_fastapi(web: str) -> bool:
    return (web or "").strip().lower() in {"fastapi", "starlette"}


def write_scaffold_values(root: Path, data: dict, version: str) -> None:
    web = data["WEB_FRAMEWORK"].strip()
    has_http = is_fastapi(web)
    env_vars = []
    for env in as_list(data, "env_vars"):
        if isinstance(env, dict) and env.get("name"):
            env_vars.append(
                {
                    "name": env["name"],
                    "example": env.get("example") or "",
                }
            )
    payload = {
        "PROJECT_NAME": data["PROJECT_NAME"],
        "ONE_LINE_DESCRIPTION": data["ONE_LINE_DESCRIPTION"],
        "LANGUAGE": data["LANGUAGE"],
        "RUNTIME_VERSION": data["RUNTIME_VERSION"],
        "PYTHON_PACKAGE": data["PYTHON_PACKAGE"],
        "PACKAGE_ROOT": data["PACKAGE_ROOT"],
        "RUNTIME_MODE": data["RUNTIME_MODE"],
        "WEB_FRAMEWORK": data["WEB_FRAMEWORK"],
        "CLI_FRAMEWORK": data["CLI_FRAMEWORK"],
        "HAS_HTTP": has_http,
        "ENV_VARS": env_vars,
        "TEMPLATE_VERSION": version,
    }
    grok = root / ".grok"
    grok.mkdir(parents=True, exist_ok=True)
    (grok / "scaffold-values.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def copy_prompt_log(init_dir: Path, root: Path, ctx: dict[str, str]) -> None:
    src = init_dir / "prompt-log"
    dest = root / "prompt-log"
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {
        "README.md.template": "README.md",
        "INDEX.md.template": "INDEX.md",
        "_topic.md.template": "_topic.md.template",
    }
    for src_name, dest_name in mapping.items():
        text = (src / src_name).read_text(encoding="utf-8")
        (dest / dest_name).write_text(substitute(text, ctx, src_name), encoding="utf-8")


def build_ctx(data: dict, version: str) -> dict[str, str]:
    for key in REQUIRED_STR:
        require_str(data, key)
    for banned in RENDERED_BY_SCRIPT:
        if banned in data and banned != "PYTHON_RULES_ROW":
            die(f"do not set {banned} in placeholders.json (render computes it)")
    ctx = {k: data[k] for k in REQUIRED_STR}
    ctx["TEMPLATE_VERSION"] = version
    if data["RUNTIME_MODE"] == "uv-native":
        ctx["DEV_COMMAND_OR_UV"] = data["UV_DEV_COMMAND"]
        ctx["STOP_COMMAND_OR_UV"] = data["UV_STOP_COMMAND"]
    else:
        ctx["DEV_COMMAND_OR_UV"] = data["DEV_COMMAND"]
        ctx["STOP_COMMAND_OR_UV"] = data["STOP_COMMAND"]
    ctx["RUNTIME_ACTIVE_BLOCK"] = runtime_block(data).rstrip()
    ctx["COMMANDS_TABLE"] = commands_table(data).rstrip()
    if is_python(data):
        ctx["PYTHON_RULES_ROW"] = "| `.grok/rules/python.md` | uv·ruff·mypy |"
    else:
        ctx["PYTHON_RULES_ROW"] = ""
    ctx.update(build_uc_ctx(data))
    ctx["data_LANGUAGE"] = data["LANGUAGE"]  # unused; keep ctx strings only
    ctx.pop("data_LANGUAGE")
    for k, v in ctx.items():
        if "{{" in v:
            die(f"value for {k} contains placeholder syntax")
    return ctx


def render(root: Path) -> None:
    init_dir = root / "init"
    ph = init_dir / "placeholders.json"
    if not ph.exists():
        die(f"missing {ph}")
    data = load_json(ph)
    version_file = root / ".grok" / "template-version"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "0.0.0-dev"
    ctx = build_ctx(data, version)

    jobs = [
        (init_dir / "AGENTS.md.template", root / "AGENTS.md"),
        (init_dir / "PLAN.md.template", root / "PLAN.md"),
        (init_dir / "project-README.md.template", root / "README.md"),
        (
            init_dir / ".grok" / "rules" / "architecture.md.template",
            root / ".grok" / "rules" / "architecture.md",
        ),
        (
            init_dir / ".grok" / "rules" / "testing.md.template",
            root / ".grok" / "rules" / "testing.md",
        ),
    ]
    if is_python(data):
        jobs.append(
            (
                init_dir / ".grok" / "rules" / "python.md.template",
                root / ".grok" / "rules" / "python.md",
            )
        )
    else:
        py_md = root / ".grok" / "rules" / "python.md"
        if py_md.exists():
            py_md.unlink()

    for src, dest in jobs:
        if not src.exists():
            die(f"missing template {src}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(substitute(src.read_text(encoding="utf-8"), ctx, src.name), encoding="utf-8")

    copy_prompt_log(init_dir, root, ctx)
    merge_gitignore(root / ".gitignore")
    write_env_example(root, data)
    write_scaffold_values(root, data, version)
    print(f"rendered {len(jobs)} files + prompt-log + gitignore + scaffold-values.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render grok-template project files")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    render(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
