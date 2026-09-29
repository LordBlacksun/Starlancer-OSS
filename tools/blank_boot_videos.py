#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""blank_boot_videos.py - skip Starlancer's startup logo movies by blanking them in the
game folder (never runs the game).

The startup movies are LOOSE files in the installed game folder, never inside a HOG
(checked against every retail HOG, 2026-09-29: resource.hog, CD1.HOG and CD2.HOG hold none
of them). By default this blanks the three branding logos:

    WARTY_.bik                 Warthog                 (developer)
    NEW_DALOGO_FS_UNCMPR.bik   Digital Anvil           (studio)
    NEW_NMS.bik                Microsoft Game Studios  (publisher)

and, with --include-splash, the animated splash->main-menu transition, "splash to mm.bik".

Each is cut to its own first frame (first_frame_bik): a real one-frame Bink movie, over
in a fifteenth of a second, that every Bink reader plays, the original's and openreliant's
alike. The first original is kept beside it as <name>.orig, and `restore` moves it back.
(This tool once rewrote HOGs, on the belief that the logos lived in one, and wrote a
zero-frame stub the original was only inferred to tolerate and openreliant cannot play.
Both are gone. Logo<->filename mapping is by static inference: warty_=Warthog,
new_dalogo="da logo"=Digital Anvil, new_nms = the remaining startup logo.)

Usage:
  python blank_boot_videos.py list    <game folder>
  python blank_boot_videos.py blank   <game folder> [--include-splash] [--blank clip.bik]
  python blank_boot_videos.py restore <game folder>

Notes:
  * Works on your own installed game folder. It never launches the game: test the result
    yourself.
  * `--blank` substitutes a known-good black Bink (e.g. esc0rtd3w's blank-intro-videos)
    for the first frames.
  * Game data is never committed to the repo (.gitignore + pre-commit guard).
"""
import argparse
import os
import shutil
import stat
import struct
import sys

# The three startup branding logos -- the DEFAULT blank set.
LOGO_VIDEOS = ["warty_.bik", "new_dalogo_fs_uncmpr.bik", "new_nms.bik"]
LOGO_LABEL = {
    "warty_.bik": "Warthog",
    "new_dalogo_fs_uncmpr.bik": "Digital Anvil",
    "new_nms.bik": "Microsoft Game Studios",
}
# Optional extras -- NOT blanked unless explicitly requested.
SPLASH_VIDEOS = ["splash to mm.bik"]   # animated splash -> main-menu transition

_NOT_A_FOLDER = ("%s is not a folder. The startup movies are loose files in the game folder "
                 "(WARTY_.bik, NEW_DALOGO_FS_UNCMPR.bik, NEW_NMS.bik), never inside a HOG: "
                 "point this at the game folder.")


def role_of(bn):
    if bn in (n.lower() for n in LOGO_VIDEOS):
        return "LOGO [default] - %s" % LOGO_LABEL.get(bn, "")
    if bn in (n.lower() for n in SPLASH_VIDEOS):
        return "splash  (--include-splash)"
    return ""


def _zero_frame_stub(version_byte=b"i"):
    """The zero-frame clip Studio 1.2 and this tool used to write, kept for the self-test only.

    openreliant's player reads frame 0 of its empty index, and the original's tolerance of it
    was only ever inferred, which is why first_frame_bik replaced it.
    """
    body = struct.pack(
        "<IIIIIIIII",
        0,          # +0x08 num frames
        0,          # +0x0C largest frame size
        0,          # +0x10 last frame
        2, 2,       # +0x14 width, +0x18 height
        15, 1,      # +0x1C fps dividend, +0x20 divisor
        0,          # +0x24 video flags
        0,          # +0x28 num audio tracks
    )
    frame_table = struct.pack("<I", 0x2C + 4)        # single end-offset = file length
    out = bytearray(b"BIK" + version_byte + b"\x00\x00\x00\x00" + body + frame_table)
    struct.pack_into("<I", out, 4, len(out) - 8)     # +0x04 = file size - 8
    return bytes(out)


def _synthetic_bik(frames, audio=b"\x08\x00\x00\x00\xAA"):
    """A movie of `frames` frames, 8x6 at 15 a second, one mono track, each frame's video its
    number: the layout of openreliant's `bink.testing.movie`, plus the standard end entry."""
    index_at = 0x2C + 4 + 4 + 4
    frame_size = (4 + len(audio) + 1 + 3) & ~3
    first = index_at + (frames + 1) * 4
    size = first + frames * frame_size
    out = bytearray(b"BIKf")
    out += struct.pack("<IIIIIIIIII", size - 8, frames, frame_size, frames, 8, 6, 15, 1, 0, 1)
    out += struct.pack("<IHHI", 0, 22050, 0x4000, 0)
    for n in range(frames):
        out += struct.pack("<I", (first + n * frame_size) | (n == 0))
    out += struct.pack("<I", size)
    for n in range(frames):
        body = struct.pack("<I", len(audio)) + audio + bytes([n])
        out += body + b"\x00" * (frame_size - len(body))
    return bytes(out)


def _reader_accepts(bik):
    """openreliant's Movie.parse and Bink.doFrame, ported: the header's checks, then frame 0's
    extent, which its player reads first. (src/formats/bink.zig, src/engine/bink.zig)"""
    if bik[:3] != b"BIK" or len(bik) < 0x2C:
        return False
    size, frames = struct.unpack_from("<II", bik, 4)
    rate, divisor, _flags, tracks = struct.unpack_from("<IIII", bik, 0x1C)
    if rate == 0 or divisor == 0 or frames == 0:
        return False
    index_at = 0x2C + tracks * 12
    if len(bik) < index_at + frames * 4:
        return False
    index = struct.unpack_from("<%dI" % frames, bik, index_at)
    for n in range(frames):
        start = index[n] & ~1
        end = index[n + 1] & ~1 if n + 1 < frames else size + 8
        if end <= start or end > len(bik):
            return False
    return True


def selftest():
    """first_frame_bik against synthetic movies. No game data is involved."""
    fails = []

    def check(cond, label):
        print("  %-4s %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            fails.append(label)

    print("=== blank_boot_videos self-test (synthetic movies) ===")
    fn = globals().get("first_frame_bik")
    check(fn is not None, "first_frame_bik exists")
    check(not _reader_accepts(_zero_frame_stub(b"i")),
          "the old zero-frame stub is one openreliant's player cannot play (the reason for the fix)")
    if fn is not None:
        src = _synthetic_bik(3)
        check(_reader_accepts(src), "the synthetic source itself reads as a valid movie")
        one = fn(src)
        check(_reader_accepts(one), "the trimmed clip passes openreliant's reader checks")
        size, frames, largest, last = struct.unpack_from("<IIII", one, 4)
        check(frames == 1 and last == 1, "the trimmed clip declares exactly one frame")
        check(size == len(one) - 8, "its size field is the file's length less 8")
        check(one[:4] == src[:4] and one[0x14:0x2C] == src[0x14:0x2C],
              "revision, picture size, rate and track count are kept")
        index_at = 0x2C + 12
        check(one[0x2C:index_at] == src[0x2C:index_at], "the audio track's tables are kept")
        start, end = struct.unpack_from("<II", one, index_at)
        check(start & 1 == 1, "frame 0 is marked a key frame")
        check(end == len(one), "the index ends at the file's end")
        s0, s1 = struct.unpack_from("<II", src, index_at)
        check(one[start & ~1:] == src[s0 & ~1:s1 & ~1], "frame 0's bytes are the original's, unchanged")
        check(largest == len(one) - (start & ~1), "the largest frame is frame 0's size")
        for bad, why in ((b"RIFF" + b"\x00" * 60, "not a Bink"), (_zero_frame_stub(b"i"), "no frames")):
            try:
                fn(bad)
                check(False, "a source with %s is refused" % why)
            except ValueError:
                check(True, "a source with %s is refused" % why)

    # --- the command line: the startup movies are loose files in the game folder ---
    import io
    import shutil
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout

    def run(*argv):
        """main(argv) -> (exit code, output); a SystemExit's message counts as output."""
        out = io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(out):
                code = main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            out.write(str(e.code))
        return code or 0, out.getvalue()

    root = tempfile.mkdtemp(prefix="bootvid_test_")
    try:
        game = os.path.join(root, "game")
        os.mkdir(game)
        movie = _synthetic_bik(3)
        for name in ("WARTY_.BIK", "new_dalogo_fs_uncmpr.bik", "new_nms.bik", "splash to mm.bik"):
            with open(os.path.join(game, name), "wb") as f:
                f.write(movie)

        def read(name):
            with open(os.path.join(game, name), "rb") as f:
                return f.read()

        code, text = run("blank", game)
        check(code == 0, "blank <game folder> succeeds")
        check(read("WARTY_.BIK") == first_frame_bik(movie) and read("new_nms.bik") != movie,
              "blank <game folder> cuts each loose logo to its first frame")
        check(read("splash to mm.bik") == movie, "the splash is left alone unless asked for")
        run("blank", game, "--include-splash")
        check(read("splash to mm.bik") != movie, "--include-splash blanks it too")
        code, text = run("restore", game)
        check(code == 0 and read("WARTY_.BIK") == movie and read("splash to mm.bik") == movie,
              "restore <game folder> puts every original back")
        check(not [f for f in os.listdir(game) if f.lower().endswith(".orig")],
              "restore moves the originals back, leaving no .orig to read as 'blanked'")

        hog = os.path.join(root, "CD2.HOG")
        with open(hog, "wb") as f:
            f.write(b"BIGF" + b"\x00" * 60)
        code, text = run("blank", hog)
        check(code != 0 and "game folder" in text,
              "blank refuses a .hog: the startup movies are never inside one")
        code, text = run("list", game)
        check(code == 0 and "WARTY_.BIK" in text, "list <game folder> names the logos found")
    finally:
        for dp, _dirs, files in os.walk(root):
            for f in files:
                os.chmod(os.path.join(dp, f), 0o666)
        shutil.rmtree(root, ignore_errors=True)
    print("blank_boot_videos self-test: %d failed" % len(fails))
    return 1 if fails else 0


def first_frame_bik(original):
    """`original` cut down to its first frame: a one-frame clip of the user's own movie.

    Frame 0 of a Bink movie is a key frame, decodable alone, so the result is a real movie
    every Bink reader plays, over in a fifteenth of a second. It replaces the zero-frame
    stub this tool once wrote, which openreliant's player cannot play (it reads frame 0 of an empty
    index) and whose tolerance by the original's player was only ever inferred. The header,
    the audio tracks' tables and frame 0's bytes are kept as they are; the frame count, the
    largest frame, the index and the size are rewritten to match. Raises ValueError for a
    file that is not a Bink movie or has no frames.
    """
    if len(original) < 0x2C or original[:3] != b"BIK":
        raise ValueError("not a Bink movie")
    frames = struct.unpack_from("<I", original, 8)[0]
    tracks = struct.unpack_from("<I", original, 0x28)[0]
    if frames == 0:
        raise ValueError("the movie has no frames")
    index_at = 0x2C + tracks * 12
    if len(original) < index_at + 8:
        raise ValueError("the movie's index is truncated")
    start, end = struct.unpack_from("<II", original, index_at)
    start &= ~1
    end = end & ~1 if frames > 1 else len(original)
    if not (index_at < start < end <= len(original)):
        raise ValueError("frame 0's extent lies outside the file")
    frame = original[start:end]
    first = index_at + 8
    out = bytearray(original[:index_at])
    out += struct.pack("<II", first | 1, first + len(frame))
    out += frame
    struct.pack_into("<IIII", out, 4, len(out) - 8, 1, len(frame), 1)
    return bytes(out)


def _writable(path):
    """Clear a file's read-only flag, which files copied off a CD keep. Best effort: if it
    cannot be cleared, the write that follows raises the PermissionError that says why."""
    try:
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    except OSError:
        pass


def blank_folder(folder, names, bundled=None):
    """Blank each of `names`, matched case-insensitively, in `folder`. -> (blanked, skipped).

    The first original is kept as <file>.orig and never overwritten, and the blank clip is
    made from it, never from a file already blanked: `bundled`, a real black clip when one
    is supplied, or else the original cut to its first frame (first_frame_bik). So
    re-blanking also repairs a folder left with the old zero-frame stub. A file that is not
    a Bink movie is left alone and named in `skipped`, with the reason.
    """
    by_lower = {f.lower(): f for f in os.listdir(folder)}
    blanked, skipped = [], []
    for name in names:
        actual = by_lower.get(name.lower())
        if not actual:
            continue
        full = os.path.join(folder, actual)
        orig = full + ".orig"
        with open(orig if os.path.exists(orig) else full, "rb") as f:
            original = f.read()
        try:
            if original[:3] != b"BIK":
                raise ValueError("not a Bink movie")
            blob = bundled if bundled is not None else first_frame_bik(original)
        except ValueError as e:
            skipped.append("%s: %s" % (actual, e))
            continue
        if not os.path.exists(orig):
            shutil.copyfile(full, orig)
        _writable(full)
        with open(full, "wb") as f:
            f.write(blob)
        blanked.append(actual)
    return blanked, skipped


def restore_folder(folder, names):
    """Put back each of `names` that blank_folder blanked, moving its .orig over it.
    -> the restored names. Moved rather than copied, so no .orig is left behind to read
    as blanked (Studio 1.2 copied it, and went on calling restored logos blanked)."""
    by_lower = {f.lower(): f for f in os.listdir(folder)}
    restored = []
    for name in names:
        orig = by_lower.get(name.lower() + ".orig")
        if not orig:
            continue
        target = os.path.join(folder, orig[:-len(".orig")])
        if os.path.exists(target):
            _writable(target)
        os.replace(os.path.join(folder, orig), target)
        restored.append(os.path.basename(target))
    return restored


def cmd_list(args):
    if not os.path.isdir(args.folder):
        sys.exit(_NOT_A_FOLDER % args.folder)
    by_lower = {f.lower(): f for f in os.listdir(args.folder)}
    print("game folder %s:" % args.folder)
    found = 0
    for name in LOGO_VIDEOS + SPLASH_VIDEOS:
        actual = by_lower.get(name.lower())
        if actual:
            found += 1
            state = "blanked (.orig kept)" if (name.lower() + ".orig") in by_lower else "original"
            print("  %-30s %-22s %s" % (actual, state, role_of(name.lower())))
    print("%d startup movie(s) here; `blank` cuts the 3 logos (and the splash with "
          "--include-splash)" % found)
    return 0


def _replacement(args):
    return open(args.blank, "rb").read() if args.blank else None


def cmd_blank(args):
    if not os.path.isdir(args.folder):
        sys.exit(_NOT_A_FOLDER % args.folder)
    names = LOGO_VIDEOS + (SPLASH_VIDEOS if args.include_splash else [])
    blanked, skipped = blank_folder(args.folder, names, _replacement(args))
    for name in blanked:
        print("  blanked %-30s (original kept as %s.orig)" % (name, name))
    for s in skipped:
        print("  left alone: " + s)
    if not blanked:
        sys.exit("no startup movies found in %s (is it the installed game folder, with "
                 "Lancer.exe?)" % args.folder)
    return 0


def cmd_restore(args):
    restored = restore_folder(args.folder, LOGO_VIDEOS + SPLASH_VIDEOS)
    print("restored: " + (", ".join(restored) if restored else "(no .orig backups found)"))
    return 0


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(
        description="Skip Starlancer's startup logo movies (static; never runs the game).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="the startup movies in the game folder, and whether blanked")
    p.add_argument("folder"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("blank", help="cut the 3 startup logos in the game folder to their first frames")
    p.add_argument("folder")
    p.add_argument("--include-splash", action="store_true", help='also blank "splash to mm.bik"')
    p.add_argument("--blank", help="use this .bik as the replacement (e.g. a real black clip)")
    p.set_defaults(fn=cmd_blank)
    p = sub.add_parser("restore", help="put back the originals `blank` kept as .orig")
    p.add_argument("folder"); p.set_defaults(fn=cmd_restore)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
