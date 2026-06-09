#!/usr/bin/env python3
"""hog_pack.py - Starlancer .HOG (EA "BIGF") archive *writer* / editor.

Companion to hog_extract.py. Builds valid BIGF archives and edits existing ones
(replace a file's bytes, or rename a TOC entry). See docs/hog-format.md.

BIGF layout: 16-byte big-endian header (magic "BIGF", archive_size, num_files,
data_start) + TOC of (offset BE, length BE, NUL-name) + raw uncompressed blobs.

  python hog_pack.py pack    <dir> -o out.hog                 # pack a folder
  python hog_pack.py replace <in.hog> <name> <file> -o out.hog  # swap one file's bytes
  python hog_pack.py rename  <in.hog> <old> <new>  -o out.hog   # rename a TOC entry
  python hog_pack.py --selftest                                # round-trip test
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hog_extract import parse, MAGIC  # noqa: E402


def build(entries):
    """entries: list of (name:str, data:bytes) -> bytes of a BIGF archive.

    Blobs are written contiguously (no alignment), matching the originals (which
    have unaligned/odd offsets). data_start = end of the TOC.
    """
    names = [n.encode("latin-1") if isinstance(n, str) else n for n, _ in entries]
    toc_size = sum(8 + len(nb) + 1 for nb in names)
    data_start = 16 + toc_size

    offsets, cur = [], data_start
    for (_, data) in entries:
        offsets.append(cur)
        cur += len(data)
    archive_size = cur

    out = bytearray()
    out += MAGIC + struct.pack(">III", archive_size, len(entries), data_start)
    for (_, data), nb, off in zip(entries, names, offsets):
        out += struct.pack(">II", off, len(data)) + nb + b"\x00"
    for (_, data) in entries:
        out += data
    assert len(out) == archive_size, (len(out), archive_size)
    return bytes(out)


def read_entries(path):
    """Return [(name, data), ...] from an existing .hog (preserving order)."""
    data = open(path, "rb").read()
    _, _, _, toc = parse(data)
    return [(name, data[off:off + length]) for (name, off, length) in toc]


def cmd_pack(args):
    entries = []
    root = args.dir
    for dp, _, files in os.walk(root):
        for f in sorted(files):
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace(os.sep, "\\")
            entries.append((rel, open(full, "rb").read()))
    open(args.out, "wb").write(build(entries))
    print(f"packed {len(entries)} files -> {args.out}")


def _match(entries, name):
    hits = [i for i, (n, _) in enumerate(entries) if n.lower() == name.lower()]
    if not hits:
        sys.exit(f"no entry named {name!r}")
    return hits[0]


def cmd_replace(args):
    entries = read_entries(args.hog)
    i = _match(entries, args.name)
    newdata = open(args.file, "rb").read()
    old = len(entries[i][1])
    entries[i] = (entries[i][0], newdata)
    open(args.out, "wb").write(build(entries))
    print(f"replaced {entries[i][0]!r}: {old} -> {len(newdata)} bytes  ->  {args.out}")


def cmd_rename(args):
    entries = read_entries(args.hog)
    i = _match(entries, args.old)
    entries[i] = (args.new, entries[i][1])
    open(args.out, "wb").write(build(entries))
    print(f"renamed {args.old!r} -> {args.new!r}  ->  {args.out}")


def selftest():
    src = [("alpha.txt", b"hello"), ("dir\\beta.bin", bytes(range(256))), ("g.dat", b"")]
    blob = build(src)
    _, n, ds, toc = parse(blob)
    got = [(name, blob[off:off + length]) for name, off, length in toc]
    assert n == len(src), n
    assert got == src, got
    # editing round-trips too
    ents = got[:]
    ents[0] = ("alpha.txt", b"HELLO WORLD")
    _, _, _, toc2 = parse(build(ents))
    assert toc2[0][2] == 11
    print("hog_pack selftest: OK (build + parse round-trip, replace)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer .HOG (BIGF) writer/editor.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pack"); p.add_argument("dir"); p.add_argument("-o", "--out", required=True); p.set_defaults(fn=cmd_pack)
    p = sub.add_parser("replace"); p.add_argument("hog"); p.add_argument("name"); p.add_argument("file"); p.add_argument("-o", "--out", required=True); p.set_defaults(fn=cmd_replace)
    p = sub.add_parser("rename"); p.add_argument("hog"); p.add_argument("old"); p.add_argument("new"); p.add_argument("-o", "--out", required=True); p.set_defaults(fn=cmd_rename)
    args = ap.parse_args(argv)
    if args.selftest:
        selftest(); return
    if not args.cmd:
        ap.error("a command or --selftest is required")
    args.fn(args)


if __name__ == "__main__":
    main()
