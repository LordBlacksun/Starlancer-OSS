# Starlancer `.DTE` mission format

Authoritative spec for Starlancer's per-mission **data + script** files, fusing two
independent reverse-engineering efforts:

* **Static RE of the decrypted executable** (this project) — addresses are RVAs/VAs for
  ImageBase `0x400000`, read from `analysis/exports/LANCER_decrypted.exe.decompiled.c`; Ghidra
  names `FUN_<addr>`. Source of struct layouts, the VM, the trigger enum, and per-command
  implementation addresses.
* **Black-box RE by Captain Foster / "Starlancer ME"** — <https://starlancerme.blogspot.com/>,
  YouTube [@CaptainFoster](https://www.youtube.com/@CaptainFoster), `email withheld`.
  Source of numeric opcode/command/AI/ship/pilot IDs and observed in-game semantics, plus a
  Python "Mission Ship Editor". **Their work is the semantic backbone; ours confirms and
  addresses it.** See §Reconciliation.

The full opcode/command/AI tables live in the companion
**[`dte-scripting-reference.md`](dte-scripting-reference.md)**; tooling in `tools/dte_parse.py`.

---

## 1. What it is, and the inventory

A `.DTE` is one **mission**: a set of data sections (ships, triggers, globals, strings, …)
plus a block of **trigger/event script bytecode** interpreted by an in-engine VM. It is data,
never native code. `resource.hog` holds **44** of them (campaign `mission1..35`, the test set
`mission191/251/271/311`, multiplayer `mission81..88`, and `mission29/99/801`). Compressed
(RefPack) sizes run 4.4 KB–66 KB; each **decompresses to a fixed-layout image** (the main
campaign template is `0xCFBE7` = 850,919 B). `dte_parse.py sweep` decodes all **44** cleanly;
`dte_parse.py decode <m>` dumps the directory, ships, objectives, triggers, and a script
disassembly.

Path at load: `..\missions\%s.dte`. The engine reads a loose `missions\` file if present, else
the HOG copy — so edited missions need not be repacked.

---

## 2. File container  [RESOLVED]

The HOG-stored `.dte` is **RefPack / EA "QFS" compressed** — signature `10 FB`, then a 3-byte
big-endian uncompressed size (the standard EA codec, unsurprising since the HOG is EA's BIGF
archive). `dte_parse.py` ships a clean-room RefPack decoder; all 44 files decompress with the
produced length matching the header size exactly.

The loader is **`FUN_00451D90`**. It obtains the bytes via `FUN_0045A300` — a loose
`missions\%s.dte` if present (`FUN_004AD6E0` = `GetFileAttributes`), else the HOG resource
(`FUN_004C5BD0` → `FUN_004C5BE0`, a straight read, *no* extra transform; a `0x1A` EOF byte is
appended to loose reads by `FUN_0045A3E0`; read failure → *"** IT'S A DISASTER! ** Emergency
file saved to 'fatal.dte'"*). The RefPack stream **expands into a fixed-layout image** (the
`≤ 0xFA000` buffer is sized for it). The loader then walks a **27-entry, 8-byte directory at
offset 0** of that image via 27 calls to **`FUN_00452A20`**, each reading `{ u16 count, byte
relocation-flags @ bits 24-27, u32 offset }`, advancing the cursor 8 bytes, and fixing `offset`
to a live pointer (`offset + image base`). `offset == 0xFFFF` marks an unused section.

> **Cross-validation with Starlancer ME.** Decompressed, our `mission1` directory places ships
> (objects) at `0x30FF7`, the FG/objective table at `0x3A7F7`, triggers at `0x3BBF7`, the event
> script at `0x47BF7`, and the target list at `0x57BF7` — **identical, to the byte**, to Captain
> Foster's black-box anchors. The blog's "offsets" are positions in exactly this decompressed
> image; the two efforts now agree completely. (The earlier "our copies differ / offsets out of
> range / inline `us_prowler` at `0xB6`" puzzle was just the compression: our extracted blob is
> the *packed* form, theirs the *expanded* one.) Relocation-flag patterns and image sizes vary by
> template — `0xF` flags / `0xCFBE7` bytes for the campaign, `0x1/0x3/0x7` flags and smaller
> images for some multiplayer / instant-action missions — but the directory format is uniform.

### The 27 sections (load order, with destination globals)

| # | global | contents (✓ = stride/role verified) |
|---|---|---|
| 0 | `DAT_00525FA8` | string pool (names resolved by index) |
| 1 | `DAT_00525F3C` | operand-resolution array (kind 0, `FUN_004529D0`) ✓ stride `2` |
| 2 | `DAT_005294F8` | **globals / variables** ✓ stride `0x0C` (`u16 nameIdx`, `u32 value`) |
| 3 | `DAT_0052951C` | **ship / flight-group array** ✓ stride `0x4C`, count `DAT_00529504` |
| 4 | `DAT_005267CC` | **objective / operand table** ✓ stride `0x14` (`FUN_00452AA0`) |
| 5 | `DAT_005294E0` | **trigger / event records** ✓ stride `0x30` |
| 6 | `DAT_00525F88` | **script bytecode base** ✓ (IP origin for the VM) |
| 7 | `DAT_005267C0` | **per-ship trigger index** ✓ stride `8` (`+1` count, `+2` u16 first-index) |
| 8 | `DAT_005267D0` | object / launch table ✓ stride `0x1C` |
| 9 | `DAT_005256C8` | populated in 16/44 missions; record layout TBD |
| 10 | `DAT_005294D8` | **per-bytecode-byte flag array** ✓ (VM yield map, indexed `IP − bytecode base`) |
| 11 | `PTR_DAT_004EF2FC` | operand / target list |
| 12 | `DAT_005294FC` | secondary trigger/condition list (count `DAT_005294F0`) |
| 13 | `DAT_00529500` | squad / membership table ✓ stride `0x0C` |
| 14 | `DAT_00525F18` | stride `8`; entry `+4` u16 → sec 15 (rare: 3/44) |
| 15 | `DAT_005256B8` | position / nav-geometry records ✓ stride `0x10` (rare: 3/44) |
| 16 | `DAT_00525FB0` | **sub-object / model table** ✓ stride `0x44` (36/44; index fields + 3-D coord vectors; `FUN_004571D0`) |
| 17 | `DAT_005294EC` | vestigial — empty in all 44 |
| 18 | `DAT_00525FB4` | vestigial — empty in all 44 |
| 19 | `DAT_0052950C` | vestigial — empty in all 44 |
| 20 | `DAT_00525FA0` | vestigial — empty in all 44 |
| 21 | (stack temp) | transient (count only) |
| 22 | `DAT_00525278` | operand-resolution array (kind 1) ✓ stride `2` (large: ≤ 61436) |
| 23 | `PTR_DAT_004EE7D8` | populated 40/44; record layout TBD |
| 24 | `DAT_00525F9C` | populated 36/44; record layout TBD |
| 25 | `DAT_00525F90` | vestigial — empty in all 44 |
| 26 | `DAT_0052570C` | operand-resolution array (kind 2) ✓ stride `2` (rare: 3/44) |

> Strides + population above come from a 44-mission `dte_parse.py sweep --sections` (offset +
> count·stride stays in-image, **zero overflow**); "vestigial" = empty in all 44. Sections 9, 12,
> 23, 24 are populated but their record layouts are still open (§11).

---

## 3. Data records

**Ship / flight-group** (stride `0x4C` = 76 B; `DAT_0052951C`, count `DAT_00529504`). Field map
verified by decoding all 44 (`dte_parse.py decode --section ships`) plus the load-time mirror
`FUN_00452010`/`FUN_004520A0` and the arm loop `FUN_0045CBC0`: flight-group # at `+0x00`; **name
index** `u16` at `+0x04` (→ string pool, e.g. `Player_Ship`, `(A1)Naginata`, `(WL)Viper's
Coyote`); **position vector** (3×`float`) at `+0x08` — the *runtime* copy, mirrored at load from
the *authored* position at `+0x1C` by `FUN_00452010`; IFF/team byte at `+0x15`; type/role code
(**`u16`** at `+0x18`) — normal ships `< 0x100`, but special objects (nav points, jump/escort
markers) use `0x3E3`–`0x3E8`/`999`, so a byte read truncates ~41% of records; flag byte `+0x17`
(bit0 = disabled);
ship-type/sub-object model indices via `FUN_004571D0` into `&DAT_00587CE0`. Coordinates are
IEEE-754 floats. This mirrors Starlancer ME's colour-coded object record (coords, flight-group #,
pilot/IFF, ship #, launch origin, gate #).

**Orientation [RESOLVED].** Three `int16` **Euler angles in whole degrees** at the *non-contiguous*
offsets **yaw `+0x2E`, pitch `+0x3A`, roll `+0x4A`** — the *authored* set, mirrored at load to the
runtime copy `+0x2C`/`+0x38`/`+0x48` by `FUN_00452010` and turned into a rotation by `FUN_00452240`,
which reads exactly those three shorts and scales each by `_DAT_004dc71c = 0.01745329` (= π/180) —
proving degrees. Verified across all 44 missions (8265 ship records; every angle ∈ [−360, 360]; a
flight group's wingmen share a heading — e.g. `mission1`'s player + escorts are all yaw 90°). The
earlier `+0x26`/`+0x32`/`+0x42` guess was the mirror loop's offsets *relative to the `+0x08` base*
(`0x26 + 8 = 0x2E`). Other runtime fields touched by the arm loop `FUN_0045CBC0`: `+0x17` flag,
`+0x1B` "claimed" byte, `+0x30` u32 handle (init `0xFFFFFFFF`). No waypoint/goal sub-array fits the
`0x4C` record — route/curve data lives in the directory sections (§2), not the ship record.

**Globals / variables** (stride `0x0C`; `DAT_005294F8`): `u16 nameIdx`, `u32 value`. Read/written
by script opcodes `0x27`/`0x40`.

**Objectives** (stride `0x14`; `DAT_005267CC`; `FUN_00452AA0` → `base + idx*0x14`). Set by
`SetObjective` (state `0 Inactive / 1 Active / 2 Current`). The HUD/MFD renderer `FUN_00486830`
emits *"ERROR: No mission Objectives defined!"* when the active slot is empty.

---

## 4. Trigger system  [VERIFIED]

**Conditions — the `TT_*` enum.** Stored at trigger-record `+0x15`. **33 scriptable types,
`0x00`–`0x20`**, verified from the string array in `FUN_0045B330` and identical to Starlancer
ME's table (this **corrects** the earlier 35-entry list with its duplicate `TT_RIPPER_*` and
mis-ordered tail). Full list in [`dte-scripting-reference.md`](dte-scripting-reference.md). The
condition-*descriptor* table `DAT_0052952C` (stride `0x1C`) has 35 entries
(`_DAT_00525F8C = 0x23`) — the 2 beyond `0x20` are internal, non-scriptable conditions.

**Trigger record** (`0x30` = 48 B; `DAT_005294E0`). From matcher `FUN_0045CEA0` and arm loop
`FUN_0045CBC0`:

| off | field |
|---|---|
| `+0x00` | subject ship / flight-group ref |
| `+0x01` | repeat mode: `0` one-shot (clears `+0x14` on fire), `2` repeat-N via counter `+0x19` |
| `+0x02` | `u16` linked action/script index (`0xFFFF` = none) |
| `+0x14` | enabled flag (armed to `1` by `FUN_0045CBC0`) |
| `+0x15` | `TT_*` condition type |
| `+0x16` | action id → spawns the script thread (`FUN_0045B8D0`) |
| `+0x19` | repeat counter |
| `+0x1C…` | operand array (stride 4), each validated by `FUN_0045D810` |

**Condition descriptor** (`0x1C`; `DAT_0052952C` → `&PTR_s_ShotAt_004F6698`): `+0x0C` scatter
slot into per-ship state, `+0x0D` discriminator, `+0x10/+0x14/+0x18` three handler pointers.

**Firing path.** Event → look up the subject's trigger list via per-ship index `DAT_005267C0`
→ `FUN_0045CEA0` tests type + operands → on success spawn the action script via the record's
`+0x16`. **Proximity** (types 5/6) and inside/outside-object (4) are *polled* in `FUN_0045AF60`
(squared-distance tests). Fired triggers queue in `DAT_0052ABE0` (stride `0x30`, cap 1000 →
*"Trigger List exceeded"*).

---

## 5. Scripting bytecode VM  [VERIFIED]

A **single bytecode stream** (section 6, base `DAT_00525F88`) interpreted by **`FUN_0045C980`**:
fetch one opcode byte → index the **256-entry handler table `DAT_004F6350`** → advance IP →
call handler; repeat until a handler returns 0 (yield/finish). Each action-script block is
prefixed by a `u16` byte length; a thread is created by `FUN_0045B8D0` (IP at thread-ctx
`+0x10`, end = base + leading length). A parallel **per-byte flag array** (section 10,
`DAT_005294D8`, indexed `IP − DAT_00525F88`) marks yield points so long scripts suspend across
frames.

Two registers of meaning share the stream: **commands** (`0x21 <i>` → the Executor catalogue at
VA `0x4F0F50`, installed by `FUN_0045CE30`, dispatched by `FUN_0045BEA0`) and **micro-ops** (compare
/ push-immediate / global read-write — the if/else machinery). The complete opcode, Executor-command
and AI-code (`0x32`, 0x00–0x44) tables are in
**[`dte-scripting-reference.md`](dte-scripting-reference.md)**. We now walk the catalogue in full —
**95 real commands (`0x00`–`0x5E`)** with the developers' own names, **parameter labels** and impl
addresses recovered from the binary — which also **corrects the command numbering** at `0x16`–`0x19`
and `0x26`–`0x2A` (see §9).

---

## 6. Outcomes, objectives, globals  [VERIFIED]

**Outcome grade** = `DAT_0052A428`, selecting `&PTR_s_Failure_004EF34C`. **Five tiers, 0–4**
(*"Failure", "Partial Failure", "Partial Success", "Success", "Success + Bonus"*; debug
*"Mission is flagged as a %s"*) — this **corrects** the earlier "1–4". A mission **defaults to
"failed"** and is promoted by the win/lose data-flow: when the kill condition fires, opcode
`0x40` writes a flag; at mission end `0x27` reads it and the `0x02/0x03` compare branches to
SUCCESS vs FAIL (playing `…_001.ut` vs `…_002.ut`). `TerminateMission` ends the mission.

---

## 7. Lifecycle, AI & multiplayer  [VERIFIED]

* **`FUN_0045A4E0`/`A530`/`A570`** = init / destroy / process (per-frame). Guards
  `DAT_005373E8` (active), `DAT_005373E4` (fire count). Process calls the proximity/timer
  trigger evaluators.
* **`FUN_00401000`** = MP AI sync gate — per-ship per-syncpoint bitmask `entity+0x710+idx`;
  returns "proceed" only once all players (`DAT_0058832C`) have set their bit (*"Player reached
  sync point"*). Driven from script by `MultiplayerScriptSync` / `MultiPlayerSync`.
* **`FUN_0040D210`** = capital-ship / turret / ion-cannon AI (ship-type ids `0x44`/`0x48`/`0xA5`;
  *"POOPING IONCANNONAI…"*).
* **`FUN_0048E140`** = debug dump to `c:\mission.txt` (`ships %d`, `syncs:`, `waitingforsync`,
  `globals:` — dumps the `DAT_005294F8` variable table).
* **`FUN_004924B0`** = per-frame mission-exit poll; manages time-compression and the outcome
  grade `DAT_0052A428`.

---

## 8. Saves / profile / pilots  [VERIFIED]

* **Saves are EA-IFF** (`saves\%sGAME%02d.IFF`, top form `'SAVE'`, one chunk `'MISS'` = mission
  state). Reader `FUN_00490930`/`…`; writer `FUN_00475650` (`gameflow.cpp`).
* **`profile.bin`** = 208 B blob (begins with the profile name = the save `%s` prefix).
* **Pilot files** = `pilots\%s.fm8`; mission-end killer/virtual-pilot record writer
  `FUN_00453DE0` uses the outcome grade `DAT_0052A428`.

---

## 9. Reconciliation — our decompilation × Starlancer ME

| Topic | Agreement / who has what |
|---|---|
| `TT_*` trigger enum | **Exact match** (33, `0x00`–`0x20`). Our `FUN_0045B330` array ≡ their *Triggers* page. |
| Executor commands (`0x21`) | We **walk the engine's live catalogue** (`0x4F0F50`; 95 cmds + impl + param labels). Indices agree **except `0x16`–`0x19` and `0x26`–`0x2A`**, where the blog mistook parameter-label text for commands (its `GTextPilotDefine`/`RadiusOfSphere`/`ShipPointToFlyTo` are the *params* of `DisplaySubTitle`/`SetActionCentre`/`Fly`; `WaitNSeconds`/`ShipToDock`/`EntityToCloak` paraphrase `Wait`/`Dock`/`Cloak`) and folds away the `CommsFromPilot`/`…Once` twins. Catalogue numbering is authoritative; blog names kept as a cross-reference. |
| `0x27`/`0x40`/`0x3F` | Their behavioural read-mem/write-mem/jump ≡ our static read-global / global-lvalue / array-lvalue. |
| AI codes (`0x32`), ship/pilot IDs | Their tables (we have not re-derived these numerically; adopted with credit). |
| Win/lose, default-fail, carrier-landing tree | Their **runtime semantics** (observed in-game) — a layer pure disassembly lacks. |
| File container offsets | **Exact match (resolved).** Their offsets = positions in our *decompressed* (RefPack) image: `ships 0x30FF7`, `events 0x47BF7`, `targets 0x57BF7` all coincide to the byte. The packed-vs-expanded form was the only difference. |
| Outcome tiers | We correct to **0–4** (five); resolved the count. |

---

## 10. Localized text & mission titles  [RESOLVED]

Campaign **mission titles** — and most front-end / campaign UI text — are **Win32 string-table
(`RT_STRING`) resources in the external `language.dll`**, not in `.text`, the `.HOG`, or the `.DTE`.
At startup `FUN_00490DC0` does `LoadLibraryA("language.dll")`, then enumerates strings with
`LoadStringA` (id from 1 upward) into a pointer array `DAT_0057DBBC` (count `DAT_0057DBC0`; backing
store + array allocated via `SR_MEM_allocate`, tagged `C:\lancer\game\language.cpp`). The accessor
`FUN_00491030(id)` returns `DAT_0057DBBC[id − 1]` (**1-based**; out-of-range → debug *"invalid
language string %d"*, matching the embedded assert *"(string_number − FIRST_RESOURCE_ID) ≥ 0 && … <
num_language_strings"*). The mission-title call site indexes a u16 string-ID table `DAT_004E5C78[slot]`
(with per-region remaps `0xB`/`0xC`→`0xE`, `0x10`→`0x12`, `0x15`→`0x17`) and passes the id to
`FUN_00491030`. So a plain string search for title text in the exe fails *by design* — the strings
live in `language.dll` (a sibling `itac_language.dll` holds tactical-computer text). `language.dll`
is a loose game file, not part of our extracted data, so this is code-proven rather than resource-walked.

## 11. Open items

* Record layouts of the still-undecoded **populated** sections — 9 (16/44), 12 (34/44), 23 (40/44),
  24 (36/44) — plus deep field decode of sec 15 (nav geometry) and sec 16 (sub-object/model table).
* Pilot → faction (IFF) binding; exact `0x28`/`0x23` compare semantics.
* RefPack **encoder** + HOG repack for a full read-modify-write mission editor (the decode side is done).

## Related
[`dte-scripting-reference.md`](dte-scripting-reference.md) · [[stats-format.md]] ·
[[hog-format.md]] · `tools/dte_parse.py` · blog `starlancerme.blogspot.com`
(memory: `starlancer-mission-format-blog`).
