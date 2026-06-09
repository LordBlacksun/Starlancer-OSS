#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Starlancer ``.DTE`` mission decoder + reference  (READ-ONLY, static).

A ``.DTE`` is a per-mission **data + script container**, interpreted by an in-engine
trigger/event VM. It is never executed as native code, so everything here is pure
data inspection.

On-disk container (fully decoded -- see ``docs/dte-format.md``):

* The HOG-stored ``.dte`` is **RefPack / EA "QFS" compressed** (signature ``10 FB``,
  3-byte big-endian uncompressed size).  The engine reads it (``FUN_0045A300`` ->
  ``FUN_004C5BE0`` HOG read, no extra transform) and the RefPack stream expands into a
  fixed image (~0xCFBE7 bytes for the main campaign template).
* The decompressed image opens with a **27-entry, 8-byte directory** at offset 0:
  each entry is ``{u16 count, byte reloc-flags @ bits 24-27, u32 offset}`` and the
  offset is absolute within the image (``0xFFFF`` = empty-section sentinel).  This is
  the table walked by ``FUN_00451D90`` / ``FUN_00452A20`` (27 sequential reads).
* The section offsets match Captain Foster / "Starlancer ME"'s black-box anchors
  exactly (objects ``0x30FF7``, events ``0x47BF7``, target-list ``0x57BF7`` ...), so
  the blog's numbers are positions in *this* decompressed image -- independent
  cross-validation of both efforts.

The semantic tables (trigger enum, Executor commands, AI codes, stream opcodes) fuse:

* **Static RE of the decrypted exe** (ImageBase 0x400000): the trigger enum
  (``FUN_0045B330``), the command catalogue ``DAT_004F3AD0``, the bytecode VM
  ``FUN_0045C980`` over the 256-entry table ``DAT_004F6350``, per-command impl
  addresses + parameter counts, and the loader's section order (``FUN_00451D90``).
* **Black-box RE by Captain Foster / "Starlancer ME"** (starlancerme.blogspot.com):
  the numeric opcode/command indices, the AI-code table, the ship/pilot ID tables,
  and the observed in-game semantics.

Usage:
  dte_parse.py ref [triggers|exec|ai|stream]   # print a reference table
  dte_parse.py decode <mission.dte> [--limit N] [--section NAME]   # full decode
  dte_parse.py inspect <mission.dte>           # raw (compressed) quick look
  dte_parse.py sweep <dir>                      # decode + validate every .dte
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

# --------------------------------------------------------------------------- #
#  Container layer -- RefPack/QFS decompression + the 27-section directory.    #
# --------------------------------------------------------------------------- #
# Decompressed-image section order, from the 27 sequential FUN_00452A20 reads in
# the loader FUN_00451D90 (the global each entry fills, + the role where known).
# "stride"/"kind" drive the record decoders; None = not record-decoded yet.
SECTIONS = [
    ("string_pool",      "DAT_00525FA8", "strings"),   # 0  -- name/text pool
    ("section1",         "DAT_00525F3C", None),         # 1  -- large aux table (open)
    ("globals",          "DAT_005294F8", "globals"),    # 2  -- script global variables
    ("ships",            "DAT_0052951C", "ships"),      # 3  -- flight-group/ship array, stride 0x4C
    ("fg_triggers",      "DAT_005267CC", "fg"),         # 4  -- per-FG table, stride 0x14 (blog: "FG triggers")
    ("triggers",         "DAT_005294E0", "triggers"),   # 5  -- scriptable triggers, stride 0x30 (blog: "fighter triggers")
    ("script",           "DAT_00525F88", "script"),     # 6  -- bytecode stream (count = #bytes)
    ("ship_trig_index",  "DAT_005267C0", None),         # 7
    ("launch_object",    "DAT_005267D0", None),         # 8
    ("section9",         "DAT_005256C8", None),         # 9
    ("script_yieldflags","DAT_005294D8", None),         # 10 -- per-byte yield flags (count = #script bytes)
    ("section11",        "PTR_DAT_004EF2FC", None),     # 11
    ("section12",        "DAT_005294FC", None),         # 12
    ("squad",            "DAT_00529500", None),         # 13
    ("section14",        "DAT_00525F18", None),         # 14
    ("section15",        "DAT_005256B8", None),         # 15
    ("section16",        "DAT_00525FB0", None),         # 16
    ("section17",        "DAT_005294EC", None),         # 17
    ("section18",        "DAT_00525FB4", None),         # 18
    ("section19",        "DAT_0052950C", None),         # 19
    ("section20",        "DAT_00525FA0", None),         # 20
    ("section21",        "(local)",      None),         # 21
    ("section22",        "DAT_00525278", None),         # 22
    ("section23",        "PTR_DAT_004EE7D8", None),     # 23
    ("section24",        "DAT_00525F9C", None),         # 24
    ("section25",        "DAT_00525F90", None),         # 25
    ("section26",        "DAT_0052570C", None),         # 26
]
EMPTY_OFF = 0xFFFF  # directory sentinel for an unused section


class DTEError(Exception):
    pass


def refpack_decompress(data):
    """Decompress an EA RefPack / "QFS" stream (the .dte container codec).

    Header: byte0 = flags, byte1 = 0xFB; uncompressed size is 3 bytes big-endian
    (4 if flags & 0x80); an optional compressed-size field precedes it if flags & 0x01.
    Returns (declared_size, bytes).  Raises DTEError on a bad signature.
    """
    if len(data) < 6 or data[1] != 0xFB:
        raise DTEError("not a RefPack stream (sig %02X %02X)" % (data[0], data[1] if len(data) > 1 else 0))
    flags = data[0]
    i = 2
    if flags & 0x01:
        i += 4 if flags & 0x80 else 3          # skip compressed-size field
    if flags & 0x80:
        size = (data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3]; i += 4
    else:
        size = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]; i += 3
    out = bytearray()
    n = len(data)
    while i < n:
        ctrl = data[i]; i += 1
        if ctrl < 0x80:                         # 2-byte form
            a = data[i]; i += 1
            nproc = ctrl & 0x03
            out += data[i:i + nproc]; i += nproc
            ncopy = ((ctrl >> 2) & 0x07) + 3
            roff = ((ctrl & 0x60) << 3) + a + 1
            for _ in range(ncopy):
                out.append(out[-roff])
        elif ctrl < 0xC0:                       # 3-byte form
            a = data[i]; b = data[i + 1]; i += 2
            nproc = (a >> 6) & 0x03
            out += data[i:i + nproc]; i += nproc
            ncopy = (ctrl & 0x3F) + 4
            roff = ((a & 0x3F) << 8) + b + 1
            for _ in range(ncopy):
                out.append(out[-roff])
        elif ctrl < 0xE0:                       # 4-byte form
            a = data[i]; b = data[i + 1]; c = data[i + 2]; i += 3
            nproc = ctrl & 0x03
            out += data[i:i + nproc]; i += nproc
            ncopy = ((ctrl & 0x0C) << 6) + c + 5
            roff = ((ctrl & 0x10) << 12) + (a << 8) + b + 1
            for _ in range(ncopy):
                out.append(out[-roff])
        elif ctrl < 0xFC:                       # literal run (4..124, multiple of 4)
            nproc = ((ctrl & 0x1F) << 2) + 4
            out += data[i:i + nproc]; i += nproc
        else:                                   # 0xFC..0xFF: final 0..3 literals, end
            nproc = ctrl & 0x03
            out += data[i:i + nproc]; i += nproc
            break
    return size, bytes(out)


class Mission:
    """A decoded mission image (decompressed) + its 27-section directory."""

    def __init__(self, raw):
        self.declared, self.image = refpack_decompress(raw)
        if self.declared != len(self.image):
            raise DTEError("size mismatch: header %d, produced %d" % (self.declared, len(self.image)))
        m = self.image
        self.dir = []  # list of (count, offset, flags)
        for k in range(27):
            cf, off = struct.unpack_from("<II", m, k * 8)
            self.dir.append((cf & 0xFFFF, off, (cf >> 24) & 0x0F))
        self.reloc_flags = self.dir[0][2] if self.dir else 0

    def count(self, slot):
        return self.dir[slot][0]

    def offset(self, slot):
        return self.dir[slot][1]

    def present(self, slot):
        off = self.dir[slot][1]
        return off != EMPTY_OFF and off <= len(self.image)

    def string(self, rel):
        """Null-terminated string at string_pool + rel (rel = 0xFFFF -> '')."""
        if rel == 0xFFFF:
            return ""
        p = self.offset(0) + rel
        e = self.image.find(b"\0", p)
        return self.image[p:e if e >= 0 else None].decode("latin-1", "replace")

    # -- record decoders -------------------------------------------------- #
    def ships(self):
        base, n, m = self.offset(3), self.count(3), self.image
        for i in range(n):
            r = base + i * 0x4C
            rec = m[r:r + 0x4C]
            if len(rec) < 0x4C:
                break
            fg = struct.unpack_from("<H", rec, 0)[0]
            name = self.string(struct.unpack_from("<H", rec, 4)[0])
            pos = struct.unpack_from("<3f", rec, 8)
            yield {"i": i, "fg": fg, "name": name, "pos": pos,
                   "b14": rec[0x14], "iff": rec[0x15], "type": rec[0x18], "raw": rec}

    def fg_records(self):
        base, n, m = self.offset(4), self.count(4), self.image
        for i in range(n):
            r = base + i * 0x14
            rec = m[r:r + 0x14]
            if len(rec) < 0x14:
                break
            a, b, c, d = struct.unpack_from("<IIII", rec, 0)
            yield {"i": i, "id": a, "ref": b, "f8": c, "f12": d, "raw": rec}

    def triggers(self):
        base, n, m = self.offset(5), self.count(5), self.image
        for i in range(n):
            r = base + i * 0x30
            rec = m[r:r + 0x30]
            if len(rec) < 0x30:
                break
            yield {"i": i, "b0": rec[0], "b1": rec[1], "b2": rec[2],
                   "fields": struct.unpack_from("<8H", rec, 8), "raw": rec}


# --------------------------------------------------------------------------- #
#  Script-stream disassembler (linear; the action + condition opcodes).        #
# --------------------------------------------------------------------------- #
# operand byte-width per opcode (best-effort; unknown opcodes consume 0 operands)
_OPW = {0x21: 1, 0x32: 1, 0x22: 1, 0x4D: 1, 0x2A: 1, 0x2C: 1, 0x2D: 1,
        0x27: 1, 0x40: 1, 0x3F: 1, 0x28: 1, 0x23: 2, 0x24: 2,
        0x02: 0, 0x03: 0, 0x43: 0, 0x14: 0, 0x42: 1, 0x09: 0, 0x07: 0}


def disasm_script(mission, limit=120):
    """Yield human-readable lines for the script bytecode section (slot 6).

    The stream is a series of u16-length-prefixed blocks; within a block the bytes
    are action/condition opcodes.  This is a *linear* decode (operands consumed by
    width); 0x22 <p> part-markers delimit logical parts.
    """
    m = mission.image
    base = mission.offset(6)
    size = mission.count(6)
    end = base + size
    p = base
    emitted = 0
    block = 0
    while p + 2 <= end and emitted < limit:
        blen = struct.unpack_from("<H", m, p)[0]
        if blen == 0 or p + 2 + blen > end:
            break
        yield "  block %-3d @+0x%05X  len=%d" % (block, p - base, blen)
        q = p + 2
        bend = q + blen
        while q < bend and emitted < limit:
            op = m[q]; q += 1
            w = _OPW.get(op, 0)
            operand = m[q:q + w]; q += w
            yield "    " + _fmt_op(op, operand)
            emitted += 1
        block += 1
        p = bend
    if emitted >= limit:
        yield "    ... (truncated at --limit %d ops)" % limit


def _fmt_op(op, operand):
    val = operand[0] if len(operand) == 1 else (struct.unpack("<H", operand)[0] if len(operand) == 2 else None)
    if op == 0x21:
        nm = EXEC_BLOG.get(val, "?")
        pc, _ = EXEC_IMPL.get(nm, (None, None))
        return "21 %02X  Exec %-26s %s" % (val, nm, ("(%d params)" % pc) if pc is not None else "")
    if op == 0x32:
        return "32 %02X  AI   %s" % (val, AI_CODES.get(val, "?"))
    if op == 0x22:
        return "22 %02X  -- part %d --" % (val, val)
    if op == 0x4D:
        return "4D %02X  jump-> part %d" % (val, val)
    if op == 0x2A:
        return "2A %02X  PlaySpeech idx=%d" % (val, val)
    if op == 0x2C:
        return "2C %02X  object ref %d" % (val, val)
    if op == 0x2D:
        return "2D %02X  flight-group ref %d" % (val, val)
    if op == 0x27:
        return "27 %02X  read global[%d]" % (val, val)
    if op == 0x40:
        return "40 %02X  &global[%d] (write)" % (val, val)
    if op == 0x3F:
        return "3F %02X  &array[%d] / jump" % (val, val)
    if op == 0x28:
        return "28 %02X  wait/operand %d" % (val, val)
    if op in (0x23, 0x24):
        return "%02X %04X  push imm 0x%04X" % (op, val, val)
    if op == 0x02:
        return "02     cmp !="
    if op == 0x03:
        return "03     cmp =="
    if op == 0x43:
        return "43     <line end>"
    if op == 0x14:
        return "14     squad/membership test"
    if op == 0x42:
        return "42 %02X  (op 0x42)" % val
    return "%02X     <op 0x%02X>" % (op, op)


# --------------------------------------------------------------------------- #
#  Commands                                                                    #
# --------------------------------------------------------------------------- #
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


def cmd_decode(args):
    try:
        mis = Mission(open(args.file, "rb").read())
    except DTEError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    only = args.section
    name = os.path.basename(args.file)
    print("%s  ->  RefPack image %d bytes (0x%X)  reloc-flags=0x%X"
          % (name, len(mis.image), len(mis.image), mis.reloc_flags))

    if only in (None, "dir"):
        print("\n# 27-section directory")
        print("  slot  section            global             count   offset")
        for k, (label, dat, kind) in enumerate(SECTIONS):
            cnt, off, fl = mis.dir[k]
            offs = "(empty)" if off == EMPTY_OFF else "0x%06X" % off
            print("  [%2d]  %-18s %-18s %5d   %s%s"
                  % (k, label, dat, cnt, offs, "  +reloc0x%X" % fl if fl else ""))

    if only in (None, "ships"):
        print("\n# ships / flight groups  (slot 3, stride 0x4C, n=%d)" % mis.count(3))
        for s in _head(mis.ships(), args.limit):
            x, y, z = s["pos"]
            print("  [%3d] fg=%-4d %-22s pos=(%11.1f,%9.1f,%11.1f) iff=0x%02X type=0x%02X"
                  % (s["i"], s["fg"], '"%s"' % s["name"], x, y, z, s["iff"], s["type"]))

    if only in (None, "fg"):
        print("\n# FG/objective table  (slot 4, stride 0x14, n=%d)" % mis.count(4))
        for r in _head(mis.fg_records(), args.limit):
            print("  [%2d] id=0x%X ref=0x%04X f8=0x%X f12=0x%X  txt=%r"
                  % (r["i"], r["id"], r["ref"], r["f8"], r["f12"], mis.string(r["ref"] & 0xFFFF)[:32]))

    if only in (None, "triggers"):
        print("\n# triggers  (slot 5, stride 0x30, n=%d)" % mis.count(5))
        for t in _head(mis.triggers(), args.limit):
            print("  [%2d] b0=0x%02X b1=0x%02X b2=0x%02X  fields=%s"
                  % (t["i"], t["b0"], t["b1"], t["b2"], " ".join("%04X" % v for v in t["fields"])))

    if only in (None, "script"):
        print("\n# script bytecode  (slot 6, %d bytes)" % mis.count(6))
        for line in disasm_script(mis, args.limit if args.limit else 120):
            print(line)
    return 0


def _head(it, limit):
    out = []
    for i, x in enumerate(it):
        if limit and i >= limit:
            break
        out.append(x)
    return out


def tokens(data, lo=3):
    return [(m.start(), m.group().decode("latin-1"))
            for m in re.finditer(("[\\x20-\\x7e]{%d,}" % lo).encode(), data)]


def cmd_inspect(args):
    data = open(args.file, "rb").read()
    n = len(data)
    sig = "RefPack" if len(data) > 1 and data[1] == 0xFB else "?"
    c = Counter(data)
    printable = sum(1 for b in data if 32 <= b < 127)
    print("%s  %d bytes (0x%X)  sig=%s  printable=%.0f%% (compressed view)"
          % (os.path.basename(args.file), n, n, sig, 100 * printable / n))
    print("top bytes:", ", ".join("%02x:%d" % (b, k) for b, k in c.most_common(8)))
    print("(use `decode` for the decompressed mission)")


def cmd_sweep(args):
    files = sorted((f for f in os.listdir(args.dir) if f.lower().endswith(".dte")),
                   key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or 0))
    print("decoding %d .dte in %s\n" % (len(files), args.dir))
    print("  %-16s %5s %9s %6s %5s %5s %7s %6s" %
          ("file", "sig", "image", "ships", "fg", "trig", "script", "flags"))
    npass = 0
    for f in files:
        try:
            mis = Mission(open(os.path.join(args.dir, f), "rb").read())
        except DTEError as e:
            print("  %-16s  FAIL  %s" % (f, e))
            continue
        ok = all(off == EMPTY_OFF or off <= len(mis.image) for _, off, _ in mis.dir)
        npass += 1 if ok else 0
        print("  %-16s %5s %9d %6d %5d %5d %7d %5s0x%X"
              % (f, "OK" if ok else "DIR?", len(mis.image), mis.count(3), mis.count(4),
                 mis.count(5), mis.count(6), "", mis.reloc_flags))
    print("\n%d/%d decoded (valid RefPack + 27-section directory)" % (npass, len(files)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer .DTE decoder + reference (read-only, static).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ref"); p.add_argument("table", nargs="?", default="all",
                                              choices=["all", "triggers", "exec", "ai", "stream"])
    p.set_defaults(func=cmd_ref)
    p = sub.add_parser("decode", help="decompress + decode a mission")
    p.add_argument("file"); p.add_argument("--limit", type=int, default=40,
                                           help="max records/ops per section (0 = no cap)")
    p.add_argument("--section", choices=["dir", "ships", "fg", "triggers", "script"],
                   help="show only one section")
    p.set_defaults(func=cmd_decode)
    p = sub.add_parser("inspect"); p.add_argument("file")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("sweep"); p.add_argument("dir")
    p.set_defaults(func=cmd_sweep)
    args = ap.parse_args(argv)
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
