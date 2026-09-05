#!/usr/bin/env python3
"""Validate /init-project outputs against hello.txt and placeholders.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from hello_parse import (
    PY_IDENT,
    has_gpu,
    language_from_hello,
    parse_hello_envs,
    parse_hello_ucs,
    runtime_mode_from_hello,
    section,
)

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")

GENERATED = (
    "AGENTS.md",
    "PLAN.md",
    "README.md",
    ".grok/rules/architecture.md",
    ".grok/rules/testing.md",
    "prompt-log/README.md",
    "prompt-log/INDEX.md",
    "prompt-log/_topic.md.template",
    ".grok/scaffold-values.json",
)


def die(msg: str) -> None:
    print(f"validate.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"ok: {msg}")


def load_hello(path: Path) -> str:
    if not path.exists():
        die(f"missing {path}")
    return path.read_text(encoding="utf-8")


def leftover_placeholders(root: Path, python: bool) -> None:
    paths = [root / p for p in GENERATED]
    paths.append(root / ".gitignore")
    if python:
        paths.append(root / ".grok" / "rules" / "python.md")
    env = root / ".env.example"
    if env.exists():
        paths.append(env)
    bad: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        found = PLACEHOLDER_RE.findall(text)
        if found:
            bad.append(f"{path.relative_to(root)}: {', '.join(found)}")
    if bad:
        die("leftover placeholders:\n  " + "\n  ".join(bad))
    ok("no leftover {{placeholders}}")


def check_files(root: Path, python: bool) -> None:
    missing = [p for p in GENERATED if not (root / p).exists()]
    if python and not (root / ".grok" / "rules" / "python.md").exists():
        missing.append(".grok/rules/python.md")
    if not python and (root / ".grok" / "rules" / "python.md").exists():
        die("python.md must not exist for non-Python")
    if missing:
        die("missing files: " + ", ".join(missing))
    ok("required files exist")


def check_gitignore(root: Path) -> None:
    gi = (root / ".gitignore").read_text(encoding="utf-8")
    if re.search(r"(?m)^prompt-log/?$", gi):
        die(".gitignore ignores prompt-log/")
    if ".grok/uc-plans/" not in gi:
        die(".gitignore missing .grok/uc-plans/")
    if ".grok/reviews/" not in gi:
        die(".gitignore missing .grok/reviews/")
    ok(".gitignore")


def check_agents_plan_readme(root: Path, ucs: list[tuple[str, str]], python: bool) -> None:
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    plan = (root / "PLAN.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    if "### 스캐폴드 마커" not in agents:
        die("AGENTS.md missing ### 스캐폴드 마커")
    if python and "python.md" not in agents:
        die("AGENTS.md missing python.md row")
    if not python and ".grok/rules/python.md" in agents:
        die("AGENTS.md has python.md row for non-Python")
    if "cp -r grok-template" in readme:
        die("README.md still has template copy instructions")
    if re.search(r"(?m)^\|\s*상태\s*\|\s*`draft`\s*\|", plan) is None:
        die("PLAN.md approval status is not draft")
    for uid, name in ucs:
        if uid not in plan:
            die(f"PLAN.md missing {uid}")
        if f"#### {uid}" not in plan:
            die(f"PLAN.md missing acceptance section for {uid}")
        # GWT must not be empty bullets
        if re.search(rf"#### {re.escape(uid)}[\s\S]*?- \*\*Given\*\*:\s*$", plan, re.M):
            die(f"PLAN.md empty Given for {uid}")
    uc_table_ids = []
    in_uc = False
    for line in plan.splitlines():
        if line.startswith("## Use Case"):
            in_uc = True
            continue
        if in_uc and line.startswith("## "):
            break
        if in_uc and re.match(r"^\| UC-\d+ \|", line):
            uc_table_ids.append(line.split("|")[1].strip())
    expected = [u[0] for u in ucs]
    if uc_table_ids != expected:
        die(f"PLAN Use Case table ids {uc_table_ids} != hello {expected}")
    ok(f"PLAN UC table matches hello ({len(expected)})")
    ok("AGENTS/PLAN/README content")


def check_json_vs_hello(data: dict, hello: str) -> None:
    hello_ucs = parse_hello_ucs(hello)
    if not hello_ucs:
        die("hello.txt has no ## 기능 items")
    json_ucs = data.get("use_cases") or []
    json_ids = [(u.get("id"), u.get("name")) for u in json_ucs]
    hello_ids = hello_ucs
    if [i[0] for i in json_ids] != [i[0] for i in hello_ids]:
        die(f"use_cases ids { [i[0] for i in json_ids] } != hello { [i[0] for i in hello_ids] }")
    json_names = [u.get("name") or "" for u in json_ucs]
    if len(hello_ids) != len(json_names):
        die("use_cases count != hello 기능 count")
    for (_id, hname), jname in zip(hello_ids, json_names):
        if hname.split("(")[0].strip() not in jname and jname not in hname:
            # allow shortened names; require overlap of first phrase
            if hname[:4] not in jname and jname[:4] not in hname:
                die(f"{_id} name {jname!r} does not match hello {hname!r}")

    hello_envs = parse_hello_envs(hello)
    json_envs = [e.get("name") for e in data.get("env_vars") or []]
    if sorted(json_envs) != sorted(hello_envs):
        die(f"env_vars {json_envs} != hello {hello_envs}")

    has_risk_section = bool(section(hello, "리스크") or section(hello, "리스크 & 의존성"))
    risks = data.get("risks") or []
    if not has_risk_section and risks:
        die("hello has no risk section but placeholders.risks is not empty")

    lang = language_from_hello(hello)
    json_lang = data.get("LANGUAGE")
    stack = section(hello, "기술 스택")
    if lang is not None:
        if json_lang != lang:
            die(f"LANGUAGE {json_lang!r} != hello stack {lang!r}")
    elif json_lang != "Python":
        if not json_lang or not re.search(
            rf"\b{re.escape(str(json_lang))}\b", stack, re.I
        ):
            die(
                f"LANGUAGE {json_lang!r} is not in hello 기술 스택 "
                "(unspecified stack defaults to Python)"
            )

    gpu = has_gpu(hello)
    mode = data.get("RUNTIME_MODE")
    py = data.get("LANGUAGE") == "Python"
    hello_mode = runtime_mode_from_hello(hello)
    if gpu and py and mode != "uv-native":
        die("Python + ## GPU → RUNTIME_MODE must be uv-native")
    if gpu and not py and mode == "uv-native":
        die("non-Python GPU must not use uv-native")
    # Python + ## GPU wins over ## 실행 모드 (MPS is not available in Docker).
    if hello_mode and mode != hello_mode and not (gpu and py):
        die(f"RUNTIME_MODE {mode!r} != hello 실행 모드 {hello_mode!r}")
    if not gpu and not hello_mode and mode != "docker-compose":
        die("no ## GPU and no 실행 모드 → RUNTIME_MODE must be docker-compose")
    if py:
        pkg = data.get("PYTHON_PACKAGE") or ""
        if not PY_IDENT.match(str(pkg)):
            die(f"PYTHON_PACKAGE {pkg!r} is not a Python identifier")
    ok("placeholders.json matches hello")


PLACEHOLDER_COMMANDS = {"", "—", "-", "— (미사용)"}


def check_non_python_commands(data: dict) -> None:
    if (data.get("LANGUAGE") or "").strip().lower() == "python":
        return
    lang = data.get("LANGUAGE")
    for key in ("PACKAGE_INSTALL_COMMAND", "UNIT_TEST_COMMAND", "PRE_COMMIT_COMMAND"):
        val = (data.get(key) or "").strip()
        if val in PLACEHOLDER_COMMANDS:
            die(f"{key} is unset for non-Python LANGUAGE={lang!r}")
    ok("non-Python commands are set")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--hello", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    hello_path = args.hello or (root / "hello.txt")
    hello = load_hello(hello_path)
    ph = root / "init" / "placeholders.json"
    if not ph.exists():
        die(f"missing {ph}")
    data = json.loads(ph.read_text(encoding="utf-8"))
    check_json_vs_hello(data, hello)
    check_non_python_commands(data)
    python = data.get("LANGUAGE") == "Python"
    check_files(root, python)
    leftover_placeholders(root, python)
    check_gitignore(root)
    check_agents_plan_readme(root, parse_hello_ucs(hello), python)
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    if "### 스캐폴드 마커" not in agents:
        die("AGENTS.md missing scaffold marker")
    print("validate.py: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
