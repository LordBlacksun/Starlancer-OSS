# Starlancer campaign flow & mission map

How the 24 single‑player campaign missions are ordered, numbered, and branched — recovered by
**static RE of the executable** (the progression logic + tables) fused with our **`.DTE` decoder**
(per‑mission content). Addresses are VA for ImageBase `0x400000`; lines reference
`LANCER_decrypted.exe.decompiled.c` (a local decompiler export, not redistributed). Claims are tagged **[verified]** (read in
code/data) or **[inferred]**.

> Method note: everything here is static — the exe is read/disassembled as data and the missions
> are decoded as data (`tools/dte_parse.py`). The game is never run.

## 1. The progression rule  [verified]

`DAT_00562DC8` holds the **current mission number**, used directly as the `%d` in
`..\missions\mission%d.dte` (lines 86347/86532/86719). It starts at **1** (line 19747) and the
mission‑advance routine (`gameflow.cpp`) steps it after each mission whose outcome is valid
(`DAT_0052A428 != -1`). The advance is a straight line with three skips and an end (switch at lines
55856‑55883):

```
next = current + 1
  11 → 14      (skip the non-existent files 12, 13)
  16 → 18      (skip 17)
  21 → 23      (skip 22)
  28 → 29      (end-game / credits; the loop exits)
```

So the campaign is **linear** — there is no performance‑based *path* divergence; "branching" is done
by loading a **variant file** for the same slot (§4), not by changing the order. Files **12, 13, 17,
22 do not exist** and are stepped over.

## 2. In‑game mission ↔ `.dte` file  [verified]

Because four file numbers are skipped, the player‑facing "Mission N" is **offset** from the file
number. Confirmed three ways (user ground‑truth that file 15 = "Mission 13"; the progression switch;
and content cross‑checks):

| In‑game | File | In‑game | File | In‑game | File |
|--:|--:|--:|--:|--:|--:|
| 1 | `mission1` | 9 | `mission9` | 17 | `mission20` |
| 2 | `mission2` | 10 | `mission10` | 18 | `mission21` |
| 3 | `mission3` | 11 | `mission11` | 19 | `mission23` |
| 4 | `mission4` | 12 | `mission14` | 20 | `mission24` |
| 5 | `mission5` | 13 | `mission15` | 21 | `mission25` |
| 6 | `mission6` | 14 | `mission16` | 22 | `mission26` |
| 7 | `mission7` | 15 | `mission18` | 23 | `mission27` |
| 8 | `mission8` | 16 | `mission19` | 24 | `mission28` |

**Rule of thumb:** in‑game *N* = the *N*‑th existing `.dte` once you drop files 12/13/17/22.

## 3. Per‑mission map (game order)  [verified — decoded content]

Carrier = the home/allied carrier(s) named in the mission; "targets" = the distinctive flight groups
(generic nav/camera/asteroid/MP groups filtered out). Ships = placed objects, Obj = objective records.

| # | File | Ships | Obj | Carrier | Distinctive targets |
|--:|--|--:|--:|--|--|
| 1 | 1 | 118 | 23 | Reliant | 45th, mammoth, prowlers, lueneburg |
| 2 | 2 | 299 | 39 | Reliant | 45th, Kestrel mammoths, pumas |
| 3 | 3¹ | 283 | 36 | Reliant² | **destroy the experimental Coalition warp gate** (`PROTOGATE`); escape through it as it detonates — or refuse (§"warp gate"). ¹slot 3 loads `mission311`; ²names Yamato as an ally |
| 4 | 4 | 276 | 43 | Reliant | 45th, Condor, Sierra, the Mammoth |
| 5 | 5 | 279 | 34 | Reliant | 45th, stiffs, mammoth, convoy |
| 6 | 6 | 302 | 35 | Reliant | 45th, Ulysses + Ulysses convoy, Kamov |
| 7 | 7 | 165 | 29 | Reliant | 45th, Ramases, escape pods |
| 8 | 8 | 205 | 37 | Reliant | 45th, Krasnaya, warp gate |
| 9 | 9 | 209 | 34 | Reliant | 45th, Endeavour, Hellcats, Limpet |
| 10 | 10 | 288 | 30 | Reliant | 45th, Hades, Sabre+Bazza, Laggs |
| 11 | 11 | 284 | 45 | Reliant | 45th, torpedo groups, Vampires, Hades |
| 12 | 14 | 214 | 21 | Reliant→Yamato | 45th, Ripper, Ronin |
| 13 | 15 | 279 | 37 | Reliant | 45th, Gamma, Hades torps, convoy, pirate base |
| 14 | 16 | 104 | 18 | Reliant | 45th, bombers, research station, coalition gate |
| **15** | **18** | 269 | 40 | **Reliant→Yamato** | **Tigers, Buccaneers, convoy — *Foster's Last Stand* (Reliant lost)** |
| 16 | 19 | 372 | 47 | Yamato | Tigers, Ronin, Bremen, Vampires |
| 17 | 20 | 188 | 37 | Yamato | Tigers, Ronin, Sabres |
| **18** | **21** | 103 | 18 | Yamato | cannon, victorious, kurgens — ***Dark Reign*** |
| 19 | 23 | 295 | 38 | Yamato | 45th main, boarding ship, Saladin, Kurgen |
| 20 | 24 | 348 | 37 | Yamato | Tigers, Coalition/Kossac convoy |
| 21 | 25 | 236 | 20 | Yamato | Tigers, Fleet 2, sentry satellites, Hellcats *(replay → `mission251`, §4)* |
| 22 | 26 | 343 | 46 | Yamato | Tigers, satellites, Black Eagles, Gold Warriors |
| 23 | 27 | 355 | 61 | Yamato | Tigers 1st wave, Pukov, Black Guard waves |
| 24 | 28 | 312 | 36 | Yamato | Yamato, Intrepid, Pirates, Steiner |

**Narrative arc:** Reliant tour (games 1–14) → **Foster's Last Stand at game 15** (the Reliant rams a
Coalition carrier; only `mission18` carries *both* Reliant and Yamato flight groups) → Yamato tour
(games 16–24), with **Dark Reign at game 18** (`mission21` — wingman line *"MOOSE: I'm getting some
activity from the dark reign"*, plus `NAV DARK REIGN`, dark‑reign turrets, an "impressive" camera
cutscene). End‑game/credits = mission **29**.

## 4. Variants, replays & unused files  [partly verified]

- **Slot 25 → `mission251.dte`** on replay: when `DAT_00562DC8 == 0x19` and the replay flag
  `DAT_00587CDC == 1`, the loader swaps in `mission251.dte` (line 86341). **[verified]**
- **Slot 3 → `mission311.dte`** (line 86343, unconditional) — so **`mission311.dte` is the shipped
  mission 3** and **`mission3.dte` is a superseded earlier cut** (both are the warp‑gate mission, see
  below). **[verified load line; cut inferred]**
- **`mission191` / `mission271`** match `mission19` / `mission27` by content (identical flight‑group
  signatures); they are almost certainly the same kind of variant, but their exact load condition is
  not yet pinned. **[inferred]**
- **Never loaded (unused):** files **12, 13, 17, 22** don't exist; **`mission3.dte`** appears
  superseded by `mission311.dte`. Good candidates for an *Unused Content* writeup. **[verified gaps]**

## 4b. Campaign state — the prototype warp gate  [verified content + player account]

**Mission 3** tasks you with destroying the **Coalition experimental warp gate** (`PROTOGATE` /
`coal_prototypegate` / `Protogate Core`). You escape *through* the gate as it detonates
(`Chase you through gate`; *"Stiener: Warp gate destroyed, but I lost the rookie!"*) — or you can
**refuse**, flying back through it instead of destroying it.

The outcome is **carried forward as campaign state**: if the gate survives, later missions spawn
extra **"gatecrasher" / warp‑attack** raids to punish the player. Confirmed in the decoded scripts:

- **Game 10** (`mission10`): *"…we've got **gatecrashers**! And they're hungry for blood!"* and
  *"…take out those **gatecrashers**!"* (Nanny 3 dialogue).
- **Game 12** (`mission14`): a script block named **`(F)Warp attack`** / `(F)2nd part of warp attack
  function`.
- (Game 13's warp strings are routine warp‑*travel*, not the raid.)

This is the clearest case of the persistent‑consequence design: the surviving‑gate state is a
campaign global the later missions read. `mission3.dte` vs `mission311.dte` are two cuts of this
mission (`311` ships). *(Mechanic from the player's account; the `PROTOGATE`/`gatecrasher`/`Warp
attack` strings are [verified] in the decoded `.dte`.)*

## 5. Tables for future work  [verified addresses]

Indexed by mission number `DAT_00562DC8`:

| Table | Addr | Stride | Holds |
|---|---|---|---|
| Mission **title ID** | `DAT_004E5C78` | 2 (short) | ID → `FUN_00491030(id)` → title string (line 55886) |
| Per‑mission **outcome grade** | `DAT_00562E2A` | 2 (short) | the 0–4 grade you earned, recorded per mission (line 55860) |
| **Bonus‑cutscene** flag | `DAT_005009BB` | 1 (byte) | if set & grade==4, play a reward movie (line 55861‑55865) |
| Nebula / nav params | `0x5040EC` | 0x28 | per‑mission environment (line 6627) |
| Misc per‑mission ints | `DAT_004E49B0/B4` | 4 | unit/limit params (lines 12572/12609) |

**Outcome grades** (`DAT_0052A428`, strings at `0x4F0BC8`): 0 Failure · 1 Partial Failure ·
2 Partial Success · 3 Success · 4 Success + Bonus.

## 6. Open items

- Resolve the **official mission titles** by following `DAT_004E5C78[mission]` → `FUN_00491030` →
  the string resource (the names aren't plain strings in `.text`).
- Pin the exact **load conditions** for `mission191` / `mission271`, and which of
  `mission3`/`mission311` the normal flow uses.
- Confirm **chapter/tour boundaries** against `new_chapter1..6.bik` triggers (the Reliant/Yamato
  split sits at the game‑15 hand‑off).

## Related
[`dte-format.md`](dte-format.md) · [`dte-scripting-reference.md`](dte-scripting-reference.md) ·
`tools/dte_parse.py`
