# Starlancer (2000) — Modding & Modern-Windows Fix Scene
*Researched 2026-06-08 (tooling / fix status updated through 2026-06-30). Every claim has a source; items I couldn't confirm are marked UNCONFIRMED.*

> ⚠️ Search note: "Starlancer" is polluted by unrelated projects (a crypto job-marketplace repo, a Lethal Company mod, and the *Freelancer* sequel's tooling). Everything below is the 2000 Digital Anvil space-combat sim only.

## TL;DR — minimum viable modern-Windows boot
Clean/NoCD exe (or test **SafeDiscShim**) + **dgVoodoo2** (DLLs from its `MS\x86`) + our **`sl_patch.py --fix-medal --fix-multicore`** EXE fixes (or the community **Starlancer Crash Fix v1.0.1**) + enable **DirectPlay**. Or just run **[Starlancer Studio](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)**, which applies all of this for you. Documented/tested on Win7 & Win10.
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
**SafeDisc v1** (Macrovision); identifiable by an `.icd` companion to the main exe. Broken by `secdrv.sys` removal. The supported remedy here is **SafeDiscShim**.

**Re-releases:** some copies are **Ubisoft-branded re-releases**, which may differ from the MS 2000 SafeDisc-v1 original in **version and/or DRM** — confirm from your own installed files rather than assuming SafeDisc v1. Inno Setup repacks can be unpacked read-only with **`innoextract`** (no need to run the installer).

## 4. Source / reimplementation
- **No Starlancer source or reimplementation exists.**
- Closest family base: **Librelancer** — MIT-style open reimplementation of the *Freelancer* engine, with **LancerEdit** tooling ( https://librelancer.net/ ). **Starlancer: Reborn** recreates Starlancer *on the Freelancer engine* ( https://www.moddb.com/mods/starlancer-reborn ). Viable base only if the goal shifts from binary-patching to reimplementation.

## 5. Formats & tools
**RESOLVED — the user's own repo provides the tooling** (cloned to `Starlancer\tools\Starlancer-mod-tools`; a mirror of download.wcnews.com/files/starlancer/). Known Starlancer formats and the tools that handle them:

| Format | What it is | Tool(s) in the repo |
|---|---|---|
| **`.HOG`** | game asset archive | **SLExtract** (extractor) — **ships with VC6/MFC source** → effectively a spec for the format; **SLEdit** also has a HOG editor |
| **`.SHP`** | 3D ship / models | **SL Tool 1.4** (viewer + hardpoint/engine-flame editor), **LWO2SL** (LightWave→SHP), **MilkShape SHP import/export** plugins — all by Mario "HCl" Brito |
| **`MYGAME*.IFF`** | save games | **StarLancEdit 1.11** (Raidersoft) |
| save / MP profile | callsign, kills, rank, level… | **StarLancer Saved Game Editor 1.0** (Twister) |
| **`SHIPSTATS.BIN` / `GUNSTATS.BIN` / `MISSILESTATS.BIN`** | stat tables | **SLEdit** (Dustin; stat editing); `hexcheat` (Userunfriendly) = pre-modded drop-ins |

- **SLExtract's source (VC6/MFC) is the key asset** — a working description of the `.HOG` archive format. **Now fully reverse-engineered → see [`hog-format.md`](hog-format.md);** a modern cross-platform extractor lives at `tools\hog_extract.py` (validated by `analysis\hog_selftest.py`).
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
2. **`.SHP` ship-model format** — only partially decoded; a full spec would unlock custom-ship mods.
3. **Native widescreen menus + flight-HUD reposition** — the flight view is already Hor+ (done); the 2D front-end staying 4:3 is the v2 frontier.

*(Already done since this was first written: native Hor+ widescreen, the medal-case + multi-core crash fixes, the `.HOG` packer, the `.DTE` decoder, and a consolidated fix pack — **[Starlancer Studio](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)** — which bundles the EXE fixes, controller shim, boot-skip, and a Ready-to-Play wizard.)*
