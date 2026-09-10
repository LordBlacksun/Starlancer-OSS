#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""refpack.py - EA RefPack ("QFS") decompressor, the codec inside Starlancer's HOGs.

The `.HOG` *container* stores raw blobs (see `docs/hog-format.md`), but most of
the blobs inside `resource.hog` are themselves RefPack streams: 98% of that
archive's 967 members begin with the `10 FB` signature, including every `.shp`
model, every `.dte` mission, every `.fnt`, `.ccb` and stats `.bin`. Extracting a
member therefore gives you a compressed payload, not a usable file.

This module is the project's single implementation of that codec. It was first
written for `dte_parse.py` (mission containers) and is generalised here so any
tool can use it; `hog_extract.py --decompress` is the main consumer.

Stream layout
-------------
    byte 0   flags
    byte 1   0xFB                      (signature; byte 0 is 0x10 in practice)
    [3-4]    compressed size, big-endian, ONLY if flags & 0x01
    3-4      uncompressed size, big-endian (4 bytes if flags & 0x80, else 3)
    ..       opcode stream

Five opcode forms, each emitting 0-3 literal bytes and then copying a run from
already-decoded output:

    ctrl < 0x80   2-byte  literals = ctrl & 3          run = ((ctrl>>2) & 7) + 3
    ctrl < 0xC0   3-byte  literals = (a>>6) & 3        run = (ctrl & 0x3F) + 4
    ctrl < 0xE0   4-byte  literals = ctrl & 3          run = ((ctrl & 0x0C) << 6) + c + 5
    ctrl < 0xFC   literal run only, ((ctrl & 0x1F) << 2) + 4 bytes (4..112, step 4)
    ctrl >= 0xFC  final 0-3 literals, then end of stream

Note the terminator: a well-formed stream ends with a `0xFC..0xFF` opcode that
may be followed by as few as zero trailing bytes. A decoder that requires four
bytes of lookahead before reading an opcode will drop that final run and return
a file that is 1-3 bytes short - silently, because the output is then clamped to
the declared size. Guard on `pos < len(data)`, and check the result against the
declared size, which this module does.

Usage:
    python refpack.py <file>                 # report sizes, verify declared size
    python refpack.py <file> -o <out>        # decompress to a file
    python refpack.py --selftest             # synthetic fixtures, no game data
"""
import argparse
import os
import sys

SIGNATURE = 0xFB  # byte 1; byte 0 carries the flags (0x10 in every Starlancer stream)


class RefPackError(ValueError):
    """Raised on a malformed or non-RefPack stream."""


def is_refpack(data: bytes) -> bool:
    """True if `data` starts with a RefPack header. Cheap enough to call per member."""
    return len(data) >= 6 and data[1] == SIGNATURE


def decompress_ex(data: bytes):
    """Decompress a RefPack stream. Returns `(declared_size, decompressed_bytes)`.

    The declared size is the header's own claim; the caller should compare it
    against `len(out)` to detect a truncated or corrupt stream.
    """
    if not is_refpack(data):
        got = "%02X %02X" % (data[0], data[1]) if len(data) > 1 else "<short>"
        raise RefPackError("not a RefPack stream (signature %s)" % got)

    flags = data[0]
    i = 2
    if flags & 0x01:
        i += 4 if flags & 0x80 else 3           # skip the compressed-size field
    if flags & 0x80:
        size = (data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3]
        i += 4
    else:
        size = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
        i += 3

    out = bytearray()
    n = len(data)
    while i < n:                                 # NOT i + 4 <= n: see the note above
        ctrl = data[i]; i += 1

        if ctrl < 0x80:                          # 2-byte form
            a = data[i]; i += 1
            nliteral = ctrl & 0x03
            ncopy = ((ctrl >> 2) & 0x07) + 3
            roff = ((ctrl & 0x60) << 3) + a + 1
        elif ctrl < 0xC0:                        # 3-byte form
            a = data[i]; b = data[i + 1]; i += 2
            nliteral = (a >> 6) & 0x03
            ncopy = (ctrl & 0x3F) + 4
            roff = ((a & 0x3F) << 8) + b + 1
        elif ctrl < 0xE0:                        # 4-byte form
            a = data[i]; b = data[i + 1]; c = data[i + 2]; i += 3
            nliteral = ctrl & 0x03
            ncopy = ((ctrl & 0x0C) << 6) + c + 5
            roff = ((ctrl & 0x10) << 12) + (a << 8) + b + 1
        elif ctrl < 0xFC:                        # literal run, 4..112 bytes (step 4)
            nliteral = ((ctrl & 0x1F) << 2) + 4
            out += data[i:i + nliteral]; i += nliteral
            continue
        else:                                    # terminator: 0-3 literals, then stop
            nliteral = ctrl & 0x03
            out += data[i:i + nliteral]; i += nliteral
            break

        out += data[i:i + nliteral]; i += nliteral
        for _ in range(ncopy):                   # runs may overlap; copy byte at a time
            out.append(out[-roff])

    return size, bytes(out)


def decompress(data: bytes) -> bytes:
    """Decompress a RefPack stream, raising if the result contradicts the header."""
    size, out = decompress_ex(data)
    if len(out) != size:
        raise RefPackError(
            "truncated stream: header declares %d bytes, decoded %d" % (size, len(out)))
    return out


def maybe_decompress(data: bytes) -> bytes:
    """Decompress if `data` is RefPack, otherwise hand it back untouched."""
    return decompress(data) if is_refpack(data) else data


# --------------------------------------------------------------------------- #
#  Self-test - hand-built streams, one per opcode form. No game data involved.  #
# --------------------------------------------------------------------------- #
def _stream(flags, size, body):
    return bytes([flags, SIGNATURE, (size >> 16) & 0xFF, (size >> 8) & 0xFF, size & 0xFF]) + body


_CASES = [
    # (label, stream, expected output)
    ("literal run + terminator carrying trailing literals",
     _stream(0x10, 10, b"\xE1" + b"ABCDEFGH" + b"\xFE" + b"IJ"), b"ABCDEFGHIJ"),
    ("2-byte back-reference",
     _stream(0x10, 8, b"\xE0" + b"ABCD" + b"\x04\x03" + b"\xFC"), b"ABCDABCD"),
    ("2-byte form, overlapping run (byte-wise RLE)",
     _stream(0x10, 6, b"\x09\x00" + b"A" + b"\xFC"), b"AAAAAA"),
    ("3-byte back-reference, run overruns into its own output",
     _stream(0x10, 18, b"\xE1" + b"ABCDEFGH" + b"\x86\x00\x04" + b"\xFC"),
     b"ABCDEFGH" + b"DEFGHDEFGH"),
    ("4-byte back-reference",
     _stream(0x10, 9, b"\xE0" + b"ABCD" + b"\xC0\x00\x03\x00" + b"\xFC"), b"ABCDABCDA"),
    ("flags bit 0: a compressed-size field precedes the uncompressed size",
     b"\x11\xFB\x00\x00\x0C" + b"\x00\x00\x0A" + b"\xE1" + b"ABCDEFGH" + b"\xFE" + b"IJ",
     b"ABCDEFGHIJ"),
]


def _selftest():
    failures = []
    for label, stream, expected in _CASES:
        try:
            size, out = decompress_ex(stream)
        except Exception as exc:                                  # noqa: BLE001
            failures.append("%s: raised %s" % (label, exc)); continue
        if out != expected:
            failures.append("%s: got %r, expected %r" % (label, out, expected))
        elif size != len(expected):
            failures.append("%s: declared %d, decoded %d" % (label, size, len(out)))
        else:
            print("  ok   %s" % label)

    # A decoder needing 4 bytes of lookahead drops the terminator's literals; the
    # first case above is exactly that shape, so assert the tail explicitly.
    _, out = decompress_ex(_CASES[0][1])
    if not out.endswith(b"IJ"):
        failures.append("terminator literals dropped (the 4-byte-lookahead bug)")
    else:
        print("  ok   terminator literals survive a short tail")

    for label, bad in (("empty", b""), ("wrong signature", b"\x10\xFA\x00\x00\x04")):
        try:
            decompress_ex(bad)
        except RefPackError:
            print("  ok   rejects %s input" % label)
        else:
            failures.append("accepted %s input" % label)

    # decompress() must refuse a stream whose header and payload disagree.
    try:
        decompress(_stream(0x10, 99, b"\xE0" + b"ABCD" + b"\xFC"))
    except RefPackError:
        print("  ok   rejects a stream shorter than its declared size")
    else:
        failures.append("accepted a truncated stream")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("\nrefpack self-test: all checks passed")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Decompress an EA RefPack / QFS stream.")
    ap.add_argument("file", nargs="?", help="RefPack-compressed file")
    ap.add_argument("-o", "--out", help="write the decompressed bytes here")
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic self-tests (no game data needed)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.file:
        ap.error("give a file, or --selftest")

    with open(args.file, "rb") as fh:
        data = fh.read()
    if not is_refpack(data):
        print("%s: not a RefPack stream (%d bytes, starts %s)"
              % (args.file, len(data), data[:2].hex()))
        return 1

    size, out = decompress_ex(data)
    status = "ok" if len(out) == size else "MISMATCH"
    print("%s: %d compressed -> %d bytes (header declares %d) [%s]"
          % (os.path.basename(args.file), len(data), len(out), size, status))
    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(out)
        print("wrote %s" % args.out)
    return 0 if len(out) == size else 1


if __name__ == "__main__":
    sys.exit(main())
