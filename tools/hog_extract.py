#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Starlancer .HOG (Electronic Arts "BIGF") archive lister / extractor.

Format reverse-engineered from SLExtract (DraconPern & KingLord); see
docs/hog-format.md. A .HOG is an EA BIGF archive: big-endian 16-byte header,
a table-of-contents of (offset, length, NUL-terminated name) entries, then
file blobs stored back-to-back.

The container applies no compression of its own, but most *payloads* inside
`resource.hog` are EA RefPack streams (98% of its members - every model,
mission, font, palette and stats table). Extracting such a member gives you a
compressed file, so `--decompress` expands them on the way out; see
`docs/hog-format.md` and `refpack.py`.

Usage:
  python hog_extract.py <archive.hog>                      # list contents
  python hog_extract.py <archive.hog> -o <outdir>          # extract all, verbatim
  python hog_extract.py <archive.hog> -o <outdir> -d       # extract, expanding RefPack
  python hog_extract.py <archive.hog> -o <outdir> -f foster.bik   # extract some
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refpack  # noqa: E402  (sibling module; the path insert above makes this work anywhere)

MAGIC = b"BIGF"


def parse(data: bytes):
    """Return (archive_size, num_files, data_start, [(name, offset, length), ...]).

    `data` needs to hold the header and the directory only (read_toc). The walk stops at the
    first record that is not a plausible one: a name of printable ASCII ending inside the
    directory, for a member inside the archive. pilots.hog and msspeech.hog count one more
    record than their directory holds, 0xCD filler, and reading it as a record invented an
    entry from bytes of the members. `num_files` stays the header's own count.
    """
    if data[:4] != MAGIC:
        raise ValueError("not a BIGF/.HOG archive (magic=%r)" % data[:4])
    archive_size, num_files, data_start = struct.unpack_from(">III", data, 4)
    directory_end = min(data_start, len(data))
    entries = []
    p = 16
    for _ in range(num_files):
        if p + 8 > directory_end:
            break
        offset, length = struct.unpack_from(">II", data, p)
        end = data.find(b"\x00", p + 8, directory_end)          # NUL-terminated ASCII name
        raw = data[p + 8:end] if end >= 0 else b""
        if not raw or any(c < 0x20 or c >= 0x7F for c in raw) or offset + length > archive_size:
            break
        entries.append((raw.decode("latin-1"), offset, length))
        p = end + 1
    return archive_size, num_files, data_start, entries


def read_toc(path):
    """parse() of the archive at `path` from its header and directory alone: the members are
    not read, so listing CD2.HOG (535 MB) reads a few kilobytes."""
    with open(path, "rb") as f:
        head = f.read(16)
        if head[:4] != MAGIC:
            raise ValueError("not a BIGF/.HOG archive (magic=%r)" % head[:4])
        data_start = struct.unpack_from(">I", head, 12)[0]
        return parse(head + f.read(max(0, data_start - 16)))


def member_payload(blob, decompress):
    """The bytes to extract for a member stored as `blob`. -> (payload, expanded, error).

    With `decompress`, a RefPack stream is expanded. One that does not expand is kept as
    stored, with the reason in `error`, rather than written out wrong.
    """
    if not (decompress and refpack.is_refpack(blob)):
        return blob, False, None
    try:
        return refpack.decompress(blob), True, None
    except refpack.RefPackError as exc:
        return blob, False, str(exc)


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
    ap.add_argument("-d", "--decompress", action="store_true",
                    help="expand RefPack payloads on extraction (leaves other members as-is)")
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
    extracted = expanded = 0
    for i, (name, offset, length) in enumerate(entries):
        blob = data[offset:offset + length]
        packed = refpack.is_refpack(blob)

        if not args.out:
            note = ""
            if packed:
                try:
                    declared, _ = refpack.decompress_ex(blob)
                    note = "  refpack -> %d" % declared
                except refpack.RefPackError as exc:
                    note = "  refpack (bad: %s)" % exc
            print("  [%4d] %10d  0x%08X  %s%s" % (i, length, offset, name, note))
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

        payload, was_expanded, error = member_payload(blob, args.decompress)
        note = ""
        if was_expanded:
            expanded += 1
            note = " <- refpack %d" % length
        elif error:
            # Keep the raw blob rather than write a file we know is wrong.
            print("  ! %s: %s; extracted compressed" % (name, error), file=sys.stderr)

        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as out:
            out.write(payload)
        extracted += 1
        print("  extracted %s  (%d bytes)%s" % (name, len(payload), note))

    if args.out:
        tail = ", %d expanded from RefPack" % expanded if args.decompress else ""
        print("Done: %d file(s) -> %s%s" % (extracted, args.out, tail))


if __name__ == "__main__":
    main()
