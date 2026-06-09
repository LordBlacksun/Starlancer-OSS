#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Starlancer .HOG (Electronic Arts "BIGF") archive lister / extractor.

Format reverse-engineered from SLExtract (DraconPern & KingLord); see
docs/hog-format.md. A .HOG is an EA BIGF archive: big-endian 16-byte header,
a table-of-contents of (offset, length, NUL-terminated name) entries, then
raw uncompressed file blobs.

Usage:
  python hog_extract.py <archive.hog>                      # list contents
  python hog_extract.py <archive.hog> -o <outdir>          # extract all
  python hog_extract.py <archive.hog> -o <outdir> -f foster.bik   # extract some
"""
import argparse
import os
import struct
import sys

MAGIC = b"BIGF"


def parse(data: bytes):
    """Return (archive_size, num_files, data_start, [(name, offset, length), ...])."""
    if data[:4] != MAGIC:
        raise ValueError("not a BIGF/.HOG archive (magic=%r)" % data[:4])
    archive_size, num_files, data_start = struct.unpack_from(">III", data, 4)
    entries = []
    p = 16
    for _ in range(num_files):
        offset, length = struct.unpack_from(">II", data, p)
        p += 8
        end = data.index(b"\x00", p)          # NUL-terminated ASCII name
        name = data[p:end].decode("latin-1")
        p = end + 1
        entries.append((name, offset, length))
    return archive_size, num_files, data_start, entries


def safe_join(outdir: str, name: str):
    """Map an archive name to a path under outdir, blocking traversal/absolute paths."""
    name = name.replace("\\", "/")
    parts = [seg for seg in name.split("/") if seg not in ("", ".", "..")]
    return os.path.join(outdir, *parts) if parts else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="List/extract Starlancer .HOG (EA BIGF) archives.")
    ap.add_argument("archive")
    ap.add_argument("-o", "--out", help="extract into this directory (omit to just list)")
    ap.add_argument("-f", "--file", action="append", default=[],
                    help="only extract this filename (repeatable); default = all")
    args = ap.parse_args(argv)

    with open(args.archive, "rb") as fh:
        data = fh.read()
    archive_size, num_files, data_start, entries = parse(data)

    print("BIGF archive: %s" % os.path.basename(args.archive))
    print("  files: %d   data @ 0x%X   declared size: %d (actual %d)"
          % (num_files, data_start, archive_size, len(data)))
    if archive_size != len(data):
        print("  ! declared archive_size != actual file size", file=sys.stderr)

    want = set(n.lower() for n in args.file)
    extracted = 0
    for i, (name, offset, length) in enumerate(entries):
        if not args.out:
            print("  [%4d] %10d  0x%08X  %s" % (i, length, offset, name))
            continue
        if want and name.lower() not in want:
            continue
        if offset + length > len(data):
            print("  ! %s: offset/length out of range, skipping" % name, file=sys.stderr)
            continue
        dest = safe_join(args.out, name)
        if not dest:
            print("  ! %s: unsafe name, skipping" % name, file=sys.stderr)
            continue
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as out:
            out.write(data[offset:offset + length])
        extracted += 1
        print("  extracted %s  (%d bytes)" % (name, length))

    if args.out:
        print("Done: %d file(s) -> %s" % (extracted, args.out))


if __name__ == "__main__":
    main()
