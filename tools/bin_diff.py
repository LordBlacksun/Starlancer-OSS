#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""bin_diff.py - diff two equal-length Starlancer .BIN stat tables as 4-byte fields.

For each differing dword, prints file offset, record number, field offset within
the record, and the old/new values interpreted as both float32 and uint32. Used
to map stat-field layouts via known-delta mods (e.g. the hexcheat pack, where
each file super-stats exactly one ship).

  python bin_diff.py original.bin modded.bin [recsize=352]
"""
import sys, struct


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()
    rec = int(sys.argv[3]) if len(sys.argv) > 3 else 352
    n = min(len(a), len(b))
    if len(a) != len(b):
        print(f"!! sizes differ: {len(a)} vs {len(b)}")
    print(f"diff {sys.argv[1]}  ->  {sys.argv[2]}   (recsize={rec})")
    i = ndiff = 0
    while i + 4 <= n:
        da, db = a[i:i + 4], b[i:i + 4]
        if da != db:
            fa = struct.unpack("<f", da)[0]
            fb = struct.unpack("<f", db)[0]
            ua = struct.unpack("<I", da)[0]
            ub = struct.unpack("<I", db)[0]
            print(f"  off 0x{i:05X}  rec {i//rec:3d}  +0x{i%rec:03X}   "
                  f"float {fa:11.4g} -> {fb:<11.4g}  u32 {ua} -> {ub}")
            ndiff += 1
        i += 4
    print(f"{ndiff} differing dwords")


if __name__ == "__main__":
    main()
