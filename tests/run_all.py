#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""run_all.py - run every self-test that needs no game data.

This is the pre-PR gate and the command CI runs. Each check is self-contained
(synthetic fixtures only); none of them touch the game's files. Run it from
anywhere:

    python tests/run_all.py

Exit status: 0 = all passed, 1 = one or more failed. Standard library only.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKS = [
    ("hog extractor self-test",
     [sys.executable, os.path.join("tests", "hog_selftest.py")]),
    ("hog packer round-trip",
     [sys.executable, os.path.join("tools", "hog_pack.py"), "--selftest"]),
    ("sl_patch engine self-test",
     [sys.executable, os.path.join("tests", "sl_patch_selftest.py")]),
    ("shp model parser self-test",
     [sys.executable, os.path.join("tools", "shp_parse.py"), "--selftest"]),
    ("game-data guard (tracked tree)",
     [sys.executable, os.path.join("tools", "check_no_game_data.py")]),
]


def main():
    failures = []
    for name, cmd in CHECKS:
        print("=== %s ===" % name)
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            failures.append(name)
        print("")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
