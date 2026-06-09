#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""blank_boot_videos.py - skip Starlancer's startup Bink movies by blanking them
in a .HOG archive (READ-ONLY toward the game; writes a NEW .hog, never runs it).

Why this works (from our static RE of the decrypted exe):
  The boot sequence (dispatcher `FUN_004ABDE0`, players `FUN_004AB9D0`/`FUN_004ABB80`)
  opens its logo/splash movies from the CD HOG via `_BinkOpen` with the resource flag
  (`0x800000`), NOT as loose files -- so the skip must live inside the HOG. The play
  loop checks every frame for input and for end-of-video, and on a missing or
  zero-frame movie `_BinkOpen` returns NULL / the end flag is set immediately: the
  engine logs an error and *continues* (it is built to tolerate absent movies). A
  minimal "blank" Bink therefore makes the boot movie a no-op.

Boot movies (filenames recovered from the decompiled string table):
  logos/splash : warty_.bik  new_dalogo_fs_uncmpr.bik  new_nms.bik  "splash to mm.bik"
  intro        : new_intro.bik            (only with --include-intro)

Usage:
  python blank_boot_videos.py list  <in.hog>
  python blank_boot_videos.py blank <in.hog> -o <out.hog> [--include-intro]
                                    [--blank path/to/blank.bik]   # use a real blank instead

Notes:
  * Operates on a COPY of your own CD HOG; output is a new file you place in your
    install. This tool never launches the game -- test the result yourself.
  * `--blank` lets you substitute a known-good minimal black Bink (e.g. esc0rtd3w's
    blank-intro-videos) if any clip misbehaves with the generated stub.
  * Game data is never committed to the repo (.gitignore + pre-commit guard); keep the
    patched .hog and any .bik in your local install only.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hog_extract import parse                      # noqa: E402
from hog_pack import build, read_entries           # noqa: E402

LOGO_VIDEOS = ["warty_.bik", "new_dalogo_fs_uncmpr.bik", "new_nms.bik", "splash to mm.bik"]
INTRO_VIDEOS = ["new_intro.bik"]


def basename(name):
    """Last path component of a TOC name (handles \\ and /)."""
    return name.replace("\\", "/").rsplit("/", 1)[-1].lower()


def make_blank_bik(version_byte=b"i"):
    """A minimal Bink-v1 header declaring zero frames.

    Signature 'BIK'+version, a 0x28-byte header (w/h 2x2, 0 frames, 0 audio tracks)
    and a 1-entry frame-offset table. With 0 frames the engine's play loop hits its
    end condition immediately and moves on (see module docstring); if BinkOpen instead
    rejects it, the loader's missing-movie path also just continues.
    """
    body = struct.pack(
        "<IIIIIIIII",
        0,          # +0x08 num frames
        0,          # +0x0C largest frame size
        0,          # +0x10 last frame
        2, 2,       # +0x14 width, +0x18 height
        15, 1,      # +0x1C fps dividend, +0x20 divisor
        0,          # +0x24 video flags
        0,          # +0x28 num audio tracks
    )
    frame_table = struct.pack("<I", 0x2C + 4)        # single end-offset = file length
    sig = b"BIK" + version_byte
    payload = sig + b"\x00\x00\x00\x00" + body + frame_table   # size patched below
    out = bytearray(payload)
    struct.pack_into("<I", out, 4, len(out) - 8)     # +0x04 = file size - 8
    return bytes(out)


def boot_targets(include_intro):
    names = list(LOGO_VIDEOS)
    if include_intro:
        names += INTRO_VIDEOS
    return set(n.lower() for n in names)


def cmd_list(args):
    data = open(args.hog, "rb").read()
    _, num, _, toc = parse(data)
    want = boot_targets(include_intro=True)
    print("BIGF %s: %d files" % (os.path.basename(args.hog), num))
    found = 0
    for name, off, length in toc:
        if basename(name) in want:
            sig = data[off:off + 4]
            print("  %-34s %8d B  sig=%r" % (name, length, sig))
            found += 1
    print("%d boot-movie(s) present (logos+intro)" % found)


def cmd_blank(args):
    entries = read_entries(args.hog)              # [(name, data), ...] preserving order
    targets = boot_targets(args.include_intro)
    replacement = open(args.blank, "rb").read() if args.blank else None

    changed = []
    new_entries = []
    for name, data in entries:
        if basename(name) in targets:
            if replacement is not None:
                blob = replacement
            else:
                ver = data[3:4] if data[:3] == b"BIK" else b"i"
                blob = make_blank_bik(ver)
            changed.append((name, len(data), len(blob)))
            new_entries.append((name, blob))
        else:
            new_entries.append((name, data))

    if not changed:
        sys.exit("no boot movies found in %s (try the other CD HOG)" % os.path.basename(args.hog))

    out = build(new_entries)
    open(args.out, "wb").write(out)

    # verify: every non-target entry is byte-identical after the round-trip
    _, _, _, toc2 = parse(out)
    rebuilt = {name: out[o:o + l] for name, o, l in toc2}
    orig = dict(entries)
    target_names = {n for n, _, _ in changed}
    bad = [n for n, d in orig.items() if n not in target_names and rebuilt.get(n) != d]

    for name, old, new in changed:
        print("  blanked %-32s %d -> %d B" % (name, old, new))
    print("wrote %s (%d files, %d bytes)" % (args.out, len(new_entries), len(out)))
    print("round-trip check: %s" % ("OK (untouched entries identical)" if not bad
                                     else "FAILED for %d entries: %s" % (len(bad), bad[:5])))
    if bad:
        sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Blank Starlancer boot Bink movies inside a .HOG (static; never runs the game).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="show which boot movies a HOG contains")
    p.add_argument("hog"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("blank", help="write a new HOG with the boot movies blanked")
    p.add_argument("hog"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--include-intro", action="store_true", help="also blank new_intro.bik")
    p.add_argument("--blank", help="use this .bik as the replacement (e.g. a real black clip)")
    p.set_defaults(fn=cmd_blank)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
