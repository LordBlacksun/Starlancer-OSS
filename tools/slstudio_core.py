#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""slstudio_core.py - Starlancer Studio's headless core.

Studio's logic, with none of its widgets. Everything here is standard library
only and imports cleanly with no GUI toolkit present, which is the whole point:
`slstudio_app.py` cannot be imported without customtkinter, so until this module
existed the app's logic was untestable and the Linux CI leg never touched a line
of it. `tests/run_all.py` now runs `selftest()` below on every platform.

What lives here:

    scan(folder)            one pass over an install -> an Install snapshot
    Install.exe_kind        stock / patched / safedisc-loader / absent / unknown,
                            each with the evidence that decided it
    patch_states()          per-fix EXE state, via sl_patch's own verify primitives
    shim_status()           XInput shim: ours / someone else's / absent
    bootvid_status()        which loose startup logos are present and blanked
    recommended_selections()  the one-click fix list, derived from sl_patch.REGISTRY
    describe_selections()   that list as one human-readable line
    retire_manifest()       retire a sidecar manifest whose exe was restored

SAFETY, as everywhere in this project: this module READS an installation and
describes it. It never launches Starlancer or any other binary, and it writes
nothing except `retire_manifest`, which renames one JSON sidecar it created.

CLI:
    python slstudio_core.py scan <game folder> [--json]
"""

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sl_patch                          # noqa: E402  declarative EXE patch pack
import blank_boot_videos as bootvid      # noqa: E402  startup-logo blanker

__all__ = [
    "Install", "scan", "find_exe", "patch_states", "shim_status", "bootvid_status",
    "recommended_selections", "describe_selections", "retire_manifest",
    "classify_exe", "LOGO_VIDEOS", "selftest",
]

LOGO_VIDEOS = list(bootvid.LOGO_VIDEOS)

# SafeDisc 2 wraps the real image in an outer loader and parks its stub in oddly
# named sections. Their presence is a positive identification, not a size guess,
# so an install can be told "this is the disc loader, the fixes cannot apply to it"
# instead of the vaguer "loader or modified build" the Dashboard used to show.
SAFEDISC_SECTIONS = ("stxt774", "stxt371")

STAT_TABLES = ("SHIPSTATS.BIN", "GUNSTATS.BIN", "MISSILESTATS.BIN")


# =============================================================== small probes ==
def find_exe(folder):
    """The install's Lancer.exe, matched case-insensitively. '' if absent."""
    try:
        for f in os.listdir(folder):
            if f.lower() == "lancer.exe":
                return os.path.join(folder, f)
    except OSError:
        pass
    return ""


def patch_states(exe_path):
    """Per-fix EXE patch state. -> (dict{fix_id: (state, desc)}, manifest|None, sha_ok|None).

    state is one of patched / stock / unknown. Every fix in sl_patch.REGISTRY is
    reported, in canonical order, so a new PatchDefinition is picked up here and in
    every front-end without an edit. A file that is not a PE yields ({}, None, None)
    rather than raising, because callers use this to *decide* whether a file is one.
    """
    states = {}
    if not exe_path or not os.path.exists(exe_path):
        return states, None, None
    try:
        data = sl_patch._load(exe_path)
        pe = sl_patch.parse_pe(data)
    except Exception:
        return states, None, None
    for defn in sl_patch.ordered_fixes():
        try:
            state = defn.verify_state(pe, data)
            desc = (defn.describe_applied(pe, data) or "") if (
                state == "patched" and defn.describe_applied) else ""
        except Exception:
            state, desc = "unknown", ""
        states[defn.id] = (state, desc)
    man = sl_patch._read_manifest(exe_path)
    sha_ok = None
    if man:
        try:
            sha_ok = (sl_patch._sha(data) == man.get("output_sha256"))
        except Exception:
            sha_ok = None
    return states, man, sha_ok


def classify_exe(exe_path, states=None):
    """What kind of executable is this? -> (kind, evidence).

    kind:  absent | safedisc-loader | patched | stock | unknown
    evidence: a short phrase naming what decided it, so the UI can show its
              reasoning rather than asserting a verdict the user cannot check.
    """
    if not exe_path or not os.path.exists(exe_path):
        return "absent", "no Lancer.exe in this folder"
    try:
        size = os.path.getsize(exe_path)
    except OSError:
        return "unknown", "file could not be read"
    try:
        with io.open(exe_path, "rb") as f:
            data = f.read()
        pe = sl_patch.parse_pe(data)
    except Exception:
        return "unknown", "%s bytes, not a readable PE image" % format(size, ",")

    names = [s["name"] for s in pe["secs"]]
    hits = [n for n in names if n in SAFEDISC_SECTIONS]
    if hits:
        return "safedisc-loader", ("SafeDisc sections %s present; the real image is "
                                   "encrypted behind this loader" % ", ".join(hits))
    if states is None:
        states, _man, _sha = patch_states(exe_path)
    applied = [k for k, (st, _d) in states.items() if st == "patched"]
    if applied:
        return "patched", "fixes applied: " + ", ".join(sorted(applied))
    if size == sl_patch.EXPECT_SIZE:
        return "stock", "%s bytes, matches the analysed build exactly" % format(size, ",")
    return "unknown", ("%s bytes, expected %s for the analysed build"
                       % (format(size, ","), format(sl_patch.EXPECT_SIZE, ",")))


def shim_status(folder, reference_dll=None):
    """XInput-shim install state. -> (state, has_backup); state in ours/other/absent.

    `reference_dll` is the bundled proxy to compare against. The GUI resolves it
    through PyInstaller's _MEIPASS, which is why it is passed in rather than
    looked up here: this module must stay importable outside the frozen app.
    """
    if not folder or not os.path.isdir(folder):
        return "absent", False
    dest = os.path.join(folder, "dinput.dll")
    has_backup = os.path.exists(dest + ".xinput-bak")
    if not os.path.exists(dest):
        return "absent", has_backup
    try:
        if reference_dll and os.path.exists(reference_dll) and \
                os.path.getsize(reference_dll) == os.path.getsize(dest):
            with io.open(reference_dll, "rb") as a, io.open(dest, "rb") as b:
                if a.read() == b.read():
                    return "ours", has_backup
    except OSError:
        pass
    return "other", has_backup


def bootvid_status(folder):
    """Loose startup-logo state. -> (present[names], blanked[names]).

    'blanked' means an .orig sits beside it, i.e. the blanker replaced the file and
    kept the true original. Names are returned in the folder's own casing.
    """
    present, blanked = [], []
    if not folder or not os.path.isdir(folder):
        return present, blanked
    try:
        by_lower = {f.lower(): f for f in os.listdir(folder)}
    except OSError:
        return present, blanked
    for name in LOGO_VIDEOS:
        actual = by_lower.get(name.lower())
        if actual:
            present.append(actual)
            if (name.lower() + ".orig") in by_lower:
                blanked.append(actual)
    return present, blanked


# ============================================================ fix selections ==
def recommended_selections(width=None, height=None, include_params=True):
    """The one-click pipelines' fix list, derived from sl_patch.REGISTRY.

    Every definition marked `recommended` is taken, in canonical order. A fix that
    declares needs_params is included only when its parameters were supplied, so a
    caller wanting "leave the aspect alone" passes include_params=False instead of
    keeping its own list of which fixes happen to exist.
    """
    sel = []
    for defn in sl_patch.ordered_fixes():
        if not defn.recommended:
            continue
        if defn.needs_params:
            if not (include_params and width and height):
                continue
            sel.append((defn.id, dict(width=int(width), height=int(height))))
        else:
            sel.append((defn.id, {}))
    return sel


def describe_selections(sel):
    """One-line human summary of a selection list, for logs and the notes file."""
    parts = []
    for did, params in sel:
        defn = sl_patch.REGISTRY.get(did)
        text = defn.label.lower() if defn else did
        if params.get("width") and params.get("height"):
            text += " %dx%d" % (params["width"], params["height"])
        parts.append(text)
    return " + ".join(parts) if parts else "(no fixes selected)"


def retire_manifest(exe_path):
    """Rename a now-stale <exe>.slpatch.json after the exe under it was restored.

    sl_patch drops its sidecar manifest next to the file it patched. Restoring
    Lancer.exe from Lancer.exe.bak puts a STOCK exe back but leaves the manifest
    describing the patched one, so the next scan reads every fix as stock while the
    manifest's checksum no longer matches: an amber "sha differs" with nothing
    actually wrong. Renamed rather than deleted, so the record of what had been
    applied survives for anyone reading the folder afterwards.
    Returns the retired basename, or None if there was nothing to retire.
    """
    man = sl_patch._manifest_path(exe_path)
    if not os.path.exists(man):
        return None
    retired = "%s.%s.retired" % (man, time.strftime("%Y%m%d-%H%M%S"))
    try:
        os.replace(man, retired)
    except OSError:
        return None
    return os.path.basename(retired)


# ============================================================ install snapshot ==
class Install(object):
    """One scan of a Starlancer folder: everything the UI asks about, read once.

    Sections used to browse for resource.hog and the stat tables separately in
    every tab even though they sit in the folder already chosen. This is the
    single answer to "what is in this install?", so a tab can seed itself.
    """

    def __init__(self, folder):
        self.folder = folder or ""
        self.files = {}                  # lower-case name -> the folder's own casing
        self.exe = ""
        self.exe_size = 0
        self.exe_kind = "absent"
        self.exe_evidence = ""
        self.patches = {}                # fix_id -> (state, desc)
        self.manifest = None
        self.manifest_sha_ok = None
        self.shim = "absent"
        self.shim_backup = False
        self.logos_present = []
        self.logos_blanked = []
        self.resource_hog = ""
        self.stats = {}                  # 'ship'|'gun'|'missile' -> path or ''
        self.missions_loose = []
        self.backups = []                # (backup name, the file it restores)
        self.writable = False
        self.under_program_files = False

    # ---- derived -----------------------------------------------------------
    def has_exe(self):
        return bool(self.exe and os.path.exists(self.exe))

    def patched_fixes(self):
        return sorted(k for k, (st, _d) in self.patches.items() if st == "patched")

    def manifest_is_stale(self):
        """True when a manifest describes an exe that is no longer the one present.

        This is the condition retire_manifest() exists to clear: a sidecar whose
        checksum does not match, with no fix actually applied. Reported separately
        from a plain checksum mismatch, which can also mean a hand-edited exe.
        """
        return bool(self.manifest) and self.manifest_sha_ok is False \
            and not self.patched_fixes()

    def to_dict(self):
        return dict(
            folder=self.folder, exe=self.exe, exe_size=self.exe_size,
            exe_kind=self.exe_kind, exe_evidence=self.exe_evidence,
            patches={k: v[0] for k, v in self.patches.items()},
            manifest_present=bool(self.manifest), manifest_sha_ok=self.manifest_sha_ok,
            manifest_stale=self.manifest_is_stale(),
            shim=self.shim, shim_backup=self.shim_backup,
            logos_present=self.logos_present, logos_blanked=self.logos_blanked,
            resource_hog=self.resource_hog, stats=self.stats,
            missions_loose=self.missions_loose, backups=self.backups,
            writable=self.writable, under_program_files=self.under_program_files,
        )


def scan(folder, reference_dll=None):
    """One pass over an install folder -> Install. Never raises on a bad folder."""
    inst = Install(folder)
    if not folder or not os.path.isdir(folder):
        return inst

    try:
        names = os.listdir(folder)
    except OSError:
        return inst
    inst.files = dict((n.lower(), n) for n in names)

    low = folder.replace("/", "\\").lower()
    inst.under_program_files = ("\\program files" in low)
    inst.writable = os.access(folder, os.W_OK)

    inst.exe = find_exe(folder)
    if inst.exe:
        try:
            inst.exe_size = os.path.getsize(inst.exe)
        except OSError:
            inst.exe_size = 0
        inst.patches, inst.manifest, inst.manifest_sha_ok = patch_states(inst.exe)
        inst.exe_kind, inst.exe_evidence = classify_exe(inst.exe, inst.patches)
    else:
        inst.exe_kind, inst.exe_evidence = "absent", "no Lancer.exe in this folder"

    inst.shim, inst.shim_backup = shim_status(folder, reference_dll)
    inst.logos_present, inst.logos_blanked = bootvid_status(folder)

    hog = inst.files.get("resource.hog")
    inst.resource_hog = os.path.join(folder, hog) if hog else ""

    for key, table in zip(("ship", "gun", "missile"), STAT_TABLES):
        actual = inst.files.get(table.lower())
        inst.stats[key] = os.path.join(folder, actual) if actual else ""

    mdir = inst.files.get("missions")
    if mdir and os.path.isdir(os.path.join(folder, mdir)):
        try:
            inst.missions_loose = sorted(
                f for f in os.listdir(os.path.join(folder, mdir))
                if f.lower().endswith(".dte"))
        except OSError:
            inst.missions_loose = []

    for lower, actual in sorted(inst.files.items()):
        if lower == "lancer.exe.bak":
            inst.backups.append((actual, "Lancer.exe"))
        elif lower == "dinput.dll.xinput-bak":
            inst.backups.append((actual, "dinput.dll"))

    return inst


# ==================================================================== selftest ==
def _mk(path, data=b""):
    with io.open(path, "wb") as f:
        f.write(data)


def selftest():
    """Exercise the core against a SYNTHETIC install. No game data is involved.

    Every file below is bytes this function makes up on the spot: the point is to
    prove the scanner's reasoning, not to test a real installation, and the repo
    must never contain game files. Returns 0 on success.
    """
    import shutil
    import struct
    import tempfile

    fails = []
    ran = [0]

    def check(cond, label):
        ran[0] += 1
        print("  %-4s %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            fails.append(label)

    print("=== slstudio_core self-test (synthetic install) ===")

    # --- a minimal, entirely synthetic PE so parse_pe has something to read ---
    def fake_pe(section_names, total_size):
        n = len(section_names)
        e_lfanew = 0x80
        opt_size = 0xE0
        buf = bytearray(b"\x00" * 0x400)
        buf[0:2] = b"MZ"
        struct.pack_into("<I", buf, 0x3C, e_lfanew)
        buf[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
        coff = e_lfanew + 4
        struct.pack_into("<H", buf, coff + 2, n)          # NumberOfSections
        struct.pack_into("<H", buf, coff + 16, opt_size)  # SizeOfOptionalHeader
        opt = coff + 20
        struct.pack_into("<I", buf, opt + 28, 0x00400000)  # ImageBase
        tbl = opt + opt_size
        for i, nm in enumerate(section_names):
            o = tbl + i * 40
            raw = nm.encode("latin-1")[:8]
            buf[o:o + len(raw)] = raw
            struct.pack_into("<IIII", buf, o + 8, 0x1000, 0x1000, 0x200, 0x400)
            struct.pack_into("<I", buf, o + 36, 0x60000020)
        if total_size > len(buf):
            buf += b"\x00" * (total_size - len(buf))
        return bytes(buf[:total_size])

    root = tempfile.mkdtemp(prefix="slcore_test_")
    try:
        # ---------------------------------------------------------- empty folder
        empty = os.path.join(root, "empty")
        os.mkdir(empty)
        inst = scan(empty)
        check(inst.exe == "" and inst.exe_kind == "absent", "empty folder -> exe absent")
        check(inst.resource_hog == "" and inst.stats["ship"] == "",
              "empty folder -> no hog, no stat tables")
        check(inst.to_dict()["exe_kind"] == "absent", "to_dict round-trips the verdict")

        # ------------------------------------------------------- a 'stock' install
        game = os.path.join(root, "game")
        os.mkdir(game)
        _mk(os.path.join(game, "Lancer.exe"), fake_pe([".text", ".data"], sl_patch.EXPECT_SIZE))
        _mk(os.path.join(game, "RESOURCE.HOG"), b"BIGF")
        _mk(os.path.join(game, "ShipStats.bin"), b"\x00" * 32)
        os.mkdir(os.path.join(game, "MISSIONS"))
        _mk(os.path.join(game, "MISSIONS", "mission1.dte"), b"\x00" * 8)
        _mk(os.path.join(game, "MISSIONS", "readme.txt"), b"hi")
        inst = scan(game)
        check(inst.has_exe(), "stock: exe found case-insensitively")
        check(inst.exe_kind == "stock", "stock: classified stock (got %r)" % inst.exe_kind)
        check(str(sl_patch.EXPECT_SIZE) in inst.exe_evidence.replace(",", ""),
              "stock: evidence names the size that decided it")
        check(inst.resource_hog.endswith("RESOURCE.HOG"), "stock: hog found in the folder's casing")
        check(inst.stats["ship"].endswith("ShipStats.bin"), "stock: ship table found")
        check(inst.stats["gun"] == "", "stock: absent gun table reported empty, not guessed")
        check(inst.missions_loose == ["mission1.dte"], "stock: loose .dte listed, .txt ignored")
        check(inst.patched_fixes() == [], "stock: no fix reports patched")

        # -------------------------------------------------- a SafeDisc disc loader
        disc = os.path.join(root, "disc")
        os.mkdir(disc)
        _mk(os.path.join(disc, "LANCER.EXE"), fake_pe([".text", "stxt774", "stxt371"], 249119))
        inst = scan(disc)
        check(inst.exe_kind == "safedisc-loader",
              "loader: identified by section name, not size (got %r)" % inst.exe_kind)
        check("stxt774" in inst.exe_evidence, "loader: evidence names the marker section")

        # ------------------------------------------------- a file that is not a PE
        junk = os.path.join(root, "junk")
        os.mkdir(junk)
        _mk(os.path.join(junk, "lancer.exe"), b"this is not a PE at all")
        inst = scan(junk)
        check(inst.exe_kind == "unknown", "non-PE: unknown rather than an exception")
        check(inst.patches == {}, "non-PE: no fix states invented")

        # ------------------------------------------------------ backups + manifest
        _mk(os.path.join(game, "Lancer.exe.bak"), b"\x00" * 16)
        _mk(os.path.join(game, "dinput.dll"), b"\x00" * 16)
        _mk(os.path.join(game, "dinput.dll.xinput-bak"), b"\x00" * 16)
        inst = scan(game)
        check(("Lancer.exe.bak", "Lancer.exe") in inst.backups, "backups: exe backup listed")
        check(("dinput.dll.xinput-bak", "dinput.dll") in inst.backups,
              "backups: shim backup listed")
        check(inst.shim == "other" and inst.shim_backup,
              "shim: an unrecognised dinput.dll reads as 'other', backup seen")

        ref = os.path.join(root, "ref_dinput.dll")
        _mk(ref, b"\x00" * 16)
        inst = scan(game, reference_dll=ref)
        check(inst.shim == "ours", "shim: byte-identical to the bundled proxy reads as 'ours'")

        exe = os.path.join(game, "Lancer.exe")
        man = sl_patch._manifest_path(exe)
        with io.open(man, "w", encoding="utf-8") as f:
            json.dump({"output_sha256": "0" * 64, "patches": [{"id": "widescreen"}]}, f)
        inst = scan(game)
        check(inst.manifest_sha_ok is False, "manifest: mismatch detected")
        check(inst.manifest_is_stale(),
              "manifest: mismatch with no fix applied reads as STALE, not as tampering")
        retired = retire_manifest(exe)
        check(retired is not None and not os.path.exists(man),
              "manifest: retired away from the restored exe")
        check(os.path.exists(os.path.join(game, retired)),
              "manifest: kept under a .retired name, not deleted")
        check(retire_manifest(exe) is None, "manifest: retiring twice is a no-op")
        check(scan(game).manifest_is_stale() is False, "manifest: stale flag clears after retiring")

        # ------------------------------------------------------------- selections
        sel = recommended_selections(1920, 1080)
        ids = [i for i, _p in sel]
        check(ids == [d.id for d in sl_patch.ordered_fixes() if d.recommended],
              "selections: every recommended fix, in canonical order")
        check(dict(sel).get("widescreen") == dict(width=1920, height=1080),
              "selections: the params fix carries its resolution")
        no_ws = recommended_selections(1920, 1080, include_params=False)
        check(all(not sl_patch.REGISTRY[i].needs_params for i, _p in no_ws),
              "selections: include_params=False drops the fixes that need params")
        check("1920x1080" in describe_selections(sel), "describe: names the resolution")
        check(describe_selections([]) == "(no fixes selected)", "describe: empty case is explicit")

        # a fix added to the registry must reach the pipelines with no edit here
        extra = sl_patch.PatchDefinition(
            id="zz-synthetic", summary="test-only", sites=[], build=None,
            verify_state=lambda pe, d: "stock", label="SYNTH")
        sl_patch.REGISTRY[extra.id] = extra
        try:
            check(extra.id in [i for i, _p in recommended_selections(800, 600)],
                  "registry: a new PatchDefinition reaches the pipelines automatically")
            check(sl_patch.ordered_fixes()[-1].id == extra.id,
                  "registry: an id outside CANONICAL_ORDER sorts last, and is not dropped")
            check(extra.label == "SYNTH" and extra.caption == "test-only",
                  "registry: label given, caption defaults to the summary")
        finally:
            del sl_patch.REGISTRY[extra.id]

        auto = sl_patch.PatchDefinition(id="fix-thing", summary="s", sites=[], build=None,
                                        verify_state=lambda pe, d: "stock")
        check(auto.label == "THING", "registry: a label is derived from the id when omitted")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("slstudio_core self-test: %d checks, %d failed" % (ran[0], len(fails)))
    for f in fails:
        print("  FAILED: " + f)
    return 1 if fails else 0


# ========================================================================= CLI ==
def _cli(argv):
    if len(argv) >= 2 and argv[0] == "scan":
        inst = scan(argv[1])
        if "--json" in argv:
            print(json.dumps(inst.to_dict(), indent=2))
            return 0
        print("folder      : %s" % (inst.folder or "(none)"))
        print("exe         : %s" % (inst.exe or "(absent)"))
        print("kind        : %s" % inst.exe_kind)
        print("  evidence  : %s" % inst.exe_evidence)
        for fid, (state, desc) in inst.patches.items():
            print("  %-14s %-8s %s" % (fid, state, desc))
        if inst.manifest:
            print("manifest    : %s%s" % (
                "sha matches" if inst.manifest_sha_ok else "sha differs",
                "  (STALE - retire it)" if inst.manifest_is_stale() else ""))
        print("shim        : %s%s" % (inst.shim, " (+backup)" if inst.shim_backup else ""))
        print("logos       : %d present, %d blanked"
              % (len(inst.logos_present), len(inst.logos_blanked)))
        print("resource.hog: %s" % (inst.resource_hog or "(absent)"))
        for k in ("ship", "gun", "missile"):
            print("  %-8s  %s" % (k, inst.stats.get(k) or "(absent)"))
        print("missions    : %d loose .dte" % len(inst.missions_loose))
        print("backups     : %s" % (", ".join(b for b, _t in inst.backups) or "(none)"))
        print("writable    : %s%s" % (inst.writable,
                                      "  [under Program Files]" if inst.under_program_files else ""))
        return 0
    if argv and argv[0] == "selftest":
        return selftest()
    print(__doc__.strip().splitlines()[0])
    print("usage: slstudio_core.py scan <game folder> [--json]")
    print("       slstudio_core.py selftest")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
