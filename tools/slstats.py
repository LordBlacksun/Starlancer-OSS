#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""slstats.py - Starlancer SHIPSTATS / GUNSTATS / MISSILESTATS.BIN editor.

All three tables are flat arrays of fixed 352-byte records:

    0x00  char  name[64]      NUL-padded ASCII. For ships the faction is encoded
                              as a name prefix ("Us "/"Uk "/"Ger "/"Jap "/"Fr "/
                              "It " = Alliance; "Ussr "/"Chi "/"Mid "/... = Coalition).
    0x40  float32 stats[15]   little-endian. Meaning depends on the table (ship
                              flight/combat vs gun vs missile - see *_FIELDS below).
    0x7C..0x160               further per-record data (loadout/geometry); NOT yet
                              decoded - preserved verbatim on every write.

Field layouts reverse-engineered 2026-06-08 by diffing the originals against the
`hexcheat` known-delta mod pack (see docs/stats-format.md). Confirmed offsets are
unmarked; provisional ones print '(?provisional)'.

Commands:
    list  <file.bin>                                  index / name / faction / key stats
    show  <file.bin> <index|name>                     labelled + raw field dump
    dump  <file.bin> [-o out.csv]                     export every record to CSV
    set   <file.bin> <index|name> <field> <value> -o <out.bin>   edit one float field
"""
import argparse
import csv
import math
import os
import struct
import sys

RECSIZE = 352
NAME_LEN = 64
STAT_BASE = 0x40
NSTATS = 15

# (offset, label, confirmed?)
SHIP_FIELDS = [
    (0x40, "MaxSpeed",        True),
    (0x44, "Inertia",         True),
    (0x48, "YawMax",          True),
    (0x4C, "YawInertia",      True),
    (0x50, "PitchMax",        True),
    (0x54, "PitchInertia",    True),
    (0x58, "RollMax",         True),
    (0x5C, "RollInertia",     True),
    (0x60, "ShieldStrength",  False),
    (0x64, "ArmorStrength",   False),
    (0x68, "AfterburnerFuel", False),
    (0x6C, "ShieldRecharge",  False),
    (0x70, "GunEnergy",       False),
    (0x74, "GunRecharge",     False),
    (0x78, "Ammo",            False),
]
# The damage, flight-time and lock-range labels are the names openreliant's engine code gives
# these offsets (src/formats/stats.zig, 2026-09-29): a gun's damage is a pair, to shields then
# to the hull; a missile's range is its speed times its flight time.
GUN_FIELDS = [
    (0x40, "Range",         True),
    (0x48, "ShieldDamage",  True),
    (0x4C, "HullDamage",    True),
    (0x50, "CyclicRate",    True),
    (0x54, "EnergyPerShot", False),
]
MISSILE_FIELDS = [
    (0x40, "MaxVelocity", True),
    (0x48, "FlightTime",  True),
    (0x54, "LockTime",    True),
    (0x5C, "LockRange",   True),
]
# The labels those offsets had before; `set` still takes them, so scripts keep working.
OLD_LABELS = {
    "gun": {"damagemin": 0x48, "damagemax": 0x4C},
    "missile": {"range": 0x48, "agility": 0x5C},
}
F32_MAX = 3.4028234663852886e38

ALLIANCE_PREFIXES = ("us", "uk", "ger", "jap", "fr", "it")
COALITION_PREFIXES = ("ussr", "chi", "mid", "arc", "kalan", "sky")


def _table(path):
    base = os.path.basename(path).lower()
    if "gun" in base:
        return "gun"
    if "missile" in base:
        return "missile"
    return "ship"


def fields_for(path):
    return {"gun": GUN_FIELDS, "missile": MISSILE_FIELDS}.get(_table(path), SHIP_FIELDS)


def field_offset(path, name):
    """A field's offset in `path`'s table, by its label, an old label, or a number like 0x48.
    Raises ValueError for anything else."""
    fl = name.lower()
    for off, lbl, _ in fields_for(path):
        if lbl.lower() == fl:
            return off
    old = OLD_LABELS.get(_table(path), {}).get(fl)
    if old is not None:
        return old
    try:
        off = int(name, 0)
    except ValueError:
        raise ValueError(f"no field {name!r}")
    if not (STAT_BASE <= off < STAT_BASE + NSTATS * 4) or off % 4:
        raise ValueError(f"bad field offset {name}")
    return off


def parse_value(text):
    """`text` as a stat value, or ValueError: a finite number a float32 can hold."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError(f"{text!r} is not a number")
    if not math.isfinite(value) or abs(value) > F32_MAX:
        raise ValueError(f"{text!r} is outside what a stat field can hold")
    return value


def load(path):
    data = bytearray(open(path, "rb").read())
    if len(data) % RECSIZE:
        print(f"warning: size {len(data)} not a multiple of {RECSIZE}", file=sys.stderr)
    return data


def num_records(data):
    return len(data) // RECSIZE


def rec_name(data, i):
    raw = bytes(data[i * RECSIZE: i * RECSIZE + NAME_LEN])
    return raw.split(b"\x00", 1)[0].decode("latin-1")


def faction(name):
    pre = name.split(" ", 1)[0].lower() if " " in name else ""
    if pre in ALLIANCE_PREFIXES:
        return "Alliance"
    if pre in COALITION_PREFIXES:
        return "Coalition"
    return "-"


def stat(data, i, off):
    return struct.unpack_from("<f", data, i * RECSIZE + off)[0]


def set_stat(data, i, off, value):
    if not math.isfinite(value) or abs(value) > F32_MAX:
        raise ValueError(f"{value!r} is outside what a stat field can hold")
    struct.pack_into("<f", data, i * RECSIZE + off, value)


def find_record(data, key):
    """key may be an integer index or a (case-insensitive) name; exact match wins."""
    try:
        idx = int(key)
        if 0 <= idx < num_records(data):
            return idx
    except ValueError:
        pass
    kl = key.lower()
    exact = [i for i in range(num_records(data)) if rec_name(data, i).lower() == kl]
    if len(exact) == 1:
        return exact[0]
    hits = [i for i in range(num_records(data)) if kl in rec_name(data, i).lower()]
    if not hits:
        sys.exit(f"no record matching {key!r}")
    if len(hits) > 1:
        opts = ", ".join(f"{i}:{rec_name(data,i)!r}" for i in hits[:12])
        sys.exit(f"ambiguous {key!r} -> {opts}{' ...' if len(hits) > 12 else ''}")
    return hits[0]


def cmd_list(args):
    data = load(args.file)
    n = num_records(data)
    flds = fields_for(args.file)[:3]
    print(f"{args.file}: {n} records x {RECSIZE} bytes")
    print(f"{'idx':>4}  {'name':<26} {'faction':<9}" + "".join(f" {lbl:>11}" for _, lbl, _ in flds))
    for i in range(n):
        name = rec_name(data, i)
        if not name:
            continue
        cols = "".join(f" {stat(data,i,off):>11.4g}" for off, _, _ in flds)
        print(f"{i:>4}  {name:<26} {faction(name):<9}{cols}")


def cmd_show(args):
    data = load(args.file)
    i = find_record(data, args.record)
    name = rec_name(data, i)
    print(f"record {i}: {name!r}   faction={faction(name)}")
    for off, label, conf in fields_for(args.file):
        mark = "" if conf else "  (?provisional)"
        print(f"  +0x{off:02X}  {label:<16} = {stat(data,i,off):<12.5g}{mark}")
    raws = " ".join(f"{stat(data,i,0x40+4*k):g}" for k in range(NSTATS))
    print(f"  raw stats[0..14] @0x40: {raws}")
    tail = bytes(data[i * RECSIZE + 0x7C: i * RECSIZE + 0x7C + 32])
    print("  tail 0x7C..: " + " ".join(f"{b:02x}" for b in tail))


def cmd_dump(args):
    data = load(args.file)
    flds = fields_for(args.file)
    out = open(args.out, "w", newline="") if args.out else sys.stdout
    w = csv.writer(out)
    w.writerow(["index", "name", "faction"] + [n for _, n, _ in flds])
    for i in range(num_records(data)):
        name = rec_name(data, i)
        w.writerow([i, name, faction(name)] + [f"{stat(data,i,off):g}" for off, _, _ in flds])
    if args.out:
        out.close()
        print(f"wrote {args.out}")


def cmd_set(args):
    if not args.out and not args.inplace:
        sys.exit("refusing to write in place: pass -o <out.bin> (or --inplace)")
    data = load(args.file)
    i = find_record(data, args.record)
    try:
        off = field_offset(args.file, args.field)
        value = parse_value(args.value)
    except ValueError as e:
        sys.exit(str(e))
    old = stat(data, i, off)
    set_stat(data, i, off, value)
    dest = args.file if args.inplace else args.out
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"record {i} ({rec_name(data,i)!r})  +0x{off:02X}: {old:g} -> {value:g}")
    print(f"wrote {dest}")


def selftest():
    """Field labels and value checks against a synthetic table. No game data is involved."""
    fails = []

    def check(cond, label):
        print("  %-4s %s" % ("ok" if cond else "FAIL", label))
        if not cond:
            fails.append(label)

    def refuses(fn, *a):
        try:
            fn(*a)
        except ValueError:
            return True
        except Exception:                     # noqa: BLE001 - any other raise is the bug
            return False
        return False

    print("=== slstats self-test (synthetic table) ===")
    gun = {off: lbl for off, lbl, _ in GUN_FIELDS}
    missile = {off: lbl for off, lbl, _ in MISSILE_FIELDS}
    # the labels openreliant's engine code gives these offsets (src/formats/stats.zig)
    check(gun.get(0x48) == "ShieldDamage" and gun.get(0x4C) == "HullDamage",
          "gun 0x48/0x4C are the shield and hull damage")
    check(missile.get(0x48) == "FlightTime", "missile 0x48 is the flight time")
    check(missile.get(0x5C) == "LockRange", "missile 0x5C is the lock range")

    parse = globals().get("parse_value")
    check(parse is not None, "parse_value exists")
    if parse is not None:
        check(parse("12.5") == 12.5 and parse("-3") == -3.0, "ordinary numbers parse")
        for text in ("nan", "inf", "-inf", "1e39", "abc", ""):
            check(refuses(parse, text), "%r is refused" % text)

    data = bytearray(RECSIZE)
    set_stat(data, 0, 0x40, 1.0)
    before = bytes(data)
    check(refuses(set_stat, data, 0, 0x40, float("nan")) and bytes(data) == before,
          "set_stat refuses nan and leaves the record untouched")
    check(refuses(set_stat, data, 0, 0x40, 1e39) and bytes(data) == before,
          "set_stat refuses 1e39 with a ValueError, not an OverflowError")

    offset = globals().get("field_offset")
    check(offset is not None, "field_offset exists")
    if offset is not None:
        check(offset("gunstats.bin", "ShieldDamage") == 0x48, "a field is found by its label")
        check(offset("gunstats.bin", "damagemin") == 0x48 and
              offset("missilestats.bin", "Range") == 0x48 and
              offset("missilestats.bin", "agility") == 0x5C,
              "the old labels still work, so scripts using them keep working")
    print("slstats self-test: %d failed" % len(fails))
    return 1 if fails else 0


def main(argv=None):
    if (argv if argv is not None else sys.argv[1:])[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description="Starlancer stat-table (.BIN) editor.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("file"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("file"); p.add_argument("record"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("dump"); p.add_argument("file"); p.add_argument("-o", "--out"); p.set_defaults(fn=cmd_dump)
    p = sub.add_parser("set")
    p.add_argument("file"); p.add_argument("record"); p.add_argument("field"); p.add_argument("value")
    p.add_argument("-o", "--out"); p.add_argument("--inplace", action="store_true")
    p.set_defaults(fn=cmd_set)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
