#!/usr/bin/env python3
r"""
map_engine.py - cluster a Ghidra decompiled-C dump into engine subsystems.

Two signals:
  1. EVIDENCE (high confidence): each function's referenced string literals
     (Ghidra inlines them as  s_<sanitized text>_<addr> ) + distinctive imported
     APIs -> keyword rules -> subsystem tag(s).
  2. CALL-GRAPH (inferred): parse FUN_xxxx calls to build caller->callee edges,
     then propagate a subsystem's ownership down into the untagged helper
     functions it dominates (multi-subsystem callers are down-weighted). This
     attributes the large mass of math/glue/leaf helpers that carry no strings.

Emits a Markdown report. ORIGINAL ANALYSIS tooling - prints addresses + inferred
purpose + recovered string evidence; does NOT copy the game's source.

Usage:  python map_engine.py [--exports DIR] [--bin NAME] [--out FILE]
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

FUNC_HDR = re.compile(r"/\* ==== ([0-9a-fA-F]{6,8})\s+(\w+) ==== \*/")
STR_SYM  = re.compile(r"\b[su]_([A-Za-z0-9_]{2,}?)_[0-9a-f]{6,8}\b")
CALL_REF = re.compile(r"\bFUN_([0-9a-f]{6,8})\b")
IMPORT_HINTS = [
    "AIL_", "Bink", "DirectInputCreate", "DirectInput", "DirectDrawCreate",
    "DirectDraw", "DirectSoundCreate", "timeGetTime", "midiOut", "waveOut",
    "DirectPlay", "WSAStartup", "socket", "recvfrom", "sendto", "connect",
    "CoCreateInstance", "QueryPerformanceCounter",
]
SUBSYSTEMS = [
    ("Renderer (DirectDraw / Direct3D 7)", [
        "ddraw", "d3d", "direct3d", "directdraw", "dderr", "d3derr", "viewport",
        "surface", "blit", "gamma", "srddraw", "vfx_", "backbuffer", "back buffer",
        "z-buffer", "zbuffer", "texture", "palette", "render", "raster", "bitdepth",
        "bit depth", "flip", "lockrect", "mip", "fog ", "vertex", " ccb", "colorcube",
    ]),
    ("Audio (Miles / mss32)", [
        "ail_", "mss32", ".fat", "redbook", "cd audio", "cdaudio", "music",
        "sound", "sample", "voice", "audio", ".wav", "midi", "volume", "3d sound",
        "hogsnd", "eax",
    ]),
    ("Video (Bink)", ["bink", ".bik", "smacker", "movie", "cutscene", "fmv"]),
    ("Input (DirectInput)", [
        "dinput", "directinput", "joystick", "keyboard", "mouse", "joy_",
        "deadzone", "dead zone", "rudder", "hotas", "keyconfig", "joyconfig",
        "forcefeedback", "hatenable", "twistenable", " frc",
    ]),
    ("Assets / HOG / Models", [
        "bigf", ".hog", ".shp", ".spr", ".tga", "resource", "texture file",
        "lod", "mipmap", " mesh", " bmo", ".fnt", "load file", "fileopen",
        "object file", "preload", "uslf",
    ]),
    ("Mission / AI / Scripting (.DTE)", [
        ".dte", "mission", "ai_", "sync point", "syncpoint", "flight group",
        "flightgroup", "wingman", "wingmen", "objective", "trigger", "waypoint",
        "squadron", "nav point", "navpoint", "patrol", "spawn", "ioncannonai",
        "tt_", "globals", "sequencesync",
    ]),
    ("HUD / UI / Menu", [
        "hud", "menu", "interface", "mfd", "reticle", "cockpit", "dialog",
        "cursor", "scoreboard", "radar", "crosshair", "panel", "pnl", "btn",
        "tooltip", "loadout", "scockpit",
    ]),
    ("Ship / Physics / Combat", [
        "ship", "shield", "armor", "weapon", "missile", "thrust", "afterburner",
        "torpedo", "turret", "hardpoint", "throttle", "collision", "damage",
        "explode", "explosion", "countermeasure", "cannon", "laser", "capital",
        "chaff", "lockring", "jumpgate", "wgate",
    ]),
    ("Networking / Multiplayer", [
        "dplay", "directplay", "dperr", "dpsys", "winsock", "wsock", "socket",
        "multiplayer", "session", "lobby", "netgame", "deathmatch", "dpbits",
        "dpsession", "zone",
    ]),
    ("Save / Config / Profile", [
        "save", "pilot", "profile", ".iff", "config", "settings", "registry",
        ".ini", "options", "difficulty", "mygame", ".fm8", "gameflow", "dmodes",
    ]),
    ("System / CRT / Memory", [
        "srmemory", "heap", "virtualalloc", "exception", "_cinit", "getversion",
        "tls", "assert", "out of memory", "fatal", "dbout", "debug assertion",
    ]),
]
SUBNAMES = [s for s, _ in SUBSYSTEMS]


def split_functions(text):
    matches = list(FUNC_HDR.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield m.group(1).lower(), m.group(2), text[start:end]


def recover_strings(body):
    out = []
    for m in STR_SYM.finditer(body):
        s = m.group(1).replace("_", " ").strip()
        if len(s) >= 3 and not s.isdigit():
            out.append(s)
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    proj = os.path.dirname(here)
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", default=os.path.join(proj, "analysis", "exports"))
    ap.add_argument("--bin", default="LANCER_decrypted.exe")
    ap.add_argument("--out", default=os.path.join(proj, "analysis", "engine_map_report.md"))
    ap.add_argument("--rounds", type=int, default=8)
    args = ap.parse_args()

    dc = os.path.join(args.exports, args.bin + ".decompiled.c")
    fc = os.path.join(args.exports, args.bin + ".functions.csv")
    if not os.path.exists(dc):
        sys.exit(f"missing {dc}")
    sizes = {}
    if os.path.exists(fc):
        with open(fc, newline="") as f:
            for row in csv.DictReader(f):
                sizes[row["entry"].lower()] = int(row["size"])

    with open(dc, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    funcs = {}
    callees = {}
    for addr, name, body in split_functions(text):
        strs = recover_strings(body)
        imps = [h for h in IMPORT_HINTS if h.lower() in body.lower()]
        evidence = " ".join(strs).lower() + " " + " ".join(imps).lower()
        etags = [s for s, kws in SUBSYSTEMS if any(k in evidence for k in kws)]
        funcs[addr] = {"addr": addr, "size": sizes.get(addr, 0), "strs": strs,
                       "imps": imps, "etags": etags}
        callees[addr] = set(m.group(1) for m in CALL_REF.finditer(body)) - {addr}

    callers = defaultdict(set)
    for a, cs in callees.items():
        for c in cs:
            if c in funcs:
                callers[c].add(a)

    # tag state: evidence first, then propagate inferred down the call graph
    tags = {a: set(f["etags"]) for a, f in funcs.items()}
    origin = {a: ("evidence" if f["etags"] else "") for a, f in funcs.items()}
    for _ in range(args.rounds):
        changed = 0
        for a, f in funcs.items():
            if tags[a]:
                continue
            score = Counter()
            for c in callers[a]:
                ct = tags.get(c)
                if ct:
                    w = 1.0 / len(ct)            # down-weight multi-subsystem callers
                    for t in ct:
                        score[t] += w
            if score:
                top, n = score.most_common(1)[0]
                if n / sum(score.values()) >= 0.6:
                    tags[a] = {top}
                    origin[a] = "inferred"
                    changed += 1
        if not changed:
            break

    ev_by = defaultdict(list)
    inf_by = defaultdict(list)
    for a, f in funcs.items():
        for t in f["etags"]:
            ev_by[t].append(f)
        if origin[a] == "inferred":
            inf_by[next(iter(tags[a]))].append(f)
    n_ev = sum(1 for a in funcs if origin[a] == "evidence")
    n_inf = sum(1 for a in funcs if origin[a] == "inferred")
    n_un = len(funcs) - n_ev - n_inf
    edges = sum(len(c & funcs.keys()) for c in callees.values())

    L = []
    L.append("# Starlancer engine map (auto-clustered + call-graph attributed)\n")
    L.append(f"Source: `{args.bin}` — {len(funcs)} functions, "
             f"{sum(f['size'] for f in funcs.values()):,} code bytes, "
             f"{edges:,} intra-image call edges.\n")
    L.append(f"Coverage: **{n_ev}** evidence-tagged (strings/APIs), "
             f"**{n_inf}** call-graph-attributed, "
             f"**{n_un}** unclassified (shared leaf/util).\n")
    L.append("## Subsystem summary\n")
    L.append("| Subsystem | Evidence funcs | +Inferred | Evidence code bytes |")
    L.append("|---|---:|---:|---:|")
    for s in SUBNAMES:
        ev = ev_by.get(s, [])
        L.append(f"| {s} | {len(ev)} | {len(inf_by.get(s, []))} | "
                 f"{sum(f['size'] for f in ev):,} |")
    L.append("")
    for s in SUBNAMES:
        ev = sorted(ev_by.get(s, []), key=lambda f: -f["size"])
        if not ev:
            continue
        inf = inf_by.get(s, [])
        L.append(f"## {s}  ({len(ev)} evidence + {len(inf)} inferred)\n")
        for f in ev[:30]:
            txt = "; ".join(dict.fromkeys(f["strs"]))[:170]
            imp = (" | imports: " + ", ".join(f["imps"])) if f["imps"] else ""
            L.append(f"- `0x{f['addr']}` ({f['size']}b) — {txt}{imp}")
        if len(ev) > 30:
            L.append(f"- … +{len(ev) - 30} more evidence funcs")
        L.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"[map] {len(funcs)} funcs | evidence={n_ev} inferred={n_inf} "
          f"unclassified={n_un} | edges={edges} -> {args.out}")
    for s in SUBNAMES:
        print(f"    ev {len(ev_by.get(s, [])):4d}  +inf {len(inf_by.get(s, [])):4d}   {s}")


if __name__ == "__main__":
    main()
