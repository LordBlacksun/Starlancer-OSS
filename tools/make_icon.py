#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""make_icon.py - generate Starlancer Studio's ORIGINAL app icon.

A clean, original "Alliance Naval Command" emblem in the app's own palette: a gold
heraldic eagle (displayed, wings spread) over a dark MFD tile with a broken cyan
orbital ring. This is ORIGINAL ART drawn from primitives — it contains none of the
game's bytes, so it is safe to ship and commit (unlike a game-extracted icon).

Renders at high resolution and downsamples (LANCZOS) into a multi-size .ico via
pe_icon.write_ico. Stdlib + Pillow only.

Usage:
    python make_icon.py [-o assets/app.ico] [--preview prev.png] [--sizes 16,...]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_icon          # noqa: E402  reuse write_ico

# palette (mirrors slstudio_app.py's "Alliance Naval Command MFD")
BG1 = "#0B111B"
BG2 = "#101A28"
CYAN = "#33E1F0"
CYAN_D = "#15808F"
LINE2 = "#284059"
GOLD = "#FFB23E"
GOLD_D = "#C77E1E"
INK = "#04141A"
DEFAULT_SIZES = [16, 24, 32, 48, 64, 128, 256]

# Eagle "displayed" (spread wings), right half only, on a 256 design grid (cx=128).
# Mirrored to the left at render time. Hand-tuned to read as a raptor at 16 px.
EAGLE_RIGHT = [
    (128, 72), (143, 78), (168, 68), (196, 54), (222, 46), (240, 52), (245, 68),
    (216, 72), (232, 90), (198, 90), (214, 110), (180, 104), (158, 130),
    (151, 162), (150, 190), (140, 210), (128, 228),
]
HEAD_C = (128, 52)        # head centre (bottom meets the neck top)
HEAD_R = 15
BEAK = [(140, 46), (160, 52), (140, 58)]   # profile beak, facing right


def _rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def render(S):
    from PIL import Image, ImageDraw
    k = S / 256.0
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def sc(pts):
        return [(x * k, y * k) for x, y in pts]

    def box(cx, cy, r):
        return [(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k]

    # dark rounded tile + thin cyan border
    m = 6 * k
    d.rounded_rectangle([m, m, S - m, S - m], radius=46 * k,
                        fill=_rgb(BG1), outline=_rgb(CYAN_D), width=max(1, int(3 * k)))
    # subtle inner panel
    m2 = 16 * k
    d.rounded_rectangle([m2, m2, S - m2, S - m2], radius=38 * k, outline=_rgb(LINE2),
                        width=max(1, int(1 * k)))
    # broken orbital rings (MFD)
    for rr, col, w, a0, a1 in ((98, CYAN_D, 3, 35, 320), (88, LINE2, 1, 210, 150)):
        d.arc(box(128, 126, rr), a0, a1, fill=_rgb(col), width=max(1, int(w * k)))

    # eagle body: right half + mirrored left half
    left = [(256 - x, y) for x, y in reversed(EAGLE_RIGHT) if x != 128]
    poly = EAGLE_RIGHT + left
    d.polygon(sc(poly), fill=_rgb(GOLD))
    # head + beak
    d.ellipse(box(*HEAD_C, HEAD_R), fill=_rgb(GOLD))
    d.polygon(sc(BEAK), fill=_rgb(GOLD))
    # eye + a single small cyan "core" accent on the chest (MFD)
    d.ellipse(box(HEAD_C[0] + 4, HEAD_C[1] - 2, 2.6), fill=_rgb(INK))
    d.ellipse(box(128, 124, 5), fill=_rgb(CYAN))
    return img


def main():
    from PIL import Image
    ap = argparse.ArgumentParser(description="Generate Starlancer Studio's original app icon.")
    ap.add_argument("-o", "--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        "assets", "app.ico"))
    ap.add_argument("--preview", help="also write a PNG preview at this path")
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)))
    args = ap.parse_args()

    master = render(1024)
    sizes = sorted({int(s) for s in args.sizes.split(",") if s.strip()})
    frames = [master.resize((s, s), Image.LANCZOS) for s in sizes]
    pe_icon.write_ico(frames, args.out)
    print("wrote %s  (sizes: %s)" % (args.out, ", ".join(map(str, sizes))))
    if args.preview:
        master.resize((256, 256), Image.LANCZOS).save(args.preview)
        print("preview ->", args.preview)


if __name__ == "__main__":
    main()
