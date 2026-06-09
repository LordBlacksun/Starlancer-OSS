#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""slswitch.py - Starlancer Coalition ship-switcher (data-layer).

Replicates the "ship switcher" from *SLEdit* (by Dustin) at the file level: swaps a fighter's 3D
model inside resource.hog so the player flies a different ship (e.g. a Coalition
fighter) when they pick an Alliance slot in the loadout screen.

Fighter models are named  <Nation>_<Ship>.SHP  with a Tiger/45th-squadron variant
t_<Nation>_<Ship>.SHP. Per the SLEdit readme the switcher replaces BOTH the
standard and the Tiger model together - this tool does that automatically
(Coalition ships have no Tiger model, so the slot's Tiger gets the standard
Coalition model). Pair with slstats.py to also copy the flown ship's stats.

Produces a structurally-valid resource.hog (hog_pack round-trips byte-exact).
It NEVER launches the game; in-game verification is the user's call.

  python slswitch.py models  resource.hog                 # list flyable fighter models
  python slswitch.py swap  resource.hog --fly Rus_Basilisk.SHP --into German_Wolverine.SHP -o out.hog
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hog_pack import read_entries, build  # noqa: E402

ALLIANCE = ("german", "british", "french", "jap", "usa", "ushf", "uslf", "usmf", "uspf", "jlf", "italian", "it")
COALITION = ("rus", "mid", "chinese", "chi", "kalan", "sky", "arc")


def norm(n):
    return n.lower().rsplit("\\", 1)[-1]


def faction_of(model):
    pre = model.split("_", 1)[0].lower() if "_" in model else ""
    if pre in ALLIANCE:
        return "Alliance"
    if pre in COALITION:
        return "Coalition"
    return "-"


def find_entry(entries, name):
    key = norm(name)
    if not key.endswith(".shp"):
        key += ".shp"
    for idx, (n, _) in enumerate(entries):
        if norm(n) == key:
            return idx
    return None


def fighter_models(entries):
    """Player-flyable fighter models = a <...>.shp that also has a t_<...>.shp
    Tiger variant. Returns a de-duplicated [(name, faction), ...]."""
    names = {norm(n) for n, _ in entries}
    seen, out = set(), []
    for n, _ in entries:
        ln = norm(n)
        if ln.startswith("t_") or not ln.endswith(".shp") or ln in seen:
            continue
        if "t_" + ln in names:
            seen.add(ln)
            out.append((n, faction_of(n)))
    return out


def all_models(entries):
    """All .shp model names (de-duplicated, original casing)."""
    seen, out = set(), []
    for n, _ in entries:
        ln = norm(n)
        if ln.endswith(".shp") and ln not in seen:
            seen.add(ln)
            out.append(n)
    return out


def swap_models(entries, fly, into):
    """Mutate `entries` so the `into` slot's standard AND Tiger model hold the
    `fly` model's bytes. Returns (fly_name, [changed names]); raises ValueError
    if a model isn't found."""
    fi = find_entry(entries, fly)
    si = find_entry(entries, into)
    if fi is None:
        raise ValueError(f"fly model not found: {fly}")
    if si is None:
        raise ValueError(f"slot model not found: {into}")
    fly_name, fly_data = entries[fi]
    slot_name = entries[si][0]
    entries[si] = (slot_name, fly_data)
    changed = [slot_name]
    t_slot = find_entry(entries, "t_" + norm(slot_name))
    if t_slot is not None:
        t_fly = find_entry(entries, "t_" + norm(fly_name))
        tiger_data = entries[t_fly][1] if t_fly is not None else fly_data
        entries[t_slot] = (entries[t_slot][0], tiger_data)
        changed.append(entries[t_slot][0])
    return fly_name, changed


def cmd_models(args):
    pairs = fighter_models(read_entries(args.hog))
    print(f"{args.hog}: {len(pairs)} fighter models (standard + Tiger pair):")
    for name, fac in sorted(pairs, key=lambda x: x[0].lower()):
        print(f"  {fac:<10} {name}")


def cmd_swap(args):
    entries = read_entries(args.hog)
    try:
        fly_name, changed = swap_models(entries, args.fly, args.into)
    except ValueError as e:
        sys.exit(str(e))
    open(args.out, "wb").write(build(entries))
    print(f"Swapped (player flies {fly_name!r}); changed: {', '.join(changed)}")
    print(f"wrote {args.out}")
    print("Tip: also copy stats with slstats.py so the swapped ship flies right.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Starlancer Coalition ship-switcher (data-layer).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("models"); p.add_argument("hog"); p.set_defaults(fn=cmd_models)
    p = sub.add_parser("swap")
    p.add_argument("hog")
    p.add_argument("--fly", required=True, help="model to fly (e.g. a Coalition ship)")
    p.add_argument("--into", required=True, help="Alliance slot model to replace")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_swap)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
