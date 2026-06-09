# Starlancer — Fighter Craft

The 26 fighter craft of the Sol War (plus two point-defense satellites). Stats are the in-game
infobox values from the [Starlancer Wiki](https://starlancer.fandom.com/) (see
[credit](README.md#-source--credit)). Ratings are on a 0–10 scale. `MaxSpeed`, `GunEnergy`
(pool, with recharge/s), and afterburner are the raw infobox fields. The discrete
`shield strength` / `armor strength` numbers are only filled in on the wiki for the **Saber**;
elsewhere only the 0–10 ratings exist.

> **Unlocks:** Alliance player fighters are unlocked by **rank** (= total kills) or by completing a
> specific mission — whichever comes first. See [`weapons-and-progression.md`](weapons-and-progression.md#ranks).
> Player weapon/missile stats live in [`weapons-and-progression.md`](weapons-and-progression.md).

## Master stats table

| Fighter | Side | Type | Spd | Acc | Agi | Shd | Arm | MaxSpd | GunEnergy | Missiles | A/B | Primary weapons |
|---------|------|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|-----------------|
| **Crusader** | Alliance | Light | 5 | 7 | 6 | 4 | 5 | 260 | 150 (8/s) | 5 | 2× Gatling laser, rear laser |
| **Naginata** | Alliance | Light | 7 | 3 | 8 | 5 | 2 | 340 | 180 (7/s) | 3 | 2× Pulse cannon |
| **Predator** | Alliance | Light | 7 | 6 | 8 | 3 | 4 | 320 | 90 (6/s) | 6 | 2× Proton cannon, rear laser |
| **Shroud** | Alliance | Light (proto) | 10 | 3 | 10 | 7 | 3 | 400 | 140 (6/s) | 4 | 2× Proton cannon |
| **Coyote** | Alliance | Medium | 6 | 10 | 6 | 5 | 5 | 300 | 100 (5/s) | 7 | 2× Proton cannon, rear laser |
| **Grendel** | Alliance | Medium | 5 | 10 | 3 | 6 | 6 | 260 | 90 (9/s) | 7 | 2× Gatling plasma, twin laser, rear turret |
| **Mirage IV** | Alliance | Medium | 7 | 5 | 6 | 5 | 4 | 320 | 220 (9/s) | 4 | 2× Meson blaster, neutron particle gun |
| **Patriot** | Alliance | Medium | 7 | 10 | 4 | 6 | 5 | 340 | 160 (7/s) | 5 | 2× Tachyon, 2× Proton, rear laser |
| **Phoenix** | Alliance | Medium (proto) | 9 | 10 | 8 | 6 | 4 | 380 | 180 (6/s) | 4 | 2× Gatling laser, 2× Pulse, rear turret, **Nova cannon** |
| **Sai** | Alliance | Medium | 4 | 10 | 6 | 5 | 6 | 160 | 100 (10/s) | 4 | 2× Pulse cannon |
| **Reaper** | Alliance | Heavy | 6 | 5 | 4 | 6 | 5 | 300 | 100 (7/s) | 8 | 2× Gatling laser, 2× Vulcan, rear quad-pulse turret |
| **Tempest** | Alliance | Heavy | 6 | 10 | 4 | 6 | 5 | 300 | 160 (6/s) | 8 | 2× Tachyon, 2× Pulse, rear pulse turret |
| **Wolverine** | Alliance | Heavy | 5 | 10 | 4 | 6 | 7 | 280 | 140 (9/s) | 8 | 2× Collapser, 2× Laser, Tachyon, rear pulse turret |
| **Azan** | Coalition | Light | 8 | 8 | 9 | 7 | 5 | — | 100 (10/s) | 1 | 2× Pulse cannon, 2× Meson blaster |
| **Loki** | Coalition | Light | 2 | 2 | 2 | 2 | 2 | — | — | 2× Vagabond | 2× Gatling laser |
| **Saber** | Coalition | Medium | 6 | 7 | 3 | 8 | 5 | 300 | 100 (10/s) | 6 | 2× Pulse cannon, 2× Meson blaster, rear laser |
| **Salin** | Coalition | Medium | 3 | 7 | 6 | 6 | 4 | — | — | 4 | 2× Pulse cannon, 2× Meson blaster, rear laser |
| **Saracen** | Coalition | Medium | 3 | 10 | 3 | 6 | 6 | — | 100 (10/s) | 4 | 2× Pulse cannon, 2× Meson blaster, rear pulse |
| **Karak** | Coalition | Medium | 4 | 7 | 5 | 8 | 6 | — | 100 (10/s) | None | 2× Meson blaster, 2× Proton, rear laser |
| **Lagg** | Coalition | Medium | 6 | 7 | 5 | 8 | 6 | — | 100 (10/s) | 9 | 2× Gatling laser, 2× Proton, 2× Laser, twin rear |
| **Basilisk** | Coalition | Medium (proto) | 9 | 9 | 9 | 9 | 7 | — | 200 (10/s) | 10 | 2× Gatling laser, 2× Meson, 2× rear laser |
| **Haidar** | Coalition | Heavy | 7 | 6 | 6 | 7 | 9 | — | 100 (10/s) | 2 | 2× Gatling laser, 2× Laser, rear laser |
| **Kossac** | Coalition | Heavy | 6 | 7 | 7 | 6 | 10 | — | 100 (10/s) | 10 | 2× Collapser, 2× Gatling laser, rear twin laser |

**Point-defense satellites** (not fighters; no ratings) — **Archer** (missile turret) and **Grazer**
(dual laser turret): light, mass-produced early-warning/radar satellites, frequent mission
destruction targets.

> **Saber discrete defenses** (only fully-specified page): shield strength **25**, shield recharge
> **16**, armor strength **14**. Treat the 0–10 Shd/Arm ratings as the comparable cross-fighter
> measure elsewhere.

---

## Alliance fighters

**Crusader** — RAF light fighter (UK). Crew 2 · 2.3 t · 12 decoys · **Special: Spectral Shields** ·
*starter*. A solid, balanced starting ship; the Spectral Shields grant brief invulnerability.

**Naginata** — Zero-inspired Japanese light fighter. Crew 2 · 1.5 t · 15 decoys · **Spectral
Shields** · *starter*. Light, fast and well-armed; favorite of the 409th Ronin. Great
maneuverability but paper-thin armor and a small missile load — for veterans.

**Predator** — Nimble US light fighter with advanced tracking. Crew 2 · 2 t · 10 decoys · **Blind
Fire** · *starter*. One of the best early picks; agility + Blind Fire give a dogfighting edge.

**Shroud** — Japanese prototype, the **swiftest fighter of the war**. Crew 2 · 1.6 t · 10 decoys ·
**Blind Fire / Spectral Shields / Reverse Thrust / Stealth Cloak** · unlock Mission 18 or Squadron
Commander (300 kills). Trades firepower/armor for unmatched speed and agility; effectively mandatory
against the ion cannon of CS Borodin (only the cloak survives its fire).

**Coyote** — Balanced US medium fighter. Crew 2 · 3 t · 16 decoys · **Blind Fire** · unlock Mission
11 or 1st Lieutenant (35 kills). Many missile hardpoints and a good all-round balance.

**Grendel** — "Ugly but powerful" German medium fighter. Crew 3 · 4.5 t · 7 decoys · *starter*.
Prioritizes firepower and survivability over accuracy and speed — a flying brick.

**Mirage IV** — French medium workhorse (atmosphere + space capable). Crew 2 · 1.9 t · 14 decoys ·
unlock Mission 11 or Flight Lieutenant (72 kills). Wingtip-mounted main guns make close-range
shooting awkward. Many were lost on the ground at Base Kennedy.

**Patriot** — An improved Coyote. Crew 2 · 3.2 t · 18 decoys · **Blind Fire** · unlock Mission 16 or
Flight Captain (150 kills). A strict upgrade except for slightly fewer missile mounts.

**Phoenix** — The pinnacle of Alliance tech. Crew 2 · 4.6 t · 16 decoys · **Blind Fire / Reverse
Thrust / Nova Cannon** · unlock Mission 18 or Flight Commander (275 kills). Built around the
prototype **Nova cannon**, which dumps the entire energy reserve in one devastating blast (conserves
missiles — e.g. for a Kurgen). A top end-game fighter.

**Sai** — A small, swift Japanese fighter, rarely encountered on the Alliance side; *not normally
available*. Often seen paired with the ANS Yamato. (Notably low max speed of 160.)

**Reaper** — Powerful, accurate US heavy fighter. Crew 3 · 4.4 t · 24 decoys · **Blind Fire** ·
unlock Mission 16 or Commander (255 kills). Its slow-firing **Vulcan** battery hits very hard
(three shots kill a Saber). Excellent end-game choice alongside the Phoenix.

**Tempest** — Heavy British fighter; "a flying gunboat." Crew 2 · 8 t · 12 decoys · **Spectral
Shields** · unlock Mission 11 or Captain (115 kills). Plenty of firepower and hardpoints; shields let
it survive capital-ship raids.

**Wolverine** — Teutonic heavy fighter built to beat any Coalition fighter or corvette. Crew 3 ·
3.9 t · 20 decoys · **Reverse Thrust** · unlock Mission 16 or Lt. Commander (200 kills). Heavy armor
and powerful collapser cannons; favorite of Cmdr. Klaus Steiner. Excels at assaulting capital ships
and bases.

---

## Coalition fighters

**Azan** (أَذَانْ) — Light East Asian Federation fighter (Tigris Confederation service), named for the
Islamic call to prayer. Crew 1 · 2 t. Among the lightest and fastest designs — hard to track without
Blind Fire. Flown by the Golden Warriors.

**Loki** — Short-range defense fighter for intercepting slow vessels. Crew 1. All ratings 2/10 —
"scarcely a challenge — free kills." Carries 2× Vagabond.

**Saber** (Сабля) — The **Coalition workhorse**: a rugged, mass-produced two-seater (Eastern
Republic). Crew 2 · 3 t. Strong shields (second only to the Basilisk) but light armor for a medium
fighter, and below-average agility. Easy to kill — but comes in packs.

**Salin** — Lightweight EAF medium fighter (the "Luda"); essentially a nimbler Saber. Higher agility
makes it a tougher target, but low armor/shields make it an easy kill for heavier fighters. Rarely
encountered.

**Saracen** — Tigris Confederation medium fighter. Crew 2 · 2 t. Excellent acceleration, average
armor, slow top speed. Dangerous in packs; rarely attacks alone. Flown by the Saracens (CS Rameses).

**Karak** (الكرك) — EAF medium fighter (the "Zhuhai"), an organic-looking sibling of the Haidar.
Crew 2 · 3.2 t · **no missiles**. Large for a medium, with an exceptionally strong shield, but slow
and easily outmaneuvered.

**Lagg** (ЛаГГ) — Large, formidable Eastern Republic fighter (named for the Soviet LaGG series).
Crew 2 · 2 t. Well-armored and shielded, deceptively agile and fast; lots of staying power, but its
size makes it an easy target unless you fly a "brick."

**Basilisk** (Василиск) — Next-gen Eastern Republic prototype used **exclusively by the Black
Guard**. Crew 2 · 4 t · **Special: Stealth Cloak**. Fast, agile, well-protected, heavily armed and
cloaking — arguably the finest fighter in the game. *Note: Vagabond missiles lose lock after it
recloaks.* Fight it at 20–30 units with superior firepower.

**Haidar** (حيدر) — Large, well-armored EAF heavy fighter (the "Han"). Crew 2 · 3 t. Poor
maneuverability from its weight; lower damage output than the heavier Kossac, but not to be ignored.

**Kossac** (Казак) — The **largest, most heavily armored Coalition fighter** (Armor 10/10; named for
the Cossacks). Crew 3 · 4 t. Dishes out and absorbs huge punishment with respectable speed; a
priority target in escort scenarios — its heavy guns can kill a ship in moments. Outmatched only by
light fighters in a turning fight.

---

*Source: [Starlancer Wiki](https://starlancer.fandom.com/) (CC BY-SA 3.0). Minor source typos
normalized (e.g. "Messon" → Meson). Native-script names preserved as on the source pages.*
