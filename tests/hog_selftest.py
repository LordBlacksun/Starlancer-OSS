#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Self-test for tools/hog_extract.py — builds a synthetic BIGF/.HOG in memory
(per docs/hog-format.md) and verifies the parser round-trips it. No game files needed."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import hog_extract as H


def build(files):
    """files: list of (name, bytes) -> a valid BIGF archive (bytes)."""
    toc_size = sum(8 + len(n.encode("latin-1")) + 1 for n, _ in files)
    data_start = 16 + toc_size
    toc = b""
    blobs = b""
    offset = data_start
    for name, payload in files:
        toc += struct.pack(">II", offset, len(payload)) + name.encode("latin-1") + b"\x00"
        blobs += payload
        offset += len(payload)
    body = toc + blobs
    header = b"BIGF" + struct.pack(">III", 16 + len(body), len(files), data_start)
    return header + body


def main():
    files = [
        ("foster.bik", b"BIK\x00fake-movie-bytes"),
        ("00000409.256", bytes(range(40))),
        ("ship.shp", b"SHP-model-payload-12345"),
    ]
    data = build(files)
    asz, n, ds, ents = H.parse(data)

    assert n == len(files), "num_files mismatch: %r" % n
    assert asz == len(data), "archive_size mismatch: %d vs %d" % (asz, len(data))
    assert [e[0] for e in ents] == [f[0] for f in files], "names: %r" % (ents,)
    by_name = dict(files)
    for name, off, ln in ents:
        assert data[off:off + ln] == by_name[name], "payload mismatch for %s" % name

    print("parse OK: %d files, archive_size=%d, data_start=0x%X" % (n, asz, ds))
    for name, off, ln in ents:
        print("  %-14s off=0x%X len=%d" % (name, off, ln))
    print("SELFTEST PASSED")


if __name__ == "__main__":
    main()
