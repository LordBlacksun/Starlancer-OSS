# Starlancer `.SHP` 3D-model format

*Reverse-engineered 2026-09-09 by static analysis only: the decrypted executable's decompilation
and disassembly (ImageBase `0x400000`; loader `FUN_004A44D0` in the developers' own
`C:\lancer\game\srofiles.cpp`, its chunk reader `FUN_004A2EB0`, the mesh builder `FUN_004A3040`, and
every game-side consumer we could locate) cross-checked against **all 435 `.shp` models in
`resource.hog`** of the owner's install, parsed as data. Nothing was executed. Independently
derived — no third-party decoder, plugin or source was consulted. Tool:
[`tools/shp_parse.py`](../tools/shp_parse.py).*

**Evidence tags.** **[verified]** = read in the decompiled/disassembled code *or* confirmed against
real bytes (usually both). **[inferred]** = consistent with the data and the code's shape, but the
field is not read by any function we located. **[open]** = not determined; listed in §9.

---

## 0. Summary

A `.SHP` is what the engine calls an **`sro_file`** (Surrender object file — Surrender is the
`SR_*` renderer). It is a **RefPack-compressed stream of tagged chunks** holding one *model* =
a header + N *parts*. A part is a rigid sub-object (hull, cockpit, turret base, door, engine …)
with its own **LOD chain** (up to 9 levels, each a vertex list + triangle list + material list),
**attachment points** (gun hardpoints, engine effects, lights, docking points …), **animation
clips** (keyframed rotation/translation, e.g. `fire`, `deploy`, `opendoor`), **face groups** used by
the explosion/effects code, a **binary bounding tree** over the LOD-0 faces, and, rarely, **trigger
polygons** that fire mission triggers when the player crosses them. Parts form a tree through a
parent index; turret barrels hang off their turret base.

---

## 1. Where they live, and who loads them

* `resource.hog` (the install-folder HOG, *not* the CD HOGs) holds **440 `.shp` entries (435
  distinct names**; five names appear twice, e.g. `gren_frm.SHP`) [verified: TOC listing].
  Packed sizes run 727 B (`M_Hrdpnt.SHP`, a hardpoint marker) to 272,725 B (`stalag.SHP`).
* Naming families seen in the binary's ship table (strings `0x4EC082…`, `0x4F6DF0…`,
  `0x4F88F0…`): flyable fighters (`USLF_Prd.SHP`, `JLF_Nagi.SHP`, …), their `t_` Tiger-squadron
  twins, `<ship>_gun.SHP` loadout variants, `<name>_frm.SHP` cockpit frames, weapons
  (`01_Lasr_can.SHP` … `14_al_STUR.SHP`, `Al_Mis_tur.shp`), missiles/pods (`01_screamer.SHP`,
  `02_raptor_POD.SHP` …), capital ships and stations. In the ship table each model string sits next
  to a `<xxxx>scem.spr` sprite pack (`czadscem.spr` / `czar_docked.shp`) [verified adjacency;
  pairing semantics inferred — see §5.6].
* Two loaders call `FUN_004A44D0(name)`: the **loadout preloader** (`FUN_00441AA0`,
  `C:\lancer\interface\loadout\loadout.cpp` — walks the ship table with stride `0x22C`, the missile
  table with `0x110`, the gun table with `0x22C`, wrapping each model in an `OBJECT FILE`
  allocation) and the **game model table** (`FUN_0045DE70`, 39 models into `DAT_00538CA8[]`)
  [verified]. Bytes come through the shared Surrender file layer `FUN_004CB420`
  (`SR_FILE_alloc`, error *"Could not open %s"*) [verified].

---

## 2. Container  [RESOLVED]

The file is an **EA RefPack ("QFS") stream**: bytes `10 FB`, a **3-byte big-endian** uncompressed
size, then the packed data — the same codec as the `.DTE` ([`dte-format.md`](dte-format.md) §2)
[verified: all 435 files begin `10 FB`; the project decoder reproduces the declared length for
every one].

Where the engine decodes it [verified]: `FUN_004C8110` (`C:\lancer\game\bigfile.cpp`) reads the
first two bytes big-endian (`FUN_004C7DF0`); if they equal `0x10FB` it calls `FUN_004C8480`, which
reads the 3-byte size into `DAT_005E8308`, allocates `size + 0x2800`, reads the packed stream to
the end of that buffer and expands it in place with `FUN_004CC350`, then copies the result to an
exact-size buffer. Any other signature is read verbatim. So the transform applies to *any* HOG
member that starts `10 FB`, one layer above the `FUN_004C5BE0` read that `dte-format.md`
describes.

---

## 3. The chunk stream  [RESOLVED]

The decompressed image is a flat sequence of chunks, terminated by tag `0xFFFF`:

```
Off  Size  Field
0    2     tag          (uint16 LE)
2    2     record_size  (uint16 LE)  — bytes per record IN THIS FILE
4    2     count        (uint16 LE)
6    ..    count × record_size bytes of records
…    6     terminator: tag = 0xFFFF, record_size = 0, count = 0   (end of image)
```

**The reader** `FUN_004A2EB0(out /*ecx*/, tag /*edx*/, struct_size /*stack*/)` [verified,
disassembly — the decompiler drops the two register arguments, which is why every call looks like
`FUN_004a2eb0(0x68)` in the C export]:

1. Starting at the cursor `DAT_005959F8`, step from chunk to chunk
   (`next = cur + 6 + record_size × count`) until the tag matches or `0xFFFF` is reached.
2. `0xFFFF` → `*out = NULL`, return 0, **cursor unchanged**.
3. `count == 0` → `*out = NULL`, cursor moves past the 6-byte header, return 0.
4. Otherwise allocate `count × struct_size` (`SR_MEM_allocate`, tag `srofiles.cpp:78`), copy
   **`min(record_size, struct_size)`** bytes per record (source advances by `record_size`,
   destination by `struct_size`), move the cursor to the end of the chunk, return `count`.

Consequences (all [verified] by the code above, and all exercised by shipped files):

* **`record_size` is the format's version mechanism.** Older exporters wrote shorter records;
  the loader copies what is there and the rest of the in-memory struct keeps whatever the
  allocator returned (see §9). Several sizes ship for most tags (table below).
* **A chunk the exporter did not emit is simply skipped** by the search-forward rule, so the
  optional chunks (`0x8`, `0xD`, `0xE`, `0xF`, `0x10`) may be absent.
* **Order matters**: the stream must present chunks in the loader's request order (§4), since a
  miss never rewinds.
* Bytes of a record beyond `struct_size` are ignored.

### Chunk catalogue

| Tag | Record | In-memory struct | File record sizes seen *(chunks)* | Belongs to | Count is stored at |
|---|---|---|---|---|---|
| `0x00` | header | `0x68` | 20 *(28)*, 24 *(24)*, 88 *(383)* | model | — |
| `0x01` | part | `0x258` | 244 *(4)*, 260 *(1)*, 264 *(127)*, 288 *(28)*, 312 *(275)* | model | hdr `+0x58` |
| `0x02` | LOD level | `0x1C` | 4 | part | part `+0x10C` |
| `0x04` | vertex | `0x20` | 28 *(5)*, 32 *(6019)* | LOD | lod `+0x0C` |
| `0x03` | face | `0x50` | 72 *(181)*, 80 *(5843)* | LOD | lod `+0x04` |
| `0x06` | material | `0x48` | 64 | LOD | lod `+0x14` |
| `0x07` | tree node | `0x5C` | 64 *(354)*, 72 *(1406)* | part | part `+0x20C` |
| `0x08` | node face list | `0x04` | 4 | node | node `+0x48` |
| `0x09` | attachment point | `0x7C` | 100 *(4)*, 124 *(330)*, 136 *(5)*, 168 *(1421)* | part | part `+0x214` |
| `0x0A` | animation clip | `0x28` | 8 *(177)*, 24 *(1583)* | part | part `+0x21C` |
| `0x0B` | keyframe | `0x1C` | 28 | clip | clip `+0x18` |
| `0x0C` | clip event | `0x0C` | 12 | clip | clip `+0x20` |
| `0x0D` | face group | `0x0C` | 4 | part | part `+0x224` |
| `0x0E` | group entry | `0x14` | 20 | group | group `+0x04` |
| `0x0F` | trigger polygon | `0x54` | 16 | part | part `+0x250` |
| `0x10` | tail record | `0x4C` | 12 *(7)*, 76 *(258)* | model | hdr `+0x60` |

(The in-memory sizes are the `struct_size` immediates pushed before each `call 0x4a2eb0`; the
"stored at" offsets are where the loader writes the returned count — the record pointer always
lands in the next dword.)

---

## 4. Stream order  [verified]

The loader requests, in this order:

```
0 header
1 parts
for each part:
    2 LOD list · 7 nodes · 9 attachments · A clips · D groups · F trigger polygons
    for each LOD:    4 vertices · 3 faces · 6 materials
    for each node:   8 face list
    for each clip:   B keyframes · C events
    for each group:  E entries
10 tail
```

Every shipped file follows exactly this order with optional chunks omitted. The three most
common shapes (435 files): `0 1 2 7 9 A D F 4 3 6 …` (143), `0 1 2 7 9 A D 4 3 6 …` (90),
`0 1 2 7 9 A D F 4 3 6 8 …` (75).

### Worked example — `M_Hrdpnt.SHP` (727 B packed → 1,656 B image)

```
@000000 tag 0000 size  20 count  1   header (old 20-byte version)
@00001a tag 0001 size 244 count  1   part "Red Box"
@000114 tag 0002 size   4 count  1   1 LOD, distance 0
@00011e tag 0007 size  64 count  0   (no nodes)
@000124 tag 0009 size 100 count  1   1 attachment: type 4 (light), colour red
@00018e tag 000a size   8 count  1   1 unnamed clip, length 100
@00019c tag 0004 size  28 count  8   8 vertices (old 28-byte version)
@000282 tag 0003 size  72 count 12   12 faces (old 72-byte version)
@0005e8 tag 0006 size  64 count  1   material "HRD_PNT"   (HRD_PNT.tga is in resource.hog)
@00062e tag 000b size  28 count  2   2 keyframes (t = 0, 100)
@00066c tag 000c size  12 count  0
@000672 tag FFFF                      terminator — exactly at the end of the image
```

Note the loader's requests for `D`, `F`, `8` and `10` all miss here (they scan to `FFFF` and
leave the cursor alone), and that `4/3/6` are found *after* the miss because the cursor still sits
on the `4` chunk.

---

## 5. Records

All integers little-endian; `f32` = IEEE single; `vec3` = 3 × f32; `mat3` = 9 × f32 (three rows
of a 3×3 matrix — orthonormal in every record inspected). Offsets are into the **file record**;
fields past a short record's end simply do not exist in that version.

### 5.1 Header (tag `0x00`; struct `0x68`; file 20 / 24 / 88)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | u32 | `107` in 432 files, `200` in 3 (`Alsacedest`, `yeranus_hi_1`, `yeranus_lo_1`) — not read by the loader | [open] |
| `0x04` | f32 | small value, `1.3e-6 … 1.1e-4` — not read | [open] |
| `0x08` | vec3 | e.g. `(2.49, −103.1, 291.1)` for the Predator — not read | [open] |
| `0x14` | u32 | **flags**. bit 1 (`0x2`) → the loader builds the second ("cloak") mesh set, §6.5. Values seen: 0 (252 files), 1 (117), 2 (33), 3 (2), 5 (3) | bit 1 [verified]; bits 0, 2 [open] |
| `0x18`–`0x57` | — | zero in every 88-byte header inspected | [open] |

Runtime-only: `+0x58` part count, `+0x5C` parts pointer, `+0x60`/`+0x64` tail count/pointer.

### 5.2 Part (tag `0x01`; struct `0x258`; file 244 … 312)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | char[64] | **name**, NUL-terminated (`"Predator Cockpit"`, `"Rus Big Tur Guns"`, `"Stalag Door 1 DEST"`) | [verified] |
| `0x40` | u32 | **part type** (subsystem class). The engine tests `== 1` (`FUN_0040D210`, `FUN_0049A8C0`, `FUN_00465380`), `== 6` (`FUN_0049A8C0`), and "is a turret" = type ∈ {3, 9, 10, 18} (`FUN_00479610`); `FUN_00486830` indexes a table with `type + 6`. Labels from the parts' own names: 0 generic/hull (1446), 1 destructible section (`… DEST`, `Mammoth`, asteroids), 2 cockpit, 3 turret base, 5 engine, 6 shield generator, 7 comms, 8 grav panel, 11 core/module, 12 comm dish, 13 door/panel, 14 exhaust, 15 projector generator, 16 core element, 17 cover/duct entrance, 18 ion cannon, 19 panel, 22 cargo pod | reads [verified]; labels [inferred] |
| `0x44` | vec3 | **position** of the part's origin, relative to its parent. Gun creation copies it into the sub-object's position (`FUN_0045E1A0`); the light bake subtracts it from a light position (`FUN_004A4130`) | [verified] |
| `0x50` | vec3 | **bounding-box min** — equals the LOD-0 vertex minima (`Gun_Base`: `(−2079, −476.1, −1800)`) | [verified] |
| `0x5C` | vec3 | **bounding-box max** | [verified] |
| `0x68` | 6 × f32 | large values that scale like sums of squared coordinates (inertia-tensor-like); not read by the loader, consumer not located | [open] |
| `0x80` | 3 × f32, f32, f32 | `+0x8C`, `+0x90` positive scalars, not size-correlated; not read | [open] |
| `0x94` | i32 | **parent part index**, `−1` = root. `FUN_00476180` links the sub-object to that parent (or to the object itself for `−1`). Data: all 1,760 values valid; turret barrels point at their base (`"Rus Big Tur Guns" → 1`, `"al2 barrel2" → 1`) | [verified] |
| `0x98` | vec3 | a point on the part: a gun's rear end (`01_Lasr_can`: `z = −96.5` = bbox min z), a gun base's bottom (`y = −476.1`) — plausibly the **mount/pivot point**; consumer not located | [inferred] |
| `0xA4` | mat3 | **orientation matrix**; identity or 90°/180° rotations in the samples; consumer not located | [inferred] |
| `0xC8` | vec3 | zero in every sample | [open] |
| `0xD4` | u32 | **link id** — small integers (0–5 dominate; one `stalag` part carries the sentinel `999`). Compared for equality between parts to find a turret's companion parts (`FUN_00479640`, `FUN_0048CA80`, `FUN_004ADE20`); the explosion module sums the damage of all parts sharing the id (`FUN_0046D090`); `FUN_004645C0` treats `≠ 0` specially | reads [verified]; "turret link" [inferred] |
| `0xD8` | f32 | **yaw min** (degrees) — bounds the turret's first aim angle in `FUN_0047CB10` | [verified read; yaw/pitch assignment inferred from which angle it bounds] |
| `0xDC` | f32 | **pitch min** (degrees) — bounds the second aim angle | [verified read] |
| `0xE0` | f32 | 0 in every sample (roll min?) | [open] |
| `0xE4` | f32 | **yaw max** | [verified read] |
| `0xE8` | f32 | **pitch max** (the aim code also snaps to it) | [verified read] |
| `0xEC` | f32 | 0 in every sample (roll max?) | [open] |
| `0xF0` | u32 | **flags** — see table below | [verified reads] |
| `0xF4` | u16 (read as short) | **turret kind** (0–3); stored as the first field of the turret record by `FUN_00479160`/`3A0`/`470`; `FUN_00479640` tests `== 1` | [verified read] |
| `0xF8` | u32 | turret slot index used by `FUN_004793A0`; 0 in the samples | [inferred] |
| `0xFC`–`0x137` | — | zero in every 312-byte record inspected; `+0x10C` is overwritten at load with the LOD count | [verified] |

Predator tail gun: type 3, link 1, turret kind 1, yaw `[−90, 90]`, pitch `[−60, 0]`.

**Part flags (`+0xF0`)** [all reads verified]:

| Bit | Loader / game effect |
|---|---|
| `0x02` | read by `FUN_004645C0`, `FUN_00479160` (turret-related tests) |
| `0x04` | splits parts into two classes for static-light baking (`FUN_004A4070`); `FUN_004645C0` returns early when set |
| `0x10` | **geomorph normals**: the mesh builder also copies each vertex's next-LOD counterpart normal (§6.3) |
| `0x20` | **geomorph positions**: likewise for positions |
| `0x40` | set by the loader when a static light exists in the part's class; read by `FUN_00459090` |
| `0x80` | with hardware multitexture (`DAT_005D5618 == 1`): a second texture `l<material>` is bound per material (§6.4) |
| `0x1000` | `FUN_00468760` propagates it to the sub-object (flag `0x2000`) |

Observed low bytes: `0x30` (316 parts), `0x00` (799), `0x34` (91), `0x32` (79), `0x04` (193), `0x02` (108), `0x80` (34) …

### 5.3 LOD level (tag `0x02`; struct `0x1C`; file 4)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | f32 | **switch distance** — `0` for single-LOD parts; multi-LOD parts carry rising sequences `5000, 10000, 15000 … 500000` (the last level is the far one). The loader stores it per LOD at `part + 0x110 + 4i`; the renderer-side selector was not located | values [verified]; meaning [inferred] |

Runtime: `+0x04` face count / `+0x08` faces, `+0x0C` vertex count / `+0x10` vertices,
`+0x14` material count / `+0x18` materials. Up to **9 LODs** per part (the per-part tables at
`+0x110`, `+0x138`, `+0x164`, `+0x18C`, `+0x1B8`, `+0x1E0` are 10 slots each).

### 5.4 Vertex (tag `0x04`; struct `0x20`; file 28 / 32)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | vec3 | **position** (model units) — copied into the renderer's position stream | [verified] |
| `0x0C` | vec3 | **normal** — copied into the normal stream; unit length in 197,466 of 200,586 records | [verified] |
| `0x18` | u32 | small integer 1–4 (1 in 96 %); not read by the loader | [open] |
| `0x1C` | i32 | **index of this vertex's counterpart in the next (coarser) LOD**, used for geomorphing when part flag `0x10`/`0x20` is set (§6.3). Absent in 28-byte records. Data: in range for 126,241 of 126,326 non-last-LOD vertices; the rest are `−1` ("no counterpart", four models) | [verified] |

### 5.5 Face (tag `0x03`; struct `0x50` = 20 dwords; file 72 / 80)

Every record is **one triangle**; N-gons and strips are encoded as runs of records (below).

| Dword | Type | Field | Status |
|---|---|---|---|
| `[0]` | u32 | **material index** into this LOD's material list | [verified] |
| `[1]` | u32 | low nibble = **shading mode** 0–10 (table below); high nibble = **sub-mode**, forwarded to the renderer for mode 7 | [verified] |
| `[2]` | u32 | bits 0 and 1 are copied verbatim into the renderer's per-face flag byte | [verified copy; meaning open] |
| `[3..5]` | u32 × 3 | **vertex indices** v0, v1, v2 into this LOD's vertex list | [verified] |
| `[6..8]` | f32 × 3 | **u** for corners 0, 1, 2 | [verified — the builder pairs `(6,9)`, `(7,10)`, `(8,11)`] |
| `[9..11]` | f32 × 3 | **v** for corners 0, 1, 2 | [verified] |
| `[12..14]` | vec3 | face normal (unit in 99.8 %); **not read** by the loader | [verified data; not read] |
| `[15]` | u32 | 1 (324k), 2 (8.6k), 4 (136), 0 (18); not read | [open] |
| `[16]` | f32 | multiplied by ⅔ (`DAT_004DC7D4`) into a per-face renderer array; `0.0` in every shipped face | [verified] |
| `[17]` | u32 | **edge mask** for mode 1 (wire): edge *k* is drawn unless bit *k* is set | [verified] |
| `[18]` | u32 | **polygon encoding**: `1` = member of a triangle **fan** (an N-gon), `2`/`3` = member of a triangle **strip** (alternating), `0` = plain triangle | fan [verified]; strip [inferred from data] |
| `[19]` | u32 | **records still to come in the same polygon/strip** (counts down to 0) | [verified for fans] |

72-byte records stop at `[17]` (no fan/strip information).

**Shading modes** (`FUN_004A3040`'s switch, writing three renderer bytes: *textured*, *A*, *B*)
[verified]: `0`,`1` → `(0,1,0)`; `2` → `(0,1,1)`; `3` → `(1,0,0)`; `4` → `(1,0,1)`; `5` → `(1,0,3)`;
`6` → `(1,1,0)` (+ lightmap stage when part flag `0x80` and multitexture); `7` → `(1,1,0)`
(+ multitexture stage fields from the sub-mode); `8`,`10` → `(1,1,1)`. Modes 7 and 8 also set
renderer flag `0x400` on multitexture hardware. Mode **1 = wire**: the builder emits 2-vertex line
primitives for the unmasked edges instead of a triangle. Shipped counts: mode 6: 253,209; 7: 90,051;
1: 6,087; 3: 857; 4: 413; 2: 89; 8: 61; 0: 15. Sub-mode: 1 (306k), 0 (21k), 2 (18k), 4, 3, 5, 7.

**Fans.** A record is a fan *lead* when `[18] == 1`, the previous record's `[19]` is 0 (or it is
the first record), and every continuation passes the coplanarity test in `FUN_004A2FD0`
(`dot ≥ DAT_004DCA04 = 0.99900`, i.e. within ≈2.6°). The builder then emits **one N-gon of
`3 + [19]` vertices**: the lead's v0 v1 v2 followed by each continuation's *third* corner (`[5]`,
with its `[8]`/`[11]` uv), and skips the continuation records [verified]. Otherwise every record
is drawn as its own triangle — which still renders correctly, because each continuation is a
complete triangle of the fan. Example (`Gun_Base`, records 0–1 = quad 7-6-0-1):
`[1,1](7,6,0)  [1,0](7,0,1)`; a hexagon fan: `[1,4](10,2,4) [1,3](10,4,9) [1,2](10,9,5) [1,1](10,5,7)
[1,0](10,7,2)`. **Strips** alternate `[3,n] [2,n−1] [3,n−2] …`, e.g. `[3,3](21,22,20) [2,2](22,20,19)
[3,1](20,19,23) [2,0](19,23,24)`; the loader does not merge them.

Because fanning changes face numbering, the loader **renumbers** every LOD-0 face reference in
the node face lists (§5.8) and group entries (§5.11) [verified].

### 5.6 Material (tag `0x06`; struct `0x48`; file 64)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | char[64] | **texture name** without extension (`"Yank_1"`, `"Missiles"`, `"HRD_PNT"`, `"ANTI_1"`); 249 distinct names across the archive | [verified] |

Runtime `+0x40`/`+0x44` hold the texture handle(s). The builder resolves the name through
`FUN_00494A30` → the image registry `FUN_004C9E20` (fatal *"Could not find image %s"*), with a
**context prefix** [verified]: while the loadout preloader's ship loop runs (`DAT_00524976`) the
name becomes `g<name>`; during its missile and gun loops (`DAT_00524977`) `r<name>`; in the game
proper the bare name; and with part flag `0x80` on multitexture hardware a second texture
`l<name>` (format string `"l%s"`, `0x508F7C`). `resource.hog` indeed carries `gMissiles.tga`,
`rMissiles.tga` and `g`/`r` twins of the twelve fighter skins (`gYank_1.TGA` / `rYank_1.tga` …)
[verified]; only 19 of the 249 material names match a `.tga` in `resource.hog` under any prefix,
so in-game textures must be registered from elsewhere — most plausibly the `<xxxx>scem.spr`
sprite packs the ship table pairs with each model [inferred; `.SPR` is undocumented].

### 5.7 Tree node (tag `0x07`; struct `0x5C`; file 64 / 72)

| Off | Type | Field | Status |
|---|---|---|---|
| `0x00` | u32 | 0 in every record | [open] |
| `0x04` | mat3 | rotation (orthonormal; e.g. 10.2° about Y for `Gun_Base`) | [inferred: values] |
| `0x28` | vec3 | extent-like vector (`Gun_Base`: `(2046, 559.6, 1956)` ≈ the box half-extents `(2079, 559.6, 1800)`) | [inferred] |
| `0x34` | vec3 | a point (`(−149, −121, 9)` for `Gun_Base`) — perhaps an area-weighted centroid | [open] |
| `0x40` | i32 | **child A index** (`−1` = none) | [verified: loader resolves to a pointer] |
| `0x44` | i32 | **child B index** (`−1` = none); absent in 64-byte records | [verified] |

The loader converts the two indices to pointers (`node + 0x50/0x54`) **only for nodes whose face
list is empty**, and stores the LOD-0 mesh handle at `node + 0x58` [verified]. Data (6,622 nodes):
every node has either both children or a face list — 3,835 leaves `(−1, −1)` with faces, 2,785
interior nodes with two children and no faces, one exception — i.e. a **binary bounding tree over
the LOD-0 faces** (a BVH; `Bremen` part 2 has 63 nodes) [verified structure; "bounding" inferred
from the matrix/extent fields]. **No runtime consumer walks the tree** — beyond the loader, the
mesh builder (renumbering) and the model destructor `FUN_004A4BF0`, no function touches
`part + 0x210` [verified by search over the decompiled set; a consumer using only the resolved
pointers could still have been missed].

### 5.8 Node face list (tag `0x08`; 4 bytes)

`u32` **face index into LOD 0** [verified: renumbered by the builder alongside group entries].
96,916 references across 150 files; a leaf holds 1–39 faces.

### 5.9 Attachment point (tag `0x09`; struct `0x7C` = 31 dwords; file 100 / 124 / 136 / 168)

| Dword | Type | Field | Status |
|---|---|---|---|
| `[0]` | u32 | **type** (0–9), table below | [verified per type as marked] |
| `[1..3]` | vec3 | **position** (`+0x04`) — gun creation adds it to the sub-object position | [verified] |
| `[4..12]` | mat3 | **orientation** (`+0x10`) — gun creation transforms by it (`FUN_004C22B0`/`FUN_004C1B50`); wing guns carry a roll about +Z | [verified] |
| `[13..16]` | u16 in u32 × 4 | type 0: **default gun-type id for loadout presets 0–3** (`FUN_0045E500` reads `*(short*)(rec + 0x34 + 4·preset)`); type 4: `[13]` = **colour code** 0 blue `(0,0,1)`, 1 green, 2 yellow, 3 red (`FUN_004A4310`); type 1: `[13]` mostly 8–19 | type 0/4 [verified]; type 1 [open] |
| `[17]` | u32 | 0 in the samples | [open] |
| `[18..19]` | f32 × 2 | type 4: **sprite size** (30×30, 48×48); other types 100/50, 120/60 | [inferred] |
| `[20]` | f32 | type 2: **negative selects the alternate engine-effect scale** (`FUN_00494400` tests `< 0`); values 0, −400, −440 | [verified read] |
| `[21..22]` | u32 × 2 | type 4: **blink on / off** — the loader bakes the light only when their sum is 0 (static); pairs 100/1500, 200/1000 | [verified condition; "blink" inferred] |
| `[23]` | u32 | 600 in the 100-byte version (`M_Hrdpnt`) | [open] |
| `[25]` | u32 | type 0: bitmask-like (`0x1FF`, `0x3BF`, `0x1DF`, `0x1B4` …) — plausibly the **allowed-gun mask**; type 3: 2 (gun barrel) / 4 (fighter) | [inferred] |
| `[29]` | f32 | type 4: **range factor** (600, 1000) — the bake radius is `intensity × range` | [verified: `fld [+0x74]`] |
| `[30]` | f32 | type 4: **intensity** (1.0); must be `> 0` to bake | [verified: `fld [+0x78]` in `FUN_004A4070`/`FUN_004A4310`] |

100-byte records stop at `[24]`, 124-byte at `[30]`.

| Type | Meaning | Evidence | Count |
|---|---|---|---|
| 0 | **gun hardpoint** — `FUN_0045E1A0` creates one gun object per type-0 record (max 20, error `0xBD`), keeps a pointer to the record, positions/orients the gun by it; `FUN_0045E500` picks the default gun per preset | [verified] | 191 |
| 1 | turret mount? — capital ships only (`A_mammoth`, `Antanov`, `Berijev` …); `[13]` 8–19 | [inferred] | 460 |
| 2 | **engine effect** — `FUN_004924B0` finds the first type-2 record and `FUN_00494400` builds the effect at it; symmetric pairs at a fighter's tail (`z = −325`) | [verified] | 319 |
| 3 | muzzle / launch point? — gun models: one at the barrel tip (`z = bbox max`); fighters: two forward wing points (`z = +633`) | [inferred] | 152 |
| 4 | **light** — static lights are baked into vertex colours (§6.6); blinking ones are left to the runtime | [verified] | 1069 |
| 5 | unknown — capital ships (`A_mammoth`, `Berijev`, `Boridin` …) | [open] | 174 |
| 6 | cockpit view point? — exactly one per flyable fighter, on the cockpit part (`(−0.7, 43.5, 13.4)` for the Predator) | [inferred] | 26 |
| 7 | **effect emitter** — `FUN_0047C800` spawns a randomised effect at every type-7 point, triggered by clip event kind 2 (§5.10); only `German_Wolverine` / `German_grendal` and their `t_` twins | [verified] | 8 |
| 8 | unknown — carriers (`BTB_Glhd`, `Bremen`, `Endeavour`, `Kiev`) | [open] | 121 |
| 9 | **docking point** — `FUN_00406C80` (`aidock.cpp`, *"Docking information not defined on %s"*) searches for type 9 | [verified] | 34 |

Predator (`USLF_Prd.SHP`) body: 2 × engine (2), 2 × light (4, red, blinking 100/1500, wing tips),
5 × gun hardpoint (0) with presets `(0,5,8,6)`, `(4,4,7,2)`, `(3,0,1,1)`, 2 × type 3 forward;
cockpit part: 1 × type 6; tail-gun part: 1 × type 3.

### 5.10 Animation clip (tag `0x0A`; struct `0x28`; file 8 / 24), keyframe (`0x0B`, 28), event (`0x0C`, 12)

| Off | Type | Clip field | Status |
|---|---|---|---|
| `0x00` | u16 | **length** in keyframe time units — the player clamps/wraps its clock at this value (`FUN_00476C90`); values 100, 20, 200, 400, 1000, 16000 (unnamed default) … | [verified] |
| `0x02` | u16 | 0 in every record | [open] |
| `0x04` | u16 | **default play mode**: 0 none, 1 once, 2 loop; the player also implements 3 = ping-pong. Used when the caller passes `−1` (`FUN_0049A2D0`) | [verified] |
| `0x06` | char[18] | **name**, NUL-terminated; 8-byte records have none. The loader records the indices of clips named `startup`, `fire`, `deploy` (case-insensitive `FUN_004DAE20`) at `part + 0x234/0x238/0x23C`, which `FUN_0049A2D0(part, which, speed, mode, …)` starts by slot | [verified] |

Names shipped: `opendoor` (89), `fire` (58), `deploy` (56), `Rotate Inner` (20), `startup` (13),
`doors open` (13), `ripper` (12), `ready to grab`, `grab pod`, `fighting position`, `floor`,
`cabin turn`, `reload`, `doors close`, `rotate`, `fin down` … (1,297 unnamed).

| Off | Type | Keyframe field | Status |
|---|---|---|---|
| `0x00` | i32 | **time** (0 … clip length) | [verified: `FUN_00499F40` brackets the clock between neighbouring times] |
| `0x04` | vec3 | **rotation**, radians (Euler) — a door key reads `(0, 1.571, 0)` = 90° about Y | [verified interpolation; axis convention inferred] |
| `0x10` | vec3 | **translation** — the second vector the evaluator lerps and applies (`FUN_0049A140`) | [verified interpolation; "translation" inferred] |

| Off | Type | Event field | Status |
|---|---|---|---|
| `0x00` | i32 | **time** at which the event fires (when the clock passes it) | [verified] |
| `0x04` | u32 | **kind**: 0 → `FUN_0047C7B0` (acts on attached kind-4 objects), 2 → `FUN_0047C800` (spawn the type-7 effects) | [verified dispatch] |
| `0x08` | u32 | 0 in every record | [open] |

Only 44 events ship (e.g. the tail-gun `fire` clip has one).

### 5.11 Face group (tag `0x0D`; struct `0x0C`; file 4) and entries (`0x0E`, 20)

Group record: `u32` **class id** (1–8 observed). Runtime `+0x04`/`+0x08` = entry count/pointer.
Entry: `+0x00` u32 (always 0, [open]); `+0x04` u32 **face index into LOD 0** (renumbered after
fanning, [verified]); `+0x08` vec3 **position** ([inferred]: the Predator's class-7 entries sit at
its engine exhausts). Consumers [verified]: class 1 (`FUN_00471290`), class 3 (`FUN_004715D0`),
class 4 (`FUN_00471470`, `explode.cpp` — spawns an effect per entry, `FUN_004C4F30`); classes 2, 5,
7, 8 ship but their reader was not located [open].

### 5.12 Trigger polygon (tag `0x0F`; struct `0x54`; file 16)

`4 × i32` **vertex indices into LOD 0** (`[3] = −1` for a triangle) [verified: the loader copies
`mesh0.vertices[idx]` into `+0x14…+0x40`, sets `+0x10` = 3 or 4, computes the normal at `+0x44`
and the plane constant at `+0x50`]. Consumer `FUN_00465380` [verified]: for the player's object,
when the signed distance to the plane changes sign and the point lies inside the polygon
(`FUN_004AD700`), it fires mission trigger `0x1C` **TT_INSIDE_OBJECT** or `0x1D`
**TT_OUTSIDE_OBJECT** (`FUN_0045B7C0`; enum per [`dte-format.md`](dte-format.md)). Only
`stalag.SHP` ships any: one quad on part 6 `"Stalag Duct"` (vertices 13, 12, 15, 14) and one on
part 10 `"Stalag Outer"` (215, 216, 217, 218).

### 5.13 Tail record (tag `0x10`; struct `0x4C`; file 12 / 76)

`+0x00` vec3 — a unit vector (714 records) or zero (115); `+0x0C` 32 × i16 in 76-byte records
(values −1, 0, −2, −4, −8, −16). 829 records in 265 files (asteroids, `A_mammoth`, `Antanov` …).
The loader stores count/pointer at `hdr + 0x60/0x64`; **no reader located** [open].

---

## 6. What the loader does after reading  [verified unless marked]

1. **Cloak/special flag.** The requested name is compared (case-sensitively) against a 12-entry
   table at `PTR_DAT_004F7490` — `uslf_prd.shp`, `jlf_nagi.shp`, `german_grendal.shp`,
   `british_crusader.shp`, `usa_coyote.shp`, `french_mirage.shp`, `british_tempest.shp`,
   `usmf_pat.shp`, `german_wolverine.shp`, `ushf_reaper.shp`, `jap_shroud.shp`, `uspf_phx.shp`
   (the twelve flyable Alliance fighters); a hit sets `DAT_005959F4`, which has the same effect as
   header flag `0x2`. (The compare is exact-case, so it hits only when the caller passes the
   lower-case name.)
2. **Read** in the order of §4. Trigger polygons are resolved against LOD-0 vertices immediately.
3. **Lights** (`FUN_004A4070`): a type-4 attachment with intensity > 0 and blink sum 0 marks every
   part of the same class (flag `0x4`) with flag `0x40`.
4. **Meshes** (`FUN_004A3040`, once per LOD): allocate a Surrender mesh (`FUN_004C4440`) sized for
   the triangles/fans/lines; copy positions and normals; for non-last LODs with part flag
   `0x10`/`0x20` also copy the *next* LOD's normal/position for the counterpart index (vertex
   `+0x1C`) — geomorph data; build primitives per shading mode; resolve textures (§5.6); finalize
   (`FUN_004C3CA0`, `FUN_004C3F10`, `FUN_004C4090`). The handle goes to `part + 0x138 + 4i`.
5. **Second mesh set** when header flag `0x2` or `DAT_005959F4`: a 500-byte copy of each mesh with
   all primitives forced to mode 3, plus a mesh built by `FUN_004A3CB0` textured with
   `<DAT_005D62D4>cloak64` — the cloaking-effect geometry [build verified; purpose inferred from
   the texture name `cloak64` and `cloak.cpp`].
6. **Bake static lights** (`FUN_004A4310` → `FUN_004A4130`): for each static type-4 light, for every
   LOD mesh of every part in the same class, vertices within `intensity × range` whose normal faces
   the light get `colour × intensity × falloff` added to their RGB, clamped to 1.0.
7. Free the file buffer; return the header pointer.

---

## 7. Coordinate frame and units  [inferred]

From placements across the fighters: cockpit view points sit above the origin (`y ≈ +43`), engine
effects at the rear (`z ≈ −325`), gun barrels and the forward points at `z > 0`, wing-tip lights at
`x ≈ ±350` — so **+Z is forward and +Y is up**; handedness of X is not established. Units are the
same as the bounding boxes (a Predator body spans `−440 … +639` in Z, i.e. ~1,080 units long), and
LOD distances (`5000 … 500000`) and light ranges (`600`, `1000`) are in those units.

---

## 8. Validation

`shp_parse.py sweep` over the 435 models: **435/435 decode and validate** — RefPack length matches
the header, every chunk lies inside the image, the terminator is the last 6 bytes, and all
structural invariants hold (face vertex/material indices, node children and face lists, group face
indices, parent indices, attachment types 0–9, geomorph indices except the documented `−1`).
Record totals: 1,760 parts · 6,024 LODs · 201,556 vertices · 350,782 faces · 15,459 materials ·
6,622 nodes · 96,916 node-face refs · 2,554 attachments · 1,797 clips · 3,705 keyframes ·
44 events · 538 groups · 10,410 entries · 2 trigger polygons · 829 tail records. Parts per model:
1 (240 files) … 72 (`stalag`).

---

## 9. Open questions

* Header `+0x00` (107 vs 200), `+0x04`, `+0x08`; header flag bits 0 and 2.
* Part `+0x68…+0x93` statistics, `+0x98` (mount point?), `+0xA4` matrix consumer, `+0xC8`,
  `+0xE0`/`+0xEC`.
* Vertex `+0x18`; face `[15]`, the meaning of flag bits `[2]`, and the strip encoding `[18] = 2/3`
  (never merged by the loader, so only an exporter-side convention).
* Attachment types 1, 3, 5, 6, 8 (no comparing function located), fields `[17]`, `[23]`, `[25]`,
  and the type-1 `[13]` values 8–19.
* Tree-node `+0x28`/`+0x34` and whether anything walks the tree at runtime.
* Face-group classes 2, 5, 7, 8; group-entry `+0x00`.
* Tag `0x10` tail records: no reader found.
* **Short-record hazard.** `SR_MEM_allocate` shows no zero-fill, so for old records (72-byte faces
  without `[18]/[19]`, 100-byte attachments without range/intensity, 64-byte nodes without child
  indices) the loader reads uninitialised memory. Shipped old files evidently work; a new exporter
  should write full-size records.
* Handedness of the coordinate frame; texture orientation of the `(u, v)` pairs; where in-game
  textures are registered (`.SPR` packs are undocumented).

---

## 10. Tool

```sh
python tools/shp_parse.py info  USLF_Prd.SHP              # chunk walk
python tools/shp_parse.py tree  USLF_Prd.SHP              # parts, LODs, attachments, clips, groups
python tools/shp_parse.py dump  USLF_Prd.SHP --tag 9 --decode
python tools/shp_parse.py obj   USLF_Prd.SHP -o predator.obj --assemble   # LOD 0 as Wavefront OBJ
python tools/shp_parse.py sweep <folder-of-shp>            # decode + validate everything
python tools/shp_parse.py --selftest                      # no game data needed (part of tests/run_all.py)
```

Extract the models first with `python tools/hog_extract.py resource.hog -o <folder>`. The tool is
read-only and standard-library; it reuses the RefPack decoder from `dte_parse.py`.

## Related
[`hog-format.md`](hog-format.md) · [`dte-format.md`](dte-format.md) §2 (RefPack) ·
[`stats-format.md`](stats-format.md) (the stat tables the gun presets index) ·
[`engine-map.md`](engine-map.md) · `tools/shp_parse.py`
