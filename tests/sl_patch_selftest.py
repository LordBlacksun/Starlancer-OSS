#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""
sl_patch_selftest.py - self-tests for the sl_patch.py patch-pack engine.

Builds a SYNTHETIC PE in a temp dir (never the game) with the same ImageBase,
size and hook-site fingerprints the real engine expects, then exercises:
  * apply widescreen -> verify state + decoded resolution
  * revert via manifest -> byte-identical round-trip to the original
  * idempotency guard (re-applying a present fix is refused)
  * fingerprint-mismatch guard (refused without --force)
  * multi-fix canonical ordering + per-fix --revert-only, using a synthetic
    second PatchDefinition injected into the registry

No game data required, so this runs in CI. Static only: nothing is executed.
Exit 0 = all pass.
"""
import os, sys, json, struct, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sl_patch():
    # works whether this test sits beside sl_patch.py (tools/) or in tests/ with
    # sl_patch.py one level up in tools/ (the OSS layout).
    candidates = [os.path.join(HERE, "sl_patch.py"),
                  os.path.join(os.path.dirname(HERE), "tools", "sl_patch.py")]
    path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    spec = importlib.util.spec_from_file_location("sl_patch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SL = _load_sl_patch()


# --------------------------------------------------------------- synthetic PE
def build_synth_exe():
    """A minimal but structurally valid PE32 of exactly EXPECT_SIZE bytes, one
    .text section mapping VA==file-offset, with the widescreen fingerprints
    planted at the real hook VAs and an extra fingerprint for a test fix."""
    size = SL.EXPECT_SIZE
    data = bytearray(size)

    e_lfanew = 0x80
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, e_lfanew)
    data[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
    coff = e_lfanew + 4
    opt = coff + 20
    opt_size = 0xE0
    struct.pack_into("<H", data, coff + 0, 0x014C)      # Machine i386
    struct.pack_into("<H", data, coff + 2, 1)           # NumberOfSections
    struct.pack_into("<H", data, coff + 16, opt_size)   # SizeOfOptionalHeader
    struct.pack_into("<H", data, opt + 0, 0x010B)       # PE32 magic
    struct.pack_into("<I", data, opt + 28, SL.IMAGE_BASE)  # ImageBase

    # one .text section: raw==va==0x1000  => file offset equals RVA
    sect_tbl = opt + opt_size
    raw = 0x1000
    sec_va = 0x1000
    vsize = 0xD2000           # mapped region covers all hook RVAs (0xACD08, 0xC3A60, OEP 0xD1210)
    rawsize = size - raw      # slack runs to EOF (cave space)
    o = sect_tbl
    data[o:o + 8] = b".text\x00\x00\x00"
    struct.pack_into("<I", data, o + 8, vsize)
    struct.pack_into("<I", data, o + 12, sec_va)
    struct.pack_into("<I", data, o + 16, rawsize)
    struct.pack_into("<I", data, o + 20, raw)
    struct.pack_into("<I", data, o + 36, 0x60000020)    # CODE|EXECUTE|READ

    # plant widescreen fingerprints (offset == VA - imagebase here)
    data[0xC3A60:0xC3A60 + len(SL.WS_ORIG_FOV)] = SL.WS_ORIG_FOV
    data[0xACD08:0xACD08 + len(SL.WS_ORIG_RES)] = SL.WS_ORIG_RES
    # plant the medal-fix fingerprint (cave-less in-place patch) at VA 0x4365EC
    data[0x365EC:0x365EC + len(SL.MEDAL_ORIG)] = SL.MEDAL_ORIG
    # plant the multicore-fix fingerprint (OEP code-cave) at VA 0x4D1210
    data[0xD1210:0xD1210 + len(SL.MC_OEP_ORIG)] = SL.MC_OEP_ORIG
    # plant a fingerprint for the synthetic test fix
    data[0xB0000:0xB0000 + len(_TESTFIX_ORIG)] = _TESTFIX_ORIG
    return data


# --------------------------------------------------- synthetic 2nd PatchDefinition
_TESTFIX_VA = 0x004B0000
_TESTFIX_CONT = 0x004B0005
_TESTFIX_ORIG = bytes.fromhex("90 90 90 90 90".replace(" ", ""))   # 5 nops


def _testfix_build(pe, params, alloc):
    off, va = alloc(8)
    cave = b"\x90\x90\x90" + b"\xE9" + SL.rel32(_TESTFIX_CONT, va + 4 + 5)  # 3 nop + jmp back
    hook = b"\xE9" + SL.rel32(va, _TESTFIX_VA + 5)                          # 5-byte jmp
    assert len(hook) == 5
    return dict(caves=[dict(off=off, va=va, bytes=cave)],
                hooks=[dict(off=SL.va_to_off(pe, _TESTFIX_VA), va=_TESTFIX_VA, bytes=hook)])


def _testfix_state(pe, data):
    b = data[SL.va_to_off(pe, _TESTFIX_VA):SL.va_to_off(pe, _TESTFIX_VA) + 5]
    if b and b[0] == 0xE9:
        return "patched"
    if bytes(b) == _TESTFIX_ORIG:
        return "stock"
    return "unknown"


TESTFIX = SL.PatchDefinition(
    id="fps",   # borrow the 'fps' slot so CANONICAL_ORDER places it after widescreen
    summary="[selftest] synthetic fix",
    sites=[dict(va=_TESTFIX_VA, orig=_TESTFIX_ORIG, hook_len=5)],
    build=_testfix_build, verify_state=_testfix_state,
)


# ---------------------------------------------------------------------- harness
PASS, FAIL = 0, 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {msg}")
    else:
        FAIL += 1
        print(f"  FAIL {msg}")


def run():
    global PASS, FAIL
    PASS = FAIL = 0
    tmp = tempfile.mkdtemp(prefix="slpatch_test_")
    src = os.path.join(tmp, "stock.exe")
    orig = build_synth_exe()
    with open(src, "wb") as f:
        f.write(orig)

    # 1) apply widescreen
    out1 = os.path.join(tmp, "ws.exe")
    rc = SL.apply(src, out1, [("widescreen", dict(width=1920, height=1080))])
    check(rc == 0, "apply widescreen returns 0")
    check(os.path.exists(SL._manifest_path(out1)), "manifest written")
    with open(out1, "rb") as f:
        d1 = bytearray(f.read())
    pe1 = SL.parse_pe(d1)
    check(SL.WIDESCREEN.verify_state(pe1, d1) == "patched", "widescreen verifies as patched")
    check("1920 x 1080" in SL.WIDESCREEN.describe_applied(pe1, d1), "decoded forced resolution 1920x1080")
    man1 = json.load(open(SL._manifest_path(out1)))
    check(man1["output_sha256"] == SL._sha(d1), "manifest output sha matches file")
    check([p["id"] for p in man1["patches"]] == ["widescreen"], "manifest lists widescreen")

    # 2) revert via manifest -> byte-identical to original
    rev1 = os.path.join(tmp, "rev.exe")
    SL.revert(out1, rev1)
    with open(rev1, "rb") as f:
        dr = f.read()
    check(dr == bytes(orig), "revert round-trips byte-identical to stock")
    check(not os.path.exists(SL._manifest_path(rev1)), "manifest removed after full revert")

    # 2b) cave-less in-place patch (fix-medal): apply + verify + byte-exact revert
    out_m = os.path.join(tmp, "medal.exe")
    SL.apply(src, out_m, [("fix-medal", {})])
    with open(out_m, "rb") as f:
        dm = bytearray(f.read())
    pem = SL.parse_pe(dm)
    check(SL.FIX_MEDAL.verify_state(pem, dm) == "patched", "fix-medal verifies as patched")
    check(bytes(dm[0x365EC:0x365EC + 5]) == SL.MEDAL_FIXED, "fix-medal wrote the in-place operand (no cave)")
    manm = json.load(open(SL._manifest_path(out_m)))
    check(manm["patches"][0]["caves"] == [], "fix-medal manifest records zero caves (in-place)")
    revm = os.path.join(tmp, "medal_rev.exe")
    SL.revert(out_m, revm)
    with open(revm, "rb") as f:
        check(f.read() == bytes(orig), "fix-medal revert round-trips byte-identical")

    # 2c) OEP code-cave (fix-multicore): apply + verify + structural checks + revert
    out_mc = os.path.join(tmp, "mc.exe")
    SL.apply(src, out_mc, [("fix-multicore", {})])
    with open(out_mc, "rb") as f:
        dmc = bytearray(f.read())
    pemc = SL.parse_pe(dmc)
    check(SL.FIX_MULTICORE.verify_state(pemc, dmc) == "patched", "fix-multicore verifies as patched")
    check(dmc[0xD1210] == 0xE9, "fix-multicore wrote a JMP hook at the OEP")
    manmc = json.load(open(SL._manifest_path(out_mc)))
    cave_hex = manmc["patches"][0]["caves"][0]["bytes"]
    cave = bytes.fromhex(cave_hex)
    check(cave[0] == 0x60 and cave.endswith(b"SetProcessAffinityMask\x00"),
          "fix-multicore cave: pushad ... embedded API name")
    check(SL.MC_OEP_ORIG in cave, "fix-multicore cave preserves the displaced OEP bytes")
    revmc = os.path.join(tmp, "mc_rev.exe")
    SL.revert(out_mc, revmc)
    with open(revmc, "rb") as f:
        check(f.read() == bytes(orig), "fix-multicore revert round-trips byte-identical")

    # 2d) --fix-crashes applies medal + multicore together
    out_fc = os.path.join(tmp, "crashes.exe")
    SL.apply(src, out_fc, [("fix-medal", {}), ("fix-multicore", {})])
    man_fc = json.load(open(SL._manifest_path(out_fc)))
    check([p["id"] for p in man_fc["patches"]] == ["fix-medal", "fix-multicore"],
          "--fix-crashes: both crash fixes applied in canonical order")

    # 3) idempotency: re-applying widescreen onto the patched file is refused
    out_dup = os.path.join(tmp, "dup.exe")
    try:
        SL.apply(out1, out_dup, [("widescreen", dict(width=1920, height=1080))])
        check(False, "re-applying widescreen should have raised")
    except SystemExit:
        check(True, "re-applying an already-applied fix is refused")

    # 4) fingerprint mismatch -> refused without --force
    bad = bytearray(orig)
    bad[0xC3A60] ^= 0xFF
    badp = os.path.join(tmp, "bad.exe")
    with open(badp, "wb") as f:
        f.write(bad)
    try:
        SL.apply(badp, os.path.join(tmp, "bo.exe"), [("widescreen", dict(width=1280, height=1024))])
        check(False, "fingerprint mismatch should have raised")
    except SystemExit:
        check(True, "fingerprint mismatch is refused without --force")

    # 5) multi-fix canonical order + per-fix revert-only (synthetic 2nd fix)
    SL.REGISTRY["fps"] = TESTFIX
    try:
        out2 = os.path.join(tmp, "multi.exe")
        # deliberately pass out of order; engine must canonicalize (widescreen, fps, fix-medal).
        # Mixes cave-based (widescreen, fps) with cave-less (fix-medal) fixes.
        SL.apply(src, out2, [("fix-medal", {}), ("fps", dict(fps=144)),
                             ("widescreen", dict(width=2560, height=1440))])
        man2 = json.load(open(SL._manifest_path(out2)))
        ids = [p["id"] for p in man2["patches"]]
        check(ids == ["widescreen", "fps", "fix-medal"], f"3 fixes in canonical order (got {ids})")
        ws_cave = man2["patches"][0]["caves"][0]["off"]
        fps_cave = man2["patches"][1]["caves"][0]["off"]
        check(fps_cave > ws_cave, "second fix's cave is allocated after the first's")
        with open(out2, "rb") as f:
            d2 = bytearray(f.read())
        pe2 = SL.parse_pe(d2)
        check(SL.WIDESCREEN.verify_state(pe2, d2) == "patched", "multi: widescreen patched")
        check(TESTFIX.verify_state(pe2, d2) == "patched", "multi: synthetic fix patched")
        check(SL.FIX_MEDAL.verify_state(pe2, d2) == "patched", "multi: fix-medal patched (cave-less + caves coexist)")

        # revert only the synthetic fix; widescreen must remain
        out3 = os.path.join(tmp, "multi_revfps.exe")
        SL.revert(out2, out3, only="fps")
        with open(out3, "rb") as f:
            d3 = bytearray(f.read())
        pe3 = SL.parse_pe(d3)
        check(TESTFIX.verify_state(pe3, d3) == "stock", "revert-only fps: synthetic fix reverted")
        check(SL.WIDESCREEN.verify_state(pe3, d3) == "patched", "revert-only fps: widescreen intact")
        check(SL.FIX_MEDAL.verify_state(pe3, d3) == "patched", "revert-only fps: fix-medal intact")
        man3 = json.load(open(SL._manifest_path(out3)))
        check([p["id"] for p in man3["patches"]] == ["widescreen", "fix-medal"],
              "manifest now lists the two surviving fixes")
    finally:
        del SL.REGISTRY["fps"]

    print(f"\nsl_patch selftest: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
