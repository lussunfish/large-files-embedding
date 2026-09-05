#!/usr/bin/env python3
"""Check that a planner UC plan file has the required sections."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED = (
    "## PLAN revision needed",
    "## Scope",
    "## Critical files",
    "## TDD",
    "## Layers",
)


def missing_sections(text: str) -> list[str]:
    return [heading for heading in REQUIRED if heading not in text]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate implement-uc planner output")
    parser.add_argument("plan_file", type=Path)
    args = parser.parse_args()
    path = args.plan_file
    if not path.is_file():
        print(f"check_uc_plan.py: missing {path}", file=sys.stderr)
        return 1
    missing = missing_sections(path.read_text(encoding="utf-8"))
    if missing:
        print(
            "check_uc_plan.py: planner output missing " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    print("check_uc_plan.py: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
