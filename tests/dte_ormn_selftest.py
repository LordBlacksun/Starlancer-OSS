#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Self-test for OpenReliant's mission name in tools/dte_parse.py.

OpenReliant keeps a mission's name in section 21, which the game binds and
never reads (docs/dte-format.md section 10.1).  This test takes the synthetic
mission of dte_selftest.py and gives it a section 21 the way OpenReliant's
writer does: appended after the image's end, with the directory pointing at
it.  It checks that dte_parse shows a well-formed name, reports each malformed
one in words without failing, and prints exactly what it printed before when
the section is absent, empty or holds anything else.  No game files needed.
"""
import contextlib
import io
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import dte_parse as D
from dte_selftest import build_image

SLOT = 21
LABEL = "mission name (OpenReliant, section 21): "


def ormn(name, version=1, length=None, nul=b"\0"):
    """Section 21's bytes: the tag, the version, the name's length in bytes, the name, `nul`."""
    raw = name.encode("utf-8") if isinstance(name, str) else name
    return (b"ORMN" + struct.pack("<HH", version, len(raw) if length is None else length)
            + raw + nul)


def with_section21(blob, count=None, offset=None):
    """The synthetic mission with `blob` after its end and slot 21 pointing at it."""
    image = bytearray(build_image())
    at = len(image) if offset is None else offset
    image += blob
    struct.pack_into("<II", image, SLOT * 8,
                     (len(blob) if count is None else count) | (0xF << 24), at)
    return bytes(image)


def run(args):
    """What dte_parse prints for `args`, run in-process, and its exit status."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            D.main(args)
            code = 0
        except SystemExit as e:
            code = e.code or 0
    return out.getvalue(), code


def decode(image, *extra):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "mission900.dte")
        with open(path, "wb") as fh:
            fh.write(image)
        out, code = run(["decode", path] + list(extra))
    assert code == 0, "decode exited %r:\n%s" % (code, out)
    return out


def without_slot21(listing):
    """A decode listing less its first line (the image size) and slot 21's directory row."""
    return [l for l in listing.splitlines()[1:] if not l.startswith("  [21]")]


def name_of(image):
    return D.Mission.from_image(image).openreliant_name()


# --------------------------------------------------------------------------- #
#  Nothing changes where section 21 holds no name                              #
# --------------------------------------------------------------------------- #
def check_absent_section_prints_nothing_new():
    out = decode(build_image())
    assert "OpenReliant" not in out and "ORMN" not in out, out


def check_empty_or_foreign_section_prints_as_before():
    base = without_slot21(decode(build_image()))
    plain = D.Mission.from_image(build_image())
    empty = bytearray(build_image())                    # count 0 at a live offset, as shipped
    struct.pack_into("<II", empty, SLOT * 8, 0xF << 24, plain.offset(8))
    for image in (bytes(empty), with_section21(b"NOPE\x01\x00\x03\x00abc\x00"),
                  with_section21(b"ORM")):
        out = decode(image)
        assert "OpenReliant" not in out and "!!" not in out, out
        assert without_slot21(out) == base, out


def check_api_is_none_without_a_tag():
    assert name_of(build_image()) is None
    assert name_of(with_section21(b"NOPE\x01\x00\x03\x00abc\x00")) is None
    assert name_of(with_section21(b"ORM")) is None
    assert name_of(with_section21(ormn("Hidden"), count=0)) is None


# --------------------------------------------------------------------------- #
#  A well-formed name                                                          #
# --------------------------------------------------------------------------- #
def check_api_reads_a_name():
    info = name_of(with_section21(ormn("The Sandbox")))
    assert info == {"name": "The Sandbox", "version": 1, "length": 11, "problems": []}, info


def check_decode_shows_the_name():
    out = decode(with_section21(ormn("The Sandbox")))
    assert LABEL + '"The Sandbox"' in out, out
    assert "!!" not in out, out
    row = [l for l in out.splitlines() if l.startswith("  [21]")]
    assert len(row) == 1 and row[0].endswith("ORMN"), row
    # every section filter carries the name, under the header line
    for section in ("dir", "ships", "script"):
        assert LABEL + '"The Sandbox"' in decode(with_section21(ormn("The Sandbox")),
                                                 "--section", section)


def check_decode_is_otherwise_unchanged():
    base = without_slot21(decode(build_image()))
    out = without_slot21(decode(with_section21(ormn("The Sandbox"))))
    assert out[0] == LABEL + '"The Sandbox"', out[0]
    assert out[1:] == base, "\n".join(out)


def check_an_empty_name_is_a_name():
    info = name_of(with_section21(ormn("")))
    assert info["name"] == "" and info["problems"] == [], info
    assert LABEL + '""' in decode(with_section21(ormn("")))


def check_non_ascii_name_counts_bytes():
    name = "\u03a9mega St\u00e5tion \u661f"             # 15 characters, 19 bytes of UTF-8
    info = name_of(with_section21(ormn(name)))
    assert info["name"] == name and info["length"] == 19 and not info["problems"], info
    assert LABEL + '"%s"' % name in decode(with_section21(ormn(name)))


def check_non_ascii_name_survives_a_narrow_console():
    # A Windows console or pipe in cp1252 cannot encode the star; print it escaped, not fail.
    name = "\u03a9mega St\u00e5tion \u661f"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "mission900.dte")
        with open(path, "wb") as fh:
            fh.write(with_section21(ormn(name)))
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        env.pop("PYTHONUTF8", None)
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "dte_parse.py"),
                               "decode", path, "--section", "dir"],
                              capture_output=True, env=env)
    text = proc.stdout.decode("cp1252")
    assert proc.returncode == 0, proc.stderr.decode("cp1252", "replace")
    assert LABEL + '"\\u03a9mega St\u00e5tion \\u661f"' in text, text


def check_control_characters_are_escaped():
    out = decode(with_section21(ormn("\x1b[31mRed\nLine")))
    assert LABEL + '"\\x1b[31mRed\\nLine"' in out, out


# --------------------------------------------------------------------------- #
#  Malformed names: reported in words, never a crash                           #
# --------------------------------------------------------------------------- #
# (bytes, count or None, the name OpenReliant would show or None, a phrase of the report)
MALFORMED = {
    "another version": (ormn("Sandbox", version=2), None, None, "version 2"),
    "a length past the section": (ormn("Sandbox", length=40), None, None,
                                  "runs past the section"),
    "a short header": (b"ORMN\x01\x00", None, None, "too few for the 8-byte header"),
    "no NUL": (ormn("Sandbox", nul=b""), None, "Sandbox", "no NUL after the name"),
    "a byte where the NUL goes": (ormn("Sandbox", nul=b"!"), None, "Sandbox", "not a NUL"),
    "bad UTF-8": (ormn(b"Bad\xff\xfeName"), None, "Bad\ufffd\ufffdName",
                  "not valid UTF-8 (byte 0xFF at 3)"),
    "a NUL inside the name": (ormn(b"San\0dbox"), None, "San\0dbox", "a NUL at byte 3"),
    "bytes after the NUL": (ormn("Sandbox", nul=b"\0\0\0"), None, "Sandbox",
                            "2 bytes follow the name's NUL"),
    "a count past the image": (ormn("Sandbox"), 8 + 7 + 1 + 10, "Sandbox",
                               "the image ends after 16"),
}


def make_malformed_check(label, blob, count, name, phrase):
    def check():
        image = with_section21(blob, count=count)
        info = name_of(image)
        assert info is not None and info["name"] == name, info
        assert any(phrase in p for p in info["problems"]), info["problems"]
        out = decode(image)
        assert any(l.startswith("  !! section 21: ") and phrase in l
                   for l in out.splitlines()), out
        shown = (LABEL + "none readable") if name is None else LABEL
        assert shown in out, out
    check.__name__ = "check_malformed_" + label.replace(" ", "_")
    return check


# --------------------------------------------------------------------------- #
#  A folder of missions                                                        #
# --------------------------------------------------------------------------- #
def mission_folder(tmp):
    files = {"mission1.dte": build_image(),
             "mission2.dte": with_section21(ormn("The Sandbox")),
             "mission3.dte": with_section21(ormn("Sandbox", version=2))}
    for f, image in files.items():
        with open(os.path.join(tmp, f), "wb") as fh:
            fh.write(image)


def check_sweep_lists_names_and_problems():
    with tempfile.TemporaryDirectory() as tmp:
        mission_folder(tmp)
        out, code = run(["sweep", tmp, "--script"])
    assert code == 0, out
    rows = {}                                           # the decode table's row, not --script's
    for l in out.splitlines():
        if l.startswith("  mission"):
            rows.setdefault(l.split()[0], l)
    assert "ORMN" not in rows["mission1.dte"] and '"' not in rows["mission1.dte"], rows
    assert rows["mission2.dte"].endswith('"The Sandbox"'), rows
    assert rows["mission3.dte"].endswith("ORMN, no name readable"), rows
    assert "3/3 decoded" in out and "0 decode errors" in out, out
    assert "OpenReliant mission names in section 21: 2" in out, out
    assert "  - mission3.dte: version 2" in out, out


def check_sweep_without_names_prints_as_before():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "mission1.dte"), "wb") as fh:
            fh.write(build_image())
        out, code = run(["sweep", tmp])
    assert code == 0 and "OpenReliant" not in out and "ORMN" not in out, out


def check_other_sections_keep_their_room():
    plain = D.Mission.from_image(build_image())
    named = D.Mission.from_image(with_section21(ormn("The Sandbox")))
    for k in range(27):
        if k != SLOT:
            assert named.capacity(k) == plain.capacity(k), (k, named.capacity(k), plain.capacity(k))


def check_roundtrip_keeps_the_name():
    with tempfile.TemporaryDirectory() as tmp:
        mission_folder(tmp)
        out, code = run(["roundtrip", tmp])
    assert code == 0 and "byte-identical round-trip            : 3/3" in out, out


CHECKS = [
    check_absent_section_prints_nothing_new,
    check_empty_or_foreign_section_prints_as_before,
    check_api_is_none_without_a_tag,
    check_api_reads_a_name,
    check_decode_shows_the_name,
    check_decode_is_otherwise_unchanged,
    check_an_empty_name_is_a_name,
    check_non_ascii_name_counts_bytes,
    check_non_ascii_name_survives_a_narrow_console,
    check_control_characters_are_escaped,
] + [make_malformed_check(label, *case) for label, case in MALFORMED.items()] + [
    check_sweep_lists_names_and_problems,
    check_sweep_without_names_prints_as_before,
    check_other_sections_keep_their_room,
    check_roundtrip_keeps_the_name,
]


def main():
    failed = []
    for check in CHECKS:
        try:
            check()
        except Exception as e:                           # report every check, then fail
            failed.append(check.__name__)
            first = str(e).splitlines()[0] if str(e) else ""
            first = first[:160].encode("ascii", "backslashreplace").decode("ascii")
            print("  FAIL  %s: %s: %s" % (check.__name__, type(e).__name__, first))
        else:
            print("  ok    %s" % check.__name__)
    if failed:
        print("SELFTEST FAILED: %d of %d checks" % (len(failed), len(CHECKS)))
        return 1
    print("SELFTEST PASSED: %d checks" % len(CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
