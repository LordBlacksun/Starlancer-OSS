# Starlancer Studio — v2 design proposal (roadmap)

> **STATUS: DESIGN PROPOSAL, NOT SHIPPED BEHAVIOUR.** Nothing described here exists yet unless it
> says so explicitly. Written 2026-09-09 against Studio **v1.1** (`tools/slstudio_app.py`, 3,121 lines)
> and the toolchain as of the `.SHP` format landing. Every claim below is tagged as *read from the
> code*, *measured* (a throwaway proof of concept run in this session, never committed), or *assumed*.
> Section 8 lists them all in one place.
>
> The project's standing rules bind every item: the app **never launches the game or any game
> binary**, never bundles game data or third-party binaries in the repo, and keeps the command-line
> tools standard-library only. Anything that would need to *run* the game to be verified is marked
> as such; in-game verification stays the user's.

---

## 0. Position

Starlancer Studio's niche is the one a from-scratch engine reimplementation cannot occupy: **make
the player's own original `Lancer.exe` excellent on modern Windows, and make the game's data
inspectable and editable.** Everything proposed here serves one of those two lines. Nothing here
moves toward rendering the game, simulating missions, or playing its media. Where an idea drifts
toward "engine", it is declined in §5.

The single largest gap today is that the project understands far more of the game than the app
exposes. Behind the command line sit a complete `.SHP` model decoder (16 record types, OBJ export,
validated on all 435 shipped models), a `.DTE` mission decoder (27 sections, 95 Executor commands,
script disassembly), a byte-exact HOG writer, and a declarative patch engine with a manifest. The app
fronts the patch engine and the HOG writer, and shows none of the two format decoders at all.

---

## 1. Honest assessment of v1.1

### What is solid  *(read from the code)*

- **Backends are imported, never shelled out.** Every section calls `sl_patch`, `slswitch`,
  `slstats`, `hog_pack`, `hog_extract` and `blank_boot_videos` as modules. A grep of the app and all
  libraries for `subprocess`, `os.system`, `os.startfile`, `os.exec*`, `os.spawn*`, `webbrowser`,
  `ShellExecute` and `CreateProcess` finds only the docstring that promises their absence. The
  no-launch invariant holds.
- **Threading is right.** `Section.run_async` and `Section.run_steps` run work on a daemon thread
  that never touches Tk and post results through a `queue.Queue` drained by a main-thread `after()`
  poll. The determinate step pipeline (`run_steps`) is a good primitive worth keeping.
- **One implementation per probe.** `patch_states`, `shim_status` and `bootvid_status` are pure
  read-only functions shared by the Patcher and the Dashboard; the Patcher's verify strip was
  refactored to reuse them rather than re-implement them.
- **Backups are non-destructive and visible.** `.bak`, `.orig` and `.xinput-bak` are created
  before in-place writes, the first true original is never overwritten, and the Dashboard lists and
  restores them.
- **Packaging works from a clean clone.** `build.bat` bundles the shim DLL and the blank clip only
  when present, and the missing-dependency paths print an install message instead of a traceback.
- **The Ready-to-Play wizard** is the right shape for the "do it for me" user: validate, copy,
  patch, shim, logos, drop-ins, notes, with amber skips for third-party files that are never bundled.

### What is weak  *(read from the code unless marked)*

1. **No testable core.** All logic lives in one 3,121-line file next to the widgets. The module
   cannot be imported without `customtkinter`, and when that import fails the fallback opens a
   *modal* Tk error dialog. *(Measured: an import attempt with `customtkinter` poisoned blocked on
   that dialog until the process was killed.)* `tests/run_all.py` therefore has no Studio check at
   all, and the Linux CI leg never touches the app. The only test is `--selftest`, which takes
   Windows-only screenshots and needs Pillow.
2. **The same pipeline is written twice.** "Backup → patch → install shim → blank logos" exists in
   `DashboardFrame._apply_recommended` and again in `DeployFrame._build_steps`, with small
   differences (the Dashboard writes a customised shim INI, the wizard copies the bundled one).
   28 lines of backup/copy logic are spread over five sections.
3. **The three fixes are hard-coded in five places** (Patcher checkboxes, Patcher LEDs, Dashboard
   LEDs, Dashboard recommended list, Deploy step list) even though `sl_patch.REGISTRY` already
   describes them. A fourth `PatchDefinition` (widescreen menus, say) would need edits in all five.
4. **`GameContext` knows only the folder and the exe.** The Patcher does not seed from it at all;
   the Switcher, Stats and HOG sections make the user browse for `resource.hog` and the stat tables
   from scratch in every tab, even though they sit in the install folder the user already picked.
5. **The Dashboard answers three questions, the setup guide asks ten.**
   `docs/running-on-modern-windows.md` covers DRM state, graphics wrapper, wrapper vsync (the only
   real FPS uncap), DirectPlay, audio DLL, compatibility mode, the `[Device]` INI reset and a
   Program-Files permission trap. The app reports patch state, shim state and boot logos only, and
   calls a 249,119-byte SafeDisc loader merely "loader or modified build".
6. **Goal #3 is only half done in the GUI.** `slswitch.py` itself says to "also copy stats with
   slstats.py so the swapped ship flies right"; the Ship Switcher tab swaps the models and stops.
7. **Nothing the project learned about `.SHP` and `.DTE` is visible.** No model view, no mission
   view, no preview of a HOG entry.
8. **HOG Tools is five separate forms.** List, extract, pack, replace and rename each have their own
   path fields; replace and rename rebuild the 57 MB archive per operation; there is no session
   (open once, stage several edits, save once), and lookups are by name although five names occur
   twice in `resource.hog`.
9. **Two small bugs.** (a) `ControllerFrame._install` wraps `run_async` in `try/except
   PermissionError`, but the error is raised on the worker thread and lands in `default_error`, so
   the friendly "run as administrator or use a writable copy" dialog can never fire. (b) Restoring
   `Lancer.exe.bak` from the Dashboard leaves `Lancer.exe.slpatch.json` beside the restored exe, so
   the next refresh shows every fix STOCK but the manifest line amber ("sha differs").
10. **Preferences hold one install.** Users who keep a pristine copy and a Ready-to-Play copy flip
    the folder back and forth.

None of this is a reason to rewrite. The shell, the design system, the threading primitives and
the section pattern are worth keeping; the work is to pull the logic out from under the widgets
and then add the sections the toolchain already earns.

---

## 2. Proposed upgrades, ranked

Effort is for one developer including tests and docs: **S** ≤ 2 days, **M** 3–6 days, **L** 1–3
weeks. Value states what it buys and for whom.

| # | Upgrade | Value | Effort | Verdict |
|--:|---|---|:-:|---|
| 1 | **Core split**: `slstudio_core.py`, stdlib-only, no Tk, with a self-test in `tests/run_all.py` | High. Makes everything below testable on Linux CI; removes the duplicated pipelines; unblocks the legacy GUI as a real fallback | M | **Do first** |
| 2 | **Install Doctor** replacing the Dashboard: the full modern-Windows checklist with one-click static fixes (wrapper bitness, vsync in `dgVoodoo.conf`, `[Device]` reset, compatibility layer, DirectPlay, loader detection, permissions) | High. This is goal #1 finished from the user's side, and the ground a reimplementation never covers | M | Stage 2 headline |
| 3 | **Registry-driven fixes**: Patcher, Doctor and wizard read `sl_patch.REGISTRY` | Medium. Future `PatchDefinition`s appear with zero GUI edits | S | With #1 |
| 4 | **Switcher carries stats**: after a model swap, copy the flown ship's stat record into the slot (and its Tiger twin) | Medium-high. Completes goal #3 as the tool's own tip describes | S–M | Stage 3 |
| 5 | **Model Viewer** (`.SHP`): part tree, LODs, attachments, clips, flat-shaded Canvas 3D view, OBJ export, open straight from a HOG | Medium-high. The showcase for the newest RE; the only maintained viewer (SL Tool is 24 years old and binary-only) | M | Stage 4 |
| 6 | **HOG Workbench**: one archive session, index-addressed entries, multi-select extract, staged edits, single save, preview pane routing to the viewers | Medium. The modder's hub; fixes weakness 8 | M | Stage 4 |
| 7 | **Mission Inspector** (`.DTE`, read-only): campaign map, directory, ships, objectives, triggers, script disassembly with the developers' command names | Medium. Everything is already computed by `dte_parse`; this is presentation | S–M | Stage 5 |
| 8 | **Mission placement editor** (write): edit ship position/orientation in the raw image and write a loose `missions\missionN.dte` | Medium for modders. Cheap on top of #7 because loose missions are **raw images, no encoder needed** (§8, verified) | S | Stage 5, behind an *experimental* label |
| 9 | **Stats Editor v2**: search, all fields with provisional flags and help, compare-to-original, copy record, CSV in/out | Low-medium. It already works | S | Stage 3 |
| 10 | **Multiple install profiles** in preferences | Low | S | With #1 |
| 11 | **Hygiene**: the two bugs, Patcher seeded from the install, manifest handling on restore | Medium (trust) | S | Stage 0 |

Items 2, 4, 5 and 7/8 are where the value is. Items 1, 3 and 11 are what makes them safe to add.

---

## 3. Architecture for the top items

### 3.1 Module boundaries

```
tools/
  slstudio_core.py     NEW  stdlib only. No Tk. Imports the validated libraries.
                            Install model, Doctor checks, Fix registry, pipelines,
                            HOG session, mission document, prefs, --selftest, `doctor` CLI.
  slstudio_view3d.py   NEW  tkinter + math only (no customtkinter). Pure transform/project/
                            sort functions + a thin MeshCanvas(tk.Canvas).
  slstudio_app.py      KEPT customtkinter shell. Sections become thin: gather params, call
                            core on a worker, render results. Gains MODELS, MISSIONS, ARCHIVES;
                            DASHBOARD becomes DOCTOR; HOG TOOLS becomes the Workbench.
  slstudio.py          KEPT stdlib fallback. Gains a text Doctor and the Model Viewer for free
                            (both need only tkinter).
  sl_patch.py, hog_*.py, slstats.py, slswitch.py, shp_parse.py, dte_parse.py, pe_inspect.py,
  blank_boot_videos.py  UNCHANGED public surfaces; small additive helpers only where noted.
```

Rule: **anything that reads or writes the disk lives in core and takes paths, not widgets.** The
GUI never opens a game file itself. The CLI tools stay standard-library only; core is too, so the
tests can run wherever the CLI tools run.

### 3.2 State: what lives where

| State | Lives in | Lifetime |
|---|---|---|
| `Install` snapshot (folder, exe kind, patch states, wrappers, shim, logos, conf, INI, loose missions, stat tables, writability) | core, built by `scan(folder, env)` | Rebuilt on section show and after every fix. Immutable; never mutates disk |
| Preferences (`installs[]`, current, last dir, drop-ins folder, section) | core `Prefs`, `~/.starlancer_studio.json` | Persistent |
| `HogSession` (path, `[(name, bytes)]`, dirty flag, op log) | core | While the Archives section has an archive open |
| `ModelDoc` (`shp_parse.Model`, source path or HOG index, chosen LOD, selected part) | core + view3d | While a model is open |
| `MissionDoc` (raw image `bytearray`, `dte_parse.Mission` view, edit list) | core | While a mission is open |
| Widget variables (entries, checkboxes) | app | Per section, derived from the above on show |

The GUI keeps no game bytes of its own. A section that needs the install asks `app.install`; a
section that works on arbitrary files (Patcher, Models, Missions, Archives) takes a path and still
seeds its file dialogs from the install when one is set.

### 3.3 Core API (proposal)

```python
# slstudio_core.py  (Python 3.8+: no `match`, no `str.removeprefix`, no dict `|`, no `list[int]` annotations)

class Env:                      # OS probes, injectable so tests run on Linux with a FakeEnv
    is_windows() -> bool
    windows_dir() -> str | None
    exists(path) -> bool
    reg_read_hkcu(subkey, value) -> str | None      # winreg, returns None off-Windows
    reg_write_hkcu(subkey, value, data) / reg_delete_hkcu(...)

class Install:                  # one scan == one os.listdir + a few small reads
    folder, exe, exe_size, exe_kind   # 'stock' | 'patched' | 'safedisc-loader' | 'unknown' | 'absent'
    patches: {fix_id: (state, desc)}, manifest, manifest_sha_ok
    files: {lower_name: actual_name}
    pe: {name: PEInfo}          # ddraw/d3dimm/dinput/dsound/mss32: machine, exports (pe_inspect)
    shim: 'ours' | 'other' | 'absent', shim_backup: bool
    logos: {name: 'original' | 'blanked' | 'absent'}
    dgvoodoo: ConfDoc | None    # section-aware INI text model (keeps comments/ordering)
    ini: ConfDoc | None         # starlancer.ini, may not exist before first run
    missions_loose: [name], resource_hog, stats: {'ship'|'gun'|'missile': path | None}
    writable: bool, under_program_files: bool
def scan(folder, env=Env()) -> Install

class Check:  id, group, title, status ('ok'|'warn'|'bad'|'skip'), detail, evidence ('verified'|'heuristic'), fix_id
def doctor(install, env) -> [Check]

class Fix:    id, title, needs_params, applies(install) -> bool,
              preview(install, params) -> [str],           # exact files/keys it will touch
              run(install, params, log) -> FixResult        # explicit backup policy per fix
FIXES = {...}                    # patch_exe, install_shim, uninstall_shim, blank_logos, restore_logos,
                                 # vsync_off, set_resolution, clear_device_section, compat_layer,
                                 # restore_backup (also retires the sidecar manifest), write_notes
def pipeline_recommended(install, params) -> [(label, callable)]
def pipeline_deploy(src, dst, params) -> [(label, callable)]
def run_pipeline(steps, progress) -> bool                    # used by the CLI and by Section.run_steps

class HogSession:  open(path); entries; replace(idx, bytes); rename(idx, name); add(name, bytes);
                   remove(idx); extract(indices, outdir); save_as(path)      # never in place
class MissionDoc:  open(path_or_bytes); ships() (authored fields); set_ship_pose(i, pos, yaw, pitch, roll);
                   set_ship_iff(i, iff); write_loose(missions_dir, n)         # raw image + .orig if a loose file exists
def selftest() -> int            # synthetic install fixture; runs on Linux; wired into tests/run_all.py
CLI:  slstudio_core.py doctor <folder> [--json]     # the same checks as text, for bug reports and Linux users
```

`patch_exe` wraps `sl_patch.apply` and exposes `sl_patch.REGISTRY` so the Patcher, the Doctor and
the wizard build their fix lists from it (needs_params → the resolution picker appears only for
fixes that declare it).

### 3.4 Data flow

```
user action ──► section gathers params ──► Section.run_async(lambda: core.fix.run(install, params, log))
                                                     │  worker thread, no Tk
                                                     ▼
                                          core writes files (backup first) ──► returns FixResult
                                                     │
main thread  ◄── queue ◄─────────────────────────────┘
   └─► app.install = core.scan(folder)  ──► every visible section re-renders from the snapshot
```

The wizard and the Doctor's "apply recommended" both call `run_pipeline` with a list from core; the
GUI's `run_steps` is just the progress adapter.

### 3.5 Screens

**DOCTOR (replaces Dashboard).** Top: target install picker with the exe verdict on one line
(`stock 1,151,021 B` / `patched: widescreen 3440x1440 + medal + multicore, manifest ok` /
`SafeDisc loader (249,119 B): the fixes need an unprotected image` / `no Lancer.exe`). Middle: a
grouped checklist, one row per `Check` with LED, title, detail, evidence tag and a FIX button when a
`Fix` applies. Groups follow the setup guide: *Start* (exe kind, permissions, Program Files),
*Graphics* (wrapper present and 32-bit, `dgVoodoo.conf` present, vsync off), *Stability* (the three
EXE fixes, compatibility layer, `[Device]` section), *Input* (shim), *Audio* (`mss32.dll` exports,
`dsound.dll`), *Windows* (DirectPlay), *Extras* (logos, loose mission overrides). Bottom: "APPLY
RECOMMENDED" with the resolution picker, the backups list, the log. Every fix preview lists the
exact files and registry values it will touch before it runs.

**MODELS.** Toolbar: open file / open from HOG (entry picker), LOD selector, shaded/wire, show
attachments, mirror X, fit, EXPORT OBJ. Left: tree (parts → LODs, attachments by type, clips,
groups) from `shp_parse.Model`. Centre: `MeshCanvas` (orbit with the left button, zoom with the
wheel, pan with the right button); selecting a part highlights it; attachment markers colour-coded
(gun hardpoint, engine, light with its colour code, docking point). Right: the selected record's
decoded fields (type name, position, bbox, turret limits, presets, materials) exactly as `tree`
prints them, plus the `[verified]/[inferred]` tag from `docs/shp-format.md` for each field group.

**MISSIONS.** Left: the campaign table from `docs/campaign-flow.md` (in-game # ↔ file, source HOG
or *loose override*, ships, objectives) plus the multiplayer and test sets. Centre: tabs *Directory*
(27 slots, count, stride, offset), *Ships* (Treeview: name, flight group, authored position, yaw /
pitch / roll, IFF, type), *Objectives*, *Triggers* (with `TT_*` names), *Script* (disassembly with
Executor names and parameter labels; a search box). Stage 5b adds an edit form under *Ships*
(position, three angles, IFF) and a "WRITE LOOSE OVERRIDE…" button that writes
`missions\missionN.dte` as a raw image, backing up any existing loose file.

**ARCHIVES (replaces HOG Tools).** Toolbar: OPEN, SAVE AS (enabled when dirty), EXTRACT SELECTED,
ADD, REMOVE, REPLACE, RENAME. Left: a Treeview of entries (index, name, size, type) with
multi-select and a filter box. Right: preview by extension — `.shp` → a small `MeshCanvas` and the
part list; `.dte` → the mission summary; `*stats.bin` → the record table; `.bik`/`.tga`/other →
header fields and a hex head. "Open in MODELS / MISSIONS / STATS" hands the bytes to the full
section. All edits are staged in the `HogSession` and written once, to a new file.

**SHIPS (Switcher + Stats).** The switcher gains a third column: "carry stats". After a swap it
proposes the matching stat record (heuristic: the ship word shared by `Rus_Basilisk.SHP` and
`Ussr Basilisk`), shows the slot's record and the flown ship's record side by side, and offers
*flight stats only* (the fifteen floats; default) or *whole record* (the undecoded 0x7C–0x160 tail
too; labelled as unverified). It writes a new `shipstats.bin` next to the new `resource.hog`, and
updates the `Tiger …` twin record found by name.

### 3.6 Failure and the missing install

- **No install chosen.** DOCTOR shows only the picker and a one-line explanation. Sections that
  need the install (Doctor fixes, Controller, Boot Videos, wizard source) show a disabled body with
  a single "set install folder" button. Sections that work on any file keep working.
- **Install chosen but incomplete.** Missing files are `absent` rows, never errors. A SafeDisc
  loader is named as such with the guide's scope note; no fix is offered for it, ever.
- **Read-only install (Program Files, admin-owned).** `scan` tests writability by creating and
  removing a temp file. Every in-place fix is disabled with the reason and a "stage a copy instead"
  link to the wizard. The friendly permission dialog moves into core's `FixResult` so it actually
  fires.
- **Frozen build without the optional bundles.** `install_shim` reports "not bundled in this
  build" with the `build.bat` note; `blank_logos` says which replacement bytes it will use
  (bundled clip or the generated stub), as today.
- **Corrupt or foreign files.** `shp_parse.SHPError`, `dte_parse.DTEError` and `ValueError` from the
  HOG parser are caught in core and shown as one red line; the section stays usable.
- **Long operations.** Decode of the largest model is ~115 ms and of a mission ~40 ms *(measured)*,
  so open-file is instant enough, but everything still runs through `run_async` because a 57 MB
  archive rebuild and a folder copy are not.

### 3.7 What is testable without the game

| Layer | How | Where it runs |
|---|---|---|
| `Install`, `doctor`, every `Fix`, both pipelines | Synthetic install in a temp dir: `tests/sl_patch_selftest.build_synth_exe()` for the exe (it already plants the real hook fingerprints), `BIK`-headed stub clips, a stub `dinput.dll` and `DDraw.dll` built as minimal PE32 images (x86 and one x64 to test the bitness check), a sample `dgVoodoo.conf` text, a `FakeEnv` with canned registry and system-file answers | Linux and Windows CI |
| `HogSession` | `hog_pack.build` round trips, duplicate names, index addressing, save-as never in place | CI |
| `MissionDoc` | A **synthetic `.dte` builder** (to add to `dte_parse`): 27-entry directory, string pool, a few ship records, RefPack literal wrapper for the "from HOG" path; assert decode → edit → write → decode equality and that untouched bytes are identical | CI |
| `slstudio_view3d` pure functions | `shp_parse.build_synthetic()` → assemble / project / sort; known coordinates | CI (no display) |
| GUI | `--selftest` screenshots per section (Pillow, Windows); a new `--smoke` that constructs every section and drives one fake action each without a game folder | Windows, optional |
| The game | Never | — |

`tests/run_all.py` gains "studio core self-test" and "view3d self-test". The Studio's Linux story
becomes: the core and the CLI are tested there; the shell is best-effort.

### 3.8 Degrading when something is absent

| Absent | Behaviour |
|---|---|
| `customtkinter` | Print the install hint, then **offer the stdlib fallback** (`slstudio.py`) instead of exiting; never a modal dialog when `sys.stdin` is not a TTY (the CI case) |
| `tkinter` | Core and CLI keep working; `slstudio_core.py doctor` prints the same checklist as text |
| Pillow | Screenshots skipped, as today |
| Not Windows | Registry and DirectPlay checks report `skip`; titlebar theming and DWM calls are no-ops; wizard and archive work are unaffected |
| Bundled shim / blank clip in the frozen exe | Already handled; keep the messages |
| `dgVoodoo.conf` keys missing or a newer layout | The vsync/resolution fix edits **only keys that already exist** in the parsed file and otherwise says "open dgVoodooCpl.exe yourself" (the app never runs it) |

---

## 4. The top items in detail

### 4.1 Core split (#1, #3, #10, #11)

Behaviour-identical refactor. Move `Prefs`, `GameContext` (→ `Install`/`scan`), the three probes,
`_blank_bytes`/`_find_blank_bik`, the shim install/uninstall bodies, both pipelines and the backup
scanner into `slstudio_core.py`; leave the widgets where they are and have them call core. Generate
the fix rows from `sl_patch.REGISTRY`. Fix the two bugs (permission dialog; manifest on restore) in
core where they belong. Add `installs[]` to prefs with a picker in the top bar. Add the synthetic
self-test and wire it into `run_all.py`. Ship as **v1.2** with no visible change except the picker.

### 4.2 Install Doctor (#2)

Checks and the evidence behind each (this is where honesty matters most, because none of it has
been run in-game by this project):

| Check | Method | Evidence | Fix offered |
|---|---|---|---|
| Exe kind | size + `sl_patch` site bytes; `pe_inspect` SafeDisc markers (`BoG_` signature, `secdrv`) for the loader | verified static | patch (in place with `.bak`), or none for a loader |
| Wrapper present and 32-bit | `DDraw.dll` / `D3DImm.dll` / `ddraw.dll`; `pe_inspect` Machine == 0x14C | verified static | none (third-party); says which file is wrong |
| Wrapper vsync | `dgVoodoo.conf` `[DirectX] ForceVerticalSync` (present in the sample conf, version 0x287; `[Glide]` repeats the key so the edit is section-scoped) | verified on one conf version | set `false`, `.orig` kept |
| Wrapper resolution | `[DirectX] Resolution` | same | set `WxH` to match the widescreen patch, or leave `unforced` |
| Compatibility layer | `HKCU\...\AppCompatFlags\Layers\<exe path>` | readable without elevation *(measured on Windows 11)* | write `~ WINXPSP3` / `RUNASADMIN` on request; undo removes the value |
| `[Device]` reset | `starlancer.ini` may not exist before first run | verified from the guide | clear the section, `.orig` kept |
| DirectPlay | `SysWOW64\dplayx.dll` + `dpwsockx.dll` present | **heuristic**: present here with the feature state unknown, because the feature query needs elevation; never tested on a machine with the feature off | none; shows the Control Panel path |
| Audio | `mss32.dll` exports `_AIL_*` (needs an export walker added to `pe_inspect`); `dsound.dll` present | verified static | none |
| Shim, logos | today's probes | verified static | today's fixes |
| Loose missions | `missions\*.dte` present (the retail install ships 18 and 25 loose) | verified on the owner's install | none; informational |
| Permissions | temp-file write test; path under Program Files | verified | route to the wizard |

Every heuristic row carries the tag in the UI. Every fix preview names the exact file, key or
registry value. The "in-game verification is yours" line stays on every fix.

### 4.3 Switcher carries stats (#4)

`slswitch.swap_models` already returns the changed model names. Add `slstats.copy_stats(data,
src_idx, dst_idx, fields_only=True)` and a `find_twin(data, name)` that looks for `"Tiger " + name`.
The model↔record mapping is a heuristic (shared ship word); the GUI shows the proposal and asks.
Default copies the fifteen floats only; the whole-record option is labelled as touching undecoded
bytes. Output is a new `shipstats.bin` beside the new archive; the wizard learns to carry both.

### 4.4 Model Viewer (#5)

*Measured* on synthetic meshes with a plain `tk.Canvas` (600×600, flat-shaded filled polygons with
back-face culling and a painter's sort; and wireframe with every edge as a line item):

| Triangles | Shaded ms/frame | Wire ms/frame |
|--:|--:|--:|
| 1,920 | 14 | 64 |
| 4,800 | 44 | 151 |
| 12,000 | 105 | 493 |

*Measured* LOD-0 sizes of real models, read in memory from `resource.hog`: Predator 471 triangles
(3 parts), Naginata 400, Wolverine 760, Reaper 815; the largest shipped models are `stalag` 2,711
(14 parts), Badanov / Krasny 2,390, Rogue base 1,920 (23 parts). Decode times 17–115 ms.

So every ship in the game renders flat-shaded at interactive rates on a stdlib Canvas, fighters at
roughly 5–15 ms a frame and the biggest stations at 30–40 ms, with no OpenGL and no new dependency.
Wireframe is the slow mode and becomes the toggle, not the default. Coarser LODs exist in the files
and can be used while dragging. The pure-Python transform is under 3 ms for 6,000 vertices, so the
cost is Tk item creation, which is why polygons beat lines.

Design: `assemble(model, lod)` walks the parent chain applying part position (verified) and the
part matrix at `+0xA4` (inferred; the viewer says "assembly approximate"); a *mirror X* toggle
covers the unknown handedness; fans and strips are drawn per record because each record is a full
triangle. Attachment markers use the verified types only; inferred types are drawn grey with a
question mark. OBJ export calls `shp_parse.cmd_obj`.

### 4.5 HOG Workbench (#6)

A `HogSession` holds `[(name, bytes)]` exactly as `hog_pack.read_entries` returns it (57 MB in
memory; the rebuild on save doubles that briefly, which is fine). Entries are addressed by index so
the five duplicated names in `resource.hog` cannot be mis-targeted. Preview routing is a dispatch on
extension to the same decoders the sections use. Saving never targets the opened path.

### 4.6 Mission Inspector and placement editor (#7, #8)

Read side is presentation over `dte_parse.Mission`. Two additions to `dte_parse`: read the
**authored** position at `+0x1C` alongside the runtime copy at `+0x08` (the doc records the load-time
mirror), and a synthetic mission builder for tests.

Write side, the key fact *(verified in this session)*: **loose `missions\*.dte` files are raw
decompressed images.** The mission read routine's loose-file branch (`FUN_0045a300` →
`FUN_0045a3e0`) does a plain `fread` plus an appended `0x1A` byte and never decompresses; the retail
install's own `missions\mission18.dte` and `mission25.dte` are 850,919-byte images that begin with
the 27-entry directory, not with the RefPack signature (and differ slightly from their HOG copies,
so they are a shipped later revision). For missions the loose file wins over the HOG copy, as
`docs/dte-format.md` §2 records. The general HOG read layer (`FUN_004c8110`, used for models)
decompresses only when an entry starts `10 FB` and otherwise reads it verbatim, and there the
archive wins: a loose file is consulted only when the name is absent from the HOG's table.
Consequences:

- A placement editor needs **no RefPack encoder**: modify the image in place (fixed layout, no
  offsets move) and write it loose. `docs/dte-format.md` §11 currently lists the encoder as a
  prerequisite; that item can be retired for the loose path.
- The loader's read buffer is 0xFA000 bytes; every shipped image is far inside it.
- Even the compressed route is safe if ever wanted: a literal-only RefPack wrapper round-trips all
  44 missions through the project decoder and respects the engine's in-place expansion margin
  (buffer = image + 0x2800, packed stream placed at the end; tightest margin 2,636 bytes at
  `mission1`; the bound is roughly a 1.1 MB image) *(measured)*.

v1 of the editor writes position (both authored and runtime copies, so it does not depend on the
mirror), the three whole-degree angles and, behind an *advanced* toggle, the IFF byte. It never
touches names, types, model indices, triggers or the script. The section is labelled experimental
because nothing here can be validated without running the game; the precedent that the approach
works is Starlancer ME's editor, which writes the same records.

---

## 5. Deliberately not building

| Idea | Why not |
|---|---|
| **A launch / "Play" button, or anything that runs `Lancer.exe`, `dgVoodooCpl.exe` or an installer** | Project boundary. Not negotiable, not revisited. |
| **Video or audio playback, thumbnails, waveform views** | Needs Bink and Miles decoders (third-party binaries the repo never ships); not the niche; and media handling is a line this project keeps well clear of. |
| **Texture / sprite viewer** (`.tga` non-standard variant, `.spr`) | Undocumented formats; the model viewer stays untextured (flat-shaded) until someone specifies them. |
| **Save-game and pilot editors** (`*.IFF`, `pilotstats.bin`, `.fm8`) | Formats not reverse-engineered here; StarLancEdit and the Twister editor exist. |
| **A trigger / script editor** | The VM's per-byte yield map, four populated-but-undecoded sections and the string pool relocation make script authoring a research project, and nothing validates it short of running the game. |
| **Custom ship import (`.SHP` writer)** | Exporter-side fields the engine never reads, five attachment types without a located consumer, `.SPR` texture packs unknown. A writer would be unverifiable. |
| **Downloading or updating wrappers, SafeDiscShim, DSOAL** | The project bundles no third-party binaries; fetching them adds a supply-chain surface to a tool that patches executables. The Doctor shows the URL as text. |
| **Any SafeDisc handling** | Out of scope by policy; the Doctor names the loader and stops. |
| **An OpenGL / moderngl / PyOpenGL viewer** | Measured unnecessary: the Canvas handles every shipped model. |
| **Migrating the shell (Qt, web, Electron)** | The shell is not the problem; the missing core is. |
| **Plugin system, localisation, auto-update** | No user pull; cost without value at this size. |
| **Widescreen menus, HUD-widget reposition, shim rumble** | These are RE and C work tracked elsewhere. Studio's job is to surface them automatically when they land, which the registry-driven fix list guarantees. |

---

## 6. Risks that could sink each item

| Item | Risk | Mitigation |
|---|---|---|
| Core split | Behaviour drift in the in-place fixes during the move | Byte-level tests on the synthetic install before and after; a before/after run on a throwaway copy of an exe (as v1.1 did), never the game; keep the shell untouched in that stage |
| Doctor | False confidence from heuristics (DirectPlay); a wrapper renamed or a future `dgVoodoo.conf` layout; registry edits surprising users | `heuristic` tag on the row; edit only existing conf keys, otherwise defer to the CPL; registry writes limited to HKCU `Layers` with a visible undo; preview before every fix |
| Doctor | Advice that sounds authoritative for things this project has never run | The "in-game verification is yours" line on every fix; wording taken from the guide, which is already marked untested by us |
| Switcher stats | Wrong record chosen by the name heuristic; copying the undecoded tail moves hardpoint data | Confirmation with both records shown; floats-only default; whole-record labelled unverified |
| Model viewer | Handedness and the part matrix are inferred; concave parts show painter's-sort artefacts | Mirror toggle; "assembly approximate" note; artefacts are acceptable for inspection, and the OBJ export is exact |
| HOG Workbench | 57 MB sessions and accidental in-place saves | Index addressing; save-as only; dirty flag; the same byte-exact writer |
| Mission inspector | Sections 9/12/23/24 undecoded; the runtime/authored position pair confusing | Show undecoded sections as hex; show the authored fields and say why |
| Placement editor | In-game breakage no one here can test; overwriting the retail loose overrides for 18 and 25 | Experimental label; back up an existing loose file; edit only pose and IFF; keep the HOG copy untouched so removal of the loose file restores stock |
| All new sections | Scope creep back into a monolith | The rule in §3.1: disk I/O only in core; a section that grows a file open of its own fails review |

---

## 7. Staged delivery (each stage leaves a working, releasable app)

| Stage | Contents | Release |
|---|---|---|
| **0 — Hygiene** (S) | Fix the permission-dialog and manifest-on-restore bugs; Patcher seeds from the install; fix rows from `sl_patch.REGISTRY`; missing-dependency path no longer modal when not interactive | v1.2 |
| **1 — Core split** (M) | `slstudio_core.py` with `Install`, fixes, pipelines, prefs, install profiles, self-test in `run_all.py`; sections call core; behaviour identical | v1.3 |
| **2 — Install Doctor** (M) | Checklist, evidence tags, wrapper bitness, `dgVoodoo.conf` vsync/resolution, `[Device]` reset, compatibility layer, DirectPlay heuristic, loader detection, permissions routing; wizard validates drop-ins and writes the Doctor report into `READ-ME-RUN-ME.txt` | **v2.0** |
| **3 — Ships** (S–M) | Switcher carries stats; Stats v2 (search, all fields with help, compare, copy, CSV) | v2.1 |
| **4 — Models + Archives** (M+M) | `slstudio_view3d.py`, MODELS section, ARCHIVES workbench with preview routing; the legacy GUI gains the viewer | v2.2 |
| **5 — Missions** (S–M, then S) | Inspector first; the placement editor behind an experimental label one release later, with the synthetic `.dte` builder in the tests | v2.3, v2.4 |

Stages 3, 4 and 5 are independent of each other and can be reordered by demand; 0 → 1 → 2 is the
spine. Each stage updates `README.md`, `docs/running-on-modern-windows.md` and the release notes.

---

## 8. What was verified, and what was assumed

**Read from the code (this session):** everything in §1; the `run_async`/`run_steps` contract; the
three probes; the five hard-coded fix sites; the duplicated pipelines; the absence of launch
primitives; the two bugs.

**Measured (throwaway scripts in the session scratchpad, nothing committed, no game bytes copied
anywhere):**

- Tk Canvas benchmark on synthetic spheres (table in §4.4).
- Real-data decode timings, read in memory from the owner's `resource.hog` and the 44 HOG-extracted
  missions: `.dte` RefPack decode 20–41 ms (median 38); `.shp` decode 17–115 ms (largest `stalag`,
  of which 62 ms is RefPack); `hog_pack.read_entries` on the 57 MB archive 0.03 s (file cached).
- Literal-only RefPack round trip for all 44 missions plus a simulation of the engine's in-place
  expansion; all safe, tightest margin 2,636 bytes.
- The loose-mission finding: the loader's loose branch in the decompiled export, and the bytes of
  the retail loose `mission18.dte` versus its HOG copy.
- `dgVoodoo.conf` sample (version 0x287): `ForceVerticalSync`, `Resolution`, `ScalingMode`,
  `KeepWindowAspectRatio` keys; `[Glide]` and `[DirectX]` both carry `ForceVerticalSync`.
- Windows 11 probes: `SysWOW64\dplayx.dll` and `dpwsockx.dll` present, `System32` copy absent; the
  optional-feature query requires elevation; the HKCU `AppCompatFlags\Layers` key is readable
  without it.
- The missing-`customtkinter` import path blocks on a modal dialog.

**Assumed (not tested):**

- `customtkinter` and the shell behave on Linux with `python3-tk` (the CI story above does not
  depend on it).
- The DirectPlay DLL-presence heuristic on a machine where the feature is *off*.
- `dgVoodoo.conf` key names on versions other than 0x287.
- The `Tiger …` stat twin can always be found by name.
- The part matrix at `+0xA4` is the part's local rotation for assembly (documented as inferred).
- That the game accepts a raw (non-RefPack) HOG entry and a modified loose mission in practice: the
  code paths say yes; nothing here runs the game to confirm, and nothing will.

## Related

[`running-on-modern-windows.md`](running-on-modern-windows.md) · [`modern-fixes.md`](modern-fixes.md) ·
[`shp-format.md`](shp-format.md) · [`dte-format.md`](dte-format.md) · [`campaign-flow.md`](campaign-flow.md) ·
[`hog-format.md`](hog-format.md) · [`stats-format.md`](stats-format.md) · `tools/slstudio_app.py`
