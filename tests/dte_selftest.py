#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""Self-test for the script disassembler in tools/dte_parse.py.

Builds a synthetic mission image in memory (per docs/dte-format.md): a
27-entry directory, a string pool, one global, one ship, one trigger held by
the ship's slice of the object table, one part, and a script of two routines
hand-assembled to exercise every control-flow form -- a branch, a jump, a
random_branch with arm-table slack, a call, an inline string and both widths
of push_constant.  Then it checks that a misread operand width cannot pass
silently.  No game files needed.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import dte_parse as D


def be(n):
    return bytes([n >> 8 & 0xFF, n & 0xFF])


# Routine A, the trigger's block, at script offset 0 (offsets in the comments).
ROUTINE_A = (
    struct.pack("<H", 52)                 # 0   length 52, counts itself
    + b"\x22\x00"                         # 2   call_part 0
    + b"\x27\x00"                         # 4   push_global 0
    + b"\x28\x00"                         # 6   push_constant 0
    + b"\x02"                             # 8   equal
    + b"\x24" + be(25 - 10)               # 9   branch_if_zero -> 25 (counted from 10)
    + b"\x2a\x07a.wav\x00"                # 12  push_string "a.wav" (length counts itself)
    + b"\x21\x06"                         # 20  command 6 PlaySpeech
    + b"\x42" + be(49 - 23)               # 22  jump -> 49 (counted from 23)
    + b"\x51\x02" + be(49 - 25)           # 25  random_branch, 2 arms, default -> 49
    + be(43 - 25) + b"\x32\x2c"           #     arm: roll < 50 -> 43 (last byte: never read)
    + be(46 - 25) + b"\x64\x42"           #     arm: roll < 100 -> 46
    + b"\x2c\x00\x32\x0a\x28\x00"         # 37  six bytes of slack: stale, never read
    + b"\x2e\x05"                         # 43  push_byte 5
    + b"\x53"                             # 45  nop, falls into the second arm
    + b"\x2e\x06"                         # 46  push_byte 6
    + b"\x53"                             # 48  nop, falls into the join
    + b"\x32\x01"                         # 49  push_byte 1
    + b"\x43"                             # 51  return; the block ends at 52, already aligned
    + struct.pack("<II", 1, 0)            # 52  constant 0 = 1, then the filler to 8 bytes
)
assert len(ROUTINE_A) == 60

# Routine B, part 0, at script offset 60.
ROUTINE_B = (
    struct.pack("<H", 12)                 # 60  length 12
    + b"\x31\x00"                         # 62  push_argument 0
    + b"\x29" + be(1)                     # 64  push_constant_wide 1
    + b"\x1b"                             # 67  add
    + b"\x43"                             # 68  return
    + b"\x00\x00\x00"                     # 69  padding to 72
    + struct.pack("<II", 10, 20)          # 72  constants 0 and 1
)
assert len(ROUTINE_B) == 20
SCRIPT = ROUTINE_A + ROUTINE_B            # 80 bytes = 40 halfwords


def build_image():
    pool = b"Hero\x00(GV)flag\x00(F)test\x00"
    name_hero, name_flag, name_part = 0, 5, 14
    ship = bytearray(0x4C)
    struct.pack_into("<IH", ship, 0, 0, name_hero)      # object ID 0, name
    ship[0x14] = 0xFF                                   # in no flight group
    glob = struct.pack("<HHI", name_flag, 0, 1) + bytes(4)
    trig = bytearray(0x30)
    trig[0x00] = 0x01                                   # TT_DESTROYED
    struct.pack_into("<H", trig, 2, 0)                  # link: halfword 0
    trig[0x14], trig[0x15] = 1, 0xFF                    # armed; the subject itself
    obj = struct.pack("<BBHI", 0, 1, 0, 0)              # object 0: a ship, 1 trigger from 0
    part = bytearray(0x1C)
    struct.pack_into("<H", part, 0x00, name_part)
    struct.pack_into("<H", part, 0x0A, 60 // 2)         # start, halfwords
    part[0x0D] = 1                                      # one argument
    struct.pack_into("<H", part, 0x10, 20 // 2)         # extent, halfwords
    sections = {0: (len(pool), pool), 2: (1, glob), 3: (1, bytes(ship)),
                5: (1, bytes(trig)), 6: (len(SCRIPT) // 2, SCRIPT), 7: (1, obj),
                8: (1, bytes(part))}
    directory = bytearray(27 * 8)
    body = bytearray()
    base = len(directory)
    for k in range(27):
        if k in sections:
            count, blob = sections[k]
            struct.pack_into("<II", directory, k * 8, count | (0xF << 24), base + len(body))
            body += blob + bytes(-len(blob) % 4)
        else:
            struct.pack_into("<II", directory, k * 8, 0, D.EMPTY_OFF)
    return bytes(directory + body)


def expect_error(fn, needle):
    try:
        fn()
    except D.DTEError as e:
        assert needle in str(e), "wrong error: %s" % e
        return str(e)
    raise AssertionError("expected a DTEError mentioning %r" % needle)


def main():
    # -- the instruction set itself --------------------------------------
    assert len(D.OPCODES) == 71, len(D.OPCODES)
    nulls = set(range(0x56)) - set(D.OPCODES)
    assert nulls == {0x00, 0x01, 0x50} | set(range(0x08, 0x14)), sorted(nulls)
    by_handler = {}
    for op, row in D.OPCODES.items():
        by_handler.setdefault(row[3], []).append(op)
    shared = sorted(tuple(v) for v in by_handler.values() if len(v) > 1)
    assert shared == [(0x23, 0x24), (0x25, 0x43), (0x2A, 0x2B), (0x2E, 0x32), (0x47, 0x55)], shared
    print("opcode table OK: 71 opcodes, 15 null slots, 5 shared handlers")

    # -- one block, control flow followed -------------------------------
    b = D.decode_block(SCRIPT, 0)
    assert sorted(b.insns) == [2, 4, 6, 8, 9, 12, 20, 22, 25, 43, 45, 46, 48, 49, 51], sorted(b.insns)
    assert b.insns[9][3] == [25] and b.insns[22][3] == [49], (b.insns[9], b.insns[22])
    assert b.insns[25][3] == [49, 43, 46], b.insns[25]
    assert b.insns[12][2] == ("a.wav",) and b.insns[12][1] == 8, b.insns[12]
    assert b.gaps == [] and b.slack == [(37, 43)], (b.gaps, b.slack)
    assert b.padding == 0 and b.nconst == 1 and b.const_bytes == 8, (b.padding, b.nconst)
    b2 = D.decode_block(SCRIPT, 60)
    assert sorted(b2.insns) == [62, 64, 67, 68] and b2.padding == 3 and b2.nconst == 2
    print("blocks OK: branch, jump, random_branch (with slack), string, both constant widths")

    # -- a whole mission ------------------------------------------------
    m = D.Mission.from_image(build_image())
    rs = D.script_routines(m)
    assert [(r.start, r.end, r.owners) for r in rs] == [
        (0, 60, [("trigger", 0)]), (60, 80, [("part", 0)])], [(r.start, r.end, r.owners) for r in rs]
    parts = list(m.parts())
    assert all(r.checks(parts) == ({"tiles": True} if r.start == 0 else {"tiles": True, "extent": True})
               for r in rs), [r.checks(parts) for r in rs]
    assert rs[1].constants(m.script()) == [10, 20]
    listing = "\n".join(D.disasm_script(m))
    for needle in ('trigger 0: TT_DESTROYED on ship 0 "Hero"', "part 0 (F)test (1 args)",
                   "PlaySpeech", "(GV)flag", "= 1", "'a.wav'", "roll < 50 -> 43",
                   "unused slots of the random_branch arm table", "constants: 10 20"):
        assert needle in listing, "listing lacks %r:\n%s" % (needle, listing)
    print("mission OK: 2 routines tile the script; parts, triggers and names resolve")

    # -- a misread must not pass silently ---------------------------------
    bad = bytearray(SCRIPT)
    bad[11] = 13 - 10                      # branch into the middle of push_string
    print("  caught:", expect_error(lambda: D.decode_block(bytes(bad), 0), "overlap"))
    bad = bytearray(SCRIPT)
    bad[45] = 0x09                         # a null opcode on a reached path
    print("  caught:", expect_error(lambda: D.decode_block(bytes(bad), 0), "null opcode"))
    bad = bytearray(SCRIPT)
    bad[23:25] = be(80)                    # jump out of the block
    print("  caught:", expect_error(lambda: D.decode_block(bytes(bad), 0), "outside"))
    saved = D.OPCODES[0x2A]
    try:                                   # the old tool's width for 0x2A: one byte
        D.OPCODES[0x2A] = ("push_string", "b", "seq", saved[3])
        print("  caught:", expect_error(lambda: D.decode_block(SCRIPT, 0), "null opcode"))
    finally:
        D.OPCODES[0x2A] = saved
    print("tripwires OK: overlap, null opcode, escape and a wrong width all raise")
    print("SELFTEST PASSED")


if __name__ == "__main__":
    main()
