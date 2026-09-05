#!/usr/bin/env python3
"""Machine-check PLAN approval and AGENTS.md scaffold-marker gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GENERIC_MANIFESTS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
)


def heading_block(text: str, heading: str) -> str:
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.M)
    match = pattern.search(text)
    if not match:
        return ""
    rest = text[match.end() :]
    nxt = re.search(r"^#{1,3} ", rest, re.M)
    return rest[: nxt.start() if nxt else None]


def approval_status(plan: str) -> str:
    block = heading_block(plan, "## 계획 승인")
    if not block:
        return ""
    row = re.search(r"^\|\s*상태\s*\|\s*([^|]+)\|", block, re.M)
    if not row:
        return ""
    return re.sub(r"[`*]", "", row.group(1)).strip().lower()


def parse_gate_rows(agents: str) -> list[tuple[str, str]]:
    block = heading_block(agents, "### 스캐폴드 마커")
    if not block:
        return []
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in block.splitlines():
        if line.startswith("|") and "조건" in line and "파일" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if re.match(r"^\|[\s:|-]+\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


def row_applies(condition: str, language: str, mode: str) -> bool:
    cond = condition.strip()
    lang = language.strip().lower()
    runtime = mode.strip().lower()
    compact = cond.replace(" ", "")
    if "LANGUAGE=Python" in compact:
        return lang == "python"
    if "Node" in cond or "TypeScript" in cond:
        return lang in {"node", "typescript", "javascript"}
    if cond == "Go" or cond.startswith("Go "):
        return lang == "go"
    if "Rust" in cond:
        return lang == "rust"
    if "그 외" in cond:
        return lang not in {
            "python",
            "node",
            "typescript",
            "javascript",
            "go",
            "rust",
        }
    if "docker-compose" in cond:
        return runtime == "docker-compose"
    return False


def check_file_spec(root: Path, spec: str) -> str | None:
    paths = re.findall(r"`([^`]+)`", spec)
    if paths:
        rel = paths[0]
        path = root / rel
        if not path.is_file():
            return f"missing {rel}"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"cannot read {rel}: {exc}"
        if not text.strip():
            return f"empty {rel}"
        if "[project]" in spec or "[tool." in spec:
            if "[project]" not in text and "[tool." not in text:
                return f"{rel} needs [project] or [tool."
        return None
    if "매니페스트" in spec:
        for rel in GENERIC_MANIFESTS:
            path = root / rel
            if path.is_file():
                try:
                    if path.read_text(encoding="utf-8").strip():
                        return None
                except OSError:
                    continue
        return "no package-manager manifest found"
    return f"unrecognized gate file spec: {spec}"


def load_values(root: Path) -> dict:
    path = root / ".grok" / "scaffold-values.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_errors(root: Path, scaffold_only: bool = False) -> list[str]:
    errors: list[str] = []
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        return ["missing AGENTS.md — run /init-project"]
    agents = agents_path.read_text(encoding="utf-8")
    if "### 스캐폴드 마커" not in agents:
        errors.append("AGENTS.md missing ### 스캐폴드 마커 — run /init-project")

    values = load_values(root)
    if not values:
        errors.append("missing .grok/scaffold-values.json — run /init-project")
        language, mode = "", ""
    else:
        language = str(values.get("LANGUAGE") or "")
        mode = str(values.get("RUNTIME_MODE") or "")

    if not scaffold_only:
        plan_path = root / "PLAN.md"
        if not plan_path.exists():
            errors.append("missing PLAN.md — run /init-project")
        else:
            status = approval_status(plan_path.read_text(encoding="utf-8"))
            if status != "approved":
                errors.append(
                    f"PLAN.md approval is {status or '(missing)'} (need `approved`). "
                    "Set ## 계획 승인 상태 to `approved` then re-run."
                )

    rows = parse_gate_rows(agents)
    if "### 스캐폴드 마커" in agents and not rows:
        errors.append("AGENTS.md scaffold marker has no gate table")
    for cond, spec in rows:
        if not row_applies(cond, language, mode):
            continue
        err = check_file_spec(root, spec)
        if err:
            errors.append(f"scaffold gate ({cond}): {err}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check PLAN approval and scaffold-marker gates"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--scaffold-only",
        action="store_true",
        help="Skip PLAN approval (for /scaffold)",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    errors = collect_errors(root, scaffold_only=args.scaffold_only)
    if not errors:
        print("check_gates.py: ok")
        return 0
    for item in errors:
        print(f"check_gates.py: {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
