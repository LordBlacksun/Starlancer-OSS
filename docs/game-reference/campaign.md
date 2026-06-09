# Starlancer — The Sol War Campaign

The 24-mission single-player campaign (plus the two demo/trial missions), from the
[Starlancer Wiki](https://starlancer.fandom.com/) (see [credit](README.md#-source--credit)),
**fused with this project's reverse-engineering of the mission flow** in
[`campaign-flow.md`](../campaign-flow.md).

> ### ✅ Cross-validation
> The wiki's narrative mission numbering and this project's *independent* static analysis of the
> executable **agree exactly** on the in-game mission order. Both place **Foster's Last Stand at
> Mission 15** (the Reliant rams the CS Volga) and the **Dark Reign at Mission 18** — numbers we
> recovered from the progression switch and decoded `.DTE` content *before* consulting the wiki, and
> the wiki's per-mission targets (CS Kirov, Czar, Krasnaya, Rameses, Volga, Pukov, Borodin…) match
> our decoded flight-group signatures mission for mission. The wiki tells us *what happens*; our RE
> tells us *which `.DTE` file and which code path drives it*. The table below joins the two.

The campaign is organized into **six phases**: *Operation Shield* (1–7), *Guerrilla War* (8–11),
*Frontier Operations* (12–16), *Advance to Titan* (17–18), *Battle of Titan* (19–21), and the final
phase (22–24, tagged *"Final Battles"* in the infoboxes and *"Final Strike"* on the index). The player
squadron is the **45th** (renamed the **45th Tigers** after Mission 11); the home carrier is the
**ANS Reliant** through Mission 15, then the **ANS Yamato**.

> **Note on titles:** the game has **no in-fiction mission names** — each is literally "Mission N."
> The descriptive labels below are the wiki's one-line summaries. Our RE's open item (resolving the
> per-mission title-string table `DAT_004E5C78`) is consistent with this: the titles are short
> descriptors, not unique names. Cross-reference by **number + carrier + key target**, not by title.

## Master campaign table (wiki ⋈ RE)

`Game #` is the in-game / wiki "Mission N". `.DTE` is the on-disk mission file that drives it (from
[`campaign-flow.md`](../campaign-flow.md) — note the file numbers skip 12/13/17/22). `Date` is the
in-fiction date from the wiki.

| Game # | `.DTE` | Phase | Date | Location | Carrier | Primary objective | Key target |
|:--:|:--:|------|------|----------|---------|-------------------|------------|
| T1 | — | Demo | betrayal day | Neptune / Triton | Yamato | Defend Station LS9 & the Yamato | 3 Tornado cruisers + Class-1 carrier |
| T2 | — | Demo | betrayal day | Neptune | Yamato | Destroy the Coalition strike force | Class-2 & Class-3 carriers |
| 1 | `mission1` | Shield | Jun 24 2160 | Neptune | Reliant | Escort British remnants to Fort Sherman | (bonus: Ivan Petrov's Basilisk) |
| 2 | `mission2` | Shield | Jul 10 2160 | Neptune | Reliant | Sweep hunter-killers; save Gen. Briggs & convoy | CS Kirov, CS Zakov |
| 3 | `mission3`¹ | Shield | Jul 19 2160 | → Venus gate | Reliant | Recover ANS Mantis black box; kill the warp-gate reactor; disable the Riza | Prototype warp gate |
| 4 | `mission4` | Shield | Aug 7 2160 | Triton | Reliant | Protect the Condors laying the early-warning satellites | (Nicolai Petrov) |
| 5 | `mission5` | Shield | Aug 15 2160 | behind lines | *(solo)* | Escort 4 Mammoth supply carriers home | CS Badanov |
| 6 | `mission6` | Shield | Aug 26 2160 | Neptune | Reliant | Escort the liner ANS Ulysses to Fort Baxter | Kamov bombers + Antonov |
| 7 | `mission7` | Shield | Sep 22 2160 | Neptune | Reliant | Aid Fort Baxter; destroy CS Rameses | **CS Rameses** (Al-Rahan) |
| 8 | `mission8` | Guerrilla | Oct 30 2160 | Neptune | Reliant | Defend the Reliant; destroy CS Krasnaya | **CS Krasnaya** |
| 9 | `mission9` | Guerrilla | Nov 13 2160 | frontier | Reliant | Cripple a command ship for boarding; protect the boarders | **CS Kozah** (Berijev) |
| 10 | `mission10` | Guerrilla | Nov 21 2160 | asteroid field | Reliant | Destroy the Latov observation base | **Latov Base** |
| 11 | `mission11` | Guerrilla | Jan 4 2161 | Saturn → Jupiter | Reliant | Destroy the super-carrier CS Czar in dock | **CS Czar** |
| 12 | `mission14` | Frontier | Mar 6 2161 | Venus | Reliant | Steal fuel cells from the Stalag; destroy it | Stalag; Red Dragon |
| 13 | `mission15` | Frontier | Apr 15 2161 | → Fort Vanguard | Reliant | Wipe out McGann's pirates | **McGann & Viper** |
| 14 | `mission16` | Frontier | May 25 2161 | warp hub | Reliant | Destroy the Coalition warp-gate command center | Warp hub; CS Krasny |
| **15** | **`mission18`** | Frontier | Jun 24 2161 | sector sweep | **Reliant→Yamato** | Sweep navs; aid the Yamato vs cruisers — **Foster's Last Stand** | **CS Volga**, Kiev, Yevstafiy |
| 16 | `mission19` | Frontier | Jul 11 2161 | frontier | Yamato | Destroy the carrier CS Morzov | **CS Morzov**; Nicolai Petrov |
| 17 | `mission20` | Advance | Aug 11 2161 | Saturn | Yamato | Capture the Coalition admiral alive | Berijev (→ **Kulov**) |
| **18** | **`mission21`** | Advance | Sep 21 2161 | Saturn / Titan | Yamato | Destroy the ion-cannon platform | **Dark Reign** |
| 19 | `mission23` | Titan | Nov 5 2161 | Saturn → Europa | Yamato | Rescue Steiner & POWs from the prison ship | **Saladin**; Kariq Madiz |
| 20 | `mission24` | Titan | Dec 8 2161 | frontier | Yamato | Wipe out the fleeing convoy | CS Ufelsky; **CS Rameses** (revenge) |
| 21 | `mission25`² | Titan | Dec 30 2161 | Titan orbit | Yamato | Destroy the Coalition Second Fleet | **CS Varyag** + Kozlov/Shinnik/Bulatov |
| 22 | `mission26` | Final | Jan 21 2162 | frontier | Yamato | Raid the supply depot Kronstadt | Kronstadt; Red Dragon |
| 23 | `mission27` | Final | Feb 16 2162 | Jupiter | Yamato | Destroy CS Pukov; break the Black Guard | **CS Pukov** (Adm. Petrov) |
| 24 | `mission28` | Final | Feb 28 2162 | Jupiter | Yamato | Destroy the command station CS Borodin | **CS Borodin** (Kulov & Ivan Petrov) |

¹ Slot 3 loads the shipped variant `mission311.dte`; `mission3.dte` is a superseded earlier cut (see
[`campaign-flow.md` §4](../campaign-flow.md)). ² On replay, slot 25 swaps in `mission251.dte`.

---

## Mission-by-mission

### Demo prologue

**Trial Mission 1** — A "routine final patrol" before the treaty signing turns out to be the opening
of the war. The 409th Ronin find three Tornado-class cruisers hidden in an asteroid belt, realize the
treaty is a trap, and race to warn the Yamato. After defending listening post LS9 and the Yamato
through three torpedo waves, the ANS Victorious jumps in to finish a Class-1 carrier. *A rare early
Alliance victory.*

**Trial Mission 2** — With Base Kennedy lost and the French/Italian fleets destroyed, the Alliance
regroups off Triton. The wing baits and destroys a hunting pack, then finds the main strike force
(Class-2 and Class-3 carriers, Kurgens, Scarab troop transports). Gamma's Hades bombers cripple the
Class-3 before being shot down; the Yamato and Bremen finish the carriers.

### Operation Shield (1–7)

**Mission 1** — The 45th's first live sortie from the Reliant. A cloaking Basilisk piloted by **Ivan
Petrov** ambushes the British convoy and kills the rear-guard Tempest before calling in Sabers and a
Kamov. Delivering the convoy reaches raw materials to the war effort; killing Petrov's Basilisk is a
prized bonus.

**Mission 2** — Rookies train alongside the veteran 110th Pumas (Jake Tanner). Gen. Briggs is shot
down and the Coalition sends an Antonov to capture him — kill it to save him. The fight escalates
through two cruisers (Kirov, Zakov) until the **ANS Yamato** arrives and torpedoes both.

**Mission 3** — Recovering the ANS Mantis black box springs a trap: a Riza science vessel warps the
whole wing to a **prototype Coalition warp gate near Venus**. Shoot out the gate's reactor and escape
through it, then disable the Riza for capture. *Failing to destroy the gate is carried as campaign
state — it triggers later "gatecrasher" warp-raids (a persistent consequence we verified in the
decoded scripts; see [`campaign-flow.md` §4b](../campaign-flow.md)).*

**Mission 4** — Plug a blind spot in Alliance defenses: protect the Condors as they deploy the
early-warning satellite net off Triton. A follow-up distress call lures the wing to **Nicolai
Petrov**, who cripples a Mammoth as bait.

**Mission 5** — A long-range run with no Reliant support, flown alongside the elite **705th Cobras**
under Col. McGann. The crippled CS Badanov is finally destroyed — but **"Viper" is seemingly killed**
when his Coyote explodes on jump, and **McGann absconds with the captured supplies and Mammoths**,
foreshadowing his betrayal.

**Mission 6** — Protect the liner **ANS Ulysses** (carrying Senate/military VIPs) to Fort Baxter.
Cloaking Kamovs and Basilisks hit the undefended liner; if it falls, escape pods launch and a
Coalition Antonov tries to capture the brass — forcing you to destroy the pods rather than let the
VIPs be taken. *Bonus: the Silver Cluster medal.*

**Mission 7** — The mission flips on launch: the **Russian carrier Rameses is destroying Fort
Baxter**, which is wiped out. Protect the escape pods (Gen. Makin's especially), then chase the
Rameses and duel ace **Al-Rahan**. *If the Reliant takes too much damage, it's destroyed → game over.
Revenge on Al-Rahan and the Rameses comes in Mission 20.*

### Guerrilla War (8–11)

**Mission 8** — The damaged Reliant limps toward repairs at Fort Carter and is ambushed by the **CS
Krasnaya**, which launches 12 torpedoes — *four hits sink the Reliant*. Steiner's Vampires assist. A
clean run takes zero torpedo hits.

**Mission 9** — A marine boarding craft (carrying Lt. Cdr. Stahl) must seize a Berijev command ship
for its codes. Once the codes are taken, **McGann and the Cobras turn openly traitor**, attacking to
seize them and murdering Stahl when he refuses. The boarding ship survives and the **CS Kozah** is
destroyed (bonus); McGann flees — the betrayal is now open.

**Mission 10** — Destroy **Latov Base**, which coordinates the Coalition's warp-jump attacks. Knock
out its comms tower within a time limit, then turrets and dish, then plant a Jackhammer in a surface
vent for an internal chain reaction. *(If you let Mission 3's gate survive, "gatecrashers" raid the
supply transports here.)*

**Mission 11** — Using a single-fighter warp projector, the wing slips to Jupiter to hit the **CS
Czar**, a super-carrier that would outclass anything the Alliance has. Clear defenses, escort a
boarding ship to find the twin power cores, then plant two Jackhammers. *Victory earns the squadron
the name **"45th Tigers"** and the pilot the Black Eagle.*

### Frontier Operations (12–16)

**Mission 12** — Steal fuel cells from the **Stalag** mining base to bring Alliance warp gates online.
The Ronin run a decoy attack while Rippers grab the cells; tag the rest for a fusion chain reaction.
*Bonus: finally kill **Red Dragon**, leader of the Golden Warriors.*

**Mission 13** — A baited arms shipment lures McGann's renegades back to **Fort Vanguard**, whose
dormant ion cannon suddenly kills a Puma. McGann (in a Phoenix) fights hard and calls in **Viper —
alive, and now the pirates' headman**. Killing both McGann (required) and Viper (bonus) breaks the
pirate threat.

**Mission 14** — Destroy the Coalition **warp-gate command center**, which holds much of their warp
fuel. After clearing defenses and Gamma's torpedo run, destroy the gate's four power cores.
*Signature beat: timing it right **shears the carrier CS Krasny in half as it transits the gate** —
the Medal of Valor.*

**Mission 15 — Foster's Last Stand.** The ion-trail "sweep" is a ruse to pull fighter cover off the
Reliant, which is then crippled by a carrier group. Rather than a hopeless fight, **Captain Foster
rams the Reliant into the CS Volga**, destroying the Coalition flagship and crippling the offensive.
The player then helps the Yamato finish the Kiev and Yevstafiy. *The Reliant and Foster are lost; the
**Yamato becomes the new home carrier**.* (This is the only `.DTE` that carries **both** Reliant and
Yamato flight groups — the hand-off is visible in the file data.)

**Mission 16** — The counterattack "for Foster." The docked **CS Morzov** is bait — a trap springs
with Basilisks under **Nicolai Petrov** (a guaranteed kill) and a carrier launch. The Morzov is
destroyed, but the **307th Vampires and the ANS Bremen are annihilated** by Ivan Petrov's Black
Guard, who execute the lone survivor.

### Advance to Titan (17–18)

**Mission 17** — Exploiting broken ConNexus codes, ambush a high-ranking admiral's flotilla and
**capture him alive** (do *not* destroy the command ship). Marines board the Berijev but find no
admiral — an escape pod ejects and self-destructs the ship. Kill the pursuing Antonov and guard the
pod: its occupant turns out to be **Admiral Kulov**.

**Mission 18 — Dark Reign.** Kulov's interrogation reveals the **Dark Reign**, a massive scaled-up
ion cannon defending Titan that can one-shot a capital ship — and it proves it by **destroying the
ANS Victorious in a single blast**. Hug the cannon to break its targeting line-of-sight, breach the
shield generator, and detonate the power core. *Time-limited; losing all the Buccaneers fails it.*

### Battle of Titan (19–21)

**Mission 19** — **Klaus Steiner** is alive aboard the prison ship **Saladin**, bound for Europa.
Flying the prototype **Shroud** stealth fighter, immobilize the Saladin (engines + gravity drive) so
marines can board; Kurgens use 20 Alliance prisoners as human shields. *Bonus: kill the Scorpions'
ace **Kariq Madiz**. Reward: the Navy Cross.*

**Mission 20** — A convoy (CS Ufelsky, Berijev, Scarabs) tries to flee to Coalition space. **If the
CS Rameses survived Mission 7, it returns here with Al-Rahan for a rematch** — and can finally be
destroyed. A distress call from the Ronin wreckage then leads to a Black Guard / Ivan Petrov ambush;
Petrov flees again, but the **409th Ronin are wiped out**.

**Mission 21** — To stop the **Second Fleet** reinforcing Titan, the Tigers fly **captured Kamov
bombers in disguise**, transmitting Coalition clearance codes, to torpedo the flagship **CS Varyag**
at point-blank range; breaking formation blows the ruse. After the Varyag falls, the carriers warp
in, the **ANS Endeavor is lost**, and you defend the Yamato and cripple the Shinnik and Kozlov.
*(The wiki pointedly flags the disguise tactic as perfidy.)*

### Final Battles (22–24)

**Mission 22** — Damaged and low on supplies, the Yamato raids the supply depot **Kronstadt**: knock
out the early-warning satellites and comms tower (time-limited), clear defenses, and breach the doors
so Mammoth-borne Rippers can haul off supplies. **Red Dragon** leads a Golden Warriors counterattack.

**Mission 23** — The Tigers slip behind the **CS Pukov**, base ship of the Black Guard, commanded by
**Admiral Petrov** (Ivan's father). A brutal close-quarters slog: strip the Black Guard, kill the
shield generator, then protect the Yamato from cloaked-Kamov torpedo volleys while it bombards the
Pukov. *Destroying it earns the Alliance Medal of Honor; **Ivan Petrov flees**, having lost both his
father and his base carrier.*

**Mission 24 — Finale.** The Coalition command station **CS Borodin** mounts a Dark-Reign-class ion
cannon (making a frontal assault suicidal) and holds both **Kulov and Ivan Petrov**. The plan —
cloaked Hades bombers behind a captured supply ship — is seen through (payback for Mission 21), but
their torpedoes still breach the core. Rippers under Josef Stahl lay charges while you fend off the
ion cannon and fighter swarms; **Steiner rams his Wolverine into a fleeing armored section** to
expose Kulov's warp core. *The Borodin is destroyed and the Coalition defeated. Bonus epilogue:
saving Steiner (he joins the Tigers) and killing both Kulov and Ivan Petrov.*

---

## Branching & persistent state

The campaign is **linear in order** — there is no performance-based *path* divergence (confirmed in
the progression switch; see [`campaign-flow.md` §1](../campaign-flow.md)). "Branching" is **persistent
state** and **variant files**, not reordering:

- **The prototype warp gate (Mission 3)** — letting it survive triggers "gatecrasher" warp-raids in
  later missions (M10, M12). *[verified in decoded scripts]*
- **The CS Rameses (Mission 7)** — if it survives, it returns for a rematch in Mission 20.
- **Fail-and-kick-out** outcomes (Missions 7, 9, 13, 14, 17, 19, 21, 23, 24) end the game.

## Cut content

The wiki documents **four cut missions** recovered from config files, plus leftover assets implying
planned **ground-operations support**:

- **Between M11–M12** — a Limpet-ship boarding raid on an asteroid station holding Coalition tech.
- **Between M14–M15** — a surprise attack on the Class-1 carrier **CS Gegarin**, luring it into a
  Kaiserlauden asteroid-belt ambush with the ANS Mitchell.
- **Between M18–M19** — the Yamato races to stop a Coalition strike on Alliance Command off Neptune.

This dovetails with our RE-side finding of **unused mission files** (`mission3.dte` superseded by
`mission311.dte`; the never-loaded variants `mission191`/`mission271`; file numbers 12/13/17/22 that
do not exist) — good candidates for a combined *Unused Content* writeup. See
[`campaign-flow.md` §4](../campaign-flow.md).

---

*Source: [Starlancer Wiki](https://starlancer.fandom.com/) (CC BY-SA 3.0), fused with this project's
static RE. Mission dates are the wiki's in-fiction dates and carry the timeline's known
inconsistencies.*
