#!/usr/bin/env python3
"""Decide planner/security/re-review for one UC. Prints JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from check_gates import heading_block

ISSUE_HEAD = re.compile(
    r"^### Issue \d+ -- Severity: (bug|suggestion|nit)\s*$", re.M | re.I
)
STATUS_LINE = re.compile(r"^\s*Status:\s*(\w+)", re.M | re.I)
SECURITY_SEEN = Path(".grok/uc-plans/_security-presentations.txt")
BC_PLAN = Path(".grok/uc-plans/_bc-plan.md")


def die(msg: str, code: int = 1) -> None:
    print(f"uc_policy.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def strip_cell(raw: str) -> str:
    return re.sub(r"[`*]", "", raw).strip()


def table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        if re.match(r"^\|[\s:|-]+\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() in {"uc-id", "항목", "port", "용어"}:
            continue
        if cells:
            rows.append(cells)
    return rows


def parse_uc_status(plan: str) -> list[dict[str, str]]:
    block = heading_block(plan, "## Use Case")
    out: list[dict[str, str]] = []
    for cells in table_rows(block):
        if len(cells) < 5:
            continue
        uid = strip_cell(cells[0])
        if not re.match(r"^UC-\d+$", uid, re.I):
            continue
        out.append(
            {
                "id": uid,
                "name": strip_cell(cells[1]) if len(cells) > 1 else uid,
                "status": strip_cell(cells[4]).lower() if len(cells) > 4 else "",
            }
        )
    return out


def parse_presentations(plan: str) -> dict[str, str]:
    block = heading_block(plan, "### 레이어 배치")
    found: dict[str, str] = {}
    for cells in table_rows(block):
        if len(cells) < 5:
            continue
        uid = strip_cell(cells[0])
        if re.match(r"^UC-\d+$", uid, re.I):
            found[uid] = strip_cell(cells[4])
    return found


def parse_layers(plan: str) -> dict[str, dict[str, str]]:
    block = heading_block(plan, "### 레이어 배치")
    found: dict[str, dict[str, str]] = {}
    for cells in table_rows(block):
        if len(cells) < 5:
            continue
        uid = strip_cell(cells[0])
        if not re.match(r"^UC-\d+$", uid, re.I):
            continue
        found[uid] = {
            "domain": strip_cell(cells[1]),
            "application": strip_cell(cells[2]),
            "infrastructure": strip_cell(cells[3]),
            "presentation": strip_cell(cells[4]),
        }
    return found


def parse_acceptance(plan: str, uc_id: str) -> dict[str, str]:
    block = heading_block(plan, "### UC 수용 기준 (Given/When/Then)")
    if not block:
        block = heading_block(plan, "### UC 수용 기준")
    pattern = re.compile(
        rf"^####\s+{re.escape(uc_id)}\b.*$", re.M
    )
    match = pattern.search(block)
    if not match:
        return {}
    rest = block[match.end() :]
    nxt = re.search(r"^#### ", rest, re.M)
    body = rest[: nxt.start() if nxt else None]
    fields: dict[str, str] = {}
    for key, label in (
        ("given", "Given"),
        ("when", "When"),
        ("then", "Then"),
        ("failure", "실패/경계"),
    ):
        row = re.search(rf"-\s*\*\*{label}\*\*:\s*(.+)", body)
        fields[key] = row.group(1).strip() if row else ""
    return fields


def remaining_ids(rows: list[dict[str, str]], current: str, queue: list[str]) -> list[str]:
    if queue:
        try:
            idx = queue.index(current)
            later_queue = queue[idx + 1 :]
        except ValueError:
            later_queue = list(queue)
    else:
        later_queue = []
    active = {
        row["id"]
        for row in rows
        if row["status"] in {"planned", "in_progress", ""}
    }
    later_plan: list[str] = []
    seen = False
    for row in rows:
        if row["id"] == current:
            seen = True
            continue
        if seen and row["id"] in active:
            later_plan.append(row["id"])
    out: list[str] = []
    for uid in later_queue + later_plan:
        if uid != current and uid not in out:
            out.append(uid)
    return out


def read_seen(root: Path) -> set[str]:
    path = root / SECURITY_SEEN
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def record_security(root: Path, presentation: str) -> None:
    if not presentation:
        return
    path = root / SECURITY_SEEN
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = read_seen(root)
    if presentation in seen:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(presentation + "\n")


def gwt_complete(fields: dict[str, str]) -> bool:
    return all(fields.get(key) for key in ("given", "when", "then", "failure"))


def layers_complete(layers: dict[str, str] | None) -> bool:
    if not layers:
        return False
    for key in ("domain", "application"):
        val = (layers.get(key) or "").strip()
        if not val or val == "—":
            return False
    return True


def need_planner(root: Path, uc_id: str, plan: str) -> tuple[bool, str]:
    fields = parse_acceptance(plan, uc_id)
    layers = parse_layers(plan).get(uc_id)
    if not gwt_complete(fields) or not layers_complete(layers):
        return True, "PLAN GWT or layer files missing — run planner"
    return False, "PLAN already has GWT and layers — write_uc_plan.py"


def need_security(
    *,
    effort: int,
    uc_id: str,
    presentation: str,
    remaining: list[str],
    presentations: dict[str, str],
    seen: set[str],
) -> tuple[bool, str]:
    if effort < 2:
        return False, "effort < 2"
    if presentation and presentation in seen:
        return False, f"presentation {presentation} already security-reviewed"
    later_same = [
        uid
        for uid in remaining
        if presentations.get(uid, presentation) == presentation
    ]
    if later_same:
        return (
            False,
            f"defer security to {later_same[-1]} (same presentation {presentation or '—'})",
        )
    return True, "last remaining UC for this presentation"


def issue_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(ISSUE_HEAD.finditer(text))
    blocks: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((match.group(1).lower(), text[match.end() : end]))
    return blocks


def open_issue_counts(text: str) -> dict[str, int]:
    counts = {"bug": 0, "suggestion": 0, "nit": 0, "open": 0}
    for severity, body in issue_blocks(text):
        status_match = STATUS_LINE.search(body)
        status = status_match.group(1).lower() if status_match else "open"
        if status != "open":
            continue
        counts["open"] += 1
        if severity in counts:
            counts[severity] += 1
    return counts


def files_with_open_issues(paths: list[Path]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            continue
        counts = open_issue_counts(path.read_text(encoding="utf-8"))
        if counts["open"]:
            out.append({"file": str(path), **counts})
    return out


def decide(
    root: Path,
    uc_id: str,
    effort: int,
    queue: list[str],
) -> dict:
    plan_path = root / "PLAN.md"
    if not plan_path.is_file():
        die("missing PLAN.md")
    plan = plan_path.read_text(encoding="utf-8")
    rows = parse_uc_status(plan)
    presentations = parse_presentations(plan)
    if not any(row["id"] == uc_id for row in rows):
        die(f"UC {uc_id} not in PLAN.md Use Case table")
    remaining = remaining_ids(rows, uc_id, queue)
    presentation = presentations.get(uc_id, "")
    planner, planner_reason = need_planner(root, uc_id, plan)
    security, security_reason = need_security(
        effort=effort,
        uc_id=uc_id,
        presentation=presentation,
        remaining=remaining,
        presentations=presentations,
        seen=read_seen(root),
    )
    return {
        "uc": uc_id,
        "effort": effort,
        "need_planner": planner,
        "need_security": security,
        "need_tests": effort >= 3,
        "presentation": presentation,
        "remaining": remaining,
        "bc_plan": str(root / BC_PLAN),
        "reason_planner": planner_reason,
        "reason_security": security_reason,
        "write_plan": (
            f"python3 .grok/skills/implement-uc/scripts/write_uc_plan.py --uc {uc_id}"
            if not planner
            else ""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Planner/security policy for one UC")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--uc", dest="uc_id")
    parser.add_argument("--effort", type=int, default=2)
    parser.add_argument(
        "--queue",
        default="",
        help="Comma-separated remaining UC ids (all mode)",
    )
    parser.add_argument(
        "--open-reviews",
        nargs="*",
        default=None,
        help="Review files: print those with Status: open issues",
    )
    parser.add_argument(
        "--record-security",
        metavar="PRESENTATION",
        help="Append presentation path as security-reviewed",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.open_reviews is not None:
        paths = [Path(item) for item in args.open_reviews]
        payload = {"rerun": files_with_open_issues(paths)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.record_security:
        record_security(root, args.record_security)
        print(json.dumps({"recorded": args.record_security}))
        return 0
    if not args.uc_id:
        die("need --uc UC-ID")
    queue = [item.strip() for item in args.queue.split(",") if item.strip()]
    payload = decide(root, args.uc_id, args.effort, queue)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
