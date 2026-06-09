#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Starlancer ``.DTE`` mission reference + inspector  (READ-ONLY, static).

A ``.DTE`` is a per-mission **data + script container**, interpreted by an in-engine
trigger/event VM. It is never executed as native code, so everything here is pure
data inspection.

This module is the machine-readable companion to ``docs/dte-format.md`` and
``docs/dte-scripting-reference.md``. It fuses two reverse-engineering sources:

* **Static RE of the decrypted exe** (ImageBase 0x400000): the trigger enum
  (``FUN_0045B330``), the command catalogue ``DAT_004F3AD0``, the bytecode VM
  ``FUN_0045C980`` over the 256-entry table ``DAT_004F6350``, and the per-command
  implementation addresses + parameter counts.
* **Black-box RE by Captain Foster / "Starlancer ME"** (starlancerme.blogspot.com):
  the numeric opcode/command indices, the AI-code table, the ship/pilot ID tables,
  and the observed in-game semantics.

Container caveat: the exact on-disk descriptor framing of the *HOG-extracted* mission
blobs is not fully decoded (see docs); this tool therefore inspects/validates rather
than fully unpacks. The semantic tables below are verified and authoritative.

Usage:
  dte_parse.py ref [triggers|exec|ai|stream]   # print a reference table
  dte_parse.py inspect <mission.dte>           # size / histogram / strings / markers
  dte_parse.py sweep <dir>                      # consistency report over many .dte
"""
import argparse
import os
import re
import struct
import sys
from collections import Counter

# --------------------------------------------------------------------------- #
#  Trigger-condition enum (TT_*)  -- VERIFIED from FUN_0045B330 string array,  #
#  and identical to the Starlancer ME "Triggers" page (0x00..0x20).            #
#  33 scriptable conditions; the condition-descriptor table DAT_0052952C has   #
#  35 entries (_DAT_00525F8C = 0x23) -- the 2 extra are internal/non-script.   #
# --------------------------------------------------------------------------- #
TT_TRIGGERS = [
    "TT_SHOTAT", "TT_DESTROYED", "TT_LAUNCHED", "TT_CAMERAREACHED", "TT_SHIPREACHED",
    "TT_PROXIMITY_CLOSE", "TT_PROXIMITY_GENERAL", "TT_OBJECT_SCOOPED",
    "TT_PLAYER_READY_TO_JUMP", "TT_JUMPED_IN", "TT_FG_JUMPED_IN", "TT_PLAYER_READY_TO_WARP",
    "TT_JUMPED_THROUGH_HOOP", "TT_PLAYER_WANTS_BACKUP", "TT_RIPPER_GRABBED_OBJECT",
    "TT_RIPPER_DROPPED_OBJECT", "TT_CLOAKED", "TT_DECLOAKED", "TT_TARGETTED",
    "TT_PLAYER_L1_DOUBLETAP", "TT_PLAYER_L2_DOUBLETAP", "TT_PLAYER_R1_DOUBLETAP",
    "TT_PLAYER_R2_DOUBLETAP", "TT_PLAYER_L1_L2_R1_R2_PRESSED", "TT_PLAYER_L1_R1_PRESSED",
    "TT_GAME_TIMER_EXPIRED", "TT_TRACTOR_BEAM_LOCKED", "TT_TRACTOR_BEAM_BROKEN",
    "TT_INSIDE_OBJECT", "TT_OUTSIDE_OBJECT", "TT_DOCKED", "TT_UNDOCKED", "TT_BEING_CHASED",
]

# --------------------------------------------------------------------------- #
#  Executor command table (script opcode 0x21 <index>).                        #
#  Index + name: Starlancer ME "Executor AI Codes" page (empirically validated #
#  in-game). impl address + param count: our decompilation command catalogue   #
#  DAT_004F3AD0 (matched by name). A handful the blog lists that look like      #
#  operand labels rather than commands are kept verbatim and flagged in docs.   #
# --------------------------------------------------------------------------- #
# index -> blog name
EXEC_BLOG = {
    0x00: "PrintShipName", 0x01: "CreateTimer", 0x02: "DestroyTimer", 0x03: "CreateFlightGroup",
    0x04: "DestroyFlightGroup", 0x05: "WaitNSeconds", 0x06: "PlaySpeech", 0x07: "WaitForSpeech",
    0x08: "PlayCommsMovie", 0x09: "WaitForMovie", 0x0A: "PrintDebugMessage", 0x0B: "SetAI",
    0x0C: "ClearAI", 0x0D: "SetPatrolRoute", 0x0E: "SetPilot", 0x0F: "SetTriggerState",
    0x10: "StartDirectorCam", 0x11: "StartShipAnimation", 0x12: "ShipFollowCurve",
    0x13: "SetupLaunch", 0x14: "StartLaunch", 0x15: "DisplaySubTitle", 0x16: "GTextPilotDefine",
    0x17: "ResetCodePriority", 0x18: "InterruptTriggerCode", 0x19: "CommsFromShip",
    0x1A: "SetInvulnerability", 0x1B: "MovingShipFollowCurve", 0x1C: "DisableObject",
    0x1D: "PositionRelative", 0x1E: "WhenPlayerLastJumped", 0x1F: "StartMissileCam",
    0x20: "StartChaseCam", 0x21: "SetPlayerTarget", 0x22: "SetTargetable", 0x23: "PlayMusic",
    0x24: "StopDirectorCam", 0x25: "SetActionCentre", 0x26: "RadiusOfSphere", 0x27: "ShipToDock",
    0x28: "DisableTaunts", 0x29: "ShipPointToFlyTo", 0x2A: "CommsFromShipOnce", 0x2B: "DisableLights",
    0x2C: "SetEnvironmentFX", 0x2D: "MultiPlayerSync", 0x2E: "DisableGenericComms", 0x2F: "DisableGuns",
    0x30: "SetNavPoint", 0x31: "SetEscortPoint", 0x32: "ResetAfterBurners", 0x33: "DisableMissiles",
    0x34: "DisableEngines", 0x35: "DisableEject", 0x36: "SetHostile", 0x37: "ResetToSpawnPositions",
    0x38: "UpdateEnvironmentFXState", 0x39: "SetPrimaryTarget", 0x3A: "WaitForJumpOrLaunch",
    0x3B: "DoNotDisturb", 0x3C: "SetEnvironmentFXNebula", 0x3D: "StartShipAnimationReverse",
    0x3E: "SnapToPoint", 0x3F: "PlayFostersLastStand", 0x40: "OpenInstrument", 0x41: "CloseInstrument",
    0x42: "DestroySubObject", 0x43: "SetObjective", 0x44: "SetRescueProbabilities",
    0x45: "IsShipThisPlayer", 0x46: "SetFlybackMarker", 0x47: "ResetFlybackMarker",
    0x48: "StopShipAnimation", 0x49: "SetShipAvoidance", 0x4A: "MatchSpeed", 0x4B: "MovingShipBackupCurve",
    0x4C: "WaitForKey", 0x4D: "TerminateMission", 0x4E: "TurretSetTarget", 0x4F: "SetAnyTriggerState",
    0x50: "WaitForDirectorCam", 0x51: "KillAllScriptExecutionExceptMe", 0x52: "StackDirectorCam",
    0x53: "Scanner", 0x54: "ReplaceSubObject", 0x55: "Fire", 0x56: "MultiplayerScriptSync",
    0x57: "FriendlyFire", 0x58: "EntityToCloak", 0x59: "ReplenishWeapons", 0x5A: "WillsBlag",
    0x5B: "ShowHudIcon", 0x5C: "DisableListing", 0x5D: "DisableObjectAtNextJump",
    0x5E: "DarrensNaughtyBlag", 0x5F: "Test_AI_Function",
}
# name -> (param_count, impl VA)  from our decompiled catalogue DAT_004F3AD0
EXEC_IMPL = {
    "PrintShipName": (2, 0x00458AB0), "CreateTimer": (4, 0x0045D210), "DestroyTimer": (1, 0x0045D290),
    "CreateFlightGroup": (1, 0x00457C40), "DestroyFlightGroup": (1, 0x00457FD0),
    "PlaySpeech": (1, 0x00458090), "WaitForSpeech": (0, 0x00458100), "PlayCommsMovie": (3, 0x00458120),
    "WaitForMovie": (0, 0x00458180), "PrintDebugMessage": (1, 0x004581A0), "SetAI": (4, 0x004581F0),
    "ClearAI": (1, 0x004588C0), "SetPatrolRoute": (2, 0x00458860), "SetPilot": (2, 0x00458830),
    "SetTriggerState": (3, 0x0045D300), "StartDirectorCam": (5, 0x004582E0),
    "StartShipAnimation": (2, 0x00458720), "ShipFollowCurve": (3, 0x004585D0), "SetupLaunch": (3, 0x00458970),
    "StartLaunch": (1, 0x00458A40), "DisplaySubTitle": (1, 0x00458A80), "ResetCodePriority": (1, 0x00458A90),
    "InterruptTriggerCode": (0, 0x0045D450), "CommsFromShip": (3, 0x00458AC0),
    "SetInvulnerability": (2, 0x00458BC0), "MovingShipFollowCurve": (4, 0x004585A0),
    "DisableObject": (2, 0x004583C0), "PositionRelative": (2, 0x004584D0), "WhenPlayerLastJumped": (0, 0x00458580),
    "StartMissileCam": (1, 0x00458B60), "StartChaseCam": (1, 0x00458B80), "SetPlayerTarget": (2, 0x00458C80),
    "SetTargetable": (2, 0x00458D50), "PlayMusic": (2, 0x00458DF0), "StopDirectorCam": (0, 0x00458E30),
    "SetActionCentre": (2, 0x00458E60), "DisableTaunts": (1, 0x00458F40), "CommsFromShipOnce": (3, 0x00458FD0),
    "DisableLights": (2, 0x00459070), "SetEnvironmentFX": (2, 0x00459170), "MultiPlayerSync": (0, 0x004591E0),
    "DisableGenericComms": (1, 0x004591F0), "DisableGuns": (2, 0x00459200), "SetNavPoint": (2, 0x00459270),
    "SetEscortPoint": (2, 0x004592F0), "ResetAfterBurners": (0, 0x004594C0), "DisableMissiles": (2, 0x00459370),
    "DisableEngines": (2, 0x004593E0), "DisableEject": (2, 0x00459450), "SetHostile": (2, 0x004594F0),
    "ResetToSpawnPositions": (0, 0x004591B0), "UpdateEnvironmentFXState": (0, 0x004591A0),
    "SetPrimaryTarget": (1, 0x00459550), "WaitForJumpOrLaunch": (1, 0x004595A0), "DoNotDisturb": (2, 0x00459640),
    "SetEnvironmentFXNebula": (1, 0x00459190), "StartShipAnimationReverse": (2, 0x004587D0),
    "SnapToPoint": (2, 0x004596A0), "PlayFostersLastStand": (0, 0x00459740), "OpenInstrument": (1, 0x0045D9D0),
    "CloseInstrument": (1, 0x0045DA30), "DestroySubObject": (2, 0x00459750), "SetObjective": (2, 0x00459870),
    "SetRescueProbabilities": (3, 0x004598D0), "IsShipThisPlayer": (1, 0x004598F0),
    "SetFlybackMarker": (2, 0x00459910), "ResetFlybackMarker": (0, 0x004599E0), "StopShipAnimation": (2, 0x00458770),
    "SetShipAvoidance": (2, 0x00459A30), "MatchSpeed": (2, 0x00459A90), "MovingShipBackupCurve": (4, 0x00458670),
    "WaitForKey": (1, 0x00459AE0), "TerminateMission": (0, 0x00459BB0), "TurretSetTarget": (2, 0x00459BD0),
    "SetAnyTriggerState": (4, 0x0045D3A0), "WaitForDirectorCam": (0, 0x00459C90),
    "KillAllScriptExecutionExceptMe": (0, 0x0045D990), "StackDirectorCam": (5, 0x00458300),
    "Scanner": (1, 0x00459CB0), "ReplaceSubObject": (2, 0x00459CF0), "Fire": (2, 0x00459DD0),
    "MultiplayerScriptSync": (1, 0x00459DF0), "FriendlyFire": (0, 0x00459F30), "ReplenishWeapons": (1, 0x00459FA0),
    "WillsBlag": (1, 0x0045A1C0), "ShowHudIcon": (2, 0x0045A1F0), "DisableListing": (2, 0x0045A210),
    "DisableObjectAtNextJump": (2, 0x0045A250), "DarrensNaughtyBlag": (2, 0x0045A290),
    "Test_AI_Function": (2, None),
    # blog names with no separately-confirmed catalogue match (operand-ish / unmatched):
    "CommsFromPilot": (3, 0x00458B10), "CommsFromPilotOnce": (3, 0x00459020),
}

# AI behaviour codes (script opcode 0x32 <index>)  -- Starlancer ME "AI Codes" page.
AI_CODES = {
    0x00: "Do Nothing", 0x01: "Fly Aimlessly", 0x02: "Launch Missile", 0x03: "Launch Missile",
    0x04: "Warp In", 0x05: "Warp Out", 0x06: "Fly", 0x07: "Run Away", 0x08: "Land", 0x09: "Escort",
    0x0A: "Find New Target", 0x0B: "Explode", 0x0C: "Ripper grabs target object", 0x0D: "Object Attach",
    0x0E: "Formation Regroup", 0x0F: "Patrol Route", 0x10: "Toggle Cloak", 0x11: "Ship Follow Curve",
    0x12: "Slow Rotate", 0x13: "Jump In", 0x14: "Jump Out", 0x15: "Find Scoop Up",
    0x16: "Random Spin Slow", 0x17: "Random Spin Med", 0x18: "Random Spin Fast",
    0x19: "Fixed Gate Jump In", 0x1A: "Fixed Gate Jump Out", 0x1B: "Formation",
    0x1C: "Fixed Gate Open", 0x1D: "Fixed Gate Close", 0x1E: "Eject", 0x1F: "Fixed Gate Collapse",
    0x20: "Match Speed", 0x21: "Dark Reign shoot", 0x22: "Move to spawn pos", 0x23: "Turn object lights on",
    0x24: "Boridin breakaway", 0x25: "FAIL", 0x26: "Rotate Boridin breakaway warp projector",
    0x27: "Make ripper drop carried object", 0x28: "Jump In", 0x29: "Jump Out", 0x2A: "(unknown)",
    0x2B: "Huge explosion", 0x2C: "Zero velocity + rotation", 0x2D: "Fly ship backwards",
    0x2E: "Player Control", 0x2F: "Multiplayer Control", 0x30: "Avoid Target", 0x31: "Torpedo",
    0x32: "Launch", 0x33: "Fight", 0x34: "Destroy itself", 0x35: "Scoop Up", 0x36: "Eject Spin",
    0x37: "Dock", 0x38: "Dark reign shoot", 0x39: "Ripper end drop object",
    0x3A: "Ripper attach cargo pod to Mammoth", 0x3B: "Eject fighter attack", 0x3C: "Disrupted",
    0x3D: "Make capship list left", 0x3E: "Make capship list right", 0x3F: "Friendly Fire",
    0x40: "Eject Player", 0x41: "Ship Follow Curve Backwards", 0x42: "Mill",
    0x43: "Deathmatch Respawn Effect", 0x44: "Deathmatch Dark Reign target",
}

# Script-stream control opcodes (the bytes that frame the action stream) and the
# condition-expression micro-ops, fused from the blog's observations + our VM.
STREAM_OPS = [
    ("0x21 <i>", "Call Executor command #i (consumes that command's params)", "command call"),
    ("0x32 <i>", "Set AI behaviour code #i on the current entity", "AI code"),
    ("0x2A <n>", "Play speech: n = speech index (our copies); inline .ut name in blog's copies", "speech"),
    ("0x2C <o>", "Single-object reference (one ship/entity)", "operand"),
    ("0x2D <g>", "Flight-group reference", "operand"),
    ("0x22 <p>", "Section/part marker (22 00..22 1F): start of script 'part' p", "part"),
    ("0x4D <p>", "Jump/branch into part p", "part jump"),
    ("0x43", "Code/line end marker", "end"),
    ("0x27 <i>", "Read global variable[i].value onto the stack (read-mem)", "expr"),
    ("0x40 <i>", "Push address of global[i].value (write-mem lvalue)", "expr"),
    ("0x3F <i>", "Push address of array slot[i] (lvalue); land-loop branch in context", "expr"),
    ("0x23/0x24", "Push 16-bit immediate", "expr"),
    ("0x28 <n>", "Wait / operand fetch (compare context)", "expr"),
    ("0x02 / 0x03", "Compare: != / ==", "expr"),
    ("0x14", "Squad / condition membership test", "expr"),
]


def merged_exec():
    """Yield (index, name, param_count, impl_va, matched) over 0x00..0x5F."""
    for i in range(0x60):
        name = EXEC_BLOG.get(i, "?")
        pc, va = EXEC_IMPL.get(name, (None, None))
        yield i, name, pc, va, name in EXEC_IMPL


def cmd_ref(args):
    what = args.table
    if what in ("triggers", "all"):
        print("# Trigger conditions (TT_*) -- script value at trigger-record +0x15")
        for i, t in enumerate(TT_TRIGGERS):
            print("  0x%02X  %s" % (i, t))
        print()
    if what in ("exec", "all"):
        print("# Executor commands (script opcode 0x21 <index>)")
        print("  idx  name                              params  impl")
        for i, name, pc, va, ok in merged_exec():
            print("  0x%02X  %-32s  %s     %s" % (
                i, name, ("%d" % pc) if pc is not None else "?",
                ("0x%08X" % va) if va else ("--" if ok else "(blog only)")))
        print()
    if what in ("ai", "all"):
        print("# AI behaviour codes (script opcode 0x32 <index>)")
        for i in range(max(AI_CODES) + 1):
            print("  0x%02X  %s" % (i, AI_CODES.get(i, "?")))
        print()
    if what in ("stream", "all"):
        print("# Script-stream / expression opcodes")
        for op, desc, kind in STREAM_OPS:
            print("  %-12s %-10s %s" % (op, "[%s]" % kind, desc))
        print()


def tokens(data, lo=3):
    return [(m.start(), m.group().decode("latin-1"))
            for m in re.finditer(("[\\x20-\\x7e]{%d,}" % lo).encode(), data)]


def cmd_inspect(args):
    data = open(args.file, "rb").read()
    n = len(data)
    c = Counter(data)
    printable = sum(1 for b in data if 32 <= b < 127)
    print("%s  %d bytes (0x%X)  printable=%.0f%%" % (os.path.basename(args.file), n, n, 100 * printable / n))
    print("top bytes:", ", ".join("%02x:%d" % (b, k) for b, k in c.most_common(8)))
    toks = tokens(data, 4)
    ships = [s for _, s in toks if re.match(r"[a-z]{2,}_[a-z]", s) or "(" in s]
    print("ASCII runs(>=4): %d   ship/object-name-like: %d" % (len(toks), len(ships)))
    for needle in (b".ut", b".shp", b".fm8", b"Proximity", b"ShipReached", b"WIN", b"SUCCESS"):
        k = len(re.findall(re.escape(needle), data))
        if k:
            print("  %-12r x%d" % (needle.decode(), k))
    if args.strings:
        for off, s in toks[:args.strings]:
            print("  0x%05x  %s" % (off, s))


def cmd_sweep(args):
    files = sorted(f for f in os.listdir(args.dir) if f.lower().endswith(".dte"))
    print("sweeping %d .dte in %s\n" % (len(files), args.dir))
    print("  %-16s %8s %6s %6s %6s %5s" % ("file", "bytes", "print%", "names", ".ut", "trig"))
    tot = Counter()
    for f in files:
        data = open(os.path.join(args.dir, f), "rb").read()
        n = len(data)
        printable = 100 * sum(1 for b in data if 32 <= b < 127) / n
        toks = tokens(data, 4)
        names = sum(1 for _, s in toks if re.match(r"[a-z]{2,}_[a-z]", s))
        uts = len(re.findall(rb"\.ut", data))
        trig = len(re.findall(rb"Proximity|ShipReached|ARRIVES|GrabbedObject", data))
        tot["bytes"] += n
        print("  %-16s %8d %5.0f%% %6d %6d %5d" % (f, n, printable, names, uts, trig))
    print("\n%d files, %d bytes total" % (len(files), tot["bytes"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer .DTE reference + inspector (read-only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ref"); p.add_argument("table", nargs="?", default="all",
                                              choices=["all", "triggers", "exec", "ai", "stream"])
    p.set_defaults(func=cmd_ref)
    p = sub.add_parser("inspect"); p.add_argument("file"); p.add_argument("--strings", type=int, default=0)
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("sweep"); p.add_argument("dir")
    p.set_defaults(func=cmd_sweep)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
