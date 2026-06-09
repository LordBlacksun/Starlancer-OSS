#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""check_no_game_data.py - the Starlancer-OSS game-data guard.

This repository must contain ONLY original code + documentation - never game
binaries, assets, disc images, or decrypted/derivative game data (copyright).
This script is the single source of truth for that rule: it is invoked by both
the local ``.githooks/pre-commit`` hook (on staged files) and the CI workflow
(on the whole tracked tree), so the two can never drift apart.

A path is blocked if its (lower-cased) name:
  - ends in a known game/binary/asset extension, or
  - matches a known game-data name pattern, or
  - (when present on disk) exceeds the 5 MB size cap.

Usage:
  python tools/check_no_game_data.py            # all tracked files (git ls-files)  [CI]
  python tools/check_no_game_data.py --staged   # staged adds/copies/mods           [hook]
  python tools/check_no_game_data.py PATH ...    # check the given paths explicitly

Exit status: 0 = clean, 1 = one or more blocked files. Standard library only.
"""
import os
import re
import subprocess
import sys

# Keep these in lock-step with .gitignore and CONTRIBUTING.md.
FORBIDDEN_EXT = re.compile(
    r"\.(exe|dll|icd|hog|iso|cue|mds|mdf|bin|bik|tga|spr|shp|fat|mp3|wav|ogg|"
    r"cab|zip|7z|rar|gpr|rep|idb|i64|fm8|iff|sav|dte)$"
)
NAME_HINT = re.compile(
    r"(lancer_decrypted|lancer\.exe|lancer\.icd|dmodes\.bin|shipstats|gunstats|"
    r"missilestats|pilotstats|\.decompiled\.c)"
)
MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Repo root = parent of this tools/ directory, so git runs against THIS repo no
# matter where the script is invoked from (hook, CI, or a stray CWD).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(args):
    """Run a git command at the repo root, return non-empty stdout lines (or [])."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [ln for ln in out.splitlines() if ln.strip()]


def reasons(path):
    """Return the list of reasons ``path`` is blocked (empty list = clean)."""
    out = []
    lc = path.lower()
    if FORBIDDEN_EXT.search(lc):
        out.append("looks like game/binary material (blocked extension)")
    if NAME_HINT.search(lc):
        out.append("matches a known game-data name pattern")
    try:
        if os.path.isfile(path):
            sz = os.path.getsize(path)
            if sz > MAX_BYTES:
                out.append(
                    "is large (%d bytes > %d) - assets must not be committed"
                    % (sz, MAX_BYTES)
                )
    except OSError:
        pass
    return out


def collect(argv):
    """Decide which paths to check, from argv (see module docstring)."""
    if argv and argv[0] == "--staged":
        return _git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    if argv and argv[0] in ("--all", "--tracked"):
        return _git(["ls-files"])
    if argv:
        return argv
    return _git(["ls-files"])  # default: the whole tracked tree (CI)


def main(argv):
    blocked = 0
    for p in collect(argv):
        rs = reasons(p)
        for r in rs:
            print("BLOCKED: '%s' %s." % (p, r))
        if rs:
            blocked += 1
    if blocked:
        print("")
        print("Rejected by the Starlancer-OSS game-data guard (copyright/data protection).")
        print("Only original code/docs belong here - never game binaries or assets.")
        print("False positive (a doc filename that merely contains a blocked word)?")
        print("  local commit:  git commit --no-verify")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
