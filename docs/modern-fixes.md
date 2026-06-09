# Starlancer (2000) — modern-systems fix catalogue

Actionable fixes for running and improving Starlancer on Windows 10/11, each tagged by **layer**
(what it touches) and, where we have it, backed by our own **static RE** of the decrypted
executable (ImageBase `0x400000`). This is the *how-to* companion to
[`modding-scene.md`](modding-scene.md) (the scene/landscape overview) and
[`engine-map.md`](engine-map.md) (the subsystem address map).

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

## 3. Resolution & widescreen  · CONFIG / **EXE (our active work)**

**INI resolution (stretch only).** `starlancer.ini` → `Xres=`/`Yres=`. Do **not** exceed
~`1280×1024` (higher values crash on many systems). This only **stretches** 4:3 — the HUD and
menus do not adapt, and menus/FMV stay 640×480.

**True Hor+ widescreen — no fix exists anywhere; this is our prime original target.** Verified
anchors in the decompilation: 640×480 is written in `FUN_004ACBE0` (`0x004ACBE0`) to the
Surrender device struct `DAT_00588730` (`+0x1666` width / `+0x166A` height), with resets at
`0x4A8880` / `0x4A8600`; the selectable mode list is gated by `dmodes.bin`. Projection scale and
centre are **independent X/Y** (`+0x166E`/`+0x1686` scale, `+0x167A`/`+0x1692` centre) — i.e.
structurally Hor+-clean. **Open item:** the device-specific render-init behind the
`DAT_00588730 + 0x40` vtable callback (end of `FUN_004ACBE0`) that writes those projection fields
— the last piece for a correct FOV. **Layer:** EXE. **Source:** our RE (`engine-map.md`).

---

## 4. Frame-rate cap (~100 FPS)  · EXE · *open*

No community fix is documented; the cap appears hardcoded and would need an EXE patch to the
timer/frame loop. Flagged as an **open opportunity** alongside widescreen. **Layer:** EXE.
**Status:** UNCONFIRMED root cause (timer routine not yet pinned).

---

## 5. Multi-core / CPU-affinity crashes  · CONFIG / EXE

Starlancer can crash on multi-core CPUs. Remedies:

- **Starlancer Crash Fix v1.0.1** (Teleguy / Choum) — patched `lancer.exe`; fixes the medal-case
  crash *and* forces single-core affinity. <https://community.pcgamingwiki.com/files/file/1952-starlancer-crash-fix/>
  (If pairing with dgVoodoo2 on NVIDIA, prefer the v1.0.2 follow-up to avoid a 2D→3D hang.)
- **Manual affinity** — launch pinned to one core (e.g. `imagecfg -a 0x1 lancer.exe` /
  `lancer.icd`, or set affinity via Task Manager / a launcher).

**Layer:** EXE (patch) or CONFIG (affinity). **Source:** community; cross-ref the crash notes in
`modding-scene.md`.

---

## 6. Crashes — medal case & general stability  · CONFIG / EXE

- **Medal-case close crash** — Win98 compatibility mode on `lancer.exe`, or the Crash Fix (§5).
- **General** — Win98/WinXP compatibility mode helps on some systems; disabling in-game *3D Sound
  Effects* avoids an EAX-path crash on others.
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

1. **Hor+ widescreen** — no fix exists; nearly fully mapped (§3). Highest-value.
2. **100-FPS uncap** — no fix exists (§4).
3. **One consolidated modern-Windows fix pack** — DRM shim + dgVoodoo2 preset + crash fix + audio
   fix + boot-skip, bundled.

## Sources
PCGamingWiki (StarLancer), VOGONS, Wing Commander CIC, WSGF, SWAT Portal; community tools as
linked; **our static RE** for the boot-video path (§1), the renderer/widescreen anchors (§3), the
MP sync gate (§8), and the file formats (§10). Items we could not confirm are marked UNCONFIRMED.
