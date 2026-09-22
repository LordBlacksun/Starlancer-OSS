# External reverse-engineering we build on — credits and provenance

*Written 2026-09-10. This file records whose work we have leaned on, what we
verified ourselves, and what we deliberately did not copy. It is the provenance
record for anything in this repository that originated outside it.*

Starlancer has been reverse-engineered more than once, by people who did not
know about each other. This project is one of those efforts. Where another
effort got somewhere first, or got somewhere we did not, the honest thing is to
say so by name, keep the boundary between their work and ours visible, and
verify rather than assume.

---

## 1. DMJC — `StarLanceDecomp` and `neoslancer` (2026)

- **Reverse-engineering notes:** https://github.com/DMJC/StarLanceDecomp
- **Reimplementation:** https://github.com/DMJC/neoslancer — "StarLancer Linux
  Port", C++20 on SDL2 + OpenGL, with Bink playback through FFmpeg.

Both repositories were created on **2026-09-08** and are moving fast. DMJC is a
long-standing open-source game developer whose other work includes Descent 3
Remastered, OpenXWA, a Wing Commander 3 remake, and the YOGEME mission editor
for the X-Wing series — i.e. the same corner of the space-sim world Starlancer
belongs to.

### What their notes contain

`StarLanceDecomp/reversing/` holds a prose function catalogue (332 entries), a
structured confidence database (503 rows, 108 of them at their top confidence
level), a dependency graph, a written methodology, and three Python tools
(`decode_spr.py`, `refpack_decompress.py`, `extract_language_strings.py`).

Their methodology is worth reading on its own terms. Every claim carries an
explicit 0–5 confidence rating, unrated legacy material is marked as such rather
than quietly promoted, and the unit of work is the subsystem rather than the
individual function. They also do live playtesting with debug instrumentation
under Wine — the half of the method this project does not use.

### The address spaces are the same

This is the fact that makes their work usable here at all. We independently
extracted every code address their three documents cite and tested it against
our own headless-Ghidra export of the decrypted image:

| check | result |
|---|---|
| distinct code addresses they cite | 99 |
| landing exactly on a function entry in our export | 96 (97%) |
| landing inside a function whose boundary our run drew differently | 3 |

Their `mainCRTStartup` sits at `0x004D1210`, which is the original entry point
our own notes recorded independently. Their `FUN_`/`DAT_` numbering is identical
to ours. Their notes and our export describe the same bytes, so their names can
be adopted directly rather than re-derived — with the verification caveat in §4.

### What we have taken, and what we have not

**Taken:** facts. Function names, addresses, struct field offsets and file-format
descriptions are discoveries about a third party's binary, not authorship, and
they are cited in place wherever used.

**Not taken:** their code. At the time of writing **neither repository carries a
licence**, which under GitHub's terms means no grant to copy, modify or
redistribute, whatever the author's intent. Most of DMJC's other projects are
GPL-3.0, the same licence as this repository, so this is very likely an oversight
rather than a decision — but until a licence appears, nothing of theirs is
vendored here. Every implementation in `tools/` is ours.

We have asked directly rather than assume:
[DMJC/StarLanceDecomp#2](https://github.com/DMJC/StarLanceDecomp/issues/2) (2026-09-10). If a
licence lands, this section gets revisited; until then the boundary above stands.

---

## 2. What we verified independently

Reading someone else's notes is not the same as confirming them. These are the
checks we ran against real game data, with our own code.

### 2.1 Most of `resource.hog` is compressed — our own doc understated this

Their `refpack_decompress.py` is a port of the game's own
`DecompressRefPackBlock` at `0x4CC350`. That prompted us to audit the archive
layer, where our documentation said extraction needs "no decompression" — true of
the container, misleading about the payloads. A census across every archive in a
retail install:

| archive | members | RefPack payloads |
|---|---:|---:|
| `resource.hog` | 967 | 950 (98%) |
| `CD1.HOG` | 225 | 18 (8%) |
| `CD2.HOG` | 174 | 0 |
| `pilots/pilots.hog` | 258 | 0 |
| `ms_speech/msspeech.hog` | 4369 | 0 |

Inside `resource.hog` every `.shp` model, every `.dte` mission, every `.fnt`,
`.ccb` and stats `.bin` is a RefPack stream. Across the set, 72 MB of stored
payload expands to 172 MB. Details and the per-extension table are in
[`hog-format.md`](hog-format.md).

We already had a RefPack decoder — it was written in June 2026 for the mission
containers — but it lived inside `dte_parse.py` and no other tool could reach it.
It is now `tools/refpack.py`, and `hog_extract.py --decompress` uses it.

### 2.2 A truncation bug in their decompressor

Running both decoders over all 968 RefPack streams in a retail install:

| | ours | theirs |
|---|---:|---:|
| output matches the stream's declared uncompressed size | 950/950 | 569/950 |
| Targa v2 footer intact on `.tga` members | 114/146 | 1/146 |

In all 381 differing cases their output is a **strict prefix** of ours — pure
truncation, 1 to 9 bytes, with no divergence in content. `brd2cd.tga` ends at
`TRUEVISION-XFILE` without the closing `.\0` of the fixed 18-byte footer.

The cause is the loop guard `while len(out) < out_size and pos+4 <= n`. A
well-formed RefPack stream ends with a `0xFC..0xFF` opcode carrying 0–3 trailing
literals, which can leave fewer than four bytes in the buffer; requiring four
bytes of lookahead drops that final run. Clamping the result to the declared size
then hides the shortfall. `tools/refpack.py` guards on `pos < len(data)` and
raises if the decoded length contradicts the header.

**Reported upstream 2026-09-10** with a minimal reproducer, the measured scale and the suggested
fix: [DMJC/StarLanceDecomp#1](https://github.com/DMJC/StarLanceDecomp/issues/1). Findings like this
go back to the person whose work they concern; they are not kept as an advantage.

### 2.3 Mission pilot IDs index `pilotstats.bin` directly

[`dte-scripting-reference.md`](dte-scripting-reference.md) recorded the mission
scripts' pilot/IFF ID space as `0x00`–`0x7B`, "~124" entries, with `0x14` as Cat
Foster — derived from mission data alone. Decompressing `pilotstats.bin` out of
`resource.hog` gives **exactly 124 records** of 352 bytes, with Cat Foster at
record `0x14` and "Cat Foster Prwlr" at `0x7A`. The ID is the record index. The
"~" is now gone, and the table can be read directly instead of inferred.

The same decompression confirms our 352-byte stats record independently: the four
tables expand to exact multiples of it — 15 guns, 16 missiles, 124 pilots, 256
ships.

### 2.4 A correction to our own engine map

Their catalogue names `0x00494040` `RunMissionGameplay`, the flight/combat main
loop. Our engine map called it "HUD target/lock widgets". Re-reading our own
decompilation settles it in their favour: the function installs a per-frame
callback, initialises the mission subsystems, runs a `do`/`while` main loop, and
then tears down — and the HUD strings we keyed on are *trace labels* passed to a
logging routine during that teardown, not drawing code.

The general lesson matters more than the single row. Much of our engine map was
built by attributing nearby string references to functions, which reliably names
a function's *neighbourhood* and not its *role*. Three further rows disagree with
their naming and are flagged for the same treatment in
[`engine-map.md`](engine-map.md).

---

## 3. What they have that we do not

Recorded honestly, as gaps rather than as a to-do list:

- **The `.SPR` sprite format.** Our notes list `.SPR` as needing a spec. They have
  a working decoder and a shape/RLE description recovered from
  `VFX_shape_blit_unclipped` inside `WINVFX8.DLL` — a WinVFX middleware format
  the game itself never parses.
- **The `.FNT` bitmap-font layout** and a `LANGUAGE.DLL` / `ITACLANG.DLL` string
  extractor for the localised UI text behind the game's string IDs.
- **Breadth.** A DirectPlay message catalogue (~80 message types), an AI
  finite-state-machine catalogue read out of the binary's own tables, the
  difficulty-scaling curve, the shield/component/hull damage tiers, and the
  mission navigation graph.
- **A running front-end.** `neoslancer` already boots the real menu tree, VR
  ship-interior room and intro movies from a retail install.

Where we are ahead: the widescreen Hor+ projection fix (`0x4C3A60`, absent from
their corpus entirely), the static EXE patch pack, the `.DTE` container decode
(27 sections with strides validated across all 44 missions), the `.SHP` model
spec, and the `.HOG` writer.

---

## 4. Rules for using their material

1. **Cite in place.** A fact adopted from their notes names them at the point of
   use, not only here.
2. **Verify before relying.** Their own methodology says the 827-entry legacy
   catalogue is unrated and that entries not in the confidence database should be
   treated as plausible-but-unchecked. Take them at their word: check a claim
   against our decompilation before it becomes load-bearing.
3. **Facts cross over; code does not.** No file from either repository is
   vendored here while they carry no licence.
4. **Record disagreements, don't average them.** Where their identification and
   ours conflict, both readings go in the map with the conflict marked until
   evidence settles it — §2.4 is the worked example.

---

## 5. Earlier work this project already builds on

For completeness, the external efforts credited elsewhere in these docs:

- **Captain Foster / "Starlancer ME"** — black-box RE of the mission `.DTE`
  format, fused with our decompilation in [`dte-format.md`](dte-format.md) and
  `tools/dte_parse.py`. https://starlancerme.blogspot.com/
- **DraconPern & KingLord — SLExtract** — the VC6/MFC extractor whose source
  documents the `.HOG`/`BIGF` container. See [`hog-format.md`](hog-format.md).
- **Mario "HCl" Brito** — SL Tool, LWO2SL and the MilkShape `.SHP` plugins.
- **RibShark — SafeDiscShim**, **Dege — dgVoodoo2**, **narzoul — DDrawCompat**,
  **Teleguy — Starlancer Crash Fix**, **esc0rtd3w — blank intro videos**. See
  [`modding-scene.md`](modding-scene.md).

---

## 6. openreliant — `vdmkenny/openreliant` (2026)

- **Reimplementation and notes:** https://github.com/vdmkenny/openreliant — "an
  open-source, faithful reimplementation of the engine of StarLancer", in Zig on
  SDL3 with Vulkan (Metal on macOS), reading the game's files in place.
- **Created 2026-09-21.** Licence: **MPL-2.0** for the code (stock text, no
  "Incompatible With Secondary Licenses" notice), **CC BY-SA 4.0** for `docs/`.

### What it contains

A flying sandbox (every ship flyable, ported flight model, cockpit view, part of
the HUD; no weapons, missions or sound yet), `sltool` (readers for `.hog`,
RefPack, `.shp`, `.spr`, texture caches, `.fat`, `.fnt`, `.dte` with a script
disassembler, and the stats tables), `tablegen` (derives the VM's opcode,
command and condition tables, the model tables and the control bindings from the
executable), Ghidra scripts with a names/types file, and 25 reference documents
covering the formats, the binary and the engine.

Its distinctive contribution to the record is **source-file reconstruction**
(`docs/binary/sources.md`): 77 `C:\lancer\...` paths recovered from the assert
macro's `__FILE__` strings, then link-order inference — objects are contiguous
and files come in alphabetical runs — that places the payload's functions into
that source tree, so a Ghidra program tree can be organised as the original
`lancer\game`, `surrender\surrenderlib` and so on.

### How they relate to us

They cite this repository in six places — the README's "Related projects",
`docs/formats/shp.md`, `docs/formats/dte.md`, `docs/formats/stats.md` (twice)
and a doc-comment in `src/formats/stats.zig` — and state that no code of ours is
used. That was the only legal option: until 2026-09-22 our documentation was
GPL-3.0, which a CC BY-SA 4.0 document set cannot incorporate. They therefore
**re-derived rather than copied**: "Everything above was re-checked against the
44 shipped missions and the engine's own code" (`dte.md`), "Every structure
offset and count in this document was re-verified against the 440 shipped
models" (`shp.md`). Our docs are now CC BY 4.0 precisely so that this kind of
re-derivation is a choice, not a requirement.

### What we verified

Their `dte.md` names five points where it follows the engine code against our
`dte-format.md`. We re-checked every one against the VM handler table at
`0x4F6350` (read out of the exe as data and disassembled with capstone) and all
44 shipped missions, and **they were right on every point**:

| their claim | what we found |
|---|---|
| `0x02` tests equality, `0x03` inequality | handlers `0x45BAD0` (`sete`) / `0x45BB00` (`setne`); ours was inverted |
| sections 4, 12, 13 hold flight groups, squads, squad members | `push_flight_group` indexes `[0x5267CC]` by `0x14`, `push_squad` `[0x5294FC]` by `0x0C`; section 12 `+8` indexes 13; object-table kind counts match 44/44 |
| the trigger's condition is at `+0x00`, its subject implicit | the matcher compares `[rec+0x00]` with the event's condition and `[rec+0x15]` with its qualifier; `+0x00` ∈ `0x00`–`0x1F` in 2,446/2,446 triggers |
| `0x28` pushes a constant, `0x32` a byte | `0x45C340` reads the block's constant table; `0x45C6B0` pushes its operand byte |
| a ship's `+0x00` is its object ID | unique and kind 0 in section 7 for 8,265/8,265 records |

The same read confirmed the shape of the handler table they describe (86
entries, 71 populated, five shared handlers), their reading of section 24 as
per-command flag words (the `0x21` handler inverts bit 0 into `DAT_00537584`),
their halfword unit for the section-6 count (section 10 holds exactly twice it
in 44/44 missions), and their byte-level disassembly of `mission1`'s first
block. Nothing in their DTE document was found to be wrong.

### What we adopted, and what we did not

**Adopted, with credit in place:** the corrections above plus `push_string`
and `branch_if_zero`, now in [`dte-format.md`](dte-format.md) §9b and the
corrected opcode table in
[`dte-scripting-reference.md`](dte-scripting-reference.md). Their opcode
names are used throughout that table; rows we could not yet re-verify are
marked as theirs.

**Not adopted:** no code (MPL-2.0 could enter a GPL-3.0 work one way under MPL
§3.3, but nothing of theirs was needed), and no prose — CC BY-SA 4.0 text cannot
be pasted into our CC BY 4.0 documents without making the result share-alike.
Facts crossed; wording did not.

### What each side has that the other lacks

They: the source-tree reconstruction, the engine documents (camera, backdrop,
rendering, objects, loop, controls, HUD, orders, maneuvers), `.spr` / `.fnt` /
`.fat` / texture-cache readers, and a running flight model. We: the widescreen
projection writer `0x4C3A60` and the static patch pack (outside their scope),
the `.SHP` tree-node, animation-clip and trigger-polygon decodes and the
attachment-kind table their issue #11 asks for, the `.frc` load path and the
`HatEnable` / `ForceFeedback` consumers their `controls.md` marks unknown, and
the RefPack in-place constraint an encoder must respect. Those are being
offered back; [`modding-scene.md`](modding-scene.md) §4 maps the licence
directions that now let that happen.
