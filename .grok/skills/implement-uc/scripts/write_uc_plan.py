#!/usr/bin/env python3
"""Write .grok/uc-plans/<UC-ID>.md from PLAN.md (no planner LLM)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_gates import heading_block
from uc_policy import (
    BC_PLAN,
    die,
    layers_complete,
    parse_acceptance,
    parse_layers,
    parse_uc_status,
    strip_cell,
    table_rows,
)


def load_values(root: Path) -> dict:
    path = root / ".grok" / "scaffold-values.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def existing_under(root: Path, rel: str) -> list[str]:
    folder = root / rel
    if not folder.is_dir():
        return []
    out: list[str] = []
    for path in sorted(folder.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        out.append(str(path.relative_to(root)))
    return out


def parse_tdd(plan: str, uc_id: str) -> dict[str, str]:
    block = heading_block(plan, "## TDD 테스트 계획")
    for cells in table_rows(block):
        if len(cells) < 4:
            continue
        if strip_cell(cells[0]) != uc_id:
            continue
        return {
            "unit": strip_cell(cells[1]),
            "integration": strip_cell(cells[2]),
            "red": strip_cell(cells[3]) if len(cells) > 3 else "",
        }
    return {}


def parse_ports(plan: str, uc_id: str) -> list[str]:
    block = heading_block(plan, "### Port & Adapter")
    rows: list[str] = []
    for cells in table_rows(block):
        if len(cells) < 3:
            continue
        if strip_cell(cells[-1]) == uc_id or uc_id in strip_cell(cells[-1]):
            port = strip_cell(cells[0])
            adapter = strip_cell(cells[1]) if len(cells) > 1 else "—"
            rows.append(f"{port} / {adapter}")
    return rows


def render_plan(
    *,
    uc_id: str,
    name: str,
    fields: dict[str, str],
    layers: dict[str, str],
    tdd: dict[str, str],
    ports: list[str],
    pkg_root: str,
    reuse: list[str],
) -> str:
    domain = layers.get("domain") or "—"
    application = layers.get("application") or "—"
    infrastructure = layers.get("infrastructure") or "—"
    presentation = layers.get("presentation") or "—"
    unit = tdd.get("unit") or "—"
    red = tdd.get("red") or fields.get("failure") or "실패 테스트 선행"
    port_line = ", ".join(ports) if ports else "PLAN Port 표"
    reuse_lines = (
        "\n".join(f"- `{path}` — existing" for path in reuse)
        if reuse
        else "- none yet (scaffold only) — create shared domain listed in Layers"
    )
    return (
        f"## PLAN revision needed\n"
        f"no\n\n"
        f"## Scope\n"
        f"- In: {uc_id} {name}. Given: {fields.get('given')}. "
        f"When: {fields.get('when')}. Then: {fields.get('then')}. "
        f"Failure: {fields.get('failure')}.\n"
        f"- Out: other UCs' application modules and tests. "
        f"Do not replace shared `domain/{domain}` with a per-UC domain file.\n\n"
        f"## Critical files\n"
        f"- `{pkg_root}/domain/{domain}` — shared entity (extend, do not fork)\n"
        f"- `{pkg_root}/application/{application}` — this UC\n"
        f"- `{pkg_root}/infrastructure/{infrastructure}` — adapter\n"
        f"- `{pkg_root}/presentation/{presentation}` — adapter\n"
        f"- `{unit}` — Red test\n\n"
        f"## TDD\n"
        f"- Red: `{unit}` — {red}\n"
        f"- Green: Domain → Application → Infrastructure → Presentation\n"
        f"- Refactor: only if tests stay green\n\n"
        f"## Layers\n"
        f"- Domain: `{domain}` (shared)\n"
        f"- Application: `{application}`\n"
        f"- Infrastructure: `{infrastructure}`\n"
        f"- Presentation: `{presentation}`\n"
        f"- Port: {port_line}\n\n"
        f"## Existing reuse\n"
        f"{reuse_lines}\n\n"
        f"## Risks\n"
        f"- Shared domain changes must keep other UC tests green.\n"
    )


def write_bc_stub(root: Path, layers: dict[str, str], pkg_root: str) -> None:
    path = root / BC_PLAN
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    domain = layers.get("domain") or "—"
    path.write_text(
        "# Bounded context — shared domain\n\n"
        f"- Domain: `{pkg_root}/domain/{domain}`\n"
        f"- Infrastructure: `{pkg_root}/infrastructure/"
        f"{layers.get('infrastructure') or '—'}`\n"
        "- Later UCs extend this entity/port. Do not add domain/uc_NN.py.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a mechanical UC plan from PLAN.md")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--uc", dest="uc_id", required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    plan_path = root / "PLAN.md"
    if not plan_path.is_file():
        die("missing PLAN.md")
    plan = plan_path.read_text(encoding="utf-8")
    rows = {row["id"]: row for row in parse_uc_status(plan)}
    if args.uc_id not in rows:
        die(f"UC {args.uc_id} not in PLAN.md")
    fields = parse_acceptance(plan, args.uc_id)
    layers = parse_layers(plan).get(args.uc_id) or {}
    if not layers_complete(layers) or not all(
        fields.get(key) for key in ("given", "when", "then", "failure")
    ):
        die("PLAN GWT or layers incomplete — run planner")
    values = load_values(root)
    pkg_root = str(values.get("PACKAGE_ROOT") or "src/app").rstrip("/")
    reuse = []
    for folder in ("domain", "application", "infrastructure"):
        reuse.extend(existing_under(root, f"{pkg_root}/{folder}"))
    text = render_plan(
        uc_id=args.uc_id,
        name=rows[args.uc_id].get("name") or args.uc_id,
        fields=fields,
        layers=layers,
        tdd=parse_tdd(plan, args.uc_id),
        ports=parse_ports(plan, args.uc_id),
        pkg_root=pkg_root,
        reuse=reuse,
    )
    out = args.out or (root / ".grok" / "uc-plans" / f"{args.uc_id}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    write_bc_stub(root, layers, pkg_root)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
