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
    # The codec inside almost every resource.hog member. Fixtures are hand-built
    # opcode streams, so this covers all five forms without any game data.
    ("refpack decompressor self-test",
     [sys.executable, os.path.join("tools", "refpack.py"), "--selftest"]),
    ("sl_patch engine self-test",
     [sys.executable, os.path.join("tests", "sl_patch_selftest.py")]),
    ("shp model parser self-test",
     [sys.executable, os.path.join("tools", "shp_parse.py"), "--selftest"]),
    # A hand-assembled mission script: every control-flow form, plus tripwires
    # proving a misread operand width raises instead of decoding quietly wrong.
    ("dte script disassembler self-test",
     [sys.executable, os.path.join("tests", "dte_selftest.py")]),
    # OpenReliant's mission name in section 21: shown when well formed, each
    # malformed form reported in words, and no change at all where it is absent.
    ("dte OpenReliant mission-name self-test",
     [sys.executable, os.path.join("tests", "dte_ormn_selftest.py")]),
    # Studio's logic, with no GUI toolkit involved. slstudio_app.py cannot be
    # imported without customtkinter, so before slstudio_core.py existed no check
    # here touched the app at all and the Linux CI leg covered none of it.
    ("studio core self-test (headless)",
     [sys.executable, os.path.join("tools", "slstudio_core.py"), "selftest"]),
    # A logo is replaced by its own first frame, a movie every Bink reader plays,
    # checked against openreliant's reader rules on synthetic movies.
    ("boot-video blanker self-test (synthetic movies)",
     [sys.executable, os.path.join("tools", "blank_boot_videos.py"), "--selftest"]),
    # Stat labels as openreliant's engine code names them; values a float32 cannot
    # hold are refused before anything is written.
    ("stat editor self-test (synthetic table)",
     [sys.executable, os.path.join("tools", "slstats.py"), "--selftest"]),
    # Skips itself cleanly when unicorn is absent, so CI legs without the optional
    # dependency stay green while machines that have it verify the harness.
    ("emulation harness self-test (synthetic program)",
     [sys.executable, os.path.join("tools", "sl_emu.py"), "selftest"]),
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
