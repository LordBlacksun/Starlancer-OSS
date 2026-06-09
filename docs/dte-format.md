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
`mission191/251/271/311`, multiplayer `mission81..88`, and `mission29/99/801`). Raw HOG sizes
run 4.4 KB–66 KB; our 44-file sweep (`dte_parse.py sweep`) shows consistent structure
(campaign missions ~30–37 % printable; MP missions sparser).

Path at load: `..\missions\%s.dte`. The engine reads a loose `missions\` file if present, else
the HOG copy — so edited missions need not be repacked.

---

## 2. File container  [PARTIALLY OPEN]

The loader is **`FUN_00451D90`**. It reads the whole file into a buffer via `FUN_0045A300`
(≤ `0xFA000`; a straight copy — no decompression — with a `0x1A` EOF byte appended by
`FUN_0045A3E0`; read failure → *"** IT'S A DISASTER! ** Emergency file saved to 'fatal.dte'"*).
It then resolves **27 sections in a fixed order** via 27 calls to **`FUN_00452A20`**, each
consuming an 8-byte descriptor `{ u16 count (+ four relocation-flag bits in the top byte),
u32 offset }`, advancing the cursor 8 bytes, and fixing `offset` to a live pointer (`offset +
base`).

> **Open caveat (verified by inspection of our files).** Decoding our HOG-extracted blobs as a
> 27×8 descriptor table at offset 0 does **not** validate — the offset fields fall out of
> range, and the first real data (records carrying inline name strings: `us_prowler`,
> `sr_sabre`, `mammoth (ANS Guliver)`, pilot `ian.fm8`) begins at ~`0xB6`, with a `00 00 ff cc`
> fill region at the tail. So either a header precedes the descriptor table or the HOG blob is a
> packed form the engine expands before this directory applies. **Our HOG copies also differ
> from Starlancer ME's working copies:** their mission1 anchors (`objects @0x30FF7`,
> `events @0x47BF7`) lie far past our 29 KB (`0x714E`) EOF, and our copies reference speech by
> index where theirs embed literal `.ut` filenames inline. The exact on-disk descriptor framing
> for our copies is the chief unresolved container question; the **section semantics below are
> verified from the loader and the consumers regardless.**

### The 27 sections (load order, with destination globals)

| # | global | contents (✓ = stride/role verified) |
|---|---|---|
| 0 | `DAT_00525FA8` | string pool (names resolved by index) |
| 1 | `DAT_00525F3C` | aux table |
| 2 | `DAT_005294F8` | **globals / variables** ✓ stride `0x0C` (`u16 nameIdx`, `u32 value`) |
| 3 | `DAT_0052951C` | **ship / flight-group array** ✓ stride `0x4C`, count `DAT_00529504` |
| 4 | `DAT_005267CC` | **objective / operand table** ✓ stride `0x14` (`FUN_00452AA0`) |
| 5 | `DAT_005294E0` | **trigger / event records** ✓ stride `0x30` |
| 6 | `DAT_00525F88` | **script bytecode base** ✓ (IP origin for the VM) |
| 7 | `DAT_005267C0` | **per-ship trigger index** ✓ stride `8` (`+1` count, `+2` u16 first-index) |
| 8 | `DAT_005267D0` | object / launch table ✓ stride `0x1C` |
| 9 | `DAT_005256C8` | — |
| 10 | `DAT_005294D8` | **per-bytecode-byte flag array** ✓ (VM yield map, indexed `IP − bytecode base`) |
| 11 | `PTR_DAT_004EF2FC` | operand / target list |
| 12 | `DAT_005294FC` | secondary trigger/condition list (count `DAT_005294F0`) |
| 13 | `DAT_00529500` | squad / membership table ✓ stride `0x0C` |
| 14–20, 22–26 | `DAT_00525F18`, `DAT_005256B8`, `DAT_00525FB0`, `DAT_005294EC`, `DAT_00525FB4`, `DAT_0052950C`, `DAT_00525FA0`, `DAT_00525278`, `PTR_DAT_004EE7D8`, `DAT_00525F9C`, `DAT_00525F90`, `DAT_0052570C` | present in the directory; record layouts not yet decoded (camera curves, nav/patrol routes, regions, comms, debris are the likely occupants — see the command catalogue) |
| 21 | (stack temp) | transient (count only) |

---

## 3. Data records

**Ship / flight-group** (stride `0x4C` = 76 B; `DAT_0052951C`, count `DAT_00529504`). Field
map from the load-time mirror `FUN_00452010`/`FUN_004520A0` and the arm loop `FUN_0045CBC0`:
position vector at `+0x14` (3×`float`); orientation **yaw/pitch/roll** at `+0x26`/`+0x32`/`+0x42`
(`u16` angles); type/role code at `+0x18` (special objects compared vs `0x3E3`–`0x3E5`/`999`);
flag byte `+0x17` (bit0 = disabled); ship-type/sub-object model indices via `FUN_004571D0` into
`&DAT_00587CE0`. Coordinates are IEEE-754 floats. This mirrors Starlancer ME's colour-coded
object record (coords, flight-group #, pilot/IFF, ship #, launch origin, gate #). *(Full 76-byte
map incl. the IFF field and waypoint sub-arrays — partial; see §Open.)*

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

Two registers of meaning share the stream: **commands** (`0x21 <i>` → the Executor catalogue
`DAT_004F3AD0`, installed by `FUN_0045CE30`) and **micro-ops** (compare / push-immediate /
global read-write — the if/else machinery). The complete opcode, Executor-command (96), and
AI-code (`0x32`, 0x00–0x44) tables are in
**[`dte-scripting-reference.md`](dte-scripting-reference.md)** — including the verified
implementation address + parameter count for ~90 of the 96 commands.

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
| Executor commands (`0x21`) | Their **indices** ≡ our **catalogue order**; we add impl address + param count for ~90/96. |
| `0x27`/`0x40`/`0x3F` | Their behavioural read-mem/write-mem/jump ≡ our static read-global / global-lvalue / array-lvalue. |
| AI codes (`0x32`), ship/pilot IDs | Their tables (we have not re-derived these numerically; adopted with credit). |
| Win/lose, default-fail, carrier-landing tree | Their **runtime semantics** (observed in-game) — a layer pure disassembly lacks. |
| File container offsets | **Differ** — their copies are larger / inline-speech; ours are HOG blobs, speech-by-index. Offset maps are **not** cross-transferable; the *semantic* tables are. |
| Outcome tiers | We correct to **0–4** (five); resolved the count. |

---

## 10. Open items

* Exact on-disk descriptor framing of our HOG `.dte` blobs (header? packed/expanded form?).
* Full 76-byte ship record (IFF/faction field, waypoint/goal sub-arrays).
* Record layouts of directory sections 9, 14–20, 22–26 (curves, routes, regions, comms, debris).
* The 6 blog-only Executor entries' implementations (`WaitNSeconds`, `GTextPilotDefine`,
  `RadiusOfSphere`, `ShipToDock`, `ShipPointToFlyTo`, `EntityToCloak`).
* Pilot → faction (IFF) binding; exact `0x28`/`0x23` compare semantics.

## Related
[`dte-scripting-reference.md`](dte-scripting-reference.md) · [[stats-format.md]] ·
[[hog-format.md]] · `tools/dte_parse.py` · blog `starlancerme.blogspot.com`
(memory: `starlancer-mission-format-blog`).
