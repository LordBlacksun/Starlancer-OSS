# Starlancer (2000) — Modding & Modern-Windows Fix Scene
*Researched 2026-06-08 (tooling / fix status updated through 2026-06-30; the reimplementations and the licence map in §4 through 2026-09-22). Every claim has a source; items that could not be confirmed are marked UNCONFIRMED.*

> ⚠️ Search note: "Starlancer" is polluted by unrelated projects (a crypto job-marketplace repo, a Lethal Company mod, and the *Freelancer* sequel's tooling). Everything below is the 2000 Digital Anvil space-combat sim only.

## TL;DR — minimum viable modern-Windows boot
**SafeDiscShim** (or an already-unprotected exe) + **dgVoodoo2** (DLLs from its `MS\x86`) + our **`sl_patch.py --fix-medal --fix-multicore`** EXE fixes (or the community **Starlancer Crash Fix v1.0.1**) + enable **DirectPlay**. Or just run **[Starlancer Studio](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)**, which applies all of this for you. Documented/tested on Win7 & Win10.
→ **Step-by-step per-fix recipes** (each tagged by layer + backed by our RE where we have it): **[`modern-fixes.md`](modern-fixes.md)**.

## 1. Modern Windows (10/11) — does NOT run out of the box; fixable
- **#1 blocker: SafeDisc v1 DRM** — relies on `secdrv.sys`, which Microsoft disabled (KB3086255) and removed on Win10/11. The protected exe won't launch. → https://www.pcgamingwiki.com/wiki/StarLancer , https://www.pcgamingwiki.com/wiki/SafeDisc
- Graphics: **Direct3D 7 / DirectDraw** → needs a wrapper on modern GPUs.
- Known bugs: medal-case close crash; multi-core CPU affinity bug; EAX/force-feedback mission crashes; high-res crash without a wrapper; 100 FPS cap.
- **DirectPlay** must be enabled (optional Windows feature) for LAN; MSN Gaming Zone matchmaking is permanently dead.
- Installer 16-bit? **UNCONFIRMED** (guides assume an already-installed/copied game dir).

## 2. Existing community fixes
**Graphics wrappers**
- **dgVoodoo2** (primary) — drop DLLs from `MS\x86` (`D3DImm.dll`,`DDraw.dll`) into game root; configure `dgVoodooCpl.exe`. Also removes the high-res crash. https://dege.freeweb.hu/dgVoodoo2/dgVoodoo2/
- **DDrawCompat** (lighter alt) — `ddraw.dll` v4.x in game folder. https://github.com/narzoul/DDrawCompat/releases

**Bug-fix patches (PCGamingWiki community files)**
- **Starlancer Crash Fix v1.0.1** — fixes medal-case crash + forces single-core affinity (orig by Teleguy, hosted by Choum). https://community.pcgamingwiki.com/files/file/1952-starlancer-crash-fix/
- **Starlancer DSound Fix** — DirectSound3D/EAX via Creative ALchemy / DSOAL. https://community.pcgamingwiki.com/files/file/1440-starlancer-dsound-fix/
- **Blank intro videos** (esc0rtd3w) — skip problematic FMV. https://github.com/esc0rtd3w/blank-intro-videos/ — **now RE-backed + tooled:** the three startup logos `warty_.bik` (Warthog) / `new_dalogo_fs_uncmpr.bik` (Digital Anvil) / `new_nms.bik` (Microsoft Game Studios) are **loose `.bik` files in the game folder** (not inside a HOG), and the engine tolerates a zero-frame movie, so `tools/blank_boot_videos.py` (and the Studio **Boot Videos** tab) replace just those three in place with a real black `blank.bik`, keeping `.orig` backups (the `splash to mm.bik` transition + the HOG-resident `new_intro.bik` are opt-in). See **[`modern-fixes.md`](modern-fixes.md) §1**.

**Widescreen** — **native Hor+ is now DONE** via `tools/sl_patch.py --widescreen` (a static EXE code-cave; the in-flight 3D view gets a correct wide FOV at any resolution). Menus stay 4:3-pillarboxed for now (native widescreen menus + HUD-widget reposition are v2). See **[`modern-fixes.md`](modern-fixes.md) §3**. https://www.wsgf.org/dr/starlancer/en

**DRM compatibility** — **SafeDiscShim (RibShark)**, a userland `secdrv` shim that restores the service Windows removed, without altering any game file: https://github.com/RibShark/SafeDiscShim

**Official patch** — no official Microsoft v1.x Starlancer patch confirmed (v1.x hits are for *Freelancer*). **UNCONFIRMED.**

## 3. Copy protection
**SafeDisc v1** (Macrovision); identifiable by an `.icd` companion to the main exe. Broken by `secdrv.sys` removal. The supported remedy here is **SafeDiscShim**, which restores that service in userland and leaves the game's own files exactly as shipped.

**Re-releases:** some copies are **Ubisoft-branded re-releases**, which may differ from the MS 2000 SafeDisc-v1 original in **version and/or DRM** — confirm from your own installed files rather than assuming SafeDisc v1. Inno Setup installers can be unpacked read-only with **`innoextract`** (no need to run the installer).

## 4. Source / reimplementation — and who may use what
- **No Starlancer source has ever been released.** Two independent reimplementations now exist (this section said otherwise until 2026-09-10), plus two tool projects. The scene's projects chose different licences, so the table at the end of this section says in which direction code and prose may legally flow. **Facts** — an address, a struct offset, a format rule — are not copyrightable and cross every boundary with a citation; it is *code* and *wording* that carry a licence.
- **openreliant** (vdmkenny, from 2026-09-21) — "a faithful reimplementation of the engine of StarLancer" in **Zig on SDL3 + Vulkan** (Metal on macOS), reading the game's files in place with nothing extracted or converted first: https://github.com/vdmkenny/openreliant . Status (2026-09-22): a **flying sandbox** — every ship flyable with the ported flight model, throttle, afterburner and the camera views including the cockpit, the backdrop (starfield, nebula, sun) and part of the HUD (targeting cluster, radar, status lights); no other ships, weapons, missions or sound yet. Ships **`sltool`** (readers for `.hog` + RefPack, `.shp` with OBJ export, `.spr`, texture caches, `.fat`, `.fnt`, `.dte` with a script disassembler, and the stats tables) and **`tablegen`**, which derives the VM's opcode, command and condition tables, the model tables and the control bindings from the executable. Its notable contribution to the RE record is **source-file reconstruction** (`docs/binary/sources.md`): 77 `C:\lancer\...` paths recovered from the assert macro's `__FILE__` strings, then link-order inference that places the payload's functions into that source tree. Its `.DTE` document also corrected six claims of ours — see [`dte-format.md`](dte-format.md) §9b. **Licence: MPL-2.0 code, CC BY-SA 4.0 docs.** Details in [`external-re-credits.md`](external-re-credits.md) §6.
- **neoslancer** (DMJC, from 2026-09-08) — a cross-platform reimplementation in C++20 on SDL2 + OpenGL, with Bink playback via FFmpeg: https://github.com/DMJC/neoslancer . Already boots a real retail install's front-end — menu tree, options screens reading and writing `starlancer.ini`, the ship-interior VR room, and the intro movie sequence. No gameplay (flight, combat, mission loading) yet. Ships `hogdump`, `sprviewer` and `tgaviewer` as dev tools. Its RE notes live in the sibling https://github.com/DMJC/StarLanceDecomp . **Neither repo carries a licence as of 2026-09-22** (we asked on 2026-09-10 — [DMJC/StarLanceDecomp#2](https://github.com/DMJC/StarLanceDecomp/issues/2) — no reply yet), so nothing from them is vendored here — see [`external-re-credits.md`](external-re-credits.md) for what we verified, what we adopted, and what we did not.
- Closest family base: **Librelancer** — MIT-style open reimplementation of the *Freelancer* engine, with **LancerEdit** tooling ( https://librelancer.net/ ). **Starlancer: Reborn** recreates Starlancer *on the Freelancer engine* ( https://www.moddb.com/mods/starlancer-reborn ). Viable base only if the goal shifts from binary-patching to reimplementation.
- **StarLancerEditor** (mini, from 2026-05-10) — a .NET library and tools for the archive, mission and save formats: https://src.ug.gg/mini/starlancereditor . **Licence: MIT** (per its repository page; not otherwise examined here).

**Licence direction — where help can flow (as of 2026-09-22).** "Docs" means the prose of a project's documentation or RE notes; facts always cross.

| project | code | docs / notes | may take from us | we may take from them |
|---|---|---|---|---|
| **Starlancer-OSS** (this repo) | GPL-3.0-only | **CC BY 4.0** (`docs/`; `docs/game-reference/` CC BY-SA 3.0) | — | — |
| **openreliant** | MPL-2.0 (stock; no "Incompatible With Secondary Licenses" notice) | CC BY-SA 4.0 | **docs: yes** — CC BY text may be included in a BY-SA work, with attribution. **Code: no** — GPL code cannot enter an MPL project. | **code: yes, one way** — MPL-2.0 files may be combined into a GPL-3.0 work under MPL §3.3, staying MPL-licensed as files. **Docs: facts only** — BY-SA prose cannot be pasted into our CC BY docs without making the result BY-SA. |
| **neoslancer / StarLanceDecomp** | none | none | **docs: yes. Code: only if they adopt a GPL-compatible licence** (a combined work has to be distributable under the GPL). | **nothing** — no licence means all rights reserved. Facts with citation only. |
| **StarLancerEditor** | MIT | (in-repo) | **docs: yes. Code: no** (GPL cannot be relicensed to MIT). | **code: yes** — MIT is GPL-compatible; keep the MIT notice. |

Until 2026-09-22 our documentation was GPL-3.0 too, which turned every "docs: yes" above into a "no". That is why it was relicensed.

## 5. Formats & tools
The historical toolchain is archived at [Starlancer-mod-tools](https://github.com/LordBlacksun/Starlancer-mod-tools), a mirror of `download.wcnews.com/files/starlancer/`. Known Starlancer formats and the tools that handle them:

| Format | What it is | Tool(s) in the repo |
|---|---|---|
| **`.HOG`** | game asset archive | **SLExtract** (extractor) — **ships with VC6/MFC source** → effectively a spec for the format; **SLEdit** also has a HOG editor |
| **`.SHP`** | 3D ship / models | **SL Tool 1.4** (viewer + hardpoint/engine-flame editor), **LWO2SL** (LightWave→SHP), **MilkShape SHP import/export** plugins — all by Mario "HCl" Brito |
| **`MYGAME*.IFF`** | save games | **StarLancEdit 1.11** (Raidersoft) |
| save / MP profile | callsign, kills, rank, level… | **StarLancer Saved Game Editor 1.0** (Twister) |
| **`SHIPSTATS.BIN` / `GUNSTATS.BIN` / `MISSILESTATS.BIN`** | stat tables | **SLEdit** (Dustin; stat editing); `hexcheat` (Userunfriendly) = pre-modded drop-ins |
| **RefPack / "QFS"** | the codec wrapping most `resource.hog` members | ours: `tools/refpack.py`, `tools/hog_extract.py -d` (decode only — no encoder yet). Also DMJC's `refpack_decompress.py` |
| **`.SPR`** | WinVFX sprite/"shape" sheets (UI, HUD, medals) | **still unspecified on our side.** DMJC has a decoder + shape/RLE spec recovered from `VFX_shape_blit_unclipped` in `WINVFX8.DLL`, plus an interactive `sprviewer` |
| **`.FNT` / `.CCB` / palette `.TGA`** | bitmap fonts and the master 256-colour palette | **unspecified on our side.** DMJC documents the font layout and reports the real master palette lives in `palette.tga` / `softpal.tga`, not the `.ccb` files |

- **SLExtract's source (VC6/MFC) is the key asset** — a working description of the `.HOG` archive format. **Now fully reverse-engineered → see [`hog-format.md`](hog-format.md);** a modern cross-platform extractor lives at `tools\hog_extract.py` (validated by `tests/hog_selftest.py`).
- ⚠️ **Extracting a HOG member does not give you a usable file.** The container is uncompressed, but **98% of `resource.hog`'s members are RefPack streams** — every model, mission, font, palette and stats table. Older tools that extract verbatim hand you a compressed blob. Use `hog_extract.py --decompress`. Table and caveats: [`hog-format.md`](hog-format.md).
- **openreliant's `sltool`** (MPL-2.0) reads `.hog` + RefPack, `.shp` (OBJ export), `.spr` (indexed PNG), texture caches, `.fat` (WAV), `.fnt`, `.dte` (with a script disassembler) and the stats tables — the most complete single reader in the scene as of 2026-09-22; its format notes are CC BY-SA 4.0 (§4).
- Tools are 24+ yrs old (Win9x/2000/XP) — may need compatibility mode / a VM / Wine for the InstallShield-packaged ones.
- Starlancer uses **its own** HOG/SHP formats (not Freelancer's UTF), though the Freelancer/Librelancer ecosystem remains a reference for shared lineage.
- FMV/movie container: still **UNCONFIRMED** (none of these tools touch it).
- `starlancer.ini` (plain text) = main user config — `Xres/Yres`, and a `[Device]` section sometimes cleared for wrapper compatibility.
- ⚠️ "**AnvilToolkit**" is **Ubisoft's Anvil / Assassin's Creed** tool, NOT Digital Anvil — does not apply to Starlancer.

## 6. Community hubs
- **PCGamingWiki** (primary): https://www.pcgamingwiki.com/wiki/StarLancer
- **Starlancer ME blog** — active (2024→2026) RE of the mission **`.DTE`** format (triggers, opcodes 27/40/3F, ship placement) + a Python Mission Ship Editor: https://starlancerme.blogspot.com/
- **Wing Commander CIC** (most alive enthusiast hub): https://www.wcnews.com/chatzone/threads/starlancer.23440/
- Fandom install guide: https://starlancer.fandom.com/wiki/How_to_run_Starlancer_on_Windows_7_and_10
- Steam fix guide: https://steamcommunity.com/sharedfiles/filedetails/?id=3308060132
- WSGF (widescreen): https://www.wsgf.org/dr/starlancer/en · VOGONS: https://www.vogons.org/viewtopic.php?t=47609 · SWAT Portal: https://swat-portal.com/forum/thread/76380-about-starlancer/ · Lutris: https://lutris.net/games/starlancer/

## Open opportunities for original patches
1. **100-FPS uncap** — a wrapper-layer fix (the cap is renderer vsync, not an EXE limiter; see [`modern-fixes.md`](modern-fixes.md) §4). The highest-value remaining item.
2. **`.SHP` ship-model format** — now specified in [`shp-format.md`](shp-format.md) (container, chunk stream, every record type, evidence-tagged) with a decoder / OBJ exporter (`tools/shp_parse.py`). What is still open for custom-ship work is listed in its §9 — chiefly the exporter-side fields the engine never reads, five attachment types without a located consumer, and a RefPack *encoder* + `.SPR` texture packs for a write path.
3. **Native widescreen menus + flight-HUD reposition** — the flight view is already Hor+ (done); the 2D front-end staying 4:3 is the v2 frontier.

*(Already done since this was first written: native Hor+ widescreen, the medal-case + multi-core crash fixes, the `.HOG` packer, the `.DTE` decoder, and a consolidated fix pack — **[Starlancer Studio](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)** — which bundles the EXE fixes, controller shim, boot-skip, and a Ready-to-Play wizard.)*
