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

    # pilots.hog and msspeech.hog count one record more than their directory holds: 0xCD filler
    # past the real records. The parser stops there rather than invent an entry from it.
    filler = b"\xCD" * 16
    body = data[16:ds] + filler + data[ds:]
    phantom = b"BIGF" + struct.pack(">III", 16 + len(body), n + 1, ds + len(filler)) + body
    _, count, _, real = H.parse(phantom)
    assert count == n + 1, "the header's own count is still reported: %r" % count
    assert [e[0] for e in real] == [f[0] for f in files], "phantom entry invented: %r" % (real,)

    # The directory alone is enough to list an archive: CD2.HOG is 535 MB, and listing it
    # used to read all of it on the window's thread.
    import tempfile
    read_toc = getattr(H, "read_toc", None)
    assert read_toc is not None, "read_toc exists"
    with tempfile.TemporaryDirectory() as tmp:
        cut = os.path.join(tmp, "directory_only.hog")
        with open(cut, "wb") as f:
            f.write(phantom[:ds + len(filler)])
        _, _, _, from_disk = read_toc(cut)
        assert from_disk == real, "read_toc: %r" % (from_disk,)

    # Extracting expands a RefPack member unless asked for it as stored, and keeps the stored
    # bytes, with the reason, where a stream does not expand.
    member_payload = getattr(H, "member_payload", None)
    assert member_payload is not None, "member_payload exists"
    stream = bytes([0x10, 0xFB, 0x00, 0x00, 0x0C, 0xE0]) + b"abcd" + bytes([0x14, 0x03, 0xFC])
    assert member_payload(stream, True) == (b"abcdabcdabcd", True, None), "expands a stream"
    assert member_payload(stream, False) == (stream, False, None), "keeps it as stored on request"
    assert member_payload(b"plain", True) == (b"plain", False, None), "leaves a plain member"
    broken = stream[:-4]
    payload, expanded, error = member_payload(broken, True)
    assert payload == broken and not expanded and error, "a broken stream stays as stored"
    print("SELFTEST PASSED")


if __name__ == "__main__":
    main()
