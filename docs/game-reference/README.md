# Starlancer — Game Reference

A structured, factual reference for the world, ships, characters, campaign, weapons, and lore of
**Starlancer** (Digital Anvil / Microsoft, 2000). This is the *content* companion to the rest of
this repository's *technical* docs (engine map, file formats, campaign-flow RE): where
[`campaign-flow.md`](../campaign-flow.md) explains how the missions are *wired in the executable*,
this section explains what actually *happens* in them.

> ### 📚 Source & credit
> The factual game data compiled here — ship statistics, mission objectives, the character roster,
> faction lore, weapon tables, ranks and medals — is sourced from the community-run
> **[Starlancer Wiki on Fandom](https://starlancer.fandom.com/)** and its contributors, made
> available under **[CC&nbsp;BY-SA&nbsp;3.0](https://creativecommons.org/licenses/by-sa/3.0/)**. This
> compilation reorganizes that information into original tables and prose for use as a modding /
> reverse-engineering reference, cross-checked against our own static analysis of the game where the
> two overlap. Full credit and thanks to the Starlancer Wiki editors. Corrections and in-game
> measurements made by this project are flagged inline. These reference pages are offered under the
> same **CC BY-SA 3.0** terms as the source (the repository's code and technical docs remain under
> the GPL — see the root [`LICENSE`](../../LICENSE)).

---

## Contents

| Page | What it covers |
|------|----------------|
| [`fighters.md`](fighters.md) | All 26 player/enemy fighter craft — full stat block (ratings, gun energy, shields, armor, weapons, specials). |
| [`capital-ships.md`](capital-ships.md) | Alliance (ANS) and Coalition (CS) capital ships, carriers, cruisers, command ships & installations. |
| [`characters.md`](characters.md) | The 53-name character roster — pilots, COs, aces, traitors — with faction, squadron, callsign and fate. |
| [`campaign.md`](campaign.md) | The 24-mission Sol War campaign + the two trial missions, fused with our exe-side mission map. |
| [`factions-and-forces.md`](factions-and-forces.md) | The two powers, their elite units, all 27 squadrons, and the war's locations. |
| [`weapons-and-progression.md`](weapons-and-progression.md) | Primary weapons, missiles, torpedoes, ion cannons, ECM, "specials", ranks and medals. |

**See also** (technical / RE side of the same subjects): [`campaign-flow.md`](../campaign-flow.md) ·
[`dte-format.md`](../dte-format.md) · [`stats-format.md`](../stats-format.md) ·
[`engine-map.md`](../engine-map.md).

---

## The game

**Starlancer** is a space-combat flight simulator created by **Chris Roberts**, developed by
**Warthog** and published by **Digital Anvil / Microsoft**. It is the **prequel to *Freelancer***.

| | |
|---|---|
| **Genre** | Space-combat simulator (single-player campaign + multiplayer) |
| **Developer / Publisher** | Digital Anvil (dev: Warthog) / Microsoft |
| **Windows release** | **March 31, 2000** (North America) |
| **Dreamcast release** | **November 27, 2000** (NA) · **March 30, 2001** (EU) |
| **Lifetime sales** | ~400,000 copies (modest — a sequel was never greenlit) |

The single-player campaign puts the player in the cockpit of the **45th Volunteer squadron** (soon
renamed the **45th Tigers**), flying from the carrier **ANS Reliant** and later the **ANS Yamato**
through the 24 missions of the Sol War.

---

## The Sol War — overview

The campaign chronicles **The Sol War (2160–2162)**, fought across the Solar System between the
**Western Alliance** and the **Eastern Coalition**.

The war opens with the **Deimos Betrayal**: under cover of the imminent **Balma Treaty** signing on
Europa, the Coalition launches a surprise first strike across Sol (June 2160). The Franco-Italian
fleets are annihilated at **Deimos** (Mars orbit), Earth and Mars fall, and the surviving ~45% of
the Allied navy retreats to its last stronghold at **Triton** (Neptune). From there the player's
squadron fights a guerrilla war out of the **ANS Reliant** — escorting convoys, destroying Coalition
super-carriers and warp infrastructure, and exposing the traitor Col. McGann.

The mid-war turning point is **Captain Foster's Last Stand** (Mission 15): with the Reliant crippled,
Foster rams it into the Coalition flagship **CS Volga**. The survivors transfer to the **ANS Yamato**
and go on the offensive — **capturing Admiral Kulov**, destroying the **Dark Reign** ion-cannon
superweapon, and liberating **Titan**. The endgame — the **Battle of Titan** and the **Final Battles**
off Jupiter — culminates in the destruction of the Black Guard's base carrier **CS Pukov** and the
command station **CS Borodin**, and the decisive defeat of the Coalition in outer Sol.

> The campaign is a **fighting retreat that turns into a counter-offensive**; see
> [`campaign.md`](campaign.md) for the full mission-by-mission account.

---

## The two powers

**Western Alliance** — A supranational union of Western nations (USA, UK, France, Germany, Italy,
Japan, Spain). The most technologically advanced power in history; it colonized much of Sol,
terraformed Mars and Europa, and built the system's industrial base. War-weary after a century of
colonial conflict, it agreed to the Balma Treaty and stood its fleets down — and was attacked.
Maintains (mostly) honorable military conduct.

**Eastern Coalition** — A newly-formed union of non-Western nations: the **Eastern Republic**
(former USSR + republics), the **Tigris Confederation** (Middle Eastern states), and the **East Asian
Federation**, later styled the "Coalition of Eastern Powers." Left behind technologically and
confined largely to Venus and Mercury, it united to avoid permanent second-rate status and used the
treaty as a ruse for a perfidious first strike. Governed by the **Political Council** backed by the
**Secret Police**, led by Admiral **Vladimir Kulov**. Notorious for total-war conduct — targeting
hospitals and civilian convoys, a "take no prisoners" policy, torture, and prison ships like the
*Saladin*.

Full detail, including all elite units and squadrons, is in
[`factions-and-forces.md`](factions-and-forces.md).

---

## Sol geography (theatre of war)

| Body | Significance in the war |
|------|-------------------------|
| **Mercury** | Coalition-held; marginal strategic value. |
| **Venus** | Long-time Coalition stronghold; core fleets + secret projects (the prototype warp gate). No moons. |
| **Earth** | Heart of human civilization; oldest capital-ship shipyards; hotly contested. |
| **Luna (Moon)** | Site of the decades-long Lunar Conflicts; where the Alliance ultimately loses the war (~2261). |
| **Mars** | Alliance-terraformed, capital-ship shipyards; conquered early — harsh rationing and civilian massacres. |
| **Deimos** (Mars moon) | Alliance space dock; site of the opening-day **Deimos Massacre** of the Franco-Italian fleets. |
| **Jupiter** (Europa, Ganymede, Io, Callisto) | Industrial powerhouse sustaining the outer-Sol fleets; setting of the final battles. |
| **Europa** | Terraformed (breathable); capital **Base Kennedy**, the intended treaty-signing site. |
| **Ganymede** | Hit hard at the war's start (Black Sun raids; a refugee convoy massacred by CS Morzov). |
| **Saturn** | Heavily militarized; Coalition proving ground (CS Czar, Dark Reign). |
| **Titan** (Saturn moon) | Largest outer-Sol colony; focus of the war's middle stage; liberated late 2161. |
| **Uranus** | Home to Fort Rushmore. |
| **Neptune** | The Alliance's last remaining territory at the war's start; the rallying point. |
| **Triton** (Neptune moon) | Seat of Alliance High Command; fortified into a near-impregnable line. |
| **Pluto** | Alliance proving ground; in the scrapped ending, the last holdout, burned by the Nomad-induced nova. |

---

## The *Freelancer* connection

Starlancer is the **prequel to *Freelancer*** (2003). In the canonical link, after the Sol War grinds
on for another century the Coalition finally wins at Luna (~2261), and the Alliance escapes Sol in
**five sleeper ships** bound for the Sirius system — **Liberty** (USA), **Bretonia** (UK), **Kusari**
(Japan), **Rheinland** (Germany), and **Hispania** (Spain) — which become the Houses of *Freelancer*
(the damaged Hispania's survivors splinter into the Corsairs and Outcasts).

A **scrapped alternate ending** — the original basis for *Freelancer*, later released on the
**Freelancer bonus disk** — had a **Nomad** capital ship decloak at Pluto and fire a spinal weapon
into the Sun, triggering a micro-nova that exterminates everything (Coalition included) out to the
Kuiper Belt, with a single Alliance ship fleeing toward New York. It was cut and the intro left
ambiguous.

---

## A note on data fidelity

The source wiki carries occasional internal inconsistencies, faithfully preserved here and flagged
where they matter:

- **The in-universe timeline is inconsistent** — e.g. the "Lunar Conflict" is variously dated 2024 /
  2075 / 2125 / 2150 across pages; some 2160–2162 mission dates disagree between articles.
- **Squadron infoboxes carry both a "live" and a leftover "beta" description** (early game-file text)
  that often disagree on kill ratios and unit names (e.g. the 51st's cut name "Diamondbacks").
- **In-game spellings differ from the wiki's canonical titles** for a few ships — notably
  **Ramases** (game) vs *Rameses* (wiki) and **Boridin** (game) vs *Borodin* (wiki). Both are noted
  where they appear, because the **game/`.DTE` spelling is what matters for RE cross-referencing**.

Where this project has measured a value directly from the game files (stat `.BIN`s, decoded `.DTE`s,
the decompiled exe), that takes precedence and is flagged as a project correction.
