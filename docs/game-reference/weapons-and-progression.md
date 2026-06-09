# Starlancer — Weapons, Systems & Progression

Player and enemy weapon systems, defensive gear, ranks and medals — from the
[Starlancer Wiki](https://starlancer.fandom.com/) (see [credit](README.md#-source--credit)).

> These are the **in-game balance values** from the wiki. The project's own
> [`stats-format.md`](../stats-format.md) documents the **on-disk** `SHIP/GUN/MISSILESTATS.BIN`
> records (352-byte stat blocks) and [`slstats.py`](../../tools/slstats.py) edits them — so these
> tables are the human-readable counterpart to the raw stat fields we reverse-engineered.

## Primary (gun) weapons

Mounted on fighters; see each fighter's loadout in [`fighters.md`](fighters.md). Sorted by shield
damage.

| Weapon | Range | Shield dmg | Hull dmg | Speed | Rounds/s | Power/shot | Example users |
|--------|:--:|:--:|:--:|:--:|:--:|:--:|---------------|
| Laser cannon | 200 | 8 | 8 | 1600 | 5.5 | 2 | Grendel, Wolverine / Haidar, Lagg |
| Pulse cannon | 300 | 8 | 8 | 1400 | 8 | 3 | Naginata, Phoenix / Saber, Saracen |
| Gatling lasers | 140 | 8.5 | 6 | 1800 | 10 | 2 | Crusader, Reaper / Basilisk, Kossac |
| Meson blaster | 150 | 9 | 9 | 1300 | 8 | 2 | Mirage IV / Saber, Salin, Azan |
| Gatling plasma cannon | 200 | 10 | 7 | 1200 | 5 | ballistic | Grendel |
| Proton cannon | 200 | 12 | 11 | 1500 | 6 | 3 | Predator, Coyote, Shroud / Karak |
| Tachyon cannon | 400 | 20 | 15 | 1400 | 5 | 5 | Tempest, Patriot, Wolverine |
| Collapser guns | 200 | 25 | 25 | 1400 | 6 | ballistic | Wolverine / Kossac |
| Vulcan battery | 300 | 30 | 35 | 1700 | 2 | ballistic | Reaper |
| Neutron particle gun | 200 | 35 | 30 | 1300 | 2 | 15 | Mirage IV |
| **Nova cannon** | 200 | **400** | **400** | 2000 | special | special | Phoenix (experimental; dumps the whole energy reserve, needs charge time) |

**Capital-ship weapons:** *Flak gun* (range 170, 15/10, 7 r/s) · *Laser turret* (400, 15/10, 7 r/s,
e.g. Kurgen) · **Main gun** (2000, **1000/1000**, 1 r/s — on all capital ships; an instant kill on
projectile collision).

## Missiles & secondary weapons

Missiles unlock in tiers: **Bronze** (start), **Silver** (Mission 12), **Gold** (Mission 17),
**Platinum** (Mission 19).

| Missile | Per mount | Range | Shield / Hull | Lock | Notes | Tier |
|---------|:--:|:--:|:--:|:--:|-------|:--:|
| Fuel Pod | 1 | — | — | — | +50 s afterburner | Bronze |
| Bandit | 1 | 60 | 220 / 200 | 5 s | Strong early dogfight missile | Bronze |
| Havoc | 1 | 80 | 300 / — | 3 s | **EMP** — no damage; disables/spins fighters in range | Bronze |
| Jackhammer | 1 | 80 | 2500 / 2500 | 6 s | Mini-torpedo; anti-capital/objective, not anti-fighter | Bronze |
| Screamer | pod of 20 | 60 | 80 / 80 | unguided | Dumb-fire rockets | Bronze |
| Imp | 1 | 60 | 240 / — | 2 s | Proximity; strips shields | Silver |
| Raptor | pod of 3 | 50 | 250 / 200 | 3 s | Improved dogfight missile | Silver |
| Vagabond | 1 | 100 | 500 / 350 | 4 s | **Homes even on cloaked targets** | Silver |
| Hawk | pod of 4 | 120 | 120 / 120 | 4 s | Long range / fast lock | Gold |
| Solomon | pod of 4 | 60 | 200 / 100 | fire-and-forget | Locks nearest hostile; great torpedo defense | Platinum |

> Game files also name **six unused missiles** with no stats: *Stalker, Blazer, Iron Tooth, Death
> Claw, Brute, Hell Fire* — candidates for the unused-content writeup.

**Torpedoes** — self-propelled anti-capital-ship weapons used by both sides (Alliance Galahad/Hades
bombers; Coalition Scimitar/Kamov, the latter with active camouflage). The most powerful have a
**daranium** tip. Thinly armored — a few shots kill them, but **colliding with one is an instant
kill**. Hotkey **T** targets incoming torpedoes.

## Ion cannons

The **deadliest weapons in the game** — they one-shot anything. Encountered three times across the
campaign:

1. **Fort Vanguard's** (Mission 13) — a captured one; killable with a single Jackhammer.
2. The **Dark Reign** (Mission 18) — afterburner out of its range / hug it to break line-of-sight.
3. The **CS Borodin** cannon (Mission 24) — infinite range; survivable only by cloaking in the Shroud.

## Defensive & special systems

**ECM** — active on all player Alliance fighters; prevents enemy lock-on (degrades their accuracy).
Toggles off automatically and does **not** affect missiles already in flight — use limited flares /
decoys for those.

**"Specials"** — prototype or unique devices shown on the loadout computer; availability varies by
fighter (see [`fighters.md`](fighters.md)):

| Special | Effect |
|---------|--------|
| **Reverse Thrust** | Fly backwards; consumes afterburner fuel. |
| **Spectral Shields** | Temporary invincibility against the most-used enemy energy type; drains fast. |
| **Cloaking** | Near-invisible to sensors; brief, recharges; firing cancels it. |
| **Blind Fire** | Auto-tracks the target in the HUD center (single weapon type; reduced fire rate). |

## Ranks

The player starts as a **2nd Lieutenant**; promotion is purely by **total kills** (each destroyed
ship = one kill, regardless of size). Each rank also unlocks a fighter (or a fighter unlocks at a
set mission, whichever comes first — see [`fighters.md`](fighters.md)):

| Rank | Kills | Fighter unlocked |
|------|:--:|------------------|
| 2nd Lieutenant | 0 | Crusader / Naginata / Grendel / Predator |
| 1st Lieutenant | 35 | Coyote |
| Flight Lieutenant | 72 | Mirage IV |
| Captain | 115 | Tempest |
| Flight Captain | 150 | Patriot |
| Lieutenant Commander | 200 | Wolverine |
| Commander | 255 | Reaper |
| Flight Commander | 275 | Phoenix |
| Squadron Commander | 300 | Shroud |

## Medals

Two kinds — **campaign medals** (one per phase) and **medals for valor** (bonus-objective heroism).

**Campaign medals:**

1. **Alliance Defense Mobilization Medal** — Jun–Sep 2160 (the retreat to Triton).
2. **Long-range Forces Commendation Medal** — Oct 2160–Feb 2161 (hit-and-run raids; squadron becomes "the Flying Tigers").
3. **Special Operations Service Medal** — Mar–Jul 2161 (destroying the Coalition Advanced Warp Gate).
4. **Joint Services Commendation Medal** — Aug–Sep 2161 (capturing Kulov + destroying the ion cannon).
5. **Battle of Titan Campaign Medal** — Oct–Dec 2161 (destroying the Coalition 2nd Forward Fleet).
6. **Outer Sol Victory** — the 6th ribbon; **never seen in-game** (the game doesn't save after the final mission; reconstructed from sprites).

**Medals for valor:**

| Medal | Mission | For |
|-------|:--:|-----|
| The Silver Cluster | 6 | Saving the ANS Ulysses convoy. |
| The Black Eagle | 11 | Destroying the CS Czar in dock. |
| Medal of Valor | 14 | Destroying the warp gate + research facility (killing CS Krasny via the gate). |
| Legion of Service | 18 | Destroying the Dark Reign ion cannon. |
| Navy Cross | 19 | Rescuing Klaus Steiner from the Saladin (killing Kariq Madiz). |
| Alliance Medal of Honor | 23 | Destroying the CS Pukov and the Black Guard. |

> The **medal-case crash** noted in our [`modern-fixes.md`](../modern-fixes.md) relates to this
> medal-display screen — useful context for that fix.

---

*Source: [Starlancer Wiki](https://starlancer.fandom.com/) (CC BY-SA 3.0). "Power per shot" and
missile decoy-resistance values are the raw infobox/table figures.*
