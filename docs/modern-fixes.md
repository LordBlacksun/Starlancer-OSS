# Starlancer (2000) — modern-systems fix catalogue

Actionable fixes for running and improving Starlancer on Windows 10/11, each tagged by **layer**
(what it touches) and, where we have it, backed by our own **static RE** of the decrypted
executable (ImageBase `0x400000`). This is the *how-to* companion to
[`modding-scene.md`](modding-scene.md) (the scene/landscape overview) and
[`engine-map.md`](engine-map.md) (the subsystem address map). For an **ordered, end-to-end setup
walkthrough** (what to install in what order, the final folder layout, and a troubleshooting map),
see [`running-on-modern-windows.md`](running-on-modern-windows.md); this file is the per-fix detail
behind it.

> ⚖️ **You must own a legal copy.** Nothing here distributes the game, its assets, or any DRM
> circumvention. Fixes that patch/replace game files operate on **your** install — keep patched
> `.hog`/`.bik`/`.exe` local (this repo commits no game data).
>
> 🛟 **We never launch the game.** All of our work is static (reading/patching files as data).
> Any *in-game* verification below is yours to perform, on your terms.

Layer legend: **CONFIG** (ini/registry/OS) · **DATA** (game asset/archive) · **EXE** (binary
patch) · **WRAP** (external DLL wrapper/tool).

---

## 1. Skip the boot/intro movies (`blank.bik`)  · DATA · *our-RE-backed*

**Issue.** The three startup **branding logos** — Warthog, Digital Anvil, Microsoft Game Studios —
play at every launch and can hang or fail on modern setups.

**What the engine does (verified).** The startup clips are a consecutive group in the string table:
`warty_.bik` (**Warthog**), `new_dalogo_fs_uncmpr.bik` (**Digital Anvil**), `new_nms.bik`
(**Microsoft Game Studios**), then the splash→main-menu transition `splash to mm.bik`; the campaign
intro is `new_intro.bik`. They open **from the CD HOG** (`BinkOpen(resource, 0x800000)` — *not* loose
files). The shared play loop (`0x004AC510`) tolerates a **missing or zero-frame** movie — `BinkOpen`
returns NULL (logged, non-fatal) or the end flag trips on frame 0 — so the engine simply moves on;
every frame also polls input, so **any keypress already aborts** a playing clip. *(The logo↔name
mapping is by static inference — `warty_`=Warthog, `new_dalogo`="da logo"=Digital Anvil, `new_nms`=
the only remaining startup logo=Microsoft Game Studios; no other `.bik` is microsoft-named.
`FUN_004ABDE0` is the related per-**chapter** intro/landing sequencer, not the logo player.)*

**Method.** Because the movies live in the HOG, blank them *in the archive* (a loose drop-in won't
override the resource path). The tool blanks **only the three startup logos by default** — the
splash and intro are left intact unless you ask for them — using a version-matched zero-frame Bink,
and verifies the archive round-trips byte-for-byte except the swapped clips:

```sh
python tools/blank_boot_videos.py list  CD1.HOG                       # show the startup clips + roles
python tools/blank_boot_videos.py blank CD1.HOG -o CD1_nologo.hog     # blank the 3 logos only (default)
python tools/blank_boot_videos.py blank CD1.HOG -o CD1_nologo.hog --include-splash --include-intro
```

Place the new HOG in your install (keep the original). If a clip misbehaves with the generated
stub, pass a known-good minimal black Bink instead: `--blank path/to/blank.bik` (e.g.
esc0rtd3w's *blank-intro-videos*). **Layer:** DATA. **Source:** method = esc0rtd3w + our Bink RE;
filenames + tolerance = our decompilation (`engine-map.md` §6).

---

## 2. Graphics — DirectDraw / Direct3D 7 on modern GPUs  · WRAP

The engine renders via **DirectDraw + Direct3D 7** (Surrender `SR_*` / `srddraw.dll`), which is
flaky-to-broken on current drivers; a wrapper fixes rendering and the high-res crash.

| Fix | Method | Notes |
|---|---|---|
| **dgVoodoo2** (primary) | Copy `D3DImm.dll` + `DDraw.dll` from its `MS\x86` into the game root; tune `dgVoodooCpl.exe` (aspect-ratio correction, resolution). | Also removes the high-resolution crash. <https://dege.freeweb.hu/dgVoodoo2/> |
| **DDrawCompat** (lighter) | Drop `ddraw.dll` (v4.x) in the game folder. | <https://github.com/narzoul/DDrawCompat/releases> |
| **DxWnd** (windowed) | Run windowed/borderless; enable *Keep cursor fixed* + *Emulate mouse relative movements* (the game uses `SetCursorPos`). | If it crashes on first run, run once without DxWnd, then retry. |

If a wrapper crashes on first launch, clear the `[Device]` section in `starlancer.ini` and retry.
**Layer:** WRAP (+ CONFIG).

---

## 3. Resolution & widescreen — native Hor+  · **EXE (our original fix)** · *SOLVED*

**No true-widescreen fix existed anywhere — this was our prime original target, and it's now done.**
The legacy options only ever *stretched* 4:3: setting `starlancer.ini` → `[Device] Xres`/`Yres`
changes the in-flight render size but, unpatched, distorts the image (non-square pixels) and the
HUD/menus don't adapt; values above ~`1280×1024` also tend to crash. Our patch makes the same
resolution render with a correct **Hor+** field of view instead.

### How to apply (`tools/ws_patch.py`)
Patch a **local copy of your own** decrypted/No-CD exe (the tool never launches it; in-game testing
is yours):

```sh
python tools/ws_patch.py --fov-table                                  # preview the FOV per aspect
python tools/ws_patch.py --width 1920 --height 1080 Lancer.exe Lancer_ws.exe
python tools/ws_patch.py --verify Lancer_ws.exe                       # confirm the patch state
python tools/ws_patch.py --revert Lancer_ws.exe Lancer_stock.exe      # restore stock bytes
```

Run `Lancer_ws.exe` (pair with **dgVoodoo2/DDrawCompat** on modern GPUs — see §2). The in-flight
3D view is Hor+ at your resolution; **menus/briefing stay 640×480 and pillarbox** (centred, not
stretched) — that's intended for v1.

### What it does (verified RE)
The projection scale/centre writer is **`FUN_004c3a60` (`0x004C3A60`)** — *not* the
`DAT_00588730+0x40` callback (that is `SR_driver_init` inside the external `srddraw.dll`, which only
*consumes* the projection). It computes `scale_x=(w−K)·sX`, `scale_y=(h−K)·sY` into the device
struct (`+0x166E`/`+0x1686` scale, `+0x167A`/`+0x1692` centre, `K≈0.1`), with `sX=0.6`, `sY=0.8`
baked in — and `0.6/0.8 = 480/640`, i.e. a 4:3 encoding that yields **square pixels only at 4:3**.

- **Patch 1 — Hor+ FOV** (code-cave at `0x004C3A60`): forces `sX := sY · height / width` at runtime,
  so `scale_x == scale_y` (square pixels) and the X clip-planes (derived from the same value) widen
  to match. Result: **vertical FOV fixed, horizontal FOV widens with the aspect** — textbook Hor+.
  At any 4:3 resolution it recomputes to exactly `0.6` ⇒ **byte-identical to stock (regression-safe)**.
- **Patch 2 — force resolution** (code-cave at `0x004ACBE0`): bakes `--width/--height` into the
  flight-resolution globals `DAT_005d6b2c`/`DAT_005d6c88`, overriding INI/`dmodes.bin`. The front-end
  device stays 640×480, so menus pillarbox.

Both caves live in `.text` slack (no new section; size unchanged — 61 bytes changed total) and were
statically verified (capstone disasm + an FOV table; the exe is never executed). Representative FOV
(vertical fixed ≈64°): **16:9 → ~96° H**, **16:10 → ~90° H**, **21:9 → ~112° H**.

**Caveats.** Widths >1280 may still hit the back/Z-buffer ceiling inside `srddraw.dll` (outside our
static view) — pair with a wrapper and verify in-game. Native-widescreen **menus** and repositioning
the few 320×240-grid **flight HUD widgets** are deferred to **v2** (the core flight HUD — radar,
reticle, screen centre — already auto-derives from width/height, so it adapts).

**Layer:** EXE. **Source:** our RE (`engine-map.md` §3/§16); tool `tools/ws_patch.py`.

---

## 4. Frame-rate cap (~100 FPS)  · WRAP (not EXE) · *root cause RE'd 2026-06-12*

**Finding (static RE): there is no in-EXE frame limiter to patch. The ~100 is the game's
simulation timebase, and the render cap is vsync in the renderer DLL.** Raising the timer would
speed up the whole game, so we deliberately ship no "FPS patch"; the safe uncap is a wrapper
setting, and game *logic* already stays correct at any render rate.

How it actually works (see `engine-map.md` → *Timer subsystem*):

- A **100 Hz multimedia timer** is the heartbeat. `FUN_00481440` registers it via
  `FUN_004a70f0` with the frequency in `ecx`: `mov ecx, 0x64` at **`0x00481689`** → period
  `1000/100 = 10 ms` passed to `timeSetEvent` (callback `FUN_004a6f80` → `LAB_004827c0`).
- That callback is the **simulation clock**: it increments `DAT_00565064` (the master clock, in
  **centiseconds**) and `DAT_005db8e8` (a raw tick counter). **~141 gameplay/AI sites** schedule
  off `DAT_00565064` with **literal centisecond constants** (`+500` = 5 s, `+1000` = 10 s,
  `+0x19` = 0.25 s, `+0x32` = 0.5 s …). So the 100 Hz is *baked into data semantics* — change it
  and every timer, animation and AI cadence rescales (the game runs faster/slower). **Not an FPS
  knob.**
- **Logic is already decoupled from render.** The main loop (`FUN_004aab20`) calls the
  fixed-timestep **catch-up executor `FUN_004a6f00`**, which advances each logic timer by the
  *real elapsed* number of steps (clamped to 50). Logic therefore runs at its true real-time rate
  no matter how fast or slow frames are drawn. Render is **not** throttled inside `lancer.exe`
  (no per-frame `Sleep`, no busy-wait on the tick).
- The **render cap is vsync** in the **DirectDraw / Direct3D 7 present path inside the external
  `srddraw.dll`** — not visible to a static patch of `lancer.exe`.

**Fix (wrapper layer):** run under **dgVoodoo2** or **DDrawCompat** with **VSync disabled** (or a
forced higher refresh). Because of the catch-up executor, frames above 100 FPS render correctly
and gameplay speed is unchanged. **Tool:** `sl_patch.py --fps N` prints this finding and the
recipe (it intentionally applies no patch). **Layer:** WRAP. **Source:** our static RE
(decompiled timer subsystem) + community wrappers. **In-game verification** (does vsync-off give
>100 FPS at correct speed) is the community's.

---

## 5. Multi-core / CPU-affinity crashes  · EXE (`sl_patch --fix-multicore`) · *2026-06-12*

**Root cause (static RE):** the stock exe has **no RDTSC and no affinity calls**; the only extra
thread is the **WINMM multimedia-timer thread** (see `engine-map.md` → *Timer subsystem*), whose
**mode-0 timer callbacks run concurrently with the main thread**. The per-timer `InterlockedExchange`
guard only blocks re-entry of the *same* timer — it does **not** serialise a callback against the
main thread touching the same globals. On one core, time-slicing hides it; on many cores it is a
genuine data race. That is exactly why the community Crash Fix *forces single-core affinity*.

Pinning the precise racy global is not statically provable (and unverifiable without launching), so
our fix is the **agreed fallback: have the exe pin itself to one core at startup** — cleaner than an
external launcher, and it composes with the separately root-caused medal fix (§6).

- **`sl_patch.py --fix-multicore`** — a code-cave at the OEP (`0x004D1210`, before the CRT/WinMain
  and before any thread spawns) resolves `SetProcessAffinityMask` at runtime (it is not imported)
  via the existing `GetModuleHandleA`/`GetProcAddress` and calls it with mask `1` (CPU 0) on the
  current process, then runs the displaced OEP bytes. 75-byte cave; statically disassembly-verified;
  revertable. **Honest framing: this is a *pin*, not a cure** — it sidesteps the race rather than
  removing it.
- **Community alternative — Starlancer Crash Fix v1.0.1** (Teleguy / Choum): patched `lancer.exe`
  that fixes the medal crash *and* forces single core. <https://community.pcgamingwiki.com/files/file/1952-starlancer-crash-fix/>
  (With dgVoodoo2 on NVIDIA, prefer their v1.0.2 to avoid a 2D→3D hang.)
- **Manual affinity** — Task Manager / `imagecfg -a 0x1 lancer.exe` / a launcher.

**Layer:** EXE. **Source:** our static RE + community. **In-game verification** (does pinning stop
the crashes) is the community's.

---

## 6. Crashes — medal case & general stability  · EXE (`sl_patch --fix-medal`) · *2026-06-12*

- **Medal-case crash — ROOT-CAUSED + fixed.** Trigger: the player's **bunk / ready-room, clicking the
  medal case** (the ready-room menu `FUN_00439fb0` case 6 calls the medal-case display
  `FUN_004362f0`). It plays a Bink "case lid" movie opening then closing, each with an early/late
  campaign art variant (mission index `DAT_00562dc8 < 0x13` = Reliant `r`-prefixed art, ≥ 0x13 =
  Yamato art). Every medal video must live in the **medal handle `DAT_0051d7e8`** — that is what the
  `_BinkWait` (line 20509), the per-frame render callback `FUN_00436b20` (installed at
  `*(DAT_00588730 + 0x88)`), and the `_BinkClose`s all use. **Four `_BinkOpen` sites store the result,
  but only one (lid-up early, `0x00436669`) targets `DAT_0051d7e8`; the other three were copy-pasted
  with a stale operand and store into `DAT_005d6c40`** (the unrelated in-flight comm-video handle):
  `0x004365EC` (lid-up late), `0x0043698F` (lid-down early), `0x00436A0B` (lid-down late). The tell at
  each bug site is the *next* instruction — `mov eax,[0x51d7e8]; cmp` — i.e. it opens one global but
  validates the other. That asymmetry explains the symptom exactly: late-campaign medals **hard-crash
  on open** (the bad lid-up handle is `_BinkWait`'d immediately), while early-campaign medals merely
  glitch on close (a just-freed handle that Win98's heap happens to tolerate). **`sl_patch.py
  --fix-medal`** restores all three stores to `DAT_0051d7e8` (3 × 4-byte in-place operand fixes, no
  cave; matches the correct early lid-up open; disassembly-verified; revertable). *(Pending a
  byte-for-byte cross-check against the community Crash Fix — its file is download-gated; see
  `analysis/crashfix/`.)*
- **General** — Win98/WinXP compatibility mode helps on some systems; disabling in-game *3D Sound
  Effects* avoids an EAX-path crash on others (not yet RE'd).
- **"Could not CoInitialise"** at start — ensure DirectX 7 runtime + DirectPlay (§8) are present;
  try compatibility mode. (OEP diagnostics noted in `engine-map.md`.)

**Layer:** CONFIG (mostly) / EXE (Crash Fix).

---

## 7. SafeDisc / DRM / No-CD  · EXE / WRAP

The MS-2000 release is **SafeDisc v1.40.004** (relies on `secdrv.sys`, disabled/removed on
Win10/11 — won't launch). Owner-legal remedies:

- **SafeDiscShim** (RibShark) — userland `secdrv` shim, no kernel driver. <https://github.com/RibShark/SafeDiscShim>
- **Scope limit** — `LANCER.EXE` is the loader and
  `LANCER.ICD` the encrypted game. *(We use a validated unprotected image for **analysis only**
  — never launched, never shipped; patches target the owned install.)*
- **Ubisoft re-release** — if yours is the Ubisoft repack, extract its bundled exe with
  `innoextract` (read-only). Confirm version/DRM from the installed files rather than assuming v1.

**Layer:** EXE / WRAP. **Source:** community + our exe fingerprinting (`modding-scene.md §3`).

---

## 8. Multiplayer  · CONFIG / WRAP

- **Enable DirectPlay** — *Control Panel → Programs → Turn Windows features on/off → Legacy
  Components → DirectPlay* (LAN/TCP-IP). Required on Win8+.
- **MSN Gaming Zone** matchmaking is **permanently dead**; use **GameRanger** for lobbies.

**Layer:** CONFIG (DirectPlay) / WRAP (GameRanger). The MP sync path is `FUN_00401000`
(per-syncpoint bitmask; *"Player reached sync point"*) — see `engine-map.md`.

---

## 9. Audio — EAX / 3D sound  · WRAP / EXE

The engine uses **Miles** (`mss32.dll`). For DirectSound3D/EAX surround on modern systems:

- **DSOAL** (DirectSound→OpenAL) — drop its `dsound.dll` in the game folder. Simplest.
- **Creative ALchemy** — rename its `dsound.dll` to `esound.dll` and hex-edit `mss32.dll` to
  reference `esound.dll`; select EAX in-game. (See the *Starlancer DSound Fix* community file.)
- If 3D sound is unstable, **disable in-game *3D Sound Effects*** (also dodges an EAX-path crash).

**Layer:** WRAP (DSOAL) / EXE (mss32 hex-edit). **Source:** community.

---

## 9b. Modern game controllers — XInput shim  · WRAP (proxy DLL) · *our fix, 2026-06-12*

Starlancer is **DirectInput-only** and predates **XInput**, so a modern Xbox-style pad works only
through DInput's legacy path — which **merges LT/RT onto one shared Z axis** (no separate triggers)
and offers no rumble. Confirmed by RE (`engine-map.md` §7): the game opens an `IDirectInput7A` and
reads the stick via `Poll` + `GetDeviceState(DIJOYSTATE)`; **keyboard and mouse also go through
`dinput.dll`**.

- **`tools/xinput_shim/` — a proxy `dinput.dll`** (drop it next to `lancer.exe`; DInput is loaded by
  name so the local copy wins). It **forwards keyboard + mouse to the real DirectInput untouched** and
  **synthesizes the joystick from XInput** with **separate triggers** (`lRx`=LT, `lRy`=RT), both
  sticks, the D-pad as a POV hat, and the buttons (mapping configurable via `xinput_shim.ini`).
  Reporting no force feedback steers the game onto its clean no-FF path, so v1 needs no effect objects.
  Built 32-bit with MSVC (`build.bat`); structurally verified with our own `test_host.exe` (drives the
  exact COM sequence with no pad → clean neutral state). **No-rumble v1**; translating the game's
  per-weapon `.frc` effects to XInput vibration is deferred.
- **External alternatives** (no build): **Steam Input**, or a generic DInput↔XInput wrapper such as
  **Xidi** (also a proxy `dinput.dll`). Easiest if you don't want to build ours.

**Layer:** WRAP. **Source:** our RE + native shim. **In-game verification is the community's.**

---

## 10. Config & file locations  · reference

- **`starlancer.ini`** (game root, plain text) — main user config: `Xres`/`Yres`, a `[Device]`
  block sometimes cleared for wrapper compatibility.
- **`dmodes.bin`** — gates the selectable display-mode list (a target for the widescreen work).
- **Saves** — `saves\<profile>GAME%02d.IFF` (EA-IFF, top form `'SAVE'`, chunk `'MISS'`);
  **`profile.bin`** = 208-byte profile blob; **pilots** = `pilots\<name>.fm8`.
- **Missions** — `missions\%s.dte` (loose overrides the HOG copy); RefPack-compressed, see
  [`dte-format.md`](dte-format.md).

---

## Open opportunities (original work)

1. ~~**Hor+ widescreen**~~ — **DONE** (§3): `tools/ws_patch.py` (static EXE code-cave). v2 = native
   widescreen menus + flight-HUD-widget reposition.
2. **100-FPS uncap** — no fix exists (§4). Now the highest-value open item.
3. **One consolidated modern-Windows fix pack** — DRM shim + dgVoodoo2 preset + crash fix + audio
   fix + boot-skip, bundled.

## Sources
PCGamingWiki (StarLancer), VOGONS, Wing Commander CIC, WSGF, SWAT Portal; community tools as
linked; **our static RE** for the boot-video path (§1), the renderer/widescreen anchors (§3), the
MP sync gate (§8), and the file formats (§10). Items we could not confirm are marked UNCONFIRMED.
