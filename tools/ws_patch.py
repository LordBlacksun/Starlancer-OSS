#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""
ws_patch.py - DEPRECATED alias for sl_patch.py (Starlancer Hor+ widescreen).

The widescreen Hor+ patcher has been folded into the unified modern-systems
patch pack `sl_patch.py`, which applies widescreen plus the other static EXE
fixes (FPS cap, crash fixes) from one tool with a shared cave engine, a sidecar
manifest, and per-fix verify/revert.

This shim preserves the original ws_patch CLI and delegates to sl_patch, so old
commands and scripts keep working. The patched-exe bytes are byte-identical to
the previous ws_patch (verified by analysis/sl_patch_regression.py). Prefer:

    python sl_patch.py --widescreen 1920x1080 IN.exe OUT.exe

Legacy usage (still supported here):
    python ws_patch.py --width 1920 --height 1080 IN.exe OUT.exe
    python ws_patch.py --verify PATCHED.exe
    python ws_patch.py --revert PATCHED.exe OUT.exe
    python ws_patch.py --fov-table

Static only: never executes the target. Run on a COPY of your own decrypted exe.
"""
import sys, os, argparse, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sl_patch", os.path.join(_HERE, "sl_patch.py"))
sl_patch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl_patch)

# Re-export the projection-model helper some callers/docs reference by name.
fov_table = sl_patch.fov_table


def _deprecation():
    print("note: ws_patch.py is deprecated - use 'sl_patch.py --widescreen WxH'. "
          "Delegating to sl_patch (output is byte-identical).", file=sys.stderr)


def main(argv):
    ap = argparse.ArgumentParser(
        description="DEPRECATED: Starlancer Hor+ widescreen patcher (now an alias for sl_patch.py).")
    ap.add_argument("--width", type=int, help="forced in-flight 3D width (e.g. 1920)")
    ap.add_argument("--height", type=int, help="forced in-flight 3D height (e.g. 1080)")
    ap.add_argument("--verify", metavar="EXE", help="report patch state of EXE and exit")
    ap.add_argument("--fov-table", action="store_true", help="print the Hor+ FOV table and exit")
    ap.add_argument("--revert", nargs=2, metavar=("IN", "OUT"), help="restore stock bytes")
    ap.add_argument("--force", action="store_true", help="override fingerprint/size guards")
    ap.add_argument("files", nargs="*", help="IN.exe OUT.exe")
    a = ap.parse_args(argv)

    if a.fov_table:
        return sl_patch.fov_table()
    _deprecation()
    if a.verify:
        return sl_patch.verify(a.verify)
    if a.revert:
        return sl_patch.revert(a.revert[0], a.revert[1])
    if len(a.files) != 2 or a.width is None or a.height is None:
        ap.error("need: --width W --height H IN.exe OUT.exe")
    if not (320 <= a.width <= 7680 and 240 <= a.height <= 4320):
        print(f"warning: {a.width}x{a.height} is outside the sane 320x240..7680x4320 range",
              file=sys.stderr)
    return sl_patch.apply(a.files[0], a.files[1],
                          [("widescreen", dict(width=a.width, height=a.height))], force=a.force)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
