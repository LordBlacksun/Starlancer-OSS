#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""bin_explore.py - quick structured-binary explorer (read-only).

Prints size + plausible record sizes (divisors), ASCII string runs with
offsets, and an optional hexdump. Used to reverse-engineer Starlancer's
*.BIN stat tables (shipstats/gunstats/missilestats/pilotstats).

  python bin_explore.py shipstats.bin --strings
  python bin_explore.py shipstats.bin --hex 256          # dump first 256 bytes
  python bin_explore.py shipstats.bin --hex 128 --at 0x1600
"""
import sys, argparse


def strings(data, minlen=4):
    out, cur, start = [], [], 0
    for i, b in enumerate(data):
        if 32 <= b < 127:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= minlen:
                out.append((start, bytes(cur).decode("latin-1")))
            cur = []
    if len(cur) >= minlen:
        out.append((start, bytes(cur).decode("latin-1")))
    return out


def hexdump(data, off, n):
    for r in range(off, min(off + n, len(data)), 16):
        chunk = data[r:r + 16]
        h = " ".join(f"{b:02x}" for b in chunk)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  0x{r:06X}  {h:<47}  {a}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--hex", type=int, default=0, help="hexdump first N bytes")
    ap.add_argument("--at", type=lambda x: int(x, 0), default=0, help="hexdump start offset")
    ap.add_argument("--minlen", type=int, default=4)
    ap.add_argument("--strings", action="store_true")
    ap.add_argument("--maxstr", type=int, default=400)
    a = ap.parse_args()
    data = open(a.file, "rb").read()
    n = len(data)
    print(f"FILE {a.file}  size={n} (0x{n:X})")
    ds = [d for d in range(8, 2049) if n % d == 0]
    print(f"record-size candidates (8..2048 dividing size): {ds}")
    print(f"  e.g. {n}//rec -> " + ", ".join(f"{r}:{n//r}recs" for r in ds[:14]))
    if a.strings:
        ss = strings(data, a.minlen)
        print(f"\n{len(ss)} ASCII runs (>= {a.minlen} chars):")
        for off, s in ss[:a.maxstr]:
            print(f"  0x{off:06X}  +{off:<7} {s!r}")
        if len(ss) > a.maxstr:
            print(f"  ... ({len(ss) - a.maxstr} more)")
    if a.hex:
        print()
        hexdump(data, a.at, a.hex)


if __name__ == "__main__":
    main()
