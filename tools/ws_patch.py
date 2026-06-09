#!/usr/bin/env python3
"""
ws_patch.py - Starlancer native Hor+ widescreen patcher (static binary patch).

Applies two surgical code-cave patches to a *local copy* of the decrypted /
No-CD Starlancer executable so the in-flight 3D view renders at an arbitrary
resolution with a correct **Hor+** field of view (vertical FOV preserved,
horizontal FOV widened, pixels stay square). Front-end menus/briefing remain
640x480 (they pillarbox on widescreen) - that is by design for v1.

  PATCH 1 - Hor+ FOV  (entry of FUN_004c3a60 @ 0x004C3A60, the projection writer)
    The engine computes the X projection scale as (width-K)*sX and the Y scale as
    (height-K)*sY, with sX=0.6, sY=0.8 baked in (a 4:3 encoding: 0.6/0.8 = 480/640).
    The cave overrides sX at runtime to sX := sY * height / width, which makes
    scale_x == scale_y (square pixels / true Hor+) at any aspect, AND derives the
    X clip planes from the same value (no edge-pop). At any 4:3 resolution this
    recomputes to 0.6 => identical to stock (regression-safe).

  PATCH 2 - force resolution  (FUN_004acbe0 @ 0x004ACBE0, device init)
    Bakes the chosen WIDTH/HEIGHT into the flight-resolution globals
    DAT_005d6b2c (width) / DAT_005d6c88 (height), overriding starlancer.ini /
    dmodes.bin. The cave is hooked at the height-save (0x004ACD08) and writes both
    globals, so the result is self-contained.

SAFETY / PROVENANCE
  * This script NEVER executes the target - it reads and writes it as data only.
  * Run it on a COPY of your own legally-owned, decrypted exe. We ship no game
    code or binaries; the patched exe is yours and stays local.
  * Addresses target the analyzed build (ImageBase 0x00400000, 1,151,021 bytes,
    OEP 0x004D1210). The tool refuses to patch if the fingerprint bytes don't match.
  * In-game verification (does 1920x1080 look right / not crash) is the user's.

Dependency-free (standard library only). Usage:
    python ws_patch.py --width 1920 --height 1080 IN.exe OUT.exe
    python ws_patch.py --verify PATCHED.exe
    python ws_patch.py --revert PATCHED.exe OUT.exe
"""
import sys, struct, argparse

IMAGE_BASE = 0x00400000

# --- engine addresses (VA) recovered by static RE; see docs/engine-map.md ---
VA_FOV_FUNC      = 0x004C3A60   # FUN_004c3a60 entry (projection scale/centre writer)
VA_FOV_CONT      = 0x004C3A67   # resume point: the 2nd `fild` (load height)
VA_RES_HOOK      = 0x004ACD08   # the `mov [DAT_005d6c88], edx` height-save in FUN_004acbe0
VA_RES_CONT      = 0x004ACD0E   # instruction after the height-save
G_WIDTH          = 0x005D6B2C   # DAT_005d6b2c - flight 3D width
G_HEIGHT         = 0x005D6C88   # DAT_005d6c88 - flight 3D height
S_WIDTH          = 0x005E81B6   # device struct +0x1666 (width, integer dword)
S_HEIGHT         = 0x005E81BA   # device struct +0x166a (height, integer dword)

# --- original bytes at the two hook sites (fingerprint + revert source) ---
ORIG_FOV  = bytes.fromhex("51" "db05b6815e00")          # push ecx ; fild dword [0x5e81b6]
ORIG_RES  = bytes.fromhex("8915886c5d00")               # mov dword [0x5d6c88], edx

EXPECT_SIZE = 1151021


# --------------------------------------------------------------------------- PE
def parse_pe(data):
    if data[:2] != b"MZ":
        raise ValueError("not an MZ/PE image")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("no PE signature")
    coff = e_lfanew + 4
    nsec, = struct.unpack_from("<H", data, coff + 2)
    opt_size, = struct.unpack_from("<H", data, coff + 16)
    opt = coff + 20
    image_base = struct.unpack_from("<I", data, opt + 28)[0]
    sect_tbl = opt + opt_size
    secs = []
    for i in range(nsec):
        o = sect_tbl + i * 40
        name = data[o:o + 8].rstrip(b"\x00").decode("latin-1", "replace")
        vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, o + 8)
        flags = struct.unpack_from("<I", data, o + 36)[0]
        secs.append(dict(name=name, va=va, vsize=vsize, raw=raw, rawsize=rawsize, flags=flags))
    return dict(image_base=image_base, secs=secs)


def text_section(pe):
    for s in pe["secs"]:
        if s["name"] == ".text" or (s["flags"] & 0x20000000):  # MEM_EXECUTE
            return s
    raise ValueError("no executable .text section")


def va_to_off(pe, va):
    rva = va - pe["image_base"]
    for s in pe["secs"]:
        if s["va"] <= rva < s["va"] + max(s["vsize"], s["rawsize"]):
            return s["raw"] + (rva - s["va"])
    raise ValueError(f"VA 0x{va:08X} not mapped to any section")


def off_to_va(pe, off, sec):
    return pe["image_base"] + sec["va"] + (off - sec["raw"])


def align_up(x, a):
    return (x + a - 1) & ~(a - 1)


# ------------------------------------------------------------------- cave bytes
def rel32(target_va, ip_after):
    """E9/E8 rel32 displacement from the instruction's end to target."""
    return struct.pack("<i", target_va - ip_after)


def build_fov_cave(cave_va):
    """param_5 := param_6 * height / width, then run displaced `fild [width]`, jmp back.
    Frame note: the displaced `push ecx` runs first, so post-push param_6=[esp+0x1C],
    param_5 slot=[esp+0x18]."""
    b = bytearray()
    b += bytes.fromhex("51")            # push ecx                (displaced #1)
    b += bytes.fromhex("db05") + struct.pack("<I", S_HEIGHT)   # fild  dword [height]  -> st0
    b += bytes.fromhex("d84c241c")      # fmul  dword [esp+0x1C]  ; * param_6 (float)
    b += bytes.fromhex("da35") + struct.pack("<I", S_WIDTH)    # fidiv dword [width]   ; / width (int)
    b += bytes.fromhex("d95c2418")      # fstp  dword [esp+0x18]  ; param_5 := result
    b += bytes.fromhex("db05") + struct.pack("<I", S_WIDTH)    # fild  dword [width]   (displaced #2)
    b += b"\xE9" + rel32(VA_FOV_CONT, cave_va + len(b) + 5)    # jmp 0x004C3A67
    return bytes(b)


def build_res_cave(cave_va, width, height):
    """mov [DAT_005d6b2c], WIDTH ; mov [DAT_005d6c88], HEIGHT ; jmp back."""
    b = bytearray()
    b += b"\xC7\x05" + struct.pack("<I", G_WIDTH)  + struct.pack("<I", width)   # mov [w], imm32
    b += b"\xC7\x05" + struct.pack("<I", G_HEIGHT) + struct.pack("<I", height)  # mov [h], imm32
    b += b"\xE9" + rel32(VA_RES_CONT, cave_va + len(b) + 5)                      # jmp 0x004ACD0E
    return bytes(b)


# ------------------------------------------------------------------- operations
def _cave_base(pe):
    """First 16-aligned free offset in the executable .text slack (between
    VirtualSize and SizeOfRawData), which is mapped+executable at runtime."""
    t = text_section(pe)
    base_off = align_up(t["raw"] + t["vsize"], 16)
    slack_end = t["raw"] + t["rawsize"]
    return t, base_off, slack_end


def patch(in_path, out_path, width, height, force=False):
    with open(in_path, "rb") as f:
        data = bytearray(f.read())
    pe = parse_pe(data)

    if len(data) != EXPECT_SIZE and not force:
        raise SystemExit(f"refusing: size {len(data):,} != expected {EXPECT_SIZE:,} "
                         f"(wrong/already-different build; use --force to override)")
    if pe["image_base"] != IMAGE_BASE:
        raise SystemExit(f"refusing: ImageBase 0x{pe['image_base']:08X} != 0x{IMAGE_BASE:08X}")

    fov_off = va_to_off(pe, VA_FOV_FUNC)
    res_off = va_to_off(pe, VA_RES_HOOK)

    # fingerprint / idempotency
    cur_fov = bytes(data[fov_off:fov_off + len(ORIG_FOV)])
    cur_res = bytes(data[res_off:res_off + len(ORIG_RES)])
    if cur_fov[0] == 0xE9 or cur_res[0] == 0xE9:
        raise SystemExit("refusing: a hook site already contains a JMP - exe looks already patched "
                         "(use --revert first).")
    if cur_fov != ORIG_FOV and not force:
        raise SystemExit(f"refusing: bytes at 0x{VA_FOV_FUNC:08X} = {cur_fov.hex()} "
                         f"!= expected {ORIG_FOV.hex()} (unexpected build; --force to override)")
    if cur_res != ORIG_RES and not force:
        raise SystemExit(f"refusing: bytes at 0x{VA_RES_HOOK:08X} = {cur_res.hex()} "
                         f"!= expected {ORIG_RES.hex()} (unexpected build; --force to override)")

    # place both caves in .text slack
    t, base, slack_end = _cave_base(pe)
    fov_cave_off = base
    fov_cave_va = off_to_va(pe, fov_cave_off, t)
    fov_cave = build_fov_cave(fov_cave_va)

    res_cave_off = align_up(fov_cave_off + len(fov_cave), 16)
    res_cave_va = off_to_va(pe, res_cave_off, t)
    res_cave = build_res_cave(res_cave_va, width, height)

    end = res_cave_off + len(res_cave)
    if end > slack_end:
        raise SystemExit(f"refusing: caves (0x{end - base:X} B) exceed .text slack "
                         f"(0x{slack_end - base:X} B). Would need a new section.")
    # the slack must actually be free (zero) where we write
    region = bytes(data[base:end])
    if any(region) and not force:
        raise SystemExit(f"refusing: .text slack at file 0x{base:X} is not all-zero "
                         f"(unexpected; --force to override)")

    # build hooks
    hook_fov = b"\xE9" + rel32(fov_cave_va, VA_FOV_FUNC + 5) + b"\x90\x90"      # 7 bytes
    hook_res = b"\xE9" + rel32(res_cave_va, VA_RES_HOOK + 5) + b"\x90"          # 6 bytes
    assert len(hook_fov) == len(ORIG_FOV) == 7
    assert len(hook_res) == len(ORIG_RES) == 6

    # apply
    data[fov_cave_off:fov_cave_off + len(fov_cave)] = fov_cave
    data[res_cave_off:res_cave_off + len(res_cave)] = res_cave
    data[fov_off:fov_off + len(hook_fov)] = hook_fov
    data[res_off:res_off + len(hook_res)] = hook_res

    with open(out_path, "wb") as f:
        f.write(data)

    print(f"[ok] patched {in_path} -> {out_path}")
    print(f"     resolution forced to {width} x {height} (aspect {width/height:.4f})")
    print(f"     FOV cave  @ VA 0x{fov_cave_va:08X} (file 0x{fov_cave_off:X}, {len(fov_cave)} B) "
          f"<- hook 0x{VA_FOV_FUNC:08X}")
    print(f"     RES cave  @ VA 0x{res_cave_va:08X} (file 0x{res_cave_off:X}, {len(res_cave)} B) "
          f"<- hook 0x{VA_RES_HOOK:08X}")
    if width > 1280:
        print("     note: widths >1280 may hit the srddraw.dll back/Z-buffer ceiling; pair with "
              "dgVoodoo2/DDrawCompat and verify in-game.")
    print("     reminder: never launch the game on the user's behalf; in-game testing is theirs.")


def verify(path):
    with open(path, "rb") as f:
        data = f.read()
    pe = parse_pe(data)
    fov_off = va_to_off(pe, VA_FOV_FUNC)
    res_off = va_to_off(pe, VA_RES_HOOK)
    fov_b = data[fov_off:fov_off + 7]
    res_b = data[res_off:res_off + 6]
    patched = (fov_b[0] == 0xE9 and res_b[0] == 0xE9)
    stock = (bytes(fov_b) == ORIG_FOV and bytes(res_b) == ORIG_RES)
    print(f"FILE: {path}  ({len(data):,} bytes)")
    print(f"  0x{VA_FOV_FUNC:08X}: {fov_b.hex()}  ({'HOOK' if fov_b[0]==0xE9 else 'stock' if bytes(fov_b)==ORIG_FOV else '???'})")
    print(f"  0x{VA_RES_HOOK:08X}: {res_b.hex()}  ({'HOOK' if res_b[0]==0xE9 else 'stock' if bytes(res_b)==ORIG_RES else '???'})")
    if patched:
        # decode forced resolution from the res cave
        rel = struct.unpack_from("<i", res_b, 1)[0]
        cave_va = (VA_RES_HOOK + 5) + rel
        cave_off = va_to_off(pe, cave_va)
        w = struct.unpack_from("<I", data, cave_off + 6)[0]
        h = struct.unpack_from("<I", data, cave_off + 16)[0]
        print(f"  => PATCHED. forced resolution {w} x {h} (cave @ 0x{cave_va:08X})")
        return 0
    if stock:
        print("  => STOCK (unpatched).")
        return 0
    print("  => UNKNOWN state (partially patched or different build).")
    return 2


def revert(in_path, out_path):
    with open(in_path, "rb") as f:
        data = bytearray(f.read())
    pe = parse_pe(data)
    fov_off = va_to_off(pe, VA_FOV_FUNC)
    res_off = va_to_off(pe, VA_RES_HOOK)
    if data[fov_off] != 0xE9 and data[res_off] != 0xE9:
        raise SystemExit("nothing to revert (no hooks present).")
    # recompute both cave bases the same way patch() did, and zero them
    t, base, slack_end = _cave_base(pe)
    fov_cave_off = base
    res_cave_off = align_up(fov_cave_off + 32, 16)
    for o, n in ((fov_cave_off, 64), (res_cave_off, 32)):
        data[o:o + n] = b"\x00" * n
    data[fov_off:fov_off + len(ORIG_FOV)] = ORIG_FOV
    data[res_off:res_off + len(ORIG_RES)] = ORIG_RES
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"[ok] reverted {in_path} -> {out_path} (hooks restored, caves zeroed)")


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fov_table():
    """Reproduce the FUN_004c3a60 projection model to show the Hor+ result per aspect.
    sX_stock=0.6, sY=0.8, K=0.1 are the baked .rdata constants; the patch sets
    sX := sY*h/w so scale_x==scale_y (square pixels, vertical FOV preserved)."""
    import math
    S6, S8, K = _f32(0.6000000238), _f32(0.8000000119), _f32(0.10000000149)
    sx0 = lambda w: _f32(_f32(w - K) * S6)
    sy  = lambda h: _f32(_f32(h - K) * S8)
    sxp = lambda w, h: _f32(_f32(w - K) * _f32(_f32(S8 * h) / w))
    hf  = lambda w, sx: math.degrees(2 * math.atan((w / 2) / sx))
    vf  = lambda h, s: math.degrees(2 * math.atan((h / 2) / s))
    print("Hor+ projection model (vertical FOV fixed; horizontal widens; pixels square)")
    print(f"{'resolution':>12} {'aspect':>7} | {'Hfov_stock':>10} {'Hfov_Hor+':>10} {'Vfov':>7} | square")
    for w, h in [(640,480),(800,600),(1024,768),(1280,1024),(1280,800),(1680,1050),
                 (1920,1080),(2560,1440),(3440,1440),(5120,1440)]:
        sq = "yes" if abs(sxp(w, h) - sy(h)) < 0.1 else "NO"
        print(f"{w:>5}x{h:<6}{w/h:>7.3f} | {hf(w,sx0(w)):10.2f} {hf(w,sxp(w,h)):10.2f} "
              f"{vf(h,sy(h)):7.2f} | {sq}")
    print("(4:3 rows: Hor+ == stock => regression-safe no-op.)")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description="Starlancer native Hor+ widescreen patcher (static).")
    ap.add_argument("--width", type=int, help="forced in-flight 3D width (e.g. 1920)")
    ap.add_argument("--height", type=int, help="forced in-flight 3D height (e.g. 1080)")
    ap.add_argument("--verify", metavar="EXE", help="report patch state of EXE and exit")
    ap.add_argument("--fov-table", action="store_true", help="print the Hor+ FOV table and exit")
    ap.add_argument("--revert", nargs=2, metavar=("IN", "OUT"), help="restore stock bytes")
    ap.add_argument("--force", action="store_true", help="override fingerprint/size guards")
    ap.add_argument("files", nargs="*", help="IN.exe OUT.exe")
    a = ap.parse_args(argv)

    if a.fov_table:
        return fov_table()
    if a.verify:
        return verify(a.verify)
    if a.revert:
        return revert(a.revert[0], a.revert[1])
    if len(a.files) != 2 or a.width is None or a.height is None:
        ap.error("need: --width W --height H IN.exe OUT.exe")
    if not (320 <= a.width <= 7680 and 240 <= a.height <= 4320):
        print(f"warning: {a.width}x{a.height} is outside the sane 320x240..7680x4320 range", file=sys.stderr)
    return patch(a.files[0], a.files[1], a.width, a.height, force=a.force)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
