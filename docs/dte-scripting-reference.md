# Starlancer `.DTE` — Mission Scripting Reference

A complete reference to Starlancer's mission **trigger/event scripting language**: the
trigger-condition enum, the Executor command set, the AI-behaviour codes, and the
script-stream opcodes. This **fuses two independent reverse-engineering efforts**:

* **Static RE of the decrypted executable** (this project; ImageBase `0x400000`). Source of
  the per-command **implementation addresses + parameter counts**, the trigger enum, the
  bytecode VM, and struct layouts.
* **Black-box RE by Captain Foster / "Starlancer ME"** — blog
  <https://starlancerme.blogspot.com/>, YouTube [@CaptainFoster](https://www.youtube.com/@CaptainFoster),
  contact `email withheld`. Source of the **numeric opcode/command indices**, the
  **AI-code** and **ship/pilot ID** tables, and the **observed in-game semantics**. Their
  empirical numbering and our disassembly agree everywhere they overlap — see
  [`dte-format.md`](dte-format.md) for the side-by-side reconciliation.

> The companion tool `tools/dte_parse.py` holds these tables as importable data and prints
> them (`dte_parse.py ref exec|triggers|ai|stream`). The Executor table below is generated
> from it verbatim, so the doc and the tool can never drift.

---

## How a mission script runs

A `.DTE` carries data sections (ships, triggers, globals, strings, …) plus a block of
**script bytecode**. Execution is event-driven:

1. The engine raises an event (a ship is destroyed, a proximity sphere is entered, a timer
   expires, …). It looks up the acting ship's **trigger list** (per-ship index → trigger
   records) and tests each record's condition (`TT_*` value at record `+0x15`) against the
   event, plus its operands (`FUN_0045CEA0`).
2. On a match, the record's **action id** (`+0x16`) spawns a **script thread**
   (`FUN_0045B8D0`): the thread's instruction pointer is set just past a leading `u16` that
   gives the block's byte length.
3. The thread is run by the interpreter **`FUN_0045C980`**: a flat loop that fetches one
   opcode byte, indexes the **256-entry handler table `DAT_004F6350`**, advances the IP, and
   calls the handler — repeating until a handler returns 0 (yield/finish). A parallel
   per-byte flag array (section `DAT_005294D8`, indexed by `IP − DAT_00525F88`) marks yield
   points so long scripts can suspend across frames.
4. Action opcodes that name a high-level command (`0x21 <index>`) dispatch through the
   **command catalogue `DAT_004F3AD0`** (installed by `FUN_0045CE30`), which holds, per
   command, its implementation pointer, parameter count, name, and per-parameter labels.

So there are two registers of meaning in one stream: **commands** (`0x21 <i>` → the Executor
table) and **micro-ops** (comparisons, immediates, global read/write — the if/else
machinery). Both are listed below.

---

## Trigger conditions (`TT_*`)

The condition type stored at trigger-record `+0x15`. **33 scriptable types, `0x00`–`0x20`** —
verified from the string array in `FUN_0045B330` and identical to Starlancer ME's *Triggers*
page. (The condition-*descriptor* table `DAT_0052952C` has 35 entries / `_DAT_00525F8C=0x23`;
the 2 beyond `0x20` are internal, non-scriptable conditions.)

| | | | |
|---|---|---|---|
| `00` TT_SHOTAT | `09` TT_JUMPED_IN | `12` TT_TARGETTED | `1B` TT_TRACTOR_BEAM_BROKEN |
| `01` TT_DESTROYED | `0A` TT_FG_JUMPED_IN | `13` TT_PLAYER_L1_DOUBLETAP | `1C` TT_INSIDE_OBJECT |
| `02` TT_LAUNCHED | `0B` TT_PLAYER_READY_TO_WARP | `14` TT_PLAYER_L2_DOUBLETAP | `1D` TT_OUTSIDE_OBJECT |
| `03` TT_CAMERAREACHED | `0C` TT_JUMPED_THROUGH_HOOP | `15` TT_PLAYER_R1_DOUBLETAP | `1E` TT_DOCKED |
| `04` TT_SHIPREACHED | `0D` TT_PLAYER_WANTS_BACKUP | `16` TT_PLAYER_R2_DOUBLETAP | `1F` TT_UNDOCKED |
| `05` TT_PROXIMITY_CLOSE | `0E` TT_RIPPER_GRABBED_OBJECT | `17` TT_PLAYER_L1_L2_R1_R2_PRESSED | `20` TT_BEING_CHASED |
| `06` TT_PROXIMITY_GENERAL | `0F` TT_RIPPER_DROPPED_OBJECT | `18` TT_PLAYER_L1_R1_PRESSED | |
| `07` TT_OBJECT_SCOOPED | `10` TT_CLOAKED | `19` TT_GAME_TIMER_EXPIRED | |
| `08` TT_PLAYER_READY_TO_JUMP | `11` TT_DECLOAKED | `1A` TT_TRACTOR_BEAM_LOCKED | |

---

## Executor commands (script opcode `0x21 <index>`)

The high-level mission verbs. This table is **authoritative**: we walk the engine's live command
catalogue at VA `0x4F0F50` (installed by `FUN_0045CE30`; the `0x21 <i>` handler `FUN_0045BEA0`
indexes entry `i`, stride `0x74`). **Name, `params`, `impl`** — and the per-parameter labels in the
[§ Command parameters](#command-parameters) appendix — are the **developers' own strings**, recovered
straight from the binary. There are **95 real commands (`0x00`–`0x5E`)**; `0x5F` is an empty slot and
a disabled `Test_AI_Function` stub sits at `0x60`.

> **Numbering vs Starlancer ME.** The blog's empirical indices agree with the catalogue **except
> `0x16`–`0x19` and `0x26`–`0x2A`**, where the black-box effort mistook *parameter-label* text for
> commands — its `GTextPilotDefine`, `RadiusOfSphere` and `ShipPointToFlyTo` are literally the
> parameter strings of `DisplaySubTitle` (*"GText pilot define"*), `SetActionCentre` (*"Radius of
> sphere…"*) and `Fly` (*"Point to fly to"*) — and folds away the `CommsFromPilot` / `CommsFromPilotOnce`
> pilot-voice twins. `WaitNSeconds` / `ShipToDock` / `EntityToCloak` are paraphrases of `Wait` / `Dock`
> / `Cloak`. The **catalogue numbering is authoritative**; the divergent rows are tabulated after the
> main table.

| idx | name | params | impl | idx | name | params | impl |
|---|---|---|---|---|---|---|---|
| `00` | PrintShipName | 2 | `0x00458AB0` | `30` | SetNavPoint | 2 | `0x00459270` |
| `01` | CreateTimer | 4 | `0x0045D210` | `31` | SetEscortPoint | 2 | `0x004592F0` |
| `02` | DestroyTimer | 1 | `0x0045D290` | `32` | ResetAfterBurners | 0 | `0x004594C0` |
| `03` | CreateFlightGroup | 1 | `0x00457C40` | `33` | DisableMissiles | 2 | `0x00459370` |
| `04` | DestroyFlightGroup | 1 | `0x00457FD0` | `34` | DisableEngines | 2 | `0x004593E0` |
| `05` | Wait | 1 | `0x0045D2E0` | `35` | DisableEject | 2 | `0x00459450` |
| `06` | PlaySpeech | 1 | `0x00458090` | `36` | SetHostile | 2 | `0x004594F0` |
| `07` | WaitForSpeech | 0 | `0x00458100` | `37` | ResetToSpawnPositions | 0 | `0x004591B0` |
| `08` | PlayCommsMovie | 3 | `0x00458120` | `38` | UpdateEnvironmentFXState | 0 | `0x004591A0` |
| `09` | WaitForMovie | 0 | `0x00458180` | `39` | SetPrimaryTarget | 1 | `0x00459550` |
| `0A` | PrintDebugMessage | 1 | `0x004581A0` | `3A` | WaitForJumpOrLaunch | 1 | `0x004595A0` |
| `0B` | SetAI | 4 | `0x004581F0` | `3B` | DoNotDisturb | 2 | `0x00459640` |
| `0C` | ClearAI | 1 | `0x004588C0` | `3C` | SetEnvironmentFXNebula | 1 | `0x00459190` |
| `0D` | SetPatrolRoute | 2 | `0x00458860` | `3D` | StartShipAnimationReverse | 2 | `0x004587D0` |
| `0E` | SetPilot | 2 | `0x00458830` | `3E` | SnapToPoint | 2 | `0x004596A0` |
| `0F` | SetTriggerState | 3 | `0x0045D300` | `3F` | PlayFostersLastStand | 0 | `0x00459740` |
| `10` | StartDirectorCam | 5 | `0x004582E0` | `40` | OpenInstrument | 1 | `0x0045D9D0` |
| `11` | StartShipAnimation | 2 | `0x00458720` | `41` | CloseInstrument | 1 | `0x0045DA30` |
| `12` | ShipFollowCurve | 3 | `0x004585D0` | `42` | DestroySubObject | 2 | `0x00459750` |
| `13` | SetupLaunch | 3 | `0x00458970` | `43` | SetObjective | 2 | `0x00459870` |
| `14` | StartLaunch | 1 | `0x00458A40` | `44` | SetRescueProbabilities | 3 | `0x004598D0` |
| `15` | DisplaySubTitle | 1 | `0x00458A80` | `45` | IsShipThisPlayer | 1 | `0x004598F0` |
| `16` | ResetCodePriority | 1 | `0x00458A90` | `46` | SetFlybackMarker | 2 | `0x00459910` |
| `17` | InterruptTriggerCode | 0 | `0x0045D450` | `47` | ResetFlybackMarker | 0 | `0x004599E0` |
| `18` | CommsFromShip | 3 | `0x00458AC0` | `48` | StopShipAnimation | 2 | `0x00458770` |
| `19` | CommsFromPilot | 3 | `0x00458B10` | `49` | SetShipAvoidance | 2 | `0x00459A30` |
| `1A` | SetInvulnerability | 2 | `0x00458BC0` | `4A` | MatchSpeed | 2 | `0x00459A90` |
| `1B` | MovingShipFollowCurve | 4 | `0x004585A0` | `4B` | MovingShipBackupCurve | 4 | `0x00458670` |
| `1C` | DisableObject | 2 | `0x004583C0` | `4C` | WaitForKey | 1 | `0x00459AE0` |
| `1D` | PositionRelative | 2 | `0x004584D0` | `4D` | TerminateMission | 0 | `0x00459BB0` |
| `1E` | WhenPlayerLastJumped | 0 | `0x00458580` | `4E` | TurretSetTarget | 2 | `0x00459BD0` |
| `1F` | StartMissileCam | 1 | `0x00458B60` | `4F` | SetAnyTriggerState | 4 | `0x0045D3A0` |
| `20` | StartChaseCam | 1 | `0x00458B80` | `50` | WaitForDirectorCam | 0 | `0x00459C90` |
| `21` | SetPlayerTarget | 2 | `0x00458C80` | `51` | KillAllScriptExecutionExecptMe | 0 | `0x0045D990` |
| `22` | SetTargetable | 2 | `0x00458D50` | `52` | StackDirectorCam | 5 | `0x00458300` |
| `23` | PlayMusic | 2 | `0x00458DF0` | `53` | Scanner | 1 | `0x00459CB0` |
| `24` | StopDirectorCam | 0 | `0x00458E30` | `54` | ReplaceSubObject | 2 | `0x00459CF0` |
| `25` | SetActionCentre | 2 | `0x00458E60` | `55` | Fire | 2 | `0x00459DD0` |
| `26` | Dock | 3 | `0x00458EB0` | `56` | MultiplayerScriptSync | 1 | `0x00459DF0` |
| `27` | DisableTaunts | 1 | `0x00458F40` | `57` | FriendlyFire | 0 | `0x00459F30` |
| `28` | Fly | 3 | `0x00458F50` | `58` | Cloak | 2 | `0x00459F40` |
| `29` | CommsFromShipOnce | 3 | `0x00458FD0` | `59` | ReplenishWeapons | 1 | `0x00459FA0` |
| `2A` | CommsFromPilotOnce | 3 | `0x00459020` | `5A` | WillsBlag | 1 | `0x0045A1C0` |
| `2B` | DisableLights | 2 | `0x00459070` | `5B` | ShowHudIcon | 2 | `0x0045A1F0` |
| `2C` | SetEnvironmentFX | 2 | `0x00459170` | `5C` | DisableListing | 2 | `0x0045A210` |
| `2D` | MultiPlayerSync | 0 | `0x004591E0` | `5D` | DisableObjectAtNextJump | 2 | `0x0045A250` |
| `2E` | DisableGenericComms | 1 | `0x004591F0` | `5E` | DarrensNaughtyBlag | 2 | `0x0045A290` |
| `2F` | DisableGuns | 2 | `0x00459200` | `5F` | _(empty)_ | — | _(empty)_ |

**Divergences from the blog numbering** (catalogue authoritative; blog index ≡ catalogue index
everywhere else):

| idx | catalogue (authoritative) | blog name | what the blog name actually is |
|---|---|---|---|
| `05` | Wait | WaitNSeconds | paraphrase of `Wait` |
| `16` | ResetCodePriority | GTextPilotDefine | `DisplaySubTitle`'s parameter label |
| `17` | InterruptTriggerCode | ResetCodePriority | (blog shifted +1) |
| `18` | CommsFromShip | InterruptTriggerCode | (blog shifted +1) |
| `19` | CommsFromPilot | CommsFromShip | blog folds the pilot twin away |
| `26` | Dock | RadiusOfSphere | `SetActionCentre`'s parameter label |
| `27` | DisableTaunts | ShipToDock | paraphrase of `Dock` |
| `28` | Fly | DisableTaunts | (blog shifted) |
| `29` | CommsFromShipOnce | ShipPointToFlyTo | `Fly`'s parameter label |
| `2A` | CommsFromPilotOnce | CommsFromShipOnce | blog folds the pilot twin away |
| `51` | KillAllScriptExecutionExecptMe | …ExceptMe | dev typo preserved in the binary |
| `58` | Cloak | EntityToCloak | paraphrase of `Cloak` |
| `5F` | _(empty)_ | Test_AI_Function | the disabled stub is at `0x60`, not `0x5F` |

The catalogue carries **`CommsFromPilot`** (`0x19`) and **`CommsFromPilotOnce`** (`0x2A`) as first-class
pilot-voice twins of `CommsFromShip`/`…Once`; the blog folds each pair into one, which — together with
the three parameter-label phantoms above — is what shifts its indices across the two ranges. Dev-original
names like `PlayFostersLastStand`, `WillsBlag`, `DarrensNaughtyBlag` — and copy-paste leftovers
(`ReplenishWeapons` and `WillsBlag` both inherit `Cloak`'s *"Entity to cloak"* label) — confirm these are
recovered symbols, not guesses. Every command's parameter labels are listed in
[§ Command parameters](#command-parameters).

---

## AI behaviour codes (script opcode `0x32 <index>`)

Set a ship/flight-group's AI pattern. From Starlancer ME's *AI Codes* page, `0x00`–`0x44`.

| | | | |
|---|---|---|---|
| `00` Do Nothing | `12` Slow Rotate | `24` Boridin breakaway | `36` Eject Spin |
| `01` Fly Aimlessly | `13` Jump In | `25` FAIL | `37` Dock |
| `02` Launch Missile | `14` Jump Out | `26` Rotate Boridin warp projector | `38` Dark Reign shoot |
| `03` Launch Missile | `15` Find Scoop Up | `27` Ripper drop carried object | `39` Ripper end drop object |
| `04` Warp In | `16` Random Spin Slow | `28` Jump In | `3A` Ripper attach pod to Mammoth |
| `05` Warp Out | `17` Random Spin Med | `29` Jump Out | `3B` Eject fighter attack |
| `06` Fly | `18` Random Spin Fast | `2A` (unknown) | `3C` Disrupted |
| `07` Run Away | `19` Fixed Gate Jump In | `2B` Huge explosion | `3D` Capship list left |
| `08` Land | `1A` Fixed Gate Jump Out | `2C` Zero velocity + rotation | `3E` Capship list right |
| `09` Escort | `1B` Formation | `2D` Fly ship backwards | `3F` Friendly Fire |
| `0A` Find New Target | `1C` Fixed Gate Open | `2E` Player Control | `40` Eject Player |
| `0B` Explode | `1D` Fixed Gate Close | `2F` Multiplayer Control | `41` Ship Follow Curve Backwards |
| `0C` Ripper grabs object | `1E` Eject | `30` Avoid Target | `42` Mill |
| `0D` Object Attach | `1F` Fixed Gate Collapse | `31` Torpedo | `43` Deathmatch Respawn Effect |
| `0E` Formation Regroup | `20` Match Speed | `32` Launch | `44` Deathmatch Dark Reign target |
| `0F` Patrol Route | `21` Dark Reign shoot | `33` Fight | |
| `10` Toggle Cloak | `22` Move to spawn pos | `34` Destroy itself | |
| `11` Ship Follow Curve | `23` Turn object lights on | `35` Scoop Up | |

---

## Script-stream & expression opcodes

The bytes that frame the action stream and evaluate conditions. `0x21`/`0x32` are the two
"prefixed" dispatchers above; the rest push operands or perform the if/else logic behind
`SUCCESS`/`FAIL` branching. (Stream-byte semantics are corroborated by Starlancer ME's
hex-level posts; the expression micro-ops by our VM table `DAT_004F6350`.)

| opcode | kind | meaning |
|---|---|---|
| `0x21 <i>` | command | Call Executor command `#i` (consumes that command's params) |
| `0x32 <i>` | AI code | Set AI behaviour `#i` on the current entity |
| `0x2A <n>` | speech | Play speech: `n` = speech index (our HOG copies); blog's copies embed a literal `.ut` filename |
| `0x2C <o>` | operand | Single-object reference (one ship/entity) |
| `0x2D <g>` | operand | Flight-group reference |
| `0x22 <p>` | part | Section/part marker `22 00`…`22 1F` — start of script "part" `p` |
| `0x4D <p>` | part jump | Branch into part `p` |
| `0x43` | end | Code/line-end marker |
| `0x27 <i>` | expr | **Read** global `var[i].value` (read-mem) |
| `0x40 <i>` | expr | Push **address** of global `var[i].value` (write-mem lvalue) |
| `0x3F <i>` | expr | Push address of array slot `[i]` (lvalue); land-loop branch in the ending context |
| `0x23` / `0x24` | expr | Push 16-bit immediate |
| `0x28 <n>` | expr | Wait / operand fetch (compare context) |
| `0x02` / `0x03` | expr | Compare `!=` / `==` |
| `0x14` | expr | Squad / condition membership test |

**Win/lose pattern** (Starlancer ME's flagship observation, matching our `0x27`/`0x40`
decode): when the kill condition is met, `0x40` **writes** a flag; at mission end `0x27`
**reads** it and the `0x02/0x03` compare selects the SUCCESS vs FAIL branch — which play
different comms (`…_001.ut` vs `…_002.ut`). Missions **default to "failed"** and are promoted
to one of the five outcome grades (see `dte-format.md` §Outcomes).

---

## Ship / pilot ID tables

These two enums are Starlancer ME's data (full lists on their *Ship list* and *Pilot list*
pages); reproduced here as anchors and cross-referenced to our `SHIPSTATS.BIN` ordering (see
[`stats-format.md`](stats-format.md)). Faction = ship-name prefix (`Us/Uk/Jap/Ger/Fr/It` =
Alliance; `Ussr/Mid/Chi/Coal` = Coalition).

**Ship types** (`0x00`–`0xFF`, anchors): `00` Us Predator · `04` Us Coyote · `07` Us Patriot ·
`0C` Uk Reliant (carrier) · `0D` Jap Yamato (carrier) · `0F` Uk Kestrel · `16` Us Ulysses ·
`1F` Us Ripper · `20` Ger Lueneburg · `21` Uk Mammoth · `2B` Ussr Sabre · `44` Ussr Dark Reign ·
`48` Ussr Boridin · `4A` Torpedo · `4E–5B` debris/corpses · `5F–6C`,`C9–D3` planets ·
`79–8B` asteroids · `F4–FF` "Tiger"-variant fighters.

**Pilots / IFF** (`0x00`–`0x7B`, ~124): named pilots & callsigns, e.g. `14` Cat Foster,
`7A` Cat Foster Prowler. The pilot page does **not** map pilot → faction; faction must be
inferred from the ship prefix. (Open item — see contribution notes.)

---

## Command parameters

The developers' own per-parameter descriptions, recovered from the catalogue at `0x4F0F50` (commands
not listed take no parameters). Spelling, casing and copy-paste leftovers are preserved verbatim.

* `00` **PrintShipName** — Test Param 1; Test Param 2
* `01` **CreateTimer** — Unique ID to identify timer; Function to execute when timer activates; Number of seconds before timer activates; Number of activations (0 == continuous)
* `02` **DestroyTimer** — Unique ID of timer to be destroyed
* `03` **CreateFlightGroup** — Flight Group name to initialize
* `04` **DestroyFlightGroup** — Flight Group name to destroy
* `05` **Wait** — Number of Seconds to wait
* `06` **PlaySpeech** — Name of speech file
* `08` **PlayCommsMovie** — Name of movie file; Name of speech file; GText thingy hangover err....
* `0A` **PrintDebugMessage** — Text to print
* `0B` **SetAI** — Entity to be controlled; AI Mode; Initialize Immediately (T/F); Entity to target (can be NULL)
* `0C` **ClearAI** — Entity to be cleared
* `0D` **SetPatrolRoute** — Entity to send to patrol route; Patrol route to follow
* `0E` **SetPilot** — Ship to host pilot; Pilot to fly ship
* `0F` **SetTriggerState** — Entity owning trigger; Trigger type to enable/disable; TRUE for enable; FALSE for disable
* `10` **StartDirectorCam** — Curve for camera to follow (or Ship for static cam); Ship for camera to track (can be NULL); Duration of camera (seconds); Tracks curve to this ship's speed (can be NULL); Ships to disable for duration
* `11` **StartShipAnimation** — Ship to animate; Animation Name
* `12` **ShipFollowCurve** — Entity to follow curve; The curve for the entity to follow; Duration of movement (seconds)
* `13` **SetupLaunch** — Entity to be launched; Ship to launch from; Launch position
* `14` **StartLaunch** — Entity to be launched
* `15` **DisplaySubTitle** — GText pilot define
* `16` **ResetCodePriority** — Entity to have priorities reset
* `18` **CommsFromShip** — Ship sending comm; Head movement; Name of speech file
* `19` **CommsFromPilot** — Ship sending comm; Head movement; Name of speech file
* `1A` **SetInvulnerability** — Ship concerned; Invulnerability (0 - non, 1 - player can hit, 2 - fully invulnerable, 3 - Eject before exploding
* `1B` **MovingShipFollowCurve** — Entity to follow curve; The curve for the entity to follow; Duration of movement (seconds); Entity for curve to use as its start offset
* `1C` **DisableObject** — Entity concerned; True/False
* `1D` **PositionRelative** — Entity to position; Ship/Point to use as relative marker
* `1F` **StartMissileCam** — Ship that fired missile
* `20` **StartChaseCam** — Ship to follow
* `21` **SetPlayerTarget** — Player Ship; Ship to target
* `22` **SetTargetable** — Entity; true - object targetable, false - not targetable
* `23` **PlayMusic** — Name of music file; True - Play Immediately, false - Fade old tune first
* `25` **SetActionCentre** — Object to action around; Radius of sphere - 0 for default
* `26` **Dock** — Ship to dock; Object ship is to dock to; Docking port
* `27` **DisableTaunts** — true - Disable bad guy taunts
* `28` **Fly** — Ship; Point to fly to; Speed (0 - Default)
* `29` **CommsFromShipOnce** — Ship sending comm; Head movement; Name of speech file
* `2A` **CommsFromPilotOnce** — Ship sending comm; Head movement; Name of speech file
* `2B` **DisableLights** — Entity; True or False
* `2C` **SetEnvironmentFX** — Effect type to set; On(TRUE) or Off(FALSE)
* `2E` **DisableGenericComms** — True - Disable all hard coded comms events
* `2F` **DisableGuns** — Entity; TRUE - disable guns, FALSE enable guns
* `30` **SetNavPoint** — Entity; Nav Point
* `31` **SetEscortPoint** — Entity; Escort Point
* `33` **DisableMissiles** — Entity; TRUE - disable missiles, FALSE enable missiles
* `34` **DisableEngines** — Entity; TRUE - disable engines, FALSE enable engines
* `35` **DisableEject** — Entity; TRUE - disable eject, FALSE enable eject
* `36` **SetHostile** — Entity; true - entity(s) hostile, false - friendly
* `39` **SetPrimaryTarget** — Entity
* `3A` **WaitForJumpOrLaunch** — Entity
* `3B` **DoNotDisturb** — Entity; true - dont disturb, false - can disturb
* `3C` **SetEnvironmentFXNebula** — Index of nebula material (0..6)
* `3D` **StartShipAnimationReverse** — Ship to animate; Animation Name
* `3E` **SnapToPoint** — Ship to move; Point to move to
* `40` **OpenInstrument** — Instrument number to open
* `41` **CloseInstrument** — Instrument number to close
* `42` **DestroySubObject** — SubObject to destroy; true - keep damaged model, false - no damaged model
* `43` **SetObjective** — Objective number; State(0=Inactive, 1=Active, 2=Current)
* `44` **SetRescueProbabilities** — Probability of Nanny Rescue ( 1-100% ); Probability of Antanov Capture ( 1-100% ); Probability of being Destroyed ( 1-100% )
* `45` **IsShipThisPlayer** — Ship to test
* `46` **SetFlybackMarker** — Entity concerned; Range
* `48` **StopShipAnimation** — Ship to stop animation for; Animation Name
* `49` **SetShipAvoidance** — Entity concerned; TRUE - Disable Avoidance code, FALSE - Enable avoidance code
* `4A` **MatchSpeed** — Entity concerned; TRUE - Enable Match Speed, FALSE - Disable Match Speed
* `4B` **MovingShipBackupCurve** — Entity to follow curve; The curve for the entity to follow; Duration of movement (seconds); Entity for curve to use as its start offset
* `4C` **WaitForKey** — Key number to wait for
* `4E` **TurretSetTarget** — Turret; Entity to target
* `4F` **SetAnyTriggerState** — Entity owning trigger; Trigger type to enable/disable; TRUE for enable; FALSE for disable; Trigger Type Number(for triggers of same type - Count from 0)
* `52` **StackDirectorCam** — Curve for camera to follow (or Ship for static cam); Ship for camera to track (can be NULL); Duration of camera (seconds); Tracks curve to this ship's speed (can be NULL); Ships to disable for duration
* `53` **Scanner** — Object to scan for - NULL to disable
* `54` **ReplaceSubObject** — SubObject to replace; Object to replace it with
* `55` **Fire** — Ship to fire; Duration
* `56` **MultiplayerScriptSync** — Sync number
* `58` **Cloak** — Entity to cloak; True - Cloak on, False - cloak off
* `59` **ReplenishWeapons** — Entity to cloak
* `5A` **WillsBlag** — Entity to cloak
* `5B` **ShowHudIcon** — Icon; 0 - off, 1 - on, 2 - flash
* `5C` **DisableListing** — Ship; true - stop listing, false - enable listing
* `5D` **DisableObjectAtNextJump** — Ship; true - disable, false - enable
* `5E` **DarrensNaughtyBlag** — Ship; Ship

---

## Attribution

The numeric opcode/command/AI/ship/pilot tables and the observed runtime semantics are the
work of **Captain Foster / "Starlancer ME"** (<https://starlancerme.blogspot.com/>,
[@CaptainFoster](https://www.youtube.com/@CaptainFoster), `email withheld`), who also
maintains a Python "Mission Ship Editor". This document pairs that black-box research with our
static disassembly (implementation addresses, parameter counts, the VM, struct layouts). Where
the two overlap they agree; where they differ it is noted above and in
[`dte-format.md`](dte-format.md).
