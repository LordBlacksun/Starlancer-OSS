# Running Starlancer on modern Windows (10/11) — setup checklist & folder layout

A practical, ordered guide to getting your **legally-owned** Starlancer running on a
current PC, with our static EXE fixes (widescreen, crash fixes) and the modern
graphics/audio/controller wrappers. It assumes you have your own install (the `.HOG`
data, stats, etc.).

> **Safety note for this project:** this repo never launches the game — every fix
> here is built and verified *statically*. **Actually running it is your call, on your
> terms.** Nothing below runs the game for you; the final launch is yours.
>
> Everything here is **in-game-untested by us** — assembled from our reverse
> engineering plus documented community fixes. Your first launch is the real test.

---

## TL;DR — three paths

- **Easiest "do it for me"** → **[Starlancer Studio](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)**,
  the all-in-one app: its **Ready-to-Play** wizard stages a complete patched copy (EXE fixes + controller
  shim + blanked logos + your graphics/audio drop-ins) into an output folder, and its **Dashboard** applies
  the recommended fixes to an existing install in one click. The manual steps below are those same fixes by
  hand, for when you want the detail.
- **Minimal "just boot it"** → (1) a DRM-free exe, (2) dgVoodoo2, (3) enable
  DirectPlay. That's usually enough to reach the menu.
- **Full "modern Starlancer"** → the above **+** `sl_patch.py` (widescreen + crash
  fixes) **+** the XInput shim **+** DSOAL audio **+** compatibility mode.

Work top-to-bottom; each step says whether it's **required** or **optional**.

---

## Final folder layout (what your game root should contain)

Everything goes in the folder that holds the runnable exe. Wrappers are all
*different* DLL names, so they coexist:

```
Starlancer\                       ← game root
├─ Lancer.exe                     ← runnable (DRM-free) exe, PATCHED by sl_patch   [step 1–2]
├─ Lancer.exe.slpatch.json        ← patch manifest sl_patch writes (harmless; lets you --verify/--revert)
│
│   ── graphics wrapper (pick ONE) ──                                              [step 3]
├─ DDraw.dll                      ← dgVoodoo2  (or DDrawCompat's ddraw.dll)
├─ D3DImm.dll                     ← dgVoodoo2 only
├─ dgVoodoo.conf                  ← dgVoodoo2 config (from dgVoodooCpl.exe)
│
│   ── optional drop-ins ──
├─ dinput.dll                     ← our XInput controller shim                     [step 6]
├─ xinput_shim.ini                ← controller mapping (optional)
├─ dsound.dll                     ← DSOAL, for 3D sound                            [step 5]
│
│   ── your existing game files (unchanged) ──
├─ starlancer.ini                 ← game config (you may clear [Device]; see troubleshooting)
├─ resource.hog,  CD1.HOG, CD2.HOG
├─ shipstats.bin, gunstats.bin, missilestats.bin, pilotstats.bin
├─ dmodes.bin
├─ missions\   saves\   pilots\   …
└─ (the rest of your install)
```

You do **not** need the original SafeDisc `LANCER.EXE` + `LANCER.ICD` if you run the
DRM-free `Lancer.exe` (step 1, Option A). Keep them around as backups.

---

## Step 0 — Back up first  · **required**

Copy your **entire** game folder somewhere safe before changing anything. Keep the
originals pristine; do all the work on the copy.

---

## Step 1 — Get a runnable (DRM-free) exe  · **required**

The stock `LANCER.EXE` is a **SafeDisc 1.40.004** loader that needs `secdrv.sys`,
which Microsoft disabled/removed on Win10/11 — so it won't start. Since you own the
game, get past it one of these ways:

- **Option A — No-CD / decrypted exe (simplest).** Use the decrypted `Lancer.exe`
  of your copy and put it in the game root. (We validated this image is a faithful
  decrypt of your `LANCER.ICD`.) This is the exe you'll patch in step 2.
- **Option B — SafeDiscShim** (keep the original loader): a userland `secdrv` shim,
  no kernel driver. <https://github.com/RibShark/SafeDiscShim>. You'd then patch
  `LANCER.ICD`'s decrypted form / run the loader pair with the shim.

> Legal: defeating the DRM on a copy **you own**, for your own use, is the point of
> a No-CD exe. Don't redistribute the exe.

---

## Step 2 — Apply our EXE fixes  · **recommended** (`tools/sl_patch.py`, stdlib Python)

Patch a **copy** of the runnable exe (the tool never runs it):

```
python tools\sl_patch.py --widescreen 1920x1080 --fix-medal --fix-multicore  Lancer.exe  Lancer.patched.exe
python tools\sl_patch.py --verify Lancer.patched.exe
```

Then make the game launch the patched exe (rename `Lancer.patched.exe` → `Lancer.exe`,
keeping a copy of the unpatched one).

- Replace `1920x1080` with **your monitor's resolution**. On a 4:3 display, omit
  `--widescreen` (it's a no-op at 4:3 anyway).
- `--fix-medal` fixes the **bunk medal-case crash** (clicking the medal case later in
  the campaign). `--fix-multicore` pins the game to one core to avoid the multi-core
  timer race.
- Pick any subset; re-run to add more later (the sidecar manifest tracks what's
  applied). `--revert Lancer.patched.exe out.exe` undoes everything; `--revert-only
  <fix> …` undoes one.
- **FPS:** there is intentionally no `--fps` patch — the ~100 cap is renderer **vsync**,
  not the exe. Turn vsync off in dgVoodoo2 (step 3) to exceed it; the game's logic
  stays correct. (`--fps N` just prints this explanation.)

---

## Step 3 — Graphics wrapper  · **required on modern GPUs** (pick one)

Direct3D 7 / DirectDraw is flaky-to-broken on current drivers and causes the
high-resolution crash. Drop one wrapper into the game root:

- **dgVoodoo2** (primary; also removes the high-res crash, and is where you set
  vsync/refresh): copy `DDraw.dll` + `D3DImm.dll` from its `MS\x86\` into the game
  root, then run `dgVoodooCpl.exe` and set your resolution + **aspect-ratio
  correction**. For >100 FPS, set **VSync = off** (or a forced higher refresh).
  <https://dege.freeweb.hu/dgVoodoo2/>
- **DDrawCompat** (lighter): drop its `ddraw.dll` (v4.x) in the game root.
  <https://github.com/narzoul/DDrawCompat/releases>

> Widescreen >1280 wide may stress the renderer's buffers — pairing the widescreen
> patch with dgVoodoo2/DDrawCompat is recommended.

---

## Step 4 — Windows components  · **required**

- **Enable DirectPlay:** *Control Panel → Programs → Turn Windows features on/off →
  Legacy Components → DirectPlay*. Needed on Win8+ (its absence causes the
  "Could not CoInitialise" startup failure).
- DirectX 7-era runtime is usually already present on Windows; if the game complains
  about DirectX at startup, install the legacy **DirectX End-User Runtime**.

---

## Step 5 — Audio  · **optional**

The engine uses Miles (`mss32.dll`). For 3D sound / EAX on modern systems:

- **Replacement `mss32.dll`** (the community "Starlancer sound fix"): drop a newer Miles 6.0a build
  over the original `mss32.dll` in the game root. The 2000-era Miles is what misbehaves on modern
  Windows; a newer build fixes it. (Verify any replacement is 32-bit and still exports the `_AIL_*`
  functions the game imports — `python tools/pe_inspect.py mss32.dll`.)
- **DSOAL** (DirectSound→OpenAL): drop its `dsound.dll` in the game root. Good for EAX surround.
- Or just **disable in-game *3D Sound Effects*** — also avoids a known EAX-path crash.

---

## Step 6 — Controller  · **optional**

For a modern Xbox-style pad with **separate triggers** (legacy DInput merges them):

- **Our shim:** copy `tools\xinput_shim\dinput.dll` (build it via `build.bat` if you
  don't have the binary) and optionally `xinput_shim.ini` into the game root.
- **Alternatives (no build):** Steam Input, or **Xidi** (also a proxy `dinput.dll`).

Keyboard + mouse keep working normally (the shim forwards them to the real
DirectInput).

---

## Step 7 — Compatibility mode  · **optional, if unstable**

Right-click the exe → **Properties → Compatibility**:
- Try **Windows 98 / Windows XP (SP3)** mode if you hit residual crashes.
- Tick **Run as administrator** if the wrapper or `starlancer.ini` can't write
  (e.g. installed under `C:\Program Files`). Installing the game **outside** Program
  Files avoids most permission headaches.

---

## Step 8 — First launch & sanity check  · your call

Launch the patched exe. Then sanity-check:
- Reaches the main menu (front-end stays 4:3 / pillarboxed by design).
- In flight: widescreen FOV looks right (horizontal widens, no vertical stretch).
- **Bunk → click the medal case** later in the campaign — no crash (the fix).
- Controller axes/triggers behave (if using the shim).

**If it crashes immediately on launch:** open `starlancer.ini`, delete the contents of
the `[Device]` section, and retry (a common wrapper-handshake fix).

---

## Troubleshooting quick-map

| Symptom | Try |
|---|---|
| Won't start / instantly exits | DRM (step 1) → DRM-free exe or SafeDiscShim |
| "Could not CoInitialise" | Enable DirectPlay (step 4); DirectX runtime |
| Black screen / garbled 3D / crash at high res | Graphics wrapper (step 3); clear `[Device]` in `starlancer.ini` |
| Stretched (not true widescreen) | Use `sl_patch --widescreen` (step 2), not the INI stretch |
| Capped at ~100 FPS | dgVoodoo2 **VSync off** (step 3) — not an exe fix |
| Crash clicking the medal case (bunk) | `sl_patch --fix-medal` (step 2) |
| Random crashes on multi-core CPUs | `sl_patch --fix-multicore` (step 2), or set CPU affinity to 1 core |
| Triggers share one axis / no separate LT-RT | XInput shim (step 6) |
| No/!broken 3D sound, or sound-related crash | DSOAL, or disable *3D Sound Effects* (step 5) |
| Permission / can't save config | Install outside `Program Files`, or run as admin (step 7) |

See [`modern-fixes.md`](modern-fixes.md) for the per-fix RE detail behind each of
these, and [`engine-map.md`](engine-map.md) for the addresses.
