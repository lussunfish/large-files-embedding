#!/usr/bin/env python3
"""Copy grok-template into a new project without git history or review leftovers."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_ALWAYS = {".git", ".github", "__pycache__", ".DS_Store"}
SKIP_UNDER_GROK = {"reviews", "uc-plans"}


def ignore(dirpath: str, names: list[str]) -> set[str]:
    skipped = {name for name in names if name in SKIP_ALWAYS}
    if Path(dirpath).name == ".grok":
        skipped.update(name for name in names if name in SKIP_UNDER_GROK)
    return skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy this grok-template into a new directory (no .git, .github, or reviews)."
    )
    parser.add_argument("dest", help="Destination directory (must be missing or empty)")
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Do not run git init in the destination",
    )
    args = parser.parse_args()

    src = Path(__file__).resolve().parent.parent
    dest = Path(args.dest).expanduser().resolve()

    if dest == src:
        print("Destination must not be the template itself.", file=sys.stderr)
        return 2

    if dest.exists():
        if any(dest.iterdir()):
            print(f"Refusing to overwrite non-empty directory: {dest}", file=sys.stderr)
            return 1
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)

    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=ignore)

    if not args.no_git:
        try:
            subprocess.run(
                ["git", "init"],
                cwd=dest,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Copied, but git init failed: {exc}", file=sys.stderr)

    print(f"Created {dest}")
    print("Next:")
    print(f"  cd {dest}")
    print("  cp hello.txt.example hello.txt   # GPU면 hello.txt.gpu.example")
    print("  # hello.txt 편집 후 grok 세션에서 /init-project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
