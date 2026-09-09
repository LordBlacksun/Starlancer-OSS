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
  - (when present on disk) exceeds the 5 MB size cap,
and, for files present on disk, if their CONTENT gives them away regardless of
what they are called:
  - the first bytes carry a known executable/archive/media signature, or
  - the file is binary at all and larger than the small-binary cap.

The content checks exist because the name checks alone are trivially defeated:
a 1.1 MB decrypted executable renamed to ``notes.txt`` passes every name rule
and sits under the 5 MB cap. ALLOWLIST pins the sole legitimate binary in the
repository to its exact hash, so swapping its contents is blocked too.

Usage:
  python tools/check_no_game_data.py            # all tracked files (git ls-files)  [CI]
  python tools/check_no_game_data.py --staged   # staged adds/copies/mods           [hook]
  python tools/check_no_game_data.py PATH ...    # check the given paths explicitly

Exit status: 0 = clean, 1 = one or more blocked files. Standard library only.
"""
import hashlib
import os
import re
import subprocess
import sys

# Keep these in lock-step with .gitignore and CONTRIBUTING.md.
FORBIDDEN_EXT = re.compile(
    r"\.(exe|dll|icd|hog|iso|cue|mds|mdf|bin|bik|tga|spr|shp|fat|mp3|wav|ogg|"
    r"cab|zip|7z|rar|gpr|rep|idb|i64|fm8|iff|sav|dte|frc|ccb|fnt|sro|pal|ico)$"
)
NAME_HINT = re.compile(
    r"(lancer_decrypted|lancer\.exe|lancer\.icd|dmodes\.bin|shipstats|gunstats|"
    r"missilestats|pilotstats|\.decompiled\.c|project-log|starlancer_repack|"
    r"\.slpatch\.json)"
)
MAX_BYTES = 5 * 1024 * 1024        # nothing this large belongs here at all
BINARY_MAX_BYTES = 256 * 1024      # any binary bigger than this needs allow-listing

# Content signatures. A file carrying one of these IS that kind of file, whatever
# it has been renamed to. Images are deliberately absent: a diagram is legitimate,
# and the binary-size rule already catches a screenshot of the game.
MAGIC = (
    (b"MZ", "a DOS/Windows executable"),
    (b"\x7fELF", "an ELF executable"),
    (b"BIGF", "an EA BIGF / .HOG archive"),
    (b"BIK", "a Bink video"),
    (b"KB2", "a Bink 2 video"),
    (b"RIFF", "a RIFF container (WAV/AVI)"),
    (b"MSCF", "a Microsoft CAB archive"),
    (b"PK\x03\x04", "a ZIP archive"),
    (b"Rar!", "a RAR archive"),
    (b"7z\xbc\xaf\x27\x1c", "a 7-Zip archive"),
    (b"FORM", "an IFF container"),
    (b"OggS", "an Ogg stream"),
)

# The only binary this repository legitimately carries, pinned by content hash so
# that re-pointing tools/pe_icon.py at the game executable cannot swap game art in
# unnoticed. Regenerate with: python tools/make_icon.py
ALLOWLIST = {
    "tools/assets/app.ico":
        "25945c47842144edc57bb6fa98801deb9cfdf7682641affcb70106bed5e25de2",
}

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


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def reasons(path):
    """Return the list of reasons ``path`` is blocked (empty list = clean)."""
    out = []
    lc = path.replace("\\", "/").lstrip("./").lower()
    pinned = ALLOWLIST.get(lc)

    if FORBIDDEN_EXT.search(lc) and pinned is None:
        out.append("looks like game/binary material (blocked extension)")
    if NAME_HINT.search(lc):
        out.append("matches a known game-data name pattern")

    try:
        if not os.path.isfile(path):
            return out
        sz = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError:
        return out

    if sz > MAX_BYTES:
        out.append("is large (%d bytes > %d) - assets must not be committed"
                   % (sz, MAX_BYTES))

    for sig, what in MAGIC:
        if head.startswith(sig):
            out.append("has the file signature of %s, whatever it is named" % what)
            break

    if b"\x00" in head and sz > BINARY_MAX_BYTES and pinned is None:
        out.append("is binary content over %d bytes - only original text belongs "
                   "here (allow-list it deliberately if it is genuinely ours)"
                   % BINARY_MAX_BYTES)

    if pinned is not None:
        actual = _sha256(path)
        if actual != pinned:
            out.append("is the allow-listed asset but its contents changed "
                       "(sha256 %s..., expected %s...) - regenerate it with "
                       "tools/make_icon.py, or update ALLOWLIST deliberately"
                       % (actual[:16], pinned[:16]))
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
