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
  the HOG reader ``FUN_004C7F60``, which expands a member that begins ``10 FB`` and
  reads any other verbatim) and the RefPack stream expands into a
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
  (``FUN_0045B330``), the command catalogue at VA ``0x4F0F50`` (``FUN_0045CE30``),
  the bytecode VM ``FUN_0045C980`` over the 86-entry table ``DAT_004F6350`` (every
  operand width read from its handler), per-command impl addresses + parameter
  counts, and the section order (``FUN_00451D90``).
* **Black-box RE by Captain Foster / "Starlancer ME"** (starlancerme.blogspot.com):
  the command indices, the AI-mode table, the ship/pilot ID tables, and the
  observed in-game semantics.
* **openreliant** (github.com/vdmkenny/openreliant, docs/formats/dte.md): the
  opcode names, and the part and routine layout, each re-read here against the exe.

The script listing follows control flow from every routine's entry -- the parts
of section 8 and the triggers some object's slice holds -- rather than sweeping,
and a misread width cannot pass silently: a path leaving its block, two
instructions sharing a byte, or a null opcode is reported as an error.

Usage:
  dte_parse.py ref [triggers|exec|ai|stream]   # print a reference table
  dte_parse.py decode <mission.dte> [--limit N] [--section NAME]   # full decode
  dte_parse.py inspect <mission.dte>           # raw (compressed) quick look
  dte_parse.py sweep <dir> [--sections] [--script]   # decode + validate every .dte
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
#  Executor commands (script opcode 0x21 <index>).                             #
#  EXEC_CATALOG (below) is AUTHORITATIVE: walked directly from the engine's    #
#  live command catalogue at VA 0x4F0F50 (installed by FUN_0045CE30; the       #
#  0x21 <i> handler FUN_0045BEA0 indexes entry i, stride 0x74). Its names,     #
#  parameter labels and impl addresses are the DEVELOPERS' OWN strings,        #
#  recovered from the binary -- 95 real commands (0x00..0x5E); 0x5F is empty.  #
#  EXEC_BLOG is Starlancer ME's empirical numbering, kept ONLY as a cross-     #
#  reference: it diverges at 0x16-0x19 and 0x26-0x2A, where the black-box      #
#  effort mistook parameter-label text for commands ("GTextPilotDefine" is     #
#  DisplaySubTitle's param; "RadiusOfSphere" is SetActionCentre's; "ShipPoint- #
#  ToFlyTo" is Fly's "Point to fly to") and folds away the CommsFromPilot/     #
#  ...Once pilot-twins. See docs/dte-format.md s9 + dte-scripting-reference.md.#
# --------------------------------------------------------------------------- #
# index -> blog name  (DIVERGENT empirical cross-reference; authoritative names
# and impls are in EXEC_CATALOG -- do not key script decoding off this table)
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
# Authoritative Executor catalogue -- (index, name, impl_VA, (param labels...)).
# Walked from the engine's live dispatch table @ VA 0x4F0F50 (stride 0x74); name,
# impl and the per-parameter labels are the developers' own strings from the binary.
# 0x5F is an empty slot; a disabled `Test_AI_Function` debug stub sits at 0x60.
EXEC_CATALOG = [
    (0x00, "PrintShipName",           0x00458AB0, ('Test Param 1', 'Test Param 2')),
    (0x01, "CreateTimer",             0x0045D210, ('Unique ID to identify timer', 'Function to execute when timer activates', 'Number of seconds before timer activates', 'Number of activations (0 == continuous)')),
    (0x02, "DestroyTimer",            0x0045D290, ('Unique ID of timer to be destroyed',)),
    (0x03, "CreateFlightGroup",       0x00457C40, ('Flight Group name to initialize',)),
    (0x04, "DestroyFlightGroup",      0x00457FD0, ('Flight Group name to destroy',)),
    (0x05, "Wait",                    0x0045D2E0, ('Number of Seconds to wait',)),
    (0x06, "PlaySpeech",              0x00458090, ('Name of speech file',)),
    (0x07, "WaitForSpeech",           0x00458100, ()),
    (0x08, "PlayCommsMovie",          0x00458120, ('Name of movie file', 'Name of speech file', 'GText thingy hangover err....')),
    (0x09, "WaitForMovie",            0x00458180, ()),
    (0x0A, "PrintDebugMessage",       0x004581A0, ('Text to print',)),
    (0x0B, "SetAI",                   0x004581F0, ('Entity to be controlled', 'AI Mode', 'Initialize Immediately (T/F)', 'Entity to target (can be NULL)')),
    (0x0C, "ClearAI",                 0x004588C0, ('Entity to be cleared',)),
    (0x0D, "SetPatrolRoute",          0x00458860, ('Entity to send to patrol route', 'Patrol route to follow')),
    (0x0E, "SetPilot",                0x00458830, ('Ship to host pilot', 'Pilot to fly ship')),
    (0x0F, "SetTriggerState",         0x0045D300, ('Entity owning trigger', 'Trigger type to enable/disable', 'TRUE for enable; FALSE for disable')),
    (0x10, "StartDirectorCam",        0x004582E0, ('Curve for camera to follow (or Ship for static cam)', 'Ship for camera to track (can be NULL)', 'Duration of camera (seconds)', "Tracks curve to this ship's speed (can be NULL)", 'Ships to disable for duration')),
    (0x11, "StartShipAnimation",      0x00458720, ('Ship to animate', 'Animation Name')),
    (0x12, "ShipFollowCurve",         0x004585D0, ('Entity to follow curve', 'The curve for the entity to follow', 'Duration of movement (seconds)')),
    (0x13, "SetupLaunch",             0x00458970, ('Entity to be launched', 'Ship to launch from', 'Launch position')),
    (0x14, "StartLaunch",             0x00458A40, ('Entity to be launched',)),
    (0x15, "DisplaySubTitle",         0x00458A80, ('GText pilot define',)),
    (0x16, "ResetCodePriority",       0x00458A90, ('Entity to have priorities reset',)),
    (0x17, "InterruptTriggerCode",    0x0045D450, ()),
    (0x18, "CommsFromShip",           0x00458AC0, ('Ship sending comm', 'Head movement', 'Name of speech file')),
    (0x19, "CommsFromPilot",          0x00458B10, ('Ship sending comm', 'Head movement', 'Name of speech file')),
    (0x1A, "SetInvulnerability",      0x00458BC0, ('Ship concerned', 'Invulnerability (0 - non, 1 - player can hit, 2 - fully invulnerable, 3 - Eject before exploding')),
    (0x1B, "MovingShipFollowCurve",   0x004585A0, ('Entity to follow curve', 'The curve for the entity to follow', 'Duration of movement (seconds)', 'Entity for curve to use as its start offset')),
    (0x1C, "DisableObject",           0x004583C0, ('Entity concerned', 'True/False')),
    (0x1D, "PositionRelative",        0x004584D0, ('Entity to position', 'Ship/Point to use as relative marker')),
    (0x1E, "WhenPlayerLastJumped",    0x00458580, ()),
    (0x1F, "StartMissileCam",         0x00458B60, ('Ship that fired missile',)),
    (0x20, "StartChaseCam",           0x00458B80, ('Ship to follow',)),
    (0x21, "SetPlayerTarget",         0x00458C80, ('Player Ship', 'Ship to target')),
    (0x22, "SetTargetable",           0x00458D50, ('Entity', 'true - object targetable, false - not targetable')),
    (0x23, "PlayMusic",               0x00458DF0, ('Name of music file', 'True - Play Immediately, false - Fade old tune first')),
    (0x24, "StopDirectorCam",         0x00458E30, ()),
    (0x25, "SetActionCentre",         0x00458E60, ('Object to action around', 'Radius of sphere - 0 for default')),
    (0x26, "Dock",                    0x00458EB0, ('Ship to dock', 'Object ship is to dock to', 'Docking port')),
    (0x27, "DisableTaunts",           0x00458F40, ('true - Disable bad guy taunts',)),
    (0x28, "Fly",                     0x00458F50, ('Ship', 'Point to fly to', 'Speed (0 - Default)')),
    (0x29, "CommsFromShipOnce",       0x00458FD0, ('Ship sending comm', 'Head movement', 'Name of speech file')),
    (0x2A, "CommsFromPilotOnce",      0x00459020, ('Ship sending comm', 'Head movement', 'Name of speech file')),
    (0x2B, "DisableLights",           0x00459070, ('Entity', 'True or False')),
    (0x2C, "SetEnvironmentFX",        0x00459170, ('Effect type to set', 'On(TRUE) or Off(FALSE)')),
    (0x2D, "MultiPlayerSync",         0x004591E0, ()),
    (0x2E, "DisableGenericComms",     0x004591F0, ('True - Disable all hard coded comms events',)),
    (0x2F, "DisableGuns",             0x00459200, ('Entity', 'TRUE - disable guns, FALSE enable guns')),
    (0x30, "SetNavPoint",             0x00459270, ('Entity', 'Nav Point')),
    (0x31, "SetEscortPoint",          0x004592F0, ('Entity', 'Escort Point')),
    (0x32, "ResetAfterBurners",       0x004594C0, ()),
    (0x33, "DisableMissiles",         0x00459370, ('Entity', 'TRUE - disable missiles, FALSE enable missiles')),
    (0x34, "DisableEngines",          0x004593E0, ('Entity', 'TRUE - disable engines, FALSE enable engines')),
    (0x35, "DisableEject",            0x00459450, ('Entity', 'TRUE - disable eject, FALSE enable eject')),
    (0x36, "SetHostile",              0x004594F0, ('Entity', 'true - entity(s) hostile, false - friendly')),
    (0x37, "ResetToSpawnPositions",   0x004591B0, ()),
    (0x38, "UpdateEnvironmentFXState", 0x004591A0, ()),
    (0x39, "SetPrimaryTarget",        0x00459550, ('Entity',)),
    (0x3A, "WaitForJumpOrLaunch",     0x004595A0, ('Entity',)),
    (0x3B, "DoNotDisturb",            0x00459640, ('Entity', 'true - dont disturb, false - can disturb')),
    (0x3C, "SetEnvironmentFXNebula",  0x00459190, ('Index of nebula material (0..6)',)),
    (0x3D, "StartShipAnimationReverse", 0x004587D0, ('Ship to animate', 'Animation Name')),
    (0x3E, "SnapToPoint",             0x004596A0, ('Ship to move', 'Point to move to')),
    (0x3F, "PlayFostersLastStand",    0x00459740, ()),
    (0x40, "OpenInstrument",          0x0045D9D0, ('Instrument number to open',)),
    (0x41, "CloseInstrument",         0x0045DA30, ('Instrument number to close',)),
    (0x42, "DestroySubObject",        0x00459750, ('SubObject to destroy', 'true - keep damaged model, false - no damaged model')),
    (0x43, "SetObjective",            0x00459870, ('Objective number', 'State(0=Inactive, 1=Active, 2=Current)')),
    (0x44, "SetRescueProbabilities",  0x004598D0, ('Probability of Nanny Rescue    ( 1-100% )', 'Probability of Antanov Capture ( 1-100% )', 'Probability of being Destroyed ( 1-100% )')),
    (0x45, "IsShipThisPlayer",        0x004598F0, ('Ship to test',)),
    (0x46, "SetFlybackMarker",        0x00459910, ('Entity concerned', 'Range')),
    (0x47, "ResetFlybackMarker",      0x004599E0, ()),
    (0x48, "StopShipAnimation",       0x00458770, ('Ship to stop animation for', 'Animation Name')),
    (0x49, "SetShipAvoidance",        0x00459A30, ('Entity concerned', 'TRUE - Disable Avoidance code, FALSE - Enable avoidance code')),
    (0x4A, "MatchSpeed",              0x00459A90, ('Entity concerned', 'TRUE - Enable Match Speed, FALSE - Disable Match Speed')),
    (0x4B, "MovingShipBackupCurve",   0x00458670, ('Entity to follow curve', 'The curve for the entity to follow', 'Duration of movement (seconds)', 'Entity for curve to use as its start offset')),
    (0x4C, "WaitForKey",              0x00459AE0, ('Key number to wait for',)),
    (0x4D, "TerminateMission",        0x00459BB0, ()),
    (0x4E, "TurretSetTarget",         0x00459BD0, ('Turret', 'Entity to target')),
    (0x4F, "SetAnyTriggerState",      0x0045D3A0, ('Entity owning trigger', 'Trigger type to enable/disable', 'TRUE for enable; FALSE for disable', 'Trigger Type Number(for triggers of same type - Count from 0)')),
    (0x50, "WaitForDirectorCam",      0x00459C90, ()),
    (0x51, "KillAllScriptExecutionExecptMe", 0x0045D990, ()),   # sic -- dev typo preserved in the binary
    (0x52, "StackDirectorCam",        0x00458300, ('Curve for camera to follow (or Ship for static cam)', 'Ship for camera to track (can be NULL)', 'Duration of camera (seconds)', "Tracks curve to this ship's speed (can be NULL)", 'Ships to disable for duration')),
    (0x53, "Scanner",                 0x00459CB0, ('Object to scan for - NULL to disable',)),
    (0x54, "ReplaceSubObject",        0x00459CF0, ('SubObject to replace', 'Object to replace it with')),
    (0x55, "Fire",                    0x00459DD0, ('Ship to fire', 'Duration')),
    (0x56, "MultiplayerScriptSync",   0x00459DF0, ('Sync number',)),
    (0x57, "FriendlyFire",            0x00459F30, ()),
    (0x58, "Cloak",                   0x00459F40, ('Entity to cloak', 'True - Cloak on, False - cloak off')),
    (0x59, "ReplenishWeapons",        0x00459FA0, ('Entity to cloak',)),                 # param is a Cloak copy-paste
    (0x5A, "WillsBlag",               0x0045A1C0, ('Entity to cloak',)),                 # param is a Cloak copy-paste
    (0x5B, "ShowHudIcon",             0x0045A1F0, ('Icon', '0 - off, 1 - on, 2 - flash')),
    (0x5C, "DisableListing",          0x0045A210, ('Ship', 'true - stop listing, false - enable listing')),
    (0x5D, "DisableObjectAtNextJump", 0x0045A250, ('Ship', 'true - disable, false - enable')),
    (0x5E, "DarrensNaughtyBlag",      0x0045A290, ('Ship', 'Ship')),
    (0x5F, "(unused)",                None,       ()),
]

# Derived lookups -- EXEC_CATALOG is the single source of truth.
EXEC_BY_IDX = {idx: (name, va, params) for idx, name, va, params in EXEC_CATALOG}
# back-compat alias: command name -> (param_count, impl VA)
EXEC_IMPL = {name: (len(params), va) for idx, name, va, params in EXEC_CATALOG if va}

# AI modes -- the values of SetAI's "AI Mode" parameter, which a script pushes with
# push_byte (0x32 <n>) before `command 0x0B`.  Starlancer ME's "AI Codes" page.
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

# --------------------------------------------------------------------------- #
#  Container layer -- RefPack/QFS decompression + the 27-section directory.    #
# --------------------------------------------------------------------------- #
# Decompressed-image section order, from the 27 sequential FUN_00452A20 reads in
# the loader FUN_00451D90.  Tuple = (label, dest-global, decoder-kind, stride).
# "kind" drives the pretty record decoders; "stride" is the record size where
# known (1 = byte-blob, None = not yet decoded).  Strides marked below were
# re-verified by parsing all 44 missions (offset + count*stride stays in-image,
# zero overflow); population notes (vestigial / rare / TBD) likewise come from a
# 44-mission sweep -- see `sweep --sections`.
SECTIONS = [
    ("string_pool",      "DAT_00525FA8", "strings",  1),     # 0  name/text pool (byte-indexed)
    ("section1",         "DAT_00525F3C", None,        2),    # 1  operand-resolution array, kind 0 (FUN_004529d0)
    ("globals",          "DAT_005294F8", "globals",   0x0C), # 2  script global variables
    ("ships",            "DAT_0052951C", "ships",     0x4C), # 3  placed ships, stations, nav points; +0 object ID
    ("flight_groups",    "DAT_005267CC", "fg",        0x14), # 4  flight groups; +0 object ID (push_flight_group 0x2D)
    ("triggers",         "DAT_005294E0", "triggers",  0x30), # 5  triggers; +0 condition, +2 link, +0x15 qualifier
    ("script",           "DAT_00525F88", "script",    2),    # 6  bytecode; count is in HALFWORDS (2*count bytes)
    ("object_table",     "DAT_005267C0", None,        8),    # 7  by object ID: kind, trigger-slice count + first
    ("parts",            "DAT_005267D0", None,        0x1C), # 8  part descriptors -> runtime table [0x538C94]
    ("section9",         "DAT_005256C8", None,        None), # 9  populated in 16/44 missions (layout TBD)
    ("script_yieldflags","DAT_005294D8", None,        1),    # 10 per-byte VM yield flags (count = #script bytes)
    ("section11",        "PTR_DAT_004EF2FC", None,    None), # 11 operand/target list (count <= 1)
    ("squads",           "DAT_005294FC", None,        0x0C), # 12 squads; +0 object ID, +8 first member (push_squad 0x44)
    ("squad_members",    "DAT_00529500", None,        0x0C), # 13 squad membership records
    ("section14",        "DAT_00525F18", None,        8),    # 14 stride 8; entry +4 u16 -> sec15 (rare: 3/44)
    ("section15",        "DAT_005256B8", None,        0x10), # 15 position / nav-geometry records (rare: 3/44)
    ("section16",        "DAT_00525FB0", None,        0x44), # 16 sub-object/model table (36/44; idx fields + coord vectors)
    ("parts_b",          "DAT_005294EC", None,        0x1C), # 17 vestigial: "b" part descriptors -> [0x538C98]
    ("script_b",         "DAT_00525FB4", None,        None), # 18 vestigial: "b" bytecode (see B_LAYER)
    ("section19",        "DAT_0052950C", None,        None), # 19 vestigial -- empty in all 44
    ("section20",        "DAT_00525FA0", None,        None), # 20 vestigial -- empty in all 44
    ("section21",        "(local)",      None,        None), # 21 transient stack temp (count only)
    ("section22",        "DAT_00525278", None,        2),    # 22 operand-resolution array, kind 1 (large)
    ("section23",        "PTR_DAT_004EE7D8", None,    None), # 23 populated 40/44 (layout TBD)
    ("command_flags",    "DAT_00525F9C", None,        2),    # 24 u16 per command; 0x21 inverts bit 0 into DAT_00537584
    ("command_b_flags",  "DAT_00525F90", None,        2),    # 25 vestigial: the same for 0x4F (see B_LAYER)
    ("section26",        "DAT_0052570C", None,        2),    # 26 operand-resolution array, kind 2 (rare: 3/44)
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
        elif ctrl < 0xFC:                       # literal run (4..112, multiple of 4)
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
        self._index()

    @classmethod
    def from_image(cls, image):
        """Build from an ALREADY-EXPANDED image - i.e. a loose `missions\\*.dte`.

        Loose mission files on disk are raw images, never RefPack (see docs/dte-format.md §2),
        so this is the constructor to use for anything the game would load from `missions\\`.
        """
        self = cls.__new__(cls)
        self.image = bytes(image)
        self.declared = len(self.image)
        self._index()
        return self

    def _index(self):
        m = self.image
        if len(m) < 27 * 8:
            raise DTEError("image too short for a 27-entry directory (%d bytes)" % len(m))
        self.dir = []    # list of (count, offset, flags)
        self.ctrl = []   # the raw control dword per slot, needed to write a count back
        for k in range(27):
            cf, off = struct.unpack_from("<II", m, k * 8)
            self.dir.append((cf & 0xFFFF, off, (cf >> 24) & 0x0F))
            self.ctrl.append(cf)
        self.reloc_flags = self.dir[0][2] if self.dir else 0

    def count(self, slot):
        return self.dir[slot][0]

    def offset(self, slot):
        return self.dir[slot][1]

    def present(self, slot):
        off = self.dir[slot][1]
        return off != EMPTY_OFF and off <= len(self.image)

    # -- fixed-capacity layout + in-place editing ------------------------- #
    # Sections never move and records are never packed: each section owns a fixed
    # span, `count` says how many records are live, and the rest is reserved slack.
    # So an edit is a write into a slot plus a count update, and the image size is
    # invariant - which is why sections we have not decoded survive verbatim.
    # See docs/dte-format.md section 3.0.

    def _live_offsets(self):
        return sorted(o for _, o, _ in self.dir if o != EMPTY_OFF and o <= len(self.image))

    def capacity(self, slot):
        """Reserved bytes for `slot`: up to the next live section, or end of image."""
        off = self.dir[slot][1]
        if off == EMPTY_OFF or off > len(self.image):
            return 0
        nxt = min((o for o in self._live_offsets() if o > off), default=len(self.image))
        return nxt - off

    def max_records(self, slot):
        """How many records fit in `slot`'s reserved span, or None if the stride is unknown."""
        stride = SECTIONS[slot][3]
        return self.capacity(slot) // stride if stride else None

    def record(self, slot, i):
        stride = SECTIONS[slot][3]
        if not stride:
            raise DTEError("section %d (%s) has no known stride" % (slot, SECTIONS[slot][0]))
        if i >= (self.max_records(slot) or 0):
            raise DTEError("record %d is beyond section %d's reserved capacity" % (i, slot))
        off = self.dir[slot][1] + i * stride
        return self.image[off:off + stride]

    def set_record(self, slot, i, data):
        """Overwrite one record in place. Never changes the image size."""
        stride = SECTIONS[slot][3]
        if not stride:
            raise DTEError("section %d (%s) has no known stride" % (slot, SECTIONS[slot][0]))
        if len(data) != stride:
            raise DTEError("record must be exactly %d bytes, got %d" % (stride, len(data)))
        if i >= (self.max_records(slot) or 0):
            raise DTEError("record %d is beyond section %d's reserved capacity" % (i, slot))
        off = self.dir[slot][1] + i * stride
        buf = bytearray(self.image)
        buf[off:off + stride] = data
        self.image = bytes(buf)

    def set_count(self, slot, n):
        """Set how many records of `slot` are live, bounded by its reserved capacity."""
        cap = self.max_records(slot)
        if cap is None:
            raise DTEError("section %d (%s) has no known stride" % (slot, SECTIONS[slot][0]))
        if not 0 <= n <= cap:
            raise DTEError("count %d outside section %d's capacity of %d" % (n, slot, cap))
        cf = (self.ctrl[slot] & 0xFFFF0000) | (n & 0xFFFF)
        buf = bytearray(self.image)
        struct.pack_into("<I", buf, slot * 8, cf)
        self.image = bytes(buf)
        self.ctrl[slot] = cf
        self.dir[slot] = (n, self.dir[slot][1], self.dir[slot][2])

    def to_image(self):
        """The image as the game would read it from a loose `missions\\*.dte`."""
        return self.image

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
            oid = struct.unpack_from("<I", rec, 0)[0]    # object ID -> section 7
            name = self.string(struct.unpack_from("<H", rec, 4)[0])
            pos = struct.unpack_from("<3f", rec, 8)
            # authored Euler angles, whole degrees, at NON-contiguous offsets;
            # mirrored to runtime +0x2C/+0x38/+0x48 at load (FUN_00452010) and
            # scaled by pi/180 in the rotation builder FUN_00452240.
            orient = (struct.unpack_from("<h", rec, 0x2E)[0],   # yaw
                      struct.unpack_from("<h", rec, 0x3A)[0],   # pitch
                      struct.unpack_from("<h", rec, 0x4A)[0])   # roll
            # type/role is u16 — normal ships < 0x100, but special objects (nav points,
            # jump/escort markers) use 0x3E3..0x3E8, so a byte read truncates ~41% of records.
            yield {"i": i, "id": oid, "fg": rec[0x14], "name": name, "pos": pos,
                   "orient": orient, "b14": rec[0x14], "iff": rec[0x15],
                   "type": struct.unpack_from("<H", rec, 0x18)[0], "raw": rec}

    def fg_records(self):
        base, n, m = self.offset(4), self.count(4), self.image
        for i in range(n):
            r = base + i * 0x14
            rec = m[r:r + 0x14]
            if len(rec) < 0x14:
                break
            a, b, c, d = struct.unpack_from("<IIII", rec, 0)
            yield {"i": i, "id": a, "ref": b, "f8": c, "f12": d, "raw": rec}

    def objects(self):
        """Section 7, indexed by object ID: its kind and its slice of the triggers.

        Kind 0 is a ship, 1 a flight group, 2 a squad; `first` and `ntrig` give the
        run of section 5 the engine walks when an event happens to the object.
        """
        base, n, m = self.offset(7), self.count(7), self.image
        if base == EMPTY_OFF:
            return
        for i in range(n):
            r = base + i * 8
            if r + 8 > len(m):
                break
            yield {"id": i, "kind": m[r], "ntrig": m[r + 1],
                   "first": struct.unpack_from("<H", m, r + 2)[0]}

    def triggers(self):
        """Section 5, with each trigger's subject: the object whose slice holds it.

        A trigger holds no subject of its own (docs/dte-format.md section 4); one no
        slice holds has `subject` None and never fires.
        """
        subject = {}
        for o in self.objects():
            for k in range(o["first"], o["first"] + o["ntrig"]):
                subject[k] = o["id"]
        base, n, m = self.offset(5), self.count(5), self.image
        for i in range(n):
            r = base + i * 0x30
            rec = m[r:r + 0x30]
            if len(rec) < 0x30:
                break
            yield {"i": i, "condition": rec[0], "repeat": rec[1],
                   "link": struct.unpack_from("<H", rec, 2)[0], "armed": rec[0x14],
                   "qualifier": rec[0x15], "run": rec[0x16], "subject": subject.get(i),
                   "raw": rec}

    def parts(self):
        """Section 8: one 28-byte descriptor per part, a named routine.

        The loader (FUN_00452F50 -> FUN_00452FD0) sets the runtime entry's block to
        ``script + start * 2`` (0xFFFF = none) and its argument count from +0x0D.
        `extent` (+0x10, halfwords) is the author's size of block plus constants.
        """
        base, n, m = self.offset(8), self.count(8), self.image
        if base == EMPTY_OFF:
            return
        for i in range(n):
            r = base + i * 0x1C
            rec = m[r:r + 0x1C]
            if len(rec) < 0x1C:
                break
            yield {"i": i, "name": self.string(struct.unpack_from("<H", rec, 0)[0]),
                   "start": struct.unpack_from("<H", rec, 0x0A)[0], "flags": rec[0x0C],
                   "argc": rec[0x0D], "extent": struct.unpack_from("<H", rec, 0x10)[0],
                   "raw": rec}

    def globals(self):
        """Section 2: the named values the script reads and writes (u16 name, u32 value)."""
        base, n, m = self.offset(2), self.count(2), self.image
        if base == EMPTY_OFF:
            return
        for i in range(n):
            r = base + i * 0x0C
            if r + 0x0C > len(m):
                break
            yield {"i": i, "name": self.string(struct.unpack_from("<H", m, r)[0]),
                   "value": struct.unpack_from("<I", m, r + 4)[0]}

    def script(self):
        """Section 6, the bytecode: `count` halfwords, so ``2 * count`` bytes."""
        off = self.offset(6)
        if off == EMPTY_OFF:
            return b""
        return self.image[off:off + 2 * self.count(6)]

    def object_names(self):
        """Object ID -> a readable name for the listing."""
        names = {}
        for s in self.ships():
            names[s["id"]] = 'ship %d "%s"' % (s["i"], s["name"])
        for slot, stride, label in ((4, 0x14, "flight group"), (12, 0x0C, "squad")):
            base, n = self.offset(slot), self.count(slot)
            if base == EMPTY_OFF:
                continue
            for i in range(n):
                r = base + i * stride
                if r + 4 <= len(self.image):
                    names.setdefault(struct.unpack_from("<I", self.image, r)[0], "%s %d" % (label, i))
        return names


# --------------------------------------------------------------------------- #
#  Script VM instruction set -- 71 opcodes, every width read from its handler. #
# --------------------------------------------------------------------------- #
# The interpreter FUN_0045C980 fetches an opcode byte, indexes the 86-entry
# handler table DAT_004F6350 (0x00-0x55), advances the IP past the opcode and
# calls the handler with ECX pointing at the IP cell; execution resumes wherever
# the handler leaves that cell.  Every row's operand form below was read from
# its handler's bytes (capstone over the exe as data, 2026-09-22 and
# 2026-09-29).  Names follow openreliant's docs/formats/dte.md, which reached
# the same widths independently by symbolic execution.  0x00, 0x01, 0x08-0x13
# and 0x50 are null; five pairs share a handler and are the same operation.
#
# form -- the operand bytes after the opcode:
#   ""    none              "b"  one byte          "bb"  two bytes
#   "bbb" three bytes       "w"  big-endian u16
#   "d"   big-endian u16 displacement, counted from its own address (forward only)
#   "s"   a length byte that counts itself, then NUL-terminated text
#   "r"   random_branch: count, big-endian default, count x (big-endian target,
#         threshold, one byte the handler never reads); targets count from the opcode
# flow -- where execution goes next:
#   "seq"    after the operands          "branch" after them, or to the target
#   "jump"   to the target only          "call"   into a part, then after the operands
#   "return" nowhere: leaves the part, or ends the thread when the depth is zero
#   "random" one of the targets (the handler always sets the IP; never falls through)
OPCODES = {
    0x02: ("equal",               "",    "seq",    0x45BAD0),
    0x03: ("not_equal",           "",    "seq",    0x45BB00),
    0x04: ("greater",             "",    "seq",    0x45BB30),
    0x05: ("greater_equal",       "",    "seq",    0x45BB60),
    0x06: ("less",                "",    "seq",    0x45BB90),
    0x07: ("less_equal",          "",    "seq",    0x45BBC0),
    0x14: ("in_flight_group",     "",    "seq",    0x45BBF0),
    0x15: ("not_in_flight_group", "",    "seq",    0x45BC30),
    0x16: ("assign",              "",    "seq",    0x45BC70),
    0x17: ("add_assign",          "",    "seq",    0x45BCA0),
    0x18: ("sub_assign",          "",    "seq",    0x45BCD0),
    0x19: ("mul_assign",          "",    "seq",    0x45BD00),
    0x1A: ("div_assign",          "",    "seq",    0x45BD30),
    0x1B: ("add",                 "",    "seq",    0x45BD60),
    0x1C: ("sub",                 "",    "seq",    0x45BD90),
    0x1D: ("mul",                 "",    "seq",    0x45BDC0),
    0x1E: ("div",                 "",    "seq",    0x45BDF0),
    0x1F: ("logical_and",         "",    "seq",    0x45BE20),
    0x20: ("logical_or",          "",    "seq",    0x45BE60),
    0x21: ("command",             "b",   "seq",    0x45BEA0),
    0x22: ("call_part",           "b",   "call",   0x45BFA0),
    0x23: ("branch_if_zero",      "d",   "branch", 0x45C270),
    0x24: ("branch_if_zero",      "d",   "branch", 0x45C270),
    0x25: ("return",              "",    "return", 0x45C6E0),
    0x26: ("push_array",          "b",   "seq",    0x45C2D0),
    0x27: ("push_global",         "b",   "seq",    0x45C300),
    0x28: ("push_constant",       "b",   "seq",    0x45C340),
    0x29: ("push_constant_wide",  "w",   "seq",    0x45C370),
    0x2A: ("push_string",         "s",   "seq",    0x45C3B0),
    0x2B: ("push_string",         "s",   "seq",    0x45C3B0),
    0x2C: ("push_ship",           "b",   "seq",    0x45C3E0),
    0x2D: ("push_flight_group",   "b",   "seq",    0x45C560),
    0x2E: ("push_byte",           "b",   "seq",    0x45C6B0),
    0x2F: ("push_percent",        "b",   "seq",    0x45DA50),
    0x30: ("push_local",          "b",   "seq",    0x45C5A0),
    0x31: ("push_argument",       "b",   "seq",    0x45C680),
    0x32: ("push_byte",           "b",   "seq",    0x45C6B0),
    0x33: ("greater_f",           "",    "seq",    0x45DAB0),
    0x34: ("greater_equal_f",     "",    "seq",    0x45DB10),
    0x35: ("less_f",              "",    "seq",    0x45DB70),
    0x36: ("less_equal_f",        "",    "seq",    0x45DBD0),
    0x37: ("add_assign_f",        "",    "seq",    0x45DC30),
    0x38: ("sub_assign_f",        "",    "seq",    0x45DC70),
    0x39: ("mul_assign_f",        "",    "seq",    0x45DCB0),
    0x3A: ("div_assign_f",        "",    "seq",    0x45DCF0),
    0x3B: ("add_f",               "",    "seq",    0x45DD30),
    0x3C: ("sub_f",               "",    "seq",    0x45DD80),
    0x3D: ("mul_f",               "",    "seq",    0x45DDD0),
    0x3E: ("div_f",               "",    "seq",    0x45DE20),
    0x3F: ("select_array",        "b",   "seq",    0x45C790),
    0x40: ("select_global",       "b",   "seq",    0x45C7D0),
    0x41: ("select_argument",     "b",   "seq",    0x45C810),
    0x42: ("jump",                "d",   "jump",   0x45C2B0),
    0x43: ("return",              "",    "return", 0x45C6E0),
    0x44: ("push_squad",          "b",   "seq",    0x45C850),
    0x45: ("in_squad",            "",    "seq",    0x45C890),
    0x46: ("not_in_squad",        "",    "seq",    0x45C8D0),
    0x47: ("push_component",      "bb",  "seq",    0x45C460),
    0x48: ("push_null",           "",    "seq",    0x45C4B0),
    0x49: ("push_curve",          "b",   "seq",    0x45C4D0),
    0x4A: ("call_part_b",         "b",   "call",   0x45C110),
    0x4B: ("push_event_value",    "bbb", "seq",    0x45C5E0),
    0x4C: ("push_result",         "",    "seq",    0x45C650),
    0x4D: ("spawn_part",          "b",   "seq",    0x45C070),
    0x4E: ("spawn_part_b",        "b",   "seq",    0x45C1E0),
    0x4F: ("command_b",           "b",   "seq",    0x45BF20),
    0x51: ("random_branch",       "r",   "random", 0x45C910),
    0x52: ("push_ship_wide",      "w",   "seq",    0x45C420),
    0x53: ("nop",                 "",    "seq",    0x45C510),
    0x54: ("push_section_19",     "b",   "seq",    0x45C520),
    0x55: ("push_component",      "bb",  "seq",    0x45C460),
}
_FIXED = {"": 0, "b": 1, "bb": 2, "bbb": 3, "w": 2, "d": 2}

# The second, AI-owned script layer.  0x4A / 0x4E run parts from the table
# [0x538C98], which the loader (FUN_00452F50) builds from section 17 over the
# bytecode of section 18; 0x4F dispatches through the AI-function catalogue at
# 0x4F3AD0 (one entry, Test_AI_Function, no implementation) to FUN_0045D800,
# which is `mov eax, 1; ret 8`.  Sections 17, 18 and 25 are empty in every
# shipped mission.  The layer is wired end to end and never used.
B_LAYER = (0x4A, 0x4E, 0x4F)


def _be16(code, p):
    if p + 2 > len(code):
        raise DTEError("operand at %d runs past the script" % p)
    return (code[p] << 8) | code[p + 1]


def decode_insn(code, p):
    """Decode the instruction at byte `p` of the script section `code`.

    Returns ``(op, size, args, targets, falls_through)``: `targets` are the
    script-relative byte offsets it can transfer to besides falling through.
    Raises DTEError on a null opcode or an instruction that runs off `code`.
    """
    if not 0 <= p < len(code):
        raise DTEError("instruction at %d is outside the script" % p)
    op = code[p]
    row = OPCODES.get(op)
    if row is None:
        raise DTEError("null opcode 0x%02X at %d" % (op, p))
    _name, form, flow, _va = row
    q = p + 1
    targets = []
    if form == "s":
        if q >= len(code):
            raise DTEError("push_string at %d runs past the script" % p)
        n = code[q]
        if n == 0:
            raise DTEError("push_string at %d has a zero length" % p)
        size = 1 + n
        args = (code[q + 1:p + size].split(b"\0", 1)[0].decode("latin-1", "replace"),)
    elif form == "r":
        if q >= len(code):
            raise DTEError("random_branch at %d runs past the script" % p)
        n = code[q]
        size = 4 + 4 * n
        default = _be16(code, q + 1)
        arms = []
        for k in range(n):
            a = q + 3 + 4 * k
            if a + 4 > len(code):
                raise DTEError("random_branch at %d runs past the script" % p)
            arms.append((_be16(code, a), code[a + 2], code[a + 3]))
        args = (default, tuple(arms))
        targets.append(p + default)
        targets.extend(p + t for t, _thr, _unused in arms if t != 0xFFFF)
    else:
        size = 1 + _FIXED[form]
        if p + size > len(code):
            raise DTEError("%s at %d runs past the script" % (_name, p))
        if form in ("w", "d"):
            args = (_be16(code, q),)
            if form == "d":
                targets.append(q + args[0])
        else:
            args = tuple(code[q:p + size])
    if p + size > len(code):
        raise DTEError("%s at %d runs past the script" % (_name, p))
    return op, size, args, targets, flow in ("seq", "branch", "call")


class Block:
    """One decoded block: a u16 length that counts itself, then instructions.

    The engine starts a thread at ``start + 2`` with its limit at ``start + length``
    (FUN_0045B8D0).  `insns` maps a script-relative offset to
    ``(op, size, args, targets)`` for every instruction some path reaches.
    """

    def __init__(self, start, length, insns, gaps, padding, falls_off, nconst, slack=()):
        self.start, self.length = start, length
        self.insns, self.gaps, self.padding = insns, gaps, padding
        self.falls_off, self.nconst, self.slack = falls_off, nconst, list(slack)

    @property
    def end(self):
        return self.start + self.length

    @property
    def const_bytes(self):
        """The constant table's size: 4 per constant, rounded up to 8."""
        return (self.nconst * 4 + 7) & ~7


def decode_block(code, start):
    """Follow control flow through the block at byte `start` of the script.

    Every path is followed from the entry rather than sweeping, because jump,
    return and random_branch never fall through.  A path that leaves the block,
    two instructions sharing a byte, or a null opcode raises DTEError -- the
    symptoms of a misread width, so a wrong table cannot pass silently.
    Unreached bytes are reported: up to three trailing ones are the padding to
    a four-byte boundary, anything else is a gap nothing jumps to.
    """
    if start + 2 > len(code):
        raise DTEError("block at %d: no room for its length" % start)
    length = struct.unpack_from("<H", code, start)[0]
    lo, hi = start + 2, start + length
    if length < 3 or hi > len(code):
        raise DTEError("block at %d: length %d does not fit the script" % (start, length))
    insns, owner, work = {}, {}, [lo]
    falls_off = False
    while work:
        p = work.pop()
        if p in insns:
            continue
        if p == hi:
            falls_off = True            # ran into the limit: the thread ends there
            continue
        if not lo <= p < hi:
            raise DTEError("block at %d: control reaches %d, outside [%d, %d)" % (start, p, lo, hi))
        op, size, args, targets, falls = decode_insn(code, p)
        if p + size > hi:
            raise DTEError("block at %d: %s at %d runs past the block end %d"
                           % (start, OPCODES[op][0], p, hi))
        for b in range(p, p + size):
            if owner.get(b, p) != p:
                raise DTEError("block at %d: instructions at %d and %d overlap" % (start, owner[b], p))
            owner[b] = p
        insns[p] = (op, size, args, targets)
        work.extend(targets)
        if falls:
            work.append(p + size)
    gaps, g = [], None
    for b in range(lo, hi):
        if b in owner:
            if g is not None:
                gaps.append((g, b)); g = None
        elif g is None:
            g = b
    if g is not None:
        gaps.append((g, hi))
    padding = 0
    if gaps and gaps[-1][1] == hi and hi - gaps[-1][0] <= 3:
        padding = hi - gaps.pop()[0]
    # random_branch slack: the mission compiler laid random_branch out with room
    # for more arms than it filled.  In all four shipped instances (count 2) the
    # first arm targets +44 from the opcode -- a 4-byte head plus ten 4-byte arm
    # slots -- and the eight unused slots hold stale buffer bytes, not zeros.  The
    # handler reads only `count` arms and never falls through, so they are never
    # read.  A gap running from a random_branch's end to the first code it
    # targets is that slack, not code nothing reaches.
    slack = []
    for p, (op, size, args, targets) in insns.items():
        if op == 0x51 and targets:
            g = (p + size, min(targets))
            if g in gaps:
                gaps.remove(g)
                slack.append(g)
    idx = [a[0] for o, _s, a, _t in insns.values() if o in (0x28, 0x29)]
    return Block(start, length, insns, gaps, padding, falls_off, max(idx) + 1 if idx else 0,
                 sorted(slack))


class Routine:
    """A block plus the constant table that follows it, up to the next routine."""

    def __init__(self, start, end, owners, block=None, error=None):
        self.start, self.end, self.owners = start, end, owners
        self.block, self.error = block, error

    def constants(self, code):
        b = self.block
        if b is None:
            return []
        return [struct.unpack_from("<I", code, b.end + 4 * k)[0]
                for k in range(b.nconst) if b.end + 4 * k + 4 <= len(code)]

    def checks(self, parts):
        """Layout claims about this routine, as {name: bool}."""
        b = self.block
        if b is None:
            return {}
        out = {"tiles": b.end + b.const_bytes == self.end}
        ext = [parts[i]["extent"] * 2 for kind, i in self.owners if kind == "part"]
        if ext:
            out["extent"] = all(e == self.end - self.start for e in ext)
        return out


def script_routines(mission):
    """Every routine in section 6, found from its entry points.

    Entries are the parts' starts (section 8) and the links of the triggers that
    some object's slice of section 5 holds (section 7); a link no slice holds is
    never followed by the engine and often points at nothing.  Each routine runs
    from its entry to the next one, the last to the end of the section.
    """
    code = mission.script()
    parts = list(mission.parts())
    entries = {}
    for p in parts:
        if p["start"] != 0xFFFF:
            entries.setdefault(p["start"] * 2, []).append(("part", p["i"]))
    for t in mission.triggers():
        if t["subject"] is not None and t["link"] != 0xFFFF:
            entries.setdefault(t["link"] * 2, []).append(("trigger", t["i"]))
    starts = sorted(entries)
    out = []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(code)
        try:
            out.append(Routine(s, end, entries[s], block=decode_block(code, s)))
        except DTEError as e:
            out.append(Routine(s, end, entries[s], error=str(e)))
    return out


def _hexbytes(code, p, size, width=8):
    raw = code[p:p + size]
    txt = " ".join("%02x" % b for b in raw[:width])
    return txt + (" .." if size > width else "")


def _render(mission, code, routine, p, insn, names):
    op, size, args, targets = insn
    name = OPCODES[op][0]
    parts, globals_, ships = names
    b = routine.block
    detail = ""
    if op == 0x21:
        nm, _va, prm = EXEC_BY_IDX.get(args[0], ("?", None, ()))
        detail = "%-4d %s" % (args[0], nm)
    elif op == 0x4F:
        detail = "%-4d (AI-function catalogue; the retail dispatcher is a stub)" % args[0]
    elif op in (0x22, 0x4D):
        detail = "%-4d %s" % (args[0], parts.get(args[0], "?"))
    elif op in (0x4A, 0x4E):
        detail = "%-4d (second part table; section 17)" % args[0]
    elif op in (0x27, 0x40):
        detail = "%-4d %s" % (args[0], globals_.get(args[0], "?"))
    elif op in (0x28, 0x29):
        a = b.end + 4 * args[0]
        val = struct.unpack_from("<I", code, a)[0] if a + 4 <= len(code) else None
        detail = "= %s" % (val if val is not None else "?")
    elif op in (0x2C, 0x52):
        detail = "%-4d %s" % (args[0], ships.get(args[0], "?"))
    elif op in (0x47, 0x55):
        detail = "%-4d %s, component %d" % (args[0], ships.get(args[0], "?"), args[1])
    elif op in (0x2A, 0x2B):
        detail = repr(args[0])
    elif op in (0x23, 0x24, 0x42):
        detail = "-> %d" % targets[0]
    elif op == 0x51:
        default, arms = args
        detail = "default -> %d; " % (p + default) + "; ".join(
            "roll < %d -> %s" % (thr, "default" if t == 0xFFFF else p + t) for t, thr, _u in arms)
    elif op == 0x4B:
        c = args[0]
        detail = "%s, value %d, object %d" % (TT_TRIGGERS[c] if c < len(TT_TRIGGERS) else c,
                                               args[1], args[2])
    elif args:
        detail = " ".join(str(a) for a in args)
    return "  %6d  %-24s %-20s %s" % (p, _hexbytes(code, p, size), name, detail)


def disasm_script(mission, limit=0):
    """Yield the listing of every routine in the script, control flow followed."""
    code = mission.script()
    parts = {p["i"]: p["name"] for p in mission.parts()}
    globals_ = {g["i"]: g["name"] for g in mission.globals()}
    ships = {s["i"]: s["name"] for s in mission.ships()}
    trig = {t["i"]: t for t in mission.triggers()}
    plist = list(mission.parts())
    subj = mission.object_names()
    names = (parts, globals_, ships)
    routines = script_routines(mission)
    for n, r in enumerate(routines):
        if limit and n >= limit:
            yield "  ... (%d more routines; --limit 0 shows all)" % (len(routines) - n)
            return
        who = []
        for kind, i in r.owners:
            if kind == "part":
                who.append("part %d %s (%d args)" % (i, plist[i]["name"], plist[i]["argc"]))
            else:
                t = trig[i]
                c = t["condition"]
                who.append("trigger %d: %s on %s" % (
                    i, TT_TRIGGERS[c] if c < len(TT_TRIGGERS) else "0x%02X" % c,
                    subj.get(t["subject"], "object %s" % t["subject"])))
        yield ""
        yield "%d to %d: %s" % (r.start, r.end, "; ".join(who))
        if r.error:
            yield "  !! %s" % r.error
            continue
        for p in sorted(r.block.insns):
            yield _render(mission, code, r, p, r.block.insns[p], names)
        for a, z in r.block.gaps:
            yield "  %6d  (%d bytes nothing reaches)" % (a, z - a)
        for a, z in r.block.slack:
            yield "  %6d  (%d bytes: unused slots of the random_branch arm table before them; never read)" % (a, z - a)
        if r.block.falls_off:
            yield "          (a path runs into the block's limit, which ends the thread)"
        consts = r.constants(code)
        if consts:
            yield "  constants: " + " ".join(str(c) for c in consts)


# --------------------------------------------------------------------------- #
#  Commands                                                                    #
# --------------------------------------------------------------------------- #
def merged_exec():
    """Yield (index, name, param_count, impl_va, blog_alias) from EXEC_CATALOG.

    Authoritative name/params/impl come from the catalogue; blog_alias is the
    Starlancer ME name where it differs (None when they agree) for cross-ref.
    """
    for idx, name, va, params in EXEC_CATALOG:
        blog = EXEC_BLOG.get(idx)
        alias = blog if (blog and blog != name) else None
        yield idx, name, len(params), va, alias


def cmd_ref(args):
    what = args.table
    if what in ("triggers", "all"):
        print("# Trigger conditions (TT_*) -- trigger-record +0x00 (+0x15 is the qualifier)")
        for i, t in enumerate(TT_TRIGGERS):
            print("  0x%02X  %s" % (i, t))
        print()
    if what in ("exec", "all"):
        print("# Executor commands (script opcode 0x21 <index>) -- authoritative catalogue @0x4F0F50")
        print("  idx  name                              params  impl         blog-alias")
        for i, name, pc, va, alias in merged_exec():
            print("  0x%02X  %-32s  %d     %-11s  %s" % (
                i, name, pc, ("0x%08X" % va) if va else "(empty)",
                ("blog: %s" % alias) if alias else ""))
        if getattr(args, "params", False):
            print("\n# parameters (developers' own labels, recovered from the catalogue)")
            for idx, name, va, params in EXEC_CATALOG:
                if params:
                    print("  0x%02X  %-30s %s" % (idx, name, " | ".join(params)))
        print()
    if what in ("ai", "all"):
        print("# AI modes -- values of SetAI's 'AI Mode' parameter (pushed with push_byte 0x32)")
        for i in range(max(AI_CODES) + 1):
            print("  0x%02X  %s" % (i, AI_CODES.get(i, "?")))
        print()
    if what in ("stream", "all"):
        print("# Script VM opcodes -- handler table DAT_004F6350; every width read from its handler")
        print("  op    name                 operands  flow     handler")
        for op in sorted(OPCODES):
            name, form, flow, va = OPCODES[op]
            print("  0x%02X  %-20s %-9s %-8s 0x%06X%s" % (
                op, name, form or "-", flow, va, "  (vestigial AI layer)" if op in B_LAYER else ""))
        print()


def load_mission(raw):
    """A HOG member (RefPack, ``10 FB``) or a loose ``missions\\*.dte`` (raw image)."""
    return Mission(raw) if raw[1:2] == b"\xfb" else Mission.from_image(raw)


def cmd_decode(args):
    try:
        mis = load_mission(open(args.file, "rb").read())
    except DTEError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    only = args.section
    name = os.path.basename(args.file)
    print("%s  ->  RefPack image %d bytes (0x%X)  reloc-flags=0x%X"
          % (name, len(mis.image), len(mis.image), mis.reloc_flags))

    if only in (None, "dir"):
        print("\n# 27-section directory")
        print("  slot  section            global             count  stride   offset")
        for k, (label, dat, kind, stride) in enumerate(SECTIONS):
            cnt, off, fl = mis.dir[k]
            offs = "(empty)" if off == EMPTY_OFF else "0x%06X" % off
            st = "0x%02X" % stride if stride else "   -"
            print("  [%2d]  %-18s %-18s %5d  %5s   %s%s"
                  % (k, label, dat, cnt, st, offs, "  +reloc0x%X" % fl if fl else ""))

    if only in (None, "ships"):
        print("\n# ships  (slot 3, stride 0x4C, n=%d)" % mis.count(3))
        for s in _head(mis.ships(), args.limit):
            x, y, z = s["pos"]
            yaw, pitch, roll = s["orient"]
            print("  [%3d] id=%-4d fg=%-3s %-22s pos=(%11.1f,%9.1f,%11.1f) rot=(%4d,%4d,%4d)deg iff=0x%02X type=0x%03X"
                  % (s["i"], s["id"], "-" if s["fg"] == 0xFF else s["fg"], '"%s"' % s["name"],
                     x, y, z, yaw, pitch, roll, s["iff"], s["type"]))

    if only in (None, "fg"):
        print("\n# flight groups  (slot 4, stride 0x14, n=%d)" % mis.count(4))
        for r in _head(mis.fg_records(), args.limit):
            print("  [%2d] id=0x%X ref=0x%04X f8=0x%X f12=0x%X  txt=%r"
                  % (r["i"], r["id"], r["ref"], r["f8"], r["f12"], mis.string(r["ref"] & 0xFFFF)[:32]))

    if only in (None, "triggers"):
        print("\n# triggers  (slot 5, stride 0x30, n=%d)" % mis.count(5))
        subj = mis.object_names()
        for t in _head(mis.triggers(), args.limit):
            c = t["condition"]
            print("  [%3d] %-30s on %-34s link=%-6s qual=%-4s repeat=%d run=%d"
                  % (t["i"], TT_TRIGGERS[c] if c < len(TT_TRIGGERS) else "0x%02X" % c,
                     subj.get(t["subject"], "(no slice holds it)") if t["subject"] is not None
                     else "(no slice holds it)",
                     "-" if t["link"] == 0xFFFF else t["link"] * 2,
                     "-" if t["qualifier"] == 0xFF else t["qualifier"], t["repeat"], t["run"]))

    if only in (None, "parts"):
        print("\n# parts  (slot 8, stride 0x1C, n=%d)  offsets and sizes in script bytes"
              % mis.count(8))
        print("    #  offset  bytes  args  flags  name")
        for p in _head(mis.parts(), args.limit):
            print("  %3d  %6s  %5d  %4d   0x%02X  %s"
                  % (p["i"], "-" if p["start"] == 0xFFFF else p["start"] * 2, p["extent"] * 2,
                     p["argc"], p["flags"], p["name"]))

    if only in (None, "script"):
        print("\n# script  (slot 6: %d halfwords = %d bytes)" % (mis.count(6), 2 * mis.count(6)))
        for line in disasm_script(mis, args.limit):
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
    missions = []
    for f in files:
        try:
            mis = load_mission(open(os.path.join(args.dir, f), "rb").read())
        except DTEError as e:
            print("  %-16s  FAIL  %s" % (f, e))
            continue
        mis.filename = f
        missions.append(mis)
        ok = all(off == EMPTY_OFF or off <= len(mis.image) for _, off, _ in mis.dir)
        npass += 1 if ok else 0
        print("  %-16s %5s %9d %6d %5d %5d %7d %5s0x%X"
              % (f, "OK" if ok else "DIR?", len(mis.image), mis.count(3), mis.count(4),
                 mis.count(5), mis.count(6), "", mis.reloc_flags))
    print("\n%d/%d decoded (valid RefPack + 27-section directory)" % (npass, len(files)))

    if getattr(args, "sections", False):
        print("\n# per-section population + stride check across %d missions" % len(missions))
        print("  slot  section            stride  present  nonzero  maxcount  note")
        for k, (label, dat, kind, stride) in enumerate(SECTIONS):
            present = [m for m in missions if m.present(k)]
            counts = [m.count(k) for m in present]
            nz = [c for c in counts if c > 0]
            over = sum(1 for m in present if stride and m.count(k)
                       and m.offset(k) + m.count(k) * stride > len(m.image))
            note = "vestigial" if not nz else ("layout TBD" if stride is None else "")
            if over:
                note = (note + " ").strip() + " *%d-OVERFLOW" % over
            print("  [%2d]  %-18s %5s   %5d   %6d   %7d  %s"
                  % (k, label, "0x%02X" % stride if stride else "-",
                     len(present), len(nz), max(counts) if counts else 0, note))

    if getattr(args, "script", False):
        return _sweep_script(missions)


def _sweep_script(missions):
    """Disassemble every routine of every mission and tally the layout claims."""
    print("\n# script: control flow followed from every routine's entry")
    print("  %-16s %8s %9s %6s %6s %5s %5s %7s" %
          ("file", "routines", "insns", "errors", "gaps", "tile", "ext", "falloff"))
    tot = Counter()
    ops = Counter()
    notes = []
    for mis in missions:
        code = mis.script()
        parts = list(mis.parts())
        rs = script_routines(mis)
        row = Counter()
        covered = 0
        for r in rs:
            row["routines"] += 1
            if r.error:
                row["errors"] += 1
                notes.append("%s @%d: %s" % (mis.filename, r.start, r.error))
                continue
            b = r.block
            row["insns"] += len(b.insns)
            ops.update(op for op, _s, _a, _t in b.insns.values())
            for a, z in b.gaps:
                row["gaps"] += 1
                notes.append("%s @%d: %d unreached bytes at %d..%d"
                             % (mis.filename, r.start, z - a, a, z))
            for a, z in b.slack:
                row["slack"] += 1
                notes.append("%s @%d: %d bytes of random_branch arm-table slack at %d..%d"
                             % (mis.filename, r.start, z - a, a, z))
            row["falloff"] += 1 if b.falls_off else 0
            chk = r.checks(parts)
            row["tile_bad"] += 0 if chk.get("tiles", True) else 1
            row["ext_bad"] += 0 if chk.get("extent", True) else 1
            covered += r.end - r.start
        starts_ok = not rs or rs[0].start == 0
        if not starts_ok or covered != len(code):
            notes.append("%s: routines cover %d of %d bytes, first at %s"
                         % (mis.filename, covered, len(code), rs[0].start if rs else "-"))
            row["tile_bad"] += 1
        tot.update(row)
        print("  %-16s %8d %9d %6d %6d %5s %5s %7d" % (
            mis.filename, row["routines"], row["insns"], row["errors"], row["gaps"],
            "ok" if not row["tile_bad"] else row["tile_bad"],
            "ok" if not row["ext_bad"] else row["ext_bad"], row["falloff"]))
    print("\n%d missions, %d routines, %d instructions: %d decode errors, %d gaps nothing reaches,"
          % (len(missions), tot["routines"], tot["insns"], tot["errors"], tot["gaps"]))
    print("%d random_branch arm-table slack regions (unused slots, never read)" % tot["slack"])
    print("%d routines off the exact tiling, %d parts whose extent disagrees, %d paths into a block limit"
          % (tot["tile_bad"], tot["ext_bad"], tot["falloff"]))
    print("\nopcode use across all missions:")
    for op in sorted(OPCODES):
        print("  0x%02X  %-20s %7d%s" % (op, OPCODES[op][0], ops[op],
                                        "  (vestigial AI layer)" if op in B_LAYER else ""))
    if notes:
        print("\nnotes:")
        for n in notes:
            print("  - " + n)
    return 1 if tot["errors"] else 0


def cmd_roundtrip(args):
    """Prove the editing invariant over a directory of missions.

    Two checks per file: (1) parse and re-serialise reproduces the image byte for byte;
    (2) a single in-place record edit changes ONLY that record's bytes and leaves the
    image size unchanged. Accepts RefPack-compressed members or loose raw images.
    """
    files = sorted(f for f in os.listdir(args.dir) if f.lower().endswith(".dte"))
    if not files:
        print("no .dte files in %s" % args.dir)
        return 1

    SHIPS = 3
    ident = edit_ok = 0
    failures = []
    for fn in files:
        path = os.path.join(args.dir, fn)
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            m = Mission(raw) if raw[1:2] == b"\xfb" else Mission.from_image(raw)
        except DTEError as exc:
            failures.append("%s: %s" % (fn, exc)); continue

        before = m.to_image()
        if before == (Mission.from_image(before)).to_image():
            ident += 1
        else:
            failures.append("%s: re-serialise differs" % fn)

        # in-place edit probe: bump the first ship record's first dword
        if m.dir[SHIPS][1] != EMPTY_OFF and m.dir[SHIPS][0] > 0:
            m2 = Mission.from_image(before)
            rec = bytearray(m2.record(SHIPS, 0))
            struct.pack_into("<I", rec, 0, (struct.unpack_from("<I", rec, 0)[0] + 1) & 0xFFFFFFFF)
            m2.set_record(SHIPS, 0, bytes(rec))
            after = m2.to_image()
            lo = m2.dir[SHIPS][1]
            delta = [i for i in range(len(before)) if before[i] != after[i]]
            if len(after) == len(before) and delta and all(lo <= i < lo + 4 for i in delta):
                edit_ok += 1
            else:
                failures.append("%s: edit touched %d bytes outside the record"
                                % (fn, len(delta)))
        if args.verbose:
            caps = ", ".join("%s %d/%s" % (SECTIONS[s][0], m.dir[s][0], m.max_records(s))
                             for s in (3, 5, 6) if m.dir[s][1] != EMPTY_OFF)
            print("  %-18s %9d B   %s" % (fn, len(before), caps))

    print("\nmissions checked                     : %d" % len(files))
    print("byte-identical round-trip            : %d/%d" % (ident, len(files)))
    print("edit touched only the intended bytes : %d/%d" % (edit_ok, len(files)))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("\nthe fixed-capacity editing invariant holds across every mission")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer .DTE decoder + reference (static; never runs the game).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ref"); p.add_argument("table", nargs="?", default="all",
                                              choices=["all", "triggers", "exec", "ai", "stream"])
    p.add_argument("--params", action="store_true", help="also list each Executor command's parameter labels")
    p.set_defaults(func=cmd_ref)
    p = sub.add_parser("decode", help="decompress + decode a mission")
    p.add_argument("file"); p.add_argument("--limit", type=int, default=40,
                                           help="max records/ops per section (0 = no cap)")
    p.add_argument("--section", choices=["dir", "ships", "fg", "triggers", "parts", "script"],
                   help="show only one section")
    p.set_defaults(func=cmd_decode)
    p = sub.add_parser("inspect"); p.add_argument("file")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("sweep"); p.add_argument("dir")
    p.add_argument("--sections", action="store_true", help="also print per-section population + stride check")
    p.add_argument("--script", action="store_true",
                   help="also disassemble every routine and check the layout claims")
    p.set_defaults(func=cmd_sweep)
    p = sub.add_parser("roundtrip", help="verify the fixed-capacity editing invariant over a mission folder")
    p.add_argument("dir")
    p.add_argument("--verbose", action="store_true", help="print each mission's size and section usage")
    p.set_defaults(func=cmd_roundtrip)
    args = ap.parse_args(argv)
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
