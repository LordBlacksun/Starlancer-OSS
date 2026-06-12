# Starlancer (2000) — Engine Map

A public reference to the architecture of **Starlancer** (Digital Anvil / Microsoft, 2000;
developed by **Warthog**). This is original reverse-engineering documentation produced by static
analysis of the game executable: it lists addresses, identifies middleware, and describes inferred
purpose plus the debug-string evidence behind each claim. **It contains no game source code or
assets** — only analysis.

> Scope & build: addresses are RVAs/VAs for ImageBase `0x400000` in the analyzed build (the
> decrypted `LANCER.ICD`, 1,151,021 bytes, OEP `0x004D1210`, 2,200 functions). All function names are
> Ghidra placeholders (`FUN_xxxx`); the original binary is stripped. Purpose is **inferred** from
> referenced debug strings (the game ships with rich `printf`-style diagnostics that name source
> files and subsystems) and imported APIs. Treat specifics as well-evidenced hypotheses, not gospel.

## 1. Architecture at a glance

Starlancer is a 32-bit Win32 space-combat sim. The engine is a thin game layer over several
late-1990s middleware SDKs:

| Layer | Middleware | Evidence | Notes |
|---|---|---|---|
| 3D renderer | **Surrender** (`SR_*`) | `c:\lancer\surrender\surrenderlib`, `SR init`, `SR CCB load/save`, `SR_color_remap`, `srddraw.dll`, `srmemory.dll`, `FATAL: SR Assertion Failed` | In-house/licensed scene renderer; talks to DirectDraw/Direct3D 7 via `srddraw.dll`. `CCB` = colour-cube/texture blocks. |
| 2D / sprites / overlay | **WinVFX** | `winvfx8.dll`, `winvfx16.dll`, `VFX shape draw/translate/transform`, `vfx.dll`, `VFX_shape_resolution`, `VFX_character_width` | John Miles' 2D effects lib. HUD/sprite blitting + transforms. |
| Audio | **Miles Sound System** (`mss32.dll`) | `AIL_*`, `Miles Fast 2D Positional Audio`, `Aureal A3D`, `Creative Labs EAX`, `RAD RSX 3D`, `Dolby Surround` | Providers selectable; EAX/A3D 3D audio. |
| Video | **Bink** (`binkw32.dll`) | hundreds of `*.bik` refs, `play bink movie …` | Briefings, cutscenes, news, medals, landing, intro/outro. |
| Input | **DirectInput** (`DINPUT.dll`) | `DirectInputCreateA`, `KeyConfig`, `ForceFeedback`, `HatEnable`, `TwistEnable`, `*.frc` | Keyboard/mouse/joystick + HOTAS + force-feedback. |
| Multiplayer | **DirectPlay** | `DPInit`, `DPERR_*`, `DPSYS_*`, `TCP/IP Address`, `requires Winsock 2.0`, "started by the zone" | TCP/IP + MSN Gaming Zone lobby. |
| Memory | **`srmemory.dll`** | static import | Surrender's allocator. |
| Backend | DirectDraw + Direct3D 7 | `DirectDrawCreateEx`, `DDERR_*`, `D3DERR_*VIEWPORT*`, `gamma` | Loaded dynamically through `srddraw.dll`. |

**Source tree** (from `__FILE__`-style assert strings): `lancer\game\*.cpp`
(`hud.cpp`, `interface.cpp`, `Create.cpp`, `explode.cpp`, `shield.cpp`, `shieldfx.cpp`, `wgate.cpp`,
`deathmatch.cpp`, `gameflow.cpp`, `DPBits.cpp`, `DPSession.cpp`), `lancer\interface\loadout`,
`lancer\surrender\surrenderlib`.

## 2. Bootstrap & lifecycle

| Addr | Role | Evidence |
|---|---|---|
| `0x004D1210` | OEP / `mainCRTStartup` (MSVC) | standard CRT prologue; calls C init then WinMain |
| `0x004A8B10` | **Main init / WinMain** (largest top-level fn, 7.5 KB) | `StarlancerRunning` (single-instance mutex), `Game already running`, `Could not CoInitialise`, `DirectX Version %03x`, `credits`, `greyscale` |
| `0x004778C0` | Graphics/input bring-up | dynamically `LoadLibrary`s `DINPUT.DLL`+`DDRAW.DLL`, `DirectInputCreateA`, `DirectDrawCreate`, `CoCreateInstance` |
| `0x004ACBE0` | Device init / fatal path | `Fatal error initializing`, `Device`, `Windowed` |
| `0x0045E670` | Generic fatal error box | `Fatal Error` |

### 2a. Timer subsystem / frame pacing (`lancer\game\timer.cpp`)  — *RE'd 2026-06-12*

The whole game runs on a **100 Hz multimedia timer**, and this is the *simulation* timebase — **not**
a render limiter (the ~100 FPS users see is renderer vsync, see §3 / `modern-fixes.md` §4). Timer
records are **8-dword (0x20 B)** nodes in the table `&DAT_00595c08` (≤ 0x14 entries, walked to
`< 0x595c58`):

| Node off | Field |
|---|---|
| `+0x00` | tick counter (callback bumps it) |
| `+0x04` | re-entrancy lock (`InterlockedExchange`) |
| `+0x08` | `timeSetEvent` id (mode-0 only) |
| `+0x0C` | **callback fn ptr** |
| `+0x14` | catch-up accumulator (mode-1) |
| `+0x18` | timer frequency in Hz (mode-1) |
| `+0x1C` | mode: `0` = winmm-thread, `1` = main-thread catch-up |

| Addr | Role | Notes (from disasm) |
|---|---|---|
| `0x004A70F0` | **register mode-0 timer** | true ABI (Ghidra mis-typed it): `ecx`=Hz, `edx`=min resolution, callback pushed on stack → node`+0x0C`; `uDelay = 1000/ecx`; `timeSetEvent(uDelay, res, FUN_004a6f80, node, TIME_PERIODIC)`. Fires on the **winmm timer thread**. |
| `0x004A7060` | register mode-1 timer | no `timeSetEvent`; accumulator `+0x14 = DAT_00565064·Hz·10`, mode `+0x1C=1`. Driven by the executor. |
| `0x004A6F00` | **catch-up executor** | called once per `FUN_004aab20`; for each mode-1 node runs the callback `(Hz·clock·10 − acc)/1000` times, **clamped to `0x32` (50)**. ⇒ logic advances in real time, decoupled from frame rate. |
| `0x004A6F80` | timer dispatch | mode-0 path takes the `InterlockedExchange` lock (guards re-entry of *that* timer only — **not** vs the main thread); mode-1 path runs lockless. |
| `0x004A71F0` | kill timer | spins on the lock (≤ 500 × `Sleep(2)`) then `timeKillEvent`. |
| `0x00481440` | **clock registration** | `mov ecx,0x64` @ **`0x00481689`** (= 100 Hz, period 10 ms) registering callback `LAB_004827C0`. Resets `DAT_00565064=0` first. |
| `0x004827C0` | **master clock callback** | `inc DAT_005db8e8` (raw ticks); `inc DAT_00565064` (master clock, **centiseconds**); maintains BCD sub-fields `DAT_00565070/72/74` (cs→s→min, rollovers at 100/0x3a/0x3a). |

**Globals:** `DAT_00565064` master clock (centiseconds, 100 Hz); `DAT_005db8e8` raw tick counter;
both are timestamps for ~141 gameplay/AI deadlines that use **literal centisecond offsets**
(`+500`=5 s, `+0x19`=0.25 s …) — so the 100 Hz is baked into data semantics and must not be changed.
The mode-0 callback running on the winmm thread, concurrent with the main thread, is also the prime
suspect for the multi-core crash (see §16 / `modern-fixes.md` §5).

## 3. Renderer — Surrender over DirectDraw/Direct3D 7

The render path is **Surrender → `srddraw.dll` → DirectDraw/Direct3D 7**. Display-mode selection and
detail settings live here (the entry points for a widescreen/Hor+ patch).

| Addr | Role | Evidence |
|---|---|---|
| `0x004A8880` | **Display-mode selection** | `dmodes.bin`, `renderdevice%d`, `Device` |
| `0x004A8600` | Graphics detail / gamma config | `Device`, `Tdetail`, `Gdetail`, `Lmaps`, `Transitions`, `gamma` |
| `0x004C3830` | Surrender init | `SR init: Attempting to call SR i…` |
| `0x004C3A60` | **Projection scale/centre writer** (sets `+0x166E`/`+0x1686` scale, `+0x167A`/`+0x1692` centre + 5 clip planes from width/height & the `sX=0.6`,`sY=0.8` 4:3 params) | called directly at the end of device init/reset (`0x004ACBE0`/`0x004AD0A0`/`0x004AD2E0`); **the Hor+ FOV patch point** (see `modern-fixes.md` §3 / `tools/ws_patch.py`) |
| `0x004C9A40` | Texture cache | `Texture Cache already initialise…` |
| `0x004CB9D0` / `0x004CBBD0` | Colour-cube (CCB) load / save | `SR CCB load/save …` |
| `0x004C98C0` | Texture attributes | `TEXTURE`, `USEPALETTE`, `ALPHACHANNEL`, `ERRDIFF` |
| `0x004BFF40` | DirectDraw error decoder | full `DDERR_*` table |
| `0x0042E9B0` | Device/gamma/transitions | `Device`, `gamma`, `Transitions` |

Config artifact: **`dmodes.bin`** enumerates render devices/resolutions. The display size lives in the
device struct `DAT_00588730` (`+0x1666` width / `+0x166A` height); the **projection** scale/centre is
written by **`FUN_004c3a60`** (`0x004C3A60`) from those dims and the baked `sX=0.6`/`sY=0.8` (= 4:3)
params — *not* by the `DAT_00588730+0x40` callback, which is `SR_driver_init` inside the external
`srddraw.dll` and only consumes the projection. **Native Hor+ widescreen is implemented** by a static
code-cave at `FUN_004c3a60` (`sX := sY·h/w` ⇒ square pixels) plus a resolution-force cave at
`0x004ACBE0` — see `modern-fixes.md` §3 and `tools/ws_patch.py`.

## 4. WinVFX — 2D shapes / overlay

| Addr | Role | Evidence |
|---|---|---|
| `0x004A26D0` | WinVFX init + shape ops | `winvfx8.dll`, `winvfx16.dll`, `init vfx: Can't find WINVFXxx DL…`, `VFX shape draw/translate/transform`, `VFX buffer transform` |
| `0x004BCD90` | VFX dll glue | `vfx dll` |

## 5. Audio — Miles Sound System

| Addr | Role | Evidence |
|---|---|---|
| `0x0042DAB0` | Audio config | `Sound`, `3DProvider`, `Fxvolume`, `Musicvolume`, `Speechvolume`, `Mastervolume` |
| `0x00481900` | 3D provider enumeration | `Miles Fast 2D Positional Audio`, `Aureal A3D`, `Creative Labs EAX`, `RAD RSX 3D`, `Dolby Surround` |
| `0x0049D160` | EAX environment | `EAX damping/effect volume/decay time` |
| `0x00482160` / `0x00481F80` | HOG-streamed sample playback | `HOGSND attempting to play sample`, `buffer sample overrun`, `HOGSND finished` |

## 6. Video — Bink

Imports 11 `binkw32` entries (`BinkOpen`, `BinkDoFrame`, `BinkWait`, `BinkNextFrame`,
`BinkCopyToBuffer`, `BinkClose`, `BinkSetSoundSystem`, `BinkOpenMiles`, `BinkSetFrameRate`,
`BinkSetVolume`, `BinkGoto`, `BinkPause`). The four player wrappers share one play loop
(`0x004AC510`: `BinkWait==0` → `BinkDoFrame`+`BinkCopyToBuffer`); each frame also polls input
(`FUN_004BD570`) so **any keypress aborts** the movie.

| Addr | Role | Evidence |
|---|---|---|
| `0x004ABDE0` | **Per-chapter intro/landing sequencer** | branches on chapter `DAT_00562DC8`; plays `new_chapter*` / landing clips (*not* the startup logos) |
| `0x004ABD40` | Habitat-selector / intro transition | calls `FUN_0042FE00` with 6 habitat clips → `FUN_004ABB80` |
| `0x004ABB80`, `0x004AB9D0` | Player, **from HOG** (clear / no-clear) | `_BinkOpen(*(DAT_005202D4+4), 0x800000)` — resource flag |
| `0x004AB850`, `0x004AB6E0` | Player, **loose file** (clear / no-clear) | `_BinkOpen(name, 0x1000/0)` |
| `0x004AC510` | Frame decode/render loop | `BinkDoFrame` → `BinkCopyToBuffer` |
| `0x00439FB0` | Interface movie/VR host (`interface.cpp`) | `VR movie resource: error …`, many `*.bik` |
| `0x004362F0` | Medal display | `MedalDisplay resource …`, `medal_d.spr` |
| `0x0043BA40` | In-world TV / news screens | `news report resource …`, `b_tv_news.bik` |
| `0x0048D030` | HUD movie (cockpit video) | `hudmovie init: load failed …` |

**Startup branding logos** — a consecutive string-table group at `0x50A2E8`, opened from the CD
HOG (flag `0x800000`, *not* loose files) at process start: `warty_.bik` (**Warthog**),
`new_dalogo_fs_uncmpr.bik` (**Digital Anvil**), `new_nms.bik` (**Microsoft Game Studios**), then the
`splash to mm.bik` transition; the campaign intro is `new_intro.bik`. **A missing or zero-frame
movie is tolerated** — `BinkOpen` returns NULL (logged, *not* fatal) or the end-of-video flag is set
on frame 0, so the play loop exits immediately; any keypress aborts too. This is why the "blank.bik"
skip works; `tools/blank_boot_videos.py` blanks the **three logos by default** (splash + intro
opt-in) via extract → version-matched blank → repack. See [`modern-fixes.md`](modern-fixes.md).

## 7. Input — DirectInput + force feedback

| Addr | Role | Evidence |
|---|---|---|
| `0x0042B690` | Key/joystick config | `KeyConfig`, `ForceFeedback`, `JoystickInvert`, `HatEnable`, `TwistEnable`, `controller` |
| `0x0042C800` / `0x0042CAA0` / `0x0042C630` | Bind serialization | `JoyConfig`, `SHIFT/CONTROL/ALT %d`, `JOY BUTTON %d`, `sdefault.txt` |
| `0x004BD800` | Force-feedback effect table | per-weapon `*.frc`: `pc/mb/prc/gl/tc/np/cg/gp/vb/nc frc`, `Missile frc`, `Shake frc`, `The FF effects file error` |
| `0x0047BDB0` / `0x00496290` | FF effect playback | `Joystick effect failed to start` |

## 8. Assets, game objects & combat

**Asset loading.** The `.HOG` (EA BIGF) archives back everything; ships are `.SHP`, sprites `.SPR`,
images non-standard `.TGA`, fonts `.FNT`, streamed audio `.FAT` (see `docs/hog-format.md`).

| Addr | Role | Evidence |
|---|---|---|
| `0x00466C10` | **Game-object factory** (`Create.cpp`) | `create object: Overrun in GO arr…`, `Trying to create object %s twice`, many `* mesh` |
| `0x00441AA0` | Mission/loadout preloader | `Preload starts %d`, `pre/post ship load %d`, `USLF.prd.SHP`, `OBJECT FILE` |
| `0x0047D9A0` | Weapon mesh registry | `LaserCannon Mesh`, `ProtonCannon Mesh`, `TachyonCannon mesh`, … |
| `0x0046D090` / `0x0046BF20` | Explosions (`explode.cpp`) | `Explode Powercore BMO`, `Explode Mesh` |
| `0x0049F790` / `0x004A0310` | Shields (`shield.cpp` / `shieldfx.cpp`) | `Capshield mesh`, shield FX |
| `0x0041FE60` / `0x0041DD70` | Jump/warp gates (`wgate.cpp`) | `WgateBeam Mesh`, `Wadvgate`, `Wboridin Mesh` |
| `0x00468FA0` | Collision | `collision %s %s` |
| `0x0040CA50` | Per-ship AI attach/detach | `Cannot set/clear ai on ship %s …` |

Stat tables (`SHIPSTATS/GUNSTATS/MISSILESTATS.BIN`, 352-byte records) are documented in
`docs/stats-format.md`; `pilotstats.bin` is loaded at `0x0049CAE0`.

## 9. Mission / AI / scripting (`.DTE`)

| Addr | Role | Evidence |
|---|---|---|
| `0x0045A4E0` / `0x0045A530` / `0x0045A570` | mission init / destroy / process | `init/destroy/process mission …` |
| `0x00486830` | Objectives | `ERROR: No mission Objectives def…` |
| `0x0044F3D0` | Mission file loader | `missions\%s.dte`, `mission29…32` |
| `0x0048E140` | Mission runtime state | `c:\mission.txt`, `syncs`, `waitingforsync %d`, `waitingforrestart %d`, `globals`, `ships %d` |
| `0x0045B330` | **Trigger-condition table** | `TT_SHOTAT`, `TT_DESTROYED`, `TT_LAUNCHED`, `TT_CAMERAREACHED`, `TT_SHIPREACHED`, `TT_PROXIMITY_CLOSE/GENERAL`, `TT_OBJECT_SCOOPED`, `TT_PLAYER_READY_TO_JUMP` |
| `0x0040D210` | Capital-ship/turret AI | `…IONCANNONAI…`, `target destroyed: quitting` |
| `0x00401000` | Multiplayer AI sync gate | `Player reached sync point: G…` |
| `0x004924B0` | Mission exit bookkeeping | `exiting mission: player strategy/status/flags %d` |

The `TT_*` set corroborates the third-party `.DTE` trigger documentation and is the key to a mission
editor (cross-ref `docs/dte-format.md`).

## 10. HUD / UI / menus / loadout

| Addr | Role | Evidence |
|---|---|---|
| `0x00483150` | **HUD render** (`hud.cpp`) | `flip buffer`, `work buffer/2`, `target mesh1/2` |
| `0x004934F0` | Cockpit / radar overlay | `scockpit frames`, `radaralpha`, `whiteout mesh` |
| `0x00494040` | HUD target/lock widgets | `uncolour hud target`, `destroy lockring`, `dockring exit`, `chaff exit` |
| `0x00439FB0` | Interface/menu host (`interface.cpp`) | menu + VR-room movies |
| `0x00437010` / `0x00437FC0` | Campaign/mission select | `new mission01…28`, `New Searching Mission …` |
| `0x00443C20` | Loadout screen (`interface\loadout`) | `PnlShipInfo`, `BtnMissiles`, `BtnShips`, `BtnDefault`, `BtnRemoveAll` |
| `0x004ADC20` | Screenshot | `screenshot%04d.tga` |

HUD geometry (`hud.cpp` + `scockpit`) is where a **Hor+ widescreen HUD** would be repositioned.

## 11. Networking / multiplayer (DirectPlay)

| Addr | Role | Evidence |
|---|---|---|
| `0x004B5C50` | DirectPlay init | `DPInit: CoCreateInstance DirectP…`, `CreateCompoundAddress`, `TCP/IP Address` |
| `0x004B62D0` | Lobby/zone glue (`DPBits.cpp`) | `DP: Not started by the zone`, `DP: Can't get settings` |
| `0x004B6A80` | DirectPlay system messages | `DPSYS_SESSIONLOST/HOST/CHAT/…` |
| `0x004B51D0` | DirectPlay error decoder | full `DPERR_*` table |
| `0x004BC390` | Winsock capability check | `The game requires Winsock 2.0`, `Thank you from Warthog` |
| `0x004AF1D0` | Deathmatch (`deathmatch.cpp`) | `pushing multiplayer control AI…` |

## 12. Save / config / profile

| Artifact | Addr | Evidence |
|---|---|---|
| Saved games `saves\GAME%02d.IFF` | `0x00431730`, `0x004315C0`, `0x00475650` (`gameflow.cpp`) | `saves\%sGAME%02d.IFF`, `saves\test.bin` |
| Pilot files `pilots\%s.fm8` | `0x00453DE0`, `0x004548…`–`0x004561C0` | `pilots\%s.fm8`, `pilots\45tigers\…` |
| `profile.bin` | `0x004751B0` | `profile bin` |
| `pilotstats.bin` | `0x0049CAE0` | `pilotstats bin` |
| Key/joy binds | `0x0042B690` etc. | `KeyConfig`, `JoyConfig`, `sdefault.txt` |
| Audio settings | `0x0042DAB0` | `Fxvolume`/`Musicvolume`/… |
| Display modes | `0x004A8880` | `dmodes.bin` |

## 13. Diagnostics

Surrender assertions route through `0x004C3710` / `0x004C37B0` / `0x004AA9C0` / `0x004AA960`
(`FATAL: SR Assertion Failed`, `Debug assertion in module %s line …`). A global debug-print routine
(`dbout.txt`) backs the `c:\dbout.txt` log. These strings are how the subsystem boundaries above were
recovered.

## 14. External DLLs

`KERNEL32`, `USER32`, `GDI32`, `ADVAPI32`, `SHELL32`, `ole32` (COM/DirectX), `WINMM` (timers/MIDI),
`VERSION`, **`DINPUT`**, **`binkw32`** (Bink), **`mss32`** (Miles), **`srmemory`** (Surrender).
DirectDraw/Direct3D, DirectInput and DirectPlay are also resolved dynamically via `LoadLibrary`
(`DDRAW.DLL`, `srddraw.dll`, `winvfx*.dll`, `vfx.dll`).

## 15. Data formats (cross-reference)

| Format | What | Status |
|---|---|---|
| `.HOG` (EA BIGF) | asset archive | spec'd — `docs/hog-format.md` |
| `SHIP/GUN/MISSILESTATS.BIN` | 352-byte stat records | spec'd — `docs/stats-format.md` |
| `.DTE` | missions/triggers (see §9 `TT_*`) | partial — `docs/dte-format.md` |
| `.SHP` / `.SPR` | 3D models / sprites | tooled (community), needs spec |
| `dmodes.bin` | render-device/resolution list | newly identified (§3) — needed for widescreen |
| `*.fm8` | pilot files | identified (§12) |
| `GAME%02d.IFF` | saved games | identified (§12), community editors exist |
| `*.frc` | force-feedback effects | identified (§7) |

## 16. Pointers for the modernization work

- **Widescreen / Hor+ (priority #1): DONE** — `tools/ws_patch.py` patches the projection writer
  `FUN_004c3a60` (`0x004C3A60`, `sX := sY·height/width` ⇒ square-pixel Hor+) and forces the flight
  resolution via a cave at device init `0x004ACBE0` (globals `DAT_005d6b2c`/`DAT_005d6c88`). The core
  flight HUD (`hud.cpp` `0x00483150`, cockpit `0x004934F0`) already auto-centres from width/height;
  **v2** = native-widescreen menus + repositioning the 320×240-grid flight widgets (`0x00494040`).
- **Mission editor:** the `TT_*` trigger table `0x0045B330` + mission runtime `0x0048E140`.
- **Stat/ship tooling:** already covered by `slstats.py` / `slswitch.py`; cross-check loaders at
  `0x0049CAE0` (pilotstats) and `0x00441AA0` (ship preload).

## Methodology & caveats

Functions were auto-clustered by `tools/map_engine.py` (harvests each function's referenced string
literals + distinctive imported APIs from the Ghidra decompiled-C dump), then reviewed by hand. The
underlying decompilation is `analysis/exports/LANCER_decrypted.exe.*`. Addresses are specific to the
analyzed build; only ~12% of functions reference strings, so the ~1,940 untagged functions (math,
vector/matrix, container, and leaf helpers) are not individually listed here. Purposes are inferred
from diagnostics and should be verified against the decompilation before relying on them for patches.
