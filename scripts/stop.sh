#!/bin/sh
set -eu
# Only the `python -m <package>` serve process for this app (not arbitrary
# commands that happen to mention the package name).
pattern="python[0-9.]* -m large_files_embedding( |$)"
if pgrep -f "$pattern" >/dev/null 2>&1; then
  pkill -f "$pattern" || true
fi
