#!/usr/bin/env python3
"""bin_diff.py - diff two equal-length Starlancer binaries.

Two modes:

  (default) FIELD mode - diff .BIN stat tables as 4-byte fields. For each differing
  dword, prints file offset, record number, field offset within the record, and the
  old/new values as both float32 and uint32. Used to map stat-field layouts via
  known-delta mods (e.g. the hexcheat pack).

      python bin_diff.py original.bin modded.bin [recsize]

  --bytes   BYTE mode - byte-granular diff for CODE (e.g. comparing a community
  patched lancer.exe against the stock exe). Groups contiguous changed bytes into
  runs and prints file offset, run length, old/new hex, and - when the inputs parse
  as a PE32 - the virtual address of each run (ImageBase + RVA).

      python bin_diff.py --bytes stock.exe patched.exe

Standard library only. Static: reads files as data; never executes them.
"""
import sys, struct, argparse


def _pe_off_to_va(data):
    """Return a function off->VA for a PE32 image, or None if it doesn't parse."""
    try:
        if data[:2] != b"MZ":
            return None
        e = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e:e + 4] != b"PE\x00\x00":
            return None
        coff = e + 4
        nsec = struct.unpack_from("<H", data, coff + 2)[0]
        opt_size = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        base = struct.unpack_from("<I", data, opt + 28)[0]
        tbl = opt + opt_size
        secs = []
        for i in range(nsec):
            o = tbl + i * 40
            vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
            secs.append((raw, rawsize, va, vsize))

        def off_to_va(off):
            for raw, rawsize, va, vsize in secs:
                if raw <= off < raw + rawsize:
                    return base + va + (off - raw)
            return None
        return off_to_va
    except Exception:
        return None


def field_mode(pa, pb, rec):
    a = open(pa, "rb").read()
    b = open(pb, "rb").read()
    n = min(len(a), len(b))
    if len(a) != len(b):
        print(f"!! sizes differ: {len(a)} vs {len(b)}")
    print(f"diff {pa}  ->  {pb}   (recsize={rec})")
    i = ndiff = 0
    while i + 4 <= n:
        da, db = a[i:i + 4], b[i:i + 4]
        if da != db:
            fa = struct.unpack("<f", da)[0]; fb = struct.unpack("<f", db)[0]
            ua = struct.unpack("<I", da)[0]; ub = struct.unpack("<I", db)[0]
            print(f"  off 0x{i:05X}  rec {i//rec:3d}  +0x{i%rec:03X}   "
                  f"float {fa:11.4g} -> {fb:<11.4g}  u32 {ua} -> {ub}")
            ndiff += 1
        i += 4
    print(f"{ndiff} differing dwords")


def byte_mode(pa, pb):
    a = open(pa, "rb").read()
    b = open(pb, "rb").read()
    n = min(len(a), len(b))
    if len(a) != len(b):
        print(f"!! sizes differ: {len(a)} vs {len(b)} (comparing first {n} bytes)")
    off_to_va = _pe_off_to_va(a) or _pe_off_to_va(b)
    print(f"diff {pa}  ->  {pb}   (byte mode{'; VA shown' if off_to_va else ''})")
    runs = []
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    for off, length in runs:
        va = off_to_va(off) if off_to_va else None
        va_s = f"  VA 0x{va:08X}" if va is not None else ""
        old = a[off:off + length].hex()
        new = b[off:off + length].hex()
        print(f"  off 0x{off:06X}{va_s}  len {length:3d}   {old}  ->  {new}")
    total = sum(l for _, l in runs)
    print(f"{len(runs)} changed run(s), {total} byte(s) total")


def main():
    ap = argparse.ArgumentParser(description="diff two equal-length Starlancer binaries")
    ap.add_argument("--bytes", action="store_true", help="byte-granular code diff (runs + VA)")
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("recsize", nargs="?", type=int, default=352,
                    help="record size for field mode (default 352)")
    args = ap.parse_args()
    if args.bytes:
        byte_mode(args.a, args.b)
    else:
        field_mode(args.a, args.b, args.recsize)


if __name__ == "__main__":
    main()
