# Starlancer stat tables — `SHIPSTATS.BIN` / `GUNSTATS.BIN` / `MISSILESTATS.BIN`

*Reverse-engineered 2026-06-08 from the extracted game files (`LANCER.CAB\CAB\*.bin`) by diffing against the **hexcheat** known-delta mod pack — each hexcheat file super-stats exactly one ship, so the changed dwords reveal field offsets. Tool: [`tools/slstats.py`](../tools/slstats.py).*

## Where they live
Not in the CD `.HOG` archives (those are media only). They ship inside the disc's InstallShield payload **`LANCER.CAB`** (a *standard MS-CAB*, LZX — `7z x LANCER.CAB`), under `CAB\shipstats.bin`, `CAB\gunstats.bin`, `CAB\missilestats.bin`, `CAB\pilotstats.bin`. At install they become loose files in the game directory (which is what SLEdit / hexcheat overwrite).

## Common record format (all three tables)
A flat array of fixed **352-byte (0x160) records**, no header:

| Off | Size | Field |
|---|---|---|
| 0x00 | 64 | `char name[64]` — NUL-padded ASCII |
| 0x40 | 4×15 | `float32 stats[15]` (little-endian) — see below |
| 0x7C | 0xE4 | per-record tail — loadout/geometry/hardpoints; **not yet decoded, preserved verbatim** |

Counts: `shipstats.bin` = **256** records (0x16000), `gunstats.bin` = **15** (0x14A0), `missilestats.bin` = **16** (0x1600). `pilotstats.bin` (43,648 B) not yet analysed.

## Ship `stats[15]` (offsets 0x40–0x78)
Confirmed by the hexcheat diffs (0x40–0x5C are solid; **0x60–0x78 labels are PROVISIONAL** — order inferred from the readme's reference values, to be confirmed against the decrypted exe's parser):

| Off | Field | Notes |
|---|---|---|
| 0x40 | MaxSpeed | e.g. Predator 320, Shroud 400, capships 80–160 |
| 0x44 | Inertia | ~0.85–0.95 |
| 0x48 | YawMax | ~0.08–0.10 rad |
| 0x4C | YawInertia | ~0.85–0.95 |
| 0x50 | PitchMax | ~0.08–0.10 |
| 0x54 | PitchInertia | ~0.85–0.95 |
| 0x58 | RollMax | ~0.15 |
| 0x5C | RollInertia | ~0.9 |
| 0x60 | ShieldStrength *(?)* | fighters 10–35; capships read ~2 (they use subsystem HP) |
| 0x64 | ArmorStrength *(?)* | |
| 0x68 | AfterburnerFuel *(?)* | ~60–200 |
| 0x6C | ShieldRecharge *(?)* | |
| 0x70 | GunEnergy *(?)* | ~90–220 |
| 0x74 | GunRecharge *(?)* | |
| 0x78 | Ammo *(?)* | ~1000 |

Gun/missile records reuse the same 352-byte frame with weapon-specific `stats[]` (decoded by diffing the hexcheat `guns/`+`missiles/` mods against the readme's stated changes):

**`gunstats.bin`** — 15 guns (Laser/Pulse/Messon/Proton/Gattling/Tachyon/Neutron/Collapser/Plasma/Vulcan/Nova/Turret×2/Allied+Coalition Huge):

| Off | Field | Evidence |
|---|---|---|
| 0x40 | Range | Vulcan 300→140 ("range→140") |
| 0x48 | DamageMin | Proton 12→30 ("damage ~30-35") |
| 0x4C | DamageMax | Proton 11→35 |
| 0x50 | **CyclicRate** (fire rate) | Proton 6→10 *and* Vulcan 2→10 ("5× cyclic") — confirmed by two mods |
| 0x54 | energy/heat per shot *(?)* | Proton 3→2 |

**`missilestats.bin`** — 16 missiles (Screamer/Raptor/Havoc/JackHammer/Bandit/Vagabond/Solomon/Hawk/Torpedo/…):

| Off | Field | Evidence |
|---|---|---|
| 0x40 | MaxVelocity | Raptor 500→600 ("max velocity") |
| 0x48 | Range | Solomon 60→120 (clean single-field, "twice the range") |
| 0x54 | LockTime | Raptor 300→100 ("lock instantly" — lower = faster) |
| 0x5C | agility / secondary range *(?)* | Raptor 1.6e5→3e5 |

Gun fields are solid; missile velocity/range/lock-time are confident, the rest provisional (confirm via exe RE).

## Factions & variants (ships)
Faction is encoded as the **name prefix**: Alliance = `Us`/`Uk`/`Ger`/`Jap`/`Fr`/`It`; Coalition = `Ussr`/`Chi`/`Mid`/`Arc`/`Kalan`/`Sky`. The roster spans fighters (recs ~0–11), capital ships, debris/corpses, planets, torpedoes, then the **`Tiger …` 45th-squadron variants at the end** (e.g. `Us Predator` rec 0 ↔ `Tiger Us Predator` rec 244) — matching the hexcheat readme ("the data … changes to definitions found at the end of the bin-file"). This faction tagging is what makes the **Coalition ship-switcher** (goal #3) a data-layer edit: a Coalition fighter (e.g. `Ussr Basilisk`, rec 49) is a normal record.

## Editing
`tools/slstats.py` reads/edits/writes any of these tables, round-trip-safe (only the targeted dword changes; the undecoded tail is preserved). Validated: a 1-field edit produced exactly one differing dword and identical file size.
```
python slstats.py list  shipstats.bin
python slstats.py show  shipstats.bin "Ussr Basilisk"
python slstats.py set   shipstats.bin 0 MaxSpeed 444 -o modified.bin
```
