#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""pe_icon.py - extract a Windows PE's embedded application icon to a .ico, and
build a crisp multi-size app icon from it.

Part of the Starlancer RE project. Walks the PE resource tree (RT_GROUP_ICON /
RT_ICON), reassembles the native .ico, then renders a modern multi-size icon by
NEAREST-neighbour scaling the native art (so a 2000-era 32x32 frame stays a crisp
retro-pixel icon instead of a blurry smear).

Reuses pe_inspect.rva_to_off for RVA->file-offset mapping (same house style, no
third-party PE deps). Pillow (PIL) is used only to decode the native frame and
re-scale it.

SAFETY (non-negotiable): like pe_inspect, this NEVER executes the target. It is a
pure file read of the binary as data. The game is never launched.

Usage:
    python pe_icon.py <file.exe> [-o assets/app.ico] [--native raw.ico]
                       [--sizes 16,24,32,48,64,128,256]
"""
import sys
import os
import io
import struct
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_inspect          # noqa: E402  reuse rva_to_off (read-only PE helper)

RT_ICON = 3
RT_GROUP_ICON = 14
DEFAULT_SIZES = [16, 24, 32, 48, 64, 128, 256]


# ----------------------------------------------------------------- PE headers --
def _parse_headers(data):
    """Return (data_directories, sections) the same way pe_inspect does, but as a
    reusable function. sections are dicts rva_to_off understands."""
    if data[:2] != b"MZ":
        raise ValueError("not an MZ image")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("no PE header")
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    pe_plus = (struct.unpack_from("<H", data, opt)[0] == 0x20b)
    ndd = struct.unpack_from("<I", data, opt + (108 if pe_plus else 92))[0]
    dd_off = opt + (112 if pe_plus else 96)
    dirs = [struct.unpack_from("<II", data, dd_off + i * 8) for i in range(min(ndd, 16))]
    sect_tbl = opt + opt_size
    sections = []
    for i in range(nsec):
        o = sect_tbl + i * 40
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
        sections.append({"va": va, "vsize": vsize, "raw": raw, "rawsize": rawsize})
    return dirs, sections


# --------------------------------------------------------- resource-tree walk --
def _res_entries(data, base_off, dir_off):
    """Entries of the IMAGE_RESOURCE_DIRECTORY at base_off+dir_off -> [(id_or_name, off)].
    off's high bit set => points at a subdirectory (offset relative to base_off)."""
    o = base_off + dir_off
    nnamed, nid = struct.unpack_from("<HH", data, o + 12)
    out = []
    for i in range(nnamed + nid):
        name, off = struct.unpack_from("<II", data, o + 16 + i * 8)
        out.append((name, off))
    return out


def _find_type_dir(data, base_off, type_id):
    """Offset (relative to base_off) of the level-2 directory for a given RT_* type id."""
    for name, off in _res_entries(data, base_off, 0):
        if name & 0x80000000:                     # named type -> skip (icons use ids)
            continue
        if name == type_id and (off & 0x80000000):
            return off & 0x7FFFFFFF
    return None


def _collect(data, base_off, type_dir_off, sections):
    """Map every resource under a type directory: id -> raw bytes (first language)."""
    out = {}
    if type_dir_off is None:
        return out
    for rid, off in _res_entries(data, base_off, type_dir_off):
        # descend language level(s) to the first IMAGE_RESOURCE_DATA_ENTRY
        cur = off
        guard = 0
        while (cur & 0x80000000) and guard < 8:
            sub = _res_entries(data, base_off, cur & 0x7FFFFFFF)
            if not sub:
                cur = None
                break
            cur = sub[0][1]
            guard += 1
        if not cur or (cur & 0x80000000):
            continue
        rva, size = struct.unpack_from("<II", data, base_off + cur)
        foff = pe_inspect.rva_to_off(rva, sections)
        if foff is None:
            continue
        out[rid] = data[foff:foff + size]
    return out


def _grp_to_ico(group, icons):
    """Reassemble a native .ico from a GRPICONDIR + its RT_ICON images."""
    _res, _typ, count = struct.unpack_from("<HHH", group, 0)
    head = bytearray(struct.pack("<HHH", 0, 1, count))
    blobs = bytearray()
    offset = 6 + count * 16
    for i in range(count):
        bW, bH, bCC, bRes, planes, bits, nbytes, nid = struct.unpack_from(
            "<BBBBHHIH", group, 6 + i * 14)
        img = icons.get(nid, b"")
        head += struct.pack("<BBBBHHII", bW, bH, bCC, bRes, planes, bits, len(img), offset)
        blobs += img
        offset += len(img)
    return bytes(head + blobs)


def extract_native_ico(path):
    """Read the PE (as data) and return the bytes of its embedded application icon."""
    with open(path, "rb") as f:
        data = f.read()
    dirs, sections = _parse_headers(data)
    if len(dirs) <= 2 or not dirs[2][0]:
        raise ValueError("no resource directory in this PE")
    base_off = pe_inspect.rva_to_off(dirs[2][0], sections)
    if base_off is None:
        raise ValueError("resource directory RVA not mapped to a section")
    groups = _collect(data, base_off, _find_type_dir(data, base_off, RT_GROUP_ICON), sections)
    icons = _collect(data, base_off, _find_type_dir(data, base_off, RT_ICON), sections)
    if not groups or not icons:
        raise ValueError("no icon resources found (groups=%d icons=%d)"
                         % (len(groups), len(icons)))
    group = groups[min(groups)]                   # lowest-id icon group = the app icon
    return _grp_to_ico(group, icons)


# ------------------------------------------------------ multi-size .ico writer --
def _dib_frame(im):
    """One ICO frame as a 32bpp BMP/DIB (bottom-up BGRA + a 1bpp AND mask from
    alpha). The most universally compatible form for both the Windows shell and
    Tk's iconbitmap."""
    w, h = im.size
    px = im.load()
    bih = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    xor = bytearray()
    mask = bytearray()
    row_bytes = ((w + 31) // 32) * 4              # 1bpp rows padded to 32 bits
    for y in range(h - 1, -1, -1):                # bottom-up
        bits = bytearray(row_bytes)
        for x in range(w):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))
            if a == 0:                            # AND-mask bit 1 == transparent
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return bih + bytes(xor) + bytes(mask)


def write_ico(frames, out_path):
    """Write a list of RGBA PIL images as one multi-size .ico (32bpp DIB frames).
    Reusable by any icon generator (e.g. make_icon.py)."""
    head = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    body = bytearray()
    offset = 6 + len(frames) * 16
    for im in frames:
        dib = _dib_frame(im)
        w, h = im.size
        head += struct.pack("<BBBBHHII", w & 0xFF, h & 0xFF, 0, 0, 1, 32, len(dib), offset)
        body += dib
        offset += len(dib)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(head + body)


def build_app_icon(native_ico, out_path, sizes=DEFAULT_SIZES):
    """Render a crisp multi-size .ico from the native icon bytes (NEAREST scaling)."""
    from PIL import Image
    base = Image.open(io.BytesIO(native_ico)).convert("RGBA")   # PIL picks the best frame
    frames = [base.resize((s, s), Image.NEAREST) for s in sorted(set(sizes))]
    write_ico(frames, out_path)
    return base.size, [im.size[0] for im in frames]


def main():
    ap = argparse.ArgumentParser(description="Extract a PE's app icon to a multi-size .ico "
                                             "(read-only; never executes the target).")
    ap.add_argument("exe", help="source PE (read as data only)")
    ap.add_argument("-o", "--out", default=os.path.join("assets", "app.ico"),
                    help="output .ico (default assets/app.ico)")
    ap.add_argument("--native", help="also write the raw reconstructed native .ico here")
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)),
                    help="comma-separated frame sizes")
    args = ap.parse_args()

    native = extract_native_ico(args.exe)
    print("native icon: %d bytes reconstructed from %s" % (len(native), os.path.basename(args.exe)))
    if args.native:
        with open(args.native, "wb") as f:
            f.write(native)
        print("  wrote native ->", args.native)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    src, made = build_app_icon(native, args.out, sizes)
    print("  source frame %dx%d -> %s  (sizes: %s)"
          % (src[0], src[1], args.out, ", ".join(map(str, made))))


if __name__ == "__main__":
    main()
