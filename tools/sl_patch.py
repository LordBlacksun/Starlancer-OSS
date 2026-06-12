#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""
sl_patch.py - Starlancer modern-systems patch pack (static binary patcher).

A unified, declarative code-cave engine for the family of static EXE fixes that
"better the executable for modern systems". Each fix is a PatchDefinition; any
subset can be applied in one pass, verified, or reverted independently. The tool
NEVER executes the target - it reads and writes a *local copy* as data only.

Fixes (toggle with the flags below):
  widescreen WxH   native Hor+ widescreen for the in-flight 3D view (the v1 patch,
                   absorbed verbatim from ws_patch.py - byte-identical output).
  fps N            raise the engine frame-cap to ~N FPS (configurable; fixed-step
                   timer design preserved). [Phase B - site TBD by RE]
  fix-medal        fix the late-campaign medal-case crash. [Phase C - TBD by RE]
  fix-multicore    stop the multi-core crash (self-affinity). [Phase C - TBD by RE]

DESIGN
  * PatchDefinition registry: each fix declares its hook sites (VA + original
    fingerprint bytes + hook length), a cave builder, a verify routine, and a
    revert payload. The engine packs all selected caves into .text slack with a
    single shared bump-allocator, in a fixed CANONICAL ORDER so output is
    deterministic and (for widescreen-only) byte-identical to ws_patch v1.
  * A sidecar manifest (OUT.exe.slpatch.json) records exactly what was applied
    (per-fix sites, caves, params, input/output sha256) so --verify / --revert
    work for any subset, and a NEW fix can be appended to an already-patched exe.

SAFETY / PROVENANCE
  * Static only: never launches the exe. Run on a COPY of your own legally-owned,
    decrypted/No-CD exe. We ship no game code or binaries; the patched exe is
    yours and stays local.
  * Addresses target the analyzed build (ImageBase 0x00400000, 1,151,021 bytes,
    OEP 0x004D1210). The tool refuses to patch if fingerprints don't match.
  * In-game verification (does it look right / not crash) is the user's, on their
    own terms. The tool never nudges you to launch the game.

Dependency-free (standard library only). Usage:
    python sl_patch.py --widescreen 1920x1080 IN.exe OUT.exe
    python sl_patch.py --widescreen 1920x1080 --fps 144 --fix-crashes IN.exe OUT.exe
    python sl_patch.py --all --widescreen 1920x1080 --fps 144 IN.exe OUT.exe
    python sl_patch.py --verify PATCHED.exe
    python sl_patch.py --revert PATCHED.exe OUT.exe          # revert all fixes
    python sl_patch.py --revert-only fps PATCHED.exe OUT.exe # revert one fix
    python sl_patch.py --fov-table
"""
import sys, os, json, struct, argparse, hashlib

TOOL_VERSION = "sl_patch/1.0"
IMAGE_BASE = 0x00400000
EXPECT_SIZE = 1151021

# Canonical order in which selected fixes are laid out in .text slack. Keeping
# widescreen first (fov-cave then res-cave) reproduces ws_patch v1 byte-for-byte
# when widescreen is the only selected fix.
CANONICAL_ORDER = ["widescreen", "fps", "fix-medal", "fix-multicore"]


# =========================================================================== PE
# (identical helpers to ws_patch.py v1 - shared so widescreen output is bit-exact)
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


def rel32(target_va, ip_after):
    """E9/E8 rel32 displacement from the instruction's end to target."""
    return struct.pack("<i", target_va - ip_after)


def _cave_base(pe):
    """First 16-aligned free offset in the executable .text slack (between
    VirtualSize and SizeOfRawData), which is mapped+executable at runtime."""
    t = text_section(pe)
    base_off = align_up(t["raw"] + t["vsize"], 16)
    slack_end = t["raw"] + t["rawsize"]
    return t, base_off, slack_end


# ============================================================ PatchDefinition API
# A PatchDefinition is a plain object with:
#   id              : str, stable key (also the CLI/manifest name)
#   summary         : str, one-line human description
#   sites           : list of dicts {va, orig (bytes), hook_len (int)}
#                     the hook sites in the ORIGINAL code; orig is the fingerprint
#                     and the revert source; hook_len bytes are overwritten by a
#                     jmp (+nop padding) to the cave.
#   build           : fn(pe, params, alloc) -> dict(caves=[...], hooks=[...])
#                       alloc(nbytes) -> (cave_off, cave_va) bumps the shared
#                         .text-slack allocator (16-aligned).
#                       caves: list of dicts {off, va, bytes}
#                       hooks: list of dicts {off, va, bytes}  (len == hook_len)
#   verify_state    : fn(pe, data) -> "patched" | "stock" | "unknown"
#                       quick byte-scan independent of the manifest.
#   describe_applied: fn(pe, data) -> str   (optional; e.g. decoded resolution)
#
# Each definition keeps the engine generic: the allocator, manifest, fingerprint
# guards, idempotency and revert are all handled centrally.

class PatchDefinition:
    def __init__(self, id, summary, sites, build,
                 verify_state, describe_applied=None, needs_params=False):
        self.id = id
        self.summary = summary
        self.sites = sites
        self.build = build
        self.verify_state = verify_state
        self.describe_applied = describe_applied
        self.needs_params = needs_params


# --------------------------------------------------------------------------------
# FIX 1: widescreen  (absorbed from ws_patch.py v1 - must stay byte-identical)
# --------------------------------------------------------------------------------
WS_VA_FOV_FUNC = 0x004C3A60   # FUN_004c3a60 entry (projection scale/centre writer)
WS_VA_FOV_CONT = 0x004C3A67   # resume point: the 2nd `fild` (load height)
WS_VA_RES_HOOK = 0x004ACD08   # the `mov [DAT_005d6c88], edx` height-save in FUN_004acbe0
WS_VA_RES_CONT = 0x004ACD0E   # instruction after the height-save
WS_G_WIDTH     = 0x005D6B2C   # DAT_005d6b2c - flight 3D width
WS_G_HEIGHT    = 0x005D6C88   # DAT_005d6c88 - flight 3D height
WS_S_WIDTH     = 0x005E81B6   # device struct +0x1666 (width, integer dword)
WS_S_HEIGHT    = 0x005E81BA   # device struct +0x166a (height, integer dword)

WS_ORIG_FOV = bytes.fromhex("51" "db05b6815e00")   # push ecx ; fild dword [0x5e81b6]
WS_ORIG_RES = bytes.fromhex("8915886c5d00")        # mov dword [0x5d6c88], edx


def _ws_build_fov_cave(cave_va):
    """param_5 := param_6 * height / width, then run displaced `fild [width]`, jmp back."""
    b = bytearray()
    b += bytes.fromhex("51")                                       # push ecx (displaced #1)
    b += bytes.fromhex("db05") + struct.pack("<I", WS_S_HEIGHT)    # fild  dword [height]
    b += bytes.fromhex("d84c241c")                                 # fmul  dword [esp+0x1C] (param_6)
    b += bytes.fromhex("da35") + struct.pack("<I", WS_S_WIDTH)     # fidiv dword [width]
    b += bytes.fromhex("d95c2418")                                 # fstp  dword [esp+0x18] (param_5)
    b += bytes.fromhex("db05") + struct.pack("<I", WS_S_WIDTH)     # fild  dword [width] (displaced #2)
    b += b"\xE9" + rel32(WS_VA_FOV_CONT, cave_va + len(b) + 5)     # jmp 0x004C3A67
    return bytes(b)


def _ws_build_res_cave(cave_va, width, height):
    """mov [DAT_005d6b2c], WIDTH ; mov [DAT_005d6c88], HEIGHT ; jmp back."""
    b = bytearray()
    b += b"\xC7\x05" + struct.pack("<I", WS_G_WIDTH)  + struct.pack("<I", width)
    b += b"\xC7\x05" + struct.pack("<I", WS_G_HEIGHT) + struct.pack("<I", height)
    b += b"\xE9" + rel32(WS_VA_RES_CONT, cave_va + len(b) + 5)
    return bytes(b)


def _ws_build(pe, params, alloc):
    width, height = params["width"], params["height"]
    # FOV cave first, then RES cave - allocate the ACTUAL cave lengths so the
    # layout reproduces ws_patch v1 byte-for-byte: fov(32B) at base, res(25B) at
    # align_up(base+32,16) == base+32. (Cave length is VA-independent, so we can
    # measure it with a throwaway build before allocating.)
    fov_off, fov_va = alloc(len(_ws_build_fov_cave(0)))
    fov_cave = _ws_build_fov_cave(fov_va)
    res_off, res_va = alloc(len(_ws_build_res_cave(0, width, height)))
    res_cave = _ws_build_res_cave(res_va, width, height)

    hook_fov = b"\xE9" + rel32(fov_va, WS_VA_FOV_FUNC + 5) + b"\x90\x90"   # 7 bytes
    hook_res = b"\xE9" + rel32(res_va, WS_VA_RES_HOOK + 5) + b"\x90"       # 6 bytes
    assert len(hook_fov) == 7 and len(hook_res) == 6
    return dict(
        caves=[dict(off=fov_off, va=fov_va, bytes=fov_cave),
               dict(off=res_off, va=res_va, bytes=res_cave)],
        hooks=[dict(off=va_to_off(pe, WS_VA_FOV_FUNC), va=WS_VA_FOV_FUNC, bytes=hook_fov),
               dict(off=va_to_off(pe, WS_VA_RES_HOOK), va=WS_VA_RES_HOOK, bytes=hook_res)],
    )


def _ws_verify_state(pe, data):
    fb = data[va_to_off(pe, WS_VA_FOV_FUNC):va_to_off(pe, WS_VA_FOV_FUNC) + 7]
    rb = data[va_to_off(pe, WS_VA_RES_HOOK):va_to_off(pe, WS_VA_RES_HOOK) + 6]
    if fb[0] == 0xE9 and rb[0] == 0xE9:
        return "patched"
    if bytes(fb) == WS_ORIG_FOV and bytes(rb) == WS_ORIG_RES:
        return "stock"
    return "unknown"


def _ws_describe(pe, data):
    rb = data[va_to_off(pe, WS_VA_RES_HOOK):va_to_off(pe, WS_VA_RES_HOOK) + 6]
    if rb[0] != 0xE9:
        return ""
    rel = struct.unpack_from("<i", rb, 1)[0]
    cave_va = (WS_VA_RES_HOOK + 5) + rel
    cave_off = va_to_off(pe, cave_va)
    w = struct.unpack_from("<I", data, cave_off + 6)[0]
    h = struct.unpack_from("<I", data, cave_off + 16)[0]
    return f"forced flight resolution {w} x {h} (aspect {w/h:.4f})"


WIDESCREEN = PatchDefinition(
    id="widescreen",
    summary="native Hor+ widescreen for the in-flight 3D view",
    sites=[dict(va=WS_VA_FOV_FUNC, orig=WS_ORIG_FOV, hook_len=7),
           dict(va=WS_VA_RES_HOOK, orig=WS_ORIG_RES, hook_len=6)],
    build=_ws_build,
    verify_state=_ws_verify_state,
    describe_applied=_ws_describe,
    needs_params=True,
)


# --------------------------------------------------------------------------------
# FIX 2/3: fps / fix-medal / fix-multicore - registered in later phases.
# Their PatchDefinitions slot in here once the RE has pinned exact sites and
# fingerprints. The engine below is already fix-agnostic.
# --------------------------------------------------------------------------------

REGISTRY = {d.id: d for d in [WIDESCREEN]}


# =================================================================== engine core
def _load(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def _sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _manifest_path(exe_path):
    return exe_path + ".slpatch.json"


def _read_manifest(exe_path):
    p = _manifest_path(exe_path)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _preflight(data, pe, force):
    if len(data) != EXPECT_SIZE and not force:
        raise SystemExit(f"refusing: size {len(data):,} != expected {EXPECT_SIZE:,} "
                         f"(wrong/already-different build; use --force to override)")
    if pe["image_base"] != IMAGE_BASE:
        raise SystemExit(f"refusing: ImageBase 0x{pe['image_base']:08X} != 0x{IMAGE_BASE:08X}")


def _check_site(data, pe, defn, site, force):
    off = va_to_off(pe, site["va"])
    cur = bytes(data[off:off + len(site["orig"])])
    if cur and cur[0] == 0xE9:
        raise SystemExit(f"refusing: hook site 0x{site['va']:08X} for '{defn.id}' already "
                         f"contains a JMP (already patched - use --revert / --revert-only first).")
    if cur != site["orig"] and not force:
        raise SystemExit(f"refusing: bytes at 0x{site['va']:08X} = {cur.hex()} != expected "
                         f"{site['orig'].hex()} for '{defn.id}' (unexpected build; --force to override).")


def apply(in_path, out_path, selections, force=False, dry_run=False):
    """selections: ordered list of (defn_id, params_dict). Applies all, packing
    caves into .text slack in CANONICAL_ORDER, writes OUT + sidecar manifest."""
    data = _load(in_path)
    pe = parse_pe(data)
    _preflight(data, pe, force)
    in_sha = _sha(data)

    # an already-patched input may carry a manifest of prior fixes; we append.
    prior = _read_manifest(in_path)
    prior_patches = (prior or {}).get("patches", []) if prior else []
    prior_ids = {p["id"] for p in prior_patches}

    # order selections canonically; reject duplicates of already-applied fixes
    sel = sorted(selections, key=lambda s: CANONICAL_ORDER.index(s[0]))
    for did, _ in sel:
        if did in prior_ids:
            raise SystemExit(f"refusing: '{did}' is already applied to {in_path} "
                             f"(per its manifest). Revert it first to re-apply.")

    # shared bump allocator over .text slack, starting after any prior caves
    t, base, slack_end = _cave_base(pe)
    cursor = [base]
    for p in prior_patches:                       # don't stomp existing caves
        for c in p.get("caves", []):
            cursor[0] = max(cursor[0], align_up(c["off"] + len(bytes.fromhex(c["bytes"])), 16))

    def alloc(nbytes):
        off = align_up(cursor[0], 16)
        cursor[0] = off + nbytes
        return off, off_to_va(pe, off, t)

    new_patches = []
    pending_writes = []   # (off, bytes)
    for did, params in sel:
        defn = REGISTRY[did]
        for site in defn.sites:
            _check_site(data, pe, defn, site, force)
        built = defn.build(pe, params, alloc)

        if cursor[0] > slack_end:
            raise SystemExit(f"refusing: caves for '{did}' (need up to file 0x{cursor[0]:X}) exceed "
                             f".text slack end 0x{slack_end:X}. Would need a new section.")
        for c in built["caves"]:
            region = bytes(data[c["off"]:c["off"] + len(c["bytes"])])
            if any(region) and not force:
                raise SystemExit(f"refusing: .text slack at file 0x{c['off']:X} is not all-zero "
                                 f"(unexpected; --force to override).")
            pending_writes.append((c["off"], c["bytes"]))
        for h in built["hooks"]:
            pending_writes.append((h["off"], h["bytes"]))

        new_patches.append(dict(
            id=did, params=params,
            sites=[dict(va=s["va"], off=va_to_off(pe, s["va"]),
                        orig=s["orig"].hex()) for s in defn.sites],
            caves=[dict(off=c["off"], va=c["va"], bytes=c["bytes"].hex()) for c in built["caves"]],
            hooks=[dict(off=h["off"], va=h["va"], bytes=h["bytes"].hex()) for h in built["hooks"]],
        ))

    for off, b in pending_writes:
        data[off:off + len(b)] = b
    out_sha = _sha(data)

    manifest = dict(
        tool_version=TOOL_VERSION,
        target=dict(expected_size=EXPECT_SIZE, image_base=IMAGE_BASE),
        input_sha256=in_sha, output_sha256=out_sha,
        patches=prior_patches + new_patches,
    )

    if dry_run:
        print(f"[dry-run] would patch {in_path} -> {out_path}")
        _print_plan(new_patches)
        return 0

    with open(out_path, "wb") as f:
        f.write(data)
    with open(_manifest_path(out_path), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[ok] patched {in_path} -> {out_path}")
    print(f"     manifest: {_manifest_path(out_path)}")
    _print_plan(new_patches)
    any_ws = any(p["id"] == "widescreen" for p in new_patches)
    if any_ws:
        wp = next(p for p in new_patches if p["id"] == "widescreen")
        if wp["params"].get("width", 0) > 1280:
            print("     note: widths >1280 may hit the srddraw.dll back/Z-buffer ceiling; pair "
                  "with dgVoodoo2/DDrawCompat and verify in-game.")
    print("     reminder: never launch the game on the user's behalf; in-game testing is theirs.")
    return 0


def _print_plan(patches):
    for p in patches:
        extra = ""
        if p["id"] == "widescreen":
            extra = f"  ({p['params']['width']}x{p['params']['height']})"
        elif p["id"] == "fps":
            extra = f"  (~{p['params'].get('fps','?')} FPS)"
        print(f"     + {p['id']}{extra}")
        for c in p["caves"]:
            print(f"         cave @ VA 0x{c['va']:08X} (file 0x{c['off']:X}, "
                  f"{len(bytes.fromhex(c['bytes']))} B)")
        for h in p["hooks"]:
            print(f"         hook @ VA 0x{h['va']:08X}")


def verify(path):
    data = _load(path)
    pe = parse_pe(data)
    print(f"FILE: {path}  ({len(data):,} bytes)")
    man = _read_manifest(path)
    if man:
        ok = (_sha(data) == man.get("output_sha256"))
        print(f"  manifest: {_manifest_path(path)}  "
              f"({'sha256 matches' if ok else 'WARNING sha256 differs from manifest'})")
    any_patched = False
    for did, defn in REGISTRY.items():
        state = defn.verify_state(pe, data)
        line = f"  {did:14s}: {state.upper()}"
        if state == "patched" and defn.describe_applied:
            desc = defn.describe_applied(pe, data)
            if desc:
                line += f"  - {desc}"
        if state == "patched":
            any_patched = True
        if state != "stock" or (man and any(p["id"] == did for p in man.get("patches", []))):
            print(line)
    if not any_patched:
        print("  => STOCK (no fixes detected).")
        return 0
    return 0


def revert(in_path, out_path, only=None):
    """Revert all fixes (only=None) or one fix id. Uses the manifest if present,
    else falls back to the widescreen byte-layout for legacy files."""
    data = _load(in_path)
    pe = parse_pe(data)
    man = _read_manifest(in_path)

    if man:
        patches = man.get("patches", [])
        targets = [p for p in patches if (only is None or p["id"] == only)]
        if not targets:
            raise SystemExit(f"nothing to revert (no '{only}' in manifest)" if only
                             else "nothing to revert (manifest has no patches).")
        for p in targets:
            for s in p["sites"]:
                orig = bytes.fromhex(s["orig"])
                data[s["off"]:s["off"] + len(orig)] = orig
            for c in p["caves"]:
                n = len(bytes.fromhex(c["bytes"]))
                data[c["off"]:c["off"] + n] = b"\x00" * n
        remaining = [p for p in patches if p not in targets]
        with open(out_path, "wb") as f:
            f.write(data)
        # update / drop sidecar
        if remaining:
            man["patches"] = remaining
            man["output_sha256"] = _sha(data)
            with open(_manifest_path(out_path), "w", encoding="utf-8") as f:
                json.dump(man, f, indent=2)
        else:
            if os.path.exists(_manifest_path(out_path)):
                os.remove(_manifest_path(out_path))
        print(f"[ok] reverted {', '.join(p['id'] for p in targets)} : {in_path} -> {out_path}")
        return 0

    # ---- legacy fallback: no manifest -> assume ws_patch v1 widescreen layout ----
    if only not in (None, "widescreen"):
        raise SystemExit(f"no manifest beside {in_path}; cannot revert just '{only}'. "
                         "Use a full --revert (handles legacy widescreen-only files).")
    fov_off = va_to_off(pe, WS_VA_FOV_FUNC)
    res_off = va_to_off(pe, WS_VA_RES_HOOK)
    if data[fov_off] != 0xE9 and data[res_off] != 0xE9:
        raise SystemExit("nothing to revert (no hooks present, no manifest).")
    t, base, _ = _cave_base(pe)
    fov_cave_off = base
    res_cave_off = align_up(fov_cave_off + 32, 16)
    for o, n in ((fov_cave_off, 64), (res_cave_off, 32)):
        data[o:o + n] = b"\x00" * n
    data[fov_off:fov_off + len(WS_ORIG_FOV)] = WS_ORIG_FOV
    data[res_off:res_off + len(WS_ORIG_RES)] = WS_ORIG_RES
    with open(out_path, "wb") as f:
        f.write(data)
    print(f"[ok] reverted (legacy widescreen layout): {in_path} -> {out_path}")
    return 0


# =================================================================== FOV helpers
def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fov_table():
    """Reproduce the FUN_004c3a60 projection model to show the Hor+ result per aspect."""
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


# =========================================================================== CLI
def _parse_wxh(s):
    s = s.lower().replace("*", "x")
    if "x" not in s:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1920x1080")
    w, h = s.split("x", 1)
    return int(w), int(h)


def main(argv):
    ap = argparse.ArgumentParser(description="Starlancer modern-systems patch pack (static).")
    ap.add_argument("--widescreen", metavar="WxH", type=_parse_wxh,
                    help="native Hor+ widescreen for the flight view, e.g. 1920x1080")
    ap.add_argument("--fps", type=int, metavar="N",
                    help="raise the frame-cap to ~N FPS (30..360) [Phase B]")
    ap.add_argument("--fix-medal", action="store_true",
                    help="fix the late-campaign medal-case crash [Phase C]")
    ap.add_argument("--fix-multicore", action="store_true",
                    help="fix the multi-core crash (self-affinity) [Phase C]")
    ap.add_argument("--fix-crashes", action="store_true",
                    help="shorthand for --fix-medal --fix-multicore")
    ap.add_argument("--all", action="store_true",
                    help="apply every fix that has its parameters supplied")
    ap.add_argument("--verify", metavar="EXE", help="report patch state of EXE and exit")
    ap.add_argument("--fov-table", action="store_true", help="print the Hor+ FOV table and exit")
    ap.add_argument("--revert", nargs=2, metavar=("IN", "OUT"),
                    help="restore stock bytes for ALL applied fixes")
    ap.add_argument("--revert-only", nargs=3, metavar=("FIX", "IN", "OUT"),
                    help="revert a single fix by id (needs the sidecar manifest)")
    ap.add_argument("--force", action="store_true", help="override fingerprint/size guards")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    ap.add_argument("files", nargs="*", help="IN.exe OUT.exe")
    a = ap.parse_args(argv)

    if a.fov_table:
        return fov_table()
    if a.verify:
        return verify(a.verify)
    if a.revert:
        return revert(a.revert[0], a.revert[1])
    if a.revert_only:
        return revert(a.revert_only[1], a.revert_only[2], only=a.revert_only[0])

    # assemble selections
    selections = []
    if a.widescreen:
        w, h = a.widescreen
        if not (320 <= w <= 7680 and 240 <= h <= 4320):
            print(f"warning: {w}x{h} is outside the sane 320x240..7680x4320 range", file=sys.stderr)
        selections.append(("widescreen", dict(width=w, height=h)))
    if a.fps is not None:
        if "fps" not in REGISTRY:
            ap.error("--fps is not yet available in this build (Phase B pending).")
        if not (30 <= a.fps <= 360):
            ap.error("--fps must be in 30..360")
        selections.append(("fps", dict(fps=a.fps)))
    want_medal = a.fix_medal or a.fix_crashes or a.all
    want_mc = a.fix_multicore or a.fix_crashes or a.all
    if want_medal:
        if "fix-medal" not in REGISTRY:
            ap.error("--fix-medal is not yet available in this build (Phase C pending).")
        selections.append(("fix-medal", {}))
    if want_mc:
        if "fix-multicore" not in REGISTRY:
            ap.error("--fix-multicore is not yet available in this build (Phase C pending).")
        selections.append(("fix-multicore", {}))

    if not selections:
        ap.error("nothing to do: pass at least one fix (e.g. --widescreen 1920x1080), "
                 "or --verify / --revert / --fov-table")
    if len(a.files) != 2:
        ap.error("need: <fix flags> IN.exe OUT.exe")

    return apply(a.files[0], a.files[1], selections, force=a.force, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
