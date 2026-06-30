# Starlancer Open-Source Project

[![CI](https://github.com/LordBlacksun/Starlancer-OSS/actions/workflows/ci.yml/badge.svg)](https://github.com/LordBlacksun/Starlancer-OSS/actions/workflows/ci.yml)

Open-source reverse-engineering tools and documentation for **Starlancer**
(Digital Anvil / Microsoft, 2000) — the space-combat flight sim.

> ⚖️ **You must own a legal copy of Starlancer to use these tools with the game.**
> This repository contains **only original code and documentation** — no game
> binaries, assets, or other copyrighted material, and none should ever be committed
> here (see `.gitignore`).

## Starlancer Studio — the all-in-one app

**[⬇ Download `StarlancerStudio.exe`](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)** · Windows, no install · verify with [`SHA256SUMS.txt`](https://github.com/LordBlacksun/Starlancer-OSS/releases/tag/studio-v1.1)

[`tools/slstudio_app.py`](tools/slstudio_app.py) is a single desktop app (and a one-file `.exe`) that
fronts the whole toolchain in a dark "Alliance Naval Command" cockpit — **eight sections**:

- **Dashboard** — at-a-glance status of your install (the three EXE fixes, controller shim, boot logos),
  a one-click **Apply Recommended Fixes**, and a backup / restore manager.
- **Patcher** — widescreen Hor+ and the RE'd crash fixes, per-fix verify / revert.
- **Ship Switcher**, **Stats Editor**, **HOG Tools** — the editors, in a GUI.
- **Controller Shim** — install the XInput → DirectInput proxy for modern pads.
- **Boot Videos** — blank the startup branding logos.
- **Ready-to-Play** — a wizard that stages a complete, patched, ready-to-run copy into an output folder.

Like every tool here it is **static — it reads and patches local copies only and never launches the
game.** The only third-party runtime dependency (`customtkinter`) is bundled. *As a one-file PyInstaller
build, some antivirus heuristics may flag it — a common false positive; the full source is in this repo,
and the release ships a `SHA256SUMS.txt` to verify your download.*

## Documentation

**Formats & archives**
| Path | Description |
|------|-------------|
| [`docs/hog-format.md`](docs/hog-format.md) | `.HOG` archive format (Electronic Arts `BIGF`). |
| [`docs/stats-format.md`](docs/stats-format.md) | `SHIP/GUN/MISSILESTATS.BIN` — 352-byte stat record layout. |

**Missions & campaign**
| Path | Description |
|------|-------------|
| [`docs/dte-format.md`](docs/dte-format.md) | `.DTE` mission format: **RefPack** container, trigger system, scripting VM. |
| [`docs/dte-scripting-reference.md`](docs/dte-scripting-reference.md) | Complete trigger / Executor-command / AI-code / opcode tables. |
| [`docs/campaign-flow.md`](docs/campaign-flow.md) | Campaign mission flow: progression rule, in-game↔`.dte` numbering, the 24-mission map. |

**Engine & modern systems**
| Path | Description |
|------|-------------|
| [`docs/engine-map.md`](docs/engine-map.md) | Engine architecture: middleware stack + per-subsystem address map. |
| [`docs/modern-fixes.md`](docs/modern-fixes.md) | Modern-Windows fix catalogue (boot-video skip, wrappers, **native Hor+ widescreen**, DRM, audio …) — RE-backed. |
| [`docs/running-on-modern-windows.md`](docs/running-on-modern-windows.md) | **Setup checklist & folder layout** — ordered, end-to-end guide to running your owned copy on Win10/11 (DRM, wrappers, our patches, controller, DirectPlay) + troubleshooting map. |
| [`docs/modding-scene.md`](docs/modding-scene.md) | Community modding tools, the widescreen gap, and DRM notes. |

**Game content reference**
| Path | Description |
|------|-------------|
| [`docs/game-reference/`](docs/game-reference/) | Ships, fighters, characters, the full campaign, factions and weapons. Compiled from the [Starlancer Fandom Wiki](https://starlancer.fandom.com/) (CC BY-SA 3.0) and cross-checked against our RE. |

See also the [project wiki](https://github.com/LordBlacksun/Starlancer-OSS/wiki) for the engine reference.

## Tools

Dependency-free Python 3 (plus one PowerShell + Ghidra-script pair). The tools operate on
files from your own copy of the game; none contain or redistribute game data, and none ever
launch the game.

**Archive, formats & missions**
| Path | Description |
|------|-------------|
| [`tools/hog_extract.py`](tools/hog_extract.py) | List / extract `.HOG` archives. |
| [`tools/hog_pack.py`](tools/hog_pack.py) | Write / repack `.HOG` (BIGF) archives (byte-identical round-trip). |
| [`tools/dte_parse.py`](tools/dte_parse.py) | `.DTE` mission **decoder** (RefPack + 27-section directory + script disasm) + reference tables. |

**Editors**
| Path | Description |
|------|-------------|
| [`tools/slstats.py`](tools/slstats.py) | Ship / weapon **stat editor** (the stat `.BIN` tables). |
| [`tools/slswitch.py`](tools/slswitch.py) | **Coalition ship-switcher** (data-layer `.shp` swap in the HOG). |
| [`tools/slstudio_app.py`](tools/slstudio_app.py) | **Starlancer Studio** — the all-in-one GUI (see [above](#starlancer-studio--the-all-in-one-app)); fronts every tool. |
| [`tools/slstudio.py`](tools/slstudio.py) | Legacy 2-tab Tkinter GUI (stdlib-only fallback). |

**Modern-systems fixes** (patch a *local copy* of your own exe / `.HOG` — never the original, never run)
| Path | Description |
|------|-------------|
| [`tools/sl_patch.py`](tools/sl_patch.py) | **Modern-systems patch pack** — one declarative code-cave engine applying any subset of the static EXE fixes (`--widescreen WxH` Hor+, `--fix-medal`, `--fix-multicore`) with a sidecar manifest and per-fix `--verify` / `--revert` / `--revert-only`. (`--fps` explains the cap; it's a vsync/wrapper matter, not an exe patch.) |
| [`tools/ws_patch.py`](tools/ws_patch.py) | **Deprecated alias** for `sl_patch.py --widescreen` — keeps the old `--width/--height` CLI working (byte-identical output). |
| [`tools/blank_boot_videos.py`](tools/blank_boot_videos.py) | Skip the boot Bink movies by blanking them in a `.HOG`. |
| [`tools/xinput_shim/`](tools/xinput_shim) | **XInput controller shim** — a proxy `dinput.dll` (C, 32-bit) that forwards keyboard/mouse to real DirectInput and synthesizes the joystick from XInput with **separate triggers** (no-rumble v1). Source + `build.bat` + test host. |

**Reverse-engineering & analysis**
| Path | Description |
|------|-------------|
| [`tools/pe_inspect.py`](tools/pe_inspect.py) | Read-only PE header / section / entropy / imports inspector. |
| [`tools/pe_icon.py`](tools/pe_icon.py) | Read-only PE **app-icon extractor** (rebuilds a `.ico` from `RT_GROUP_ICON`/`RT_ICON`; never executes the target). |
| [`tools/make_icon.py`](tools/make_icon.py) | Generator for Starlancer Studio's **original** app icon (PIL primitives — no game art). |
| [`tools/bin_explore.py`](tools/bin_explore.py) · [`tools/bin_diff.py`](tools/bin_diff.py) | Generic binary explore / diff helpers. |
| [`tools/map_engine.py`](tools/map_engine.py) | Cluster decompiled functions into subsystems (builds the engine map). |
| [`tools/ghidra_headless.ps1`](tools/ghidra_headless.ps1) + [`tools/ghidra_scripts/ExportAll.java`](tools/ghidra_scripts/ExportAll.java) | Headless Ghidra import / analyze / export automation. |

**Tests & guard**
| Path | Description |
|------|-------------|
| [`tools/check_no_game_data.py`](tools/check_no_game_data.py) | Game-data guard (run by the pre-commit hook and CI). |
| [`tests/run_all.py`](tests/run_all.py) | Pre-PR / CI gate — hog + sl_patch self-tests + guard (no game files needed). |
| [`tests/hog_selftest.py`](tests/hog_selftest.py) | Extractor self-test. |
| [`tests/sl_patch_selftest.py`](tests/sl_patch_selftest.py) | Patch-engine self-test (synthetic PE; apply / verify / revert / manifest / ordering). |

## Quick start

```sh
python tools/hog_extract.py path/to/resource.hog            # list contents
python tools/hog_extract.py path/to/resource.hog -o out/    # extract everything
python tools/slstats.py --help                              # ship/weapon stat editor
python tools/dte_parse.py ref exec                          # print the Executor command table
python tools/dte_parse.py decode mission1.dte               # decompress (RefPack) + decode a mission
python tools/sl_patch.py --fov-table                        # preview the Hor+ widescreen FOV per aspect
python tools/sl_patch.py --widescreen 1920x1080 in.exe out.exe      # patch a local exe copy
python tests/run_all.py                                     # run the full self-test gate
```

## Status

Documented & tooled: the `.HOG`/BIGF archive format (extractor + packer), the ship/weapon stat
tables (editor + GUI), the Coalition ship-switcher, and the `.DTE` mission format — the **RefPack
container is decoded end-to-end** (`dte_parse.py` decodes all 44 missions: directory, ships,
triggers, and the script bytecode) plus the full scripting opcode/command reference. A
**modern-Windows fix catalogue** ([`docs/modern-fixes.md`](docs/modern-fixes.md)), fusing
community fixes with our RE, ships with a boot-video-skip tool, **native Hor+ widescreen**, and the
RE'd **crash fixes** (medal-case, multi-core) — all via the [`tools/sl_patch.py`](tools/sl_patch.py)
declarative patch-pack (per-fix verify / revert), and all wrapped together with the editors and the
controller shim in the **[Starlancer Studio](#starlancer-studio--the-all-in-one-app)** app. In progress:
the `.SHP` ship-model format; the main remaining modern-systems target is the 100-FPS uncap (a vsync /
wrapper matter, not an exe patch).

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) (dev setup, commit style, and how
to submit) and our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). The one hard rule: **never commit game
data** (binaries, assets, or decrypted/derivative game files); a `.gitignore`, a pre-commit guard,
and a CI check ([`tools/check_no_game_data.py`](tools/check_no_game_data.py)) enforce it. Run
`python tests/run_all.py` before a PR. To report a guard bypass or other issue privately, see
[SECURITY.md](SECURITY.md).

## AI transparency

This project is, by design, **AI-assisted reverse engineering** — essentially all of its code and
documentation were written by Anthropic's Claude under human direction. See
[AI-TRANSPARENCY.md](AI-TRANSPARENCY.md) for the full implementation disclosure.

## Credits

This project stands on the work of the Starlancer modding community. The file formats here were
**reverse-engineered independently** (clean-room, statically); these are the people whose earlier
tools and research we build on, with thanks:

- **DraconPern & KingLord** — the `.HOG` / EA `BIGF` archive format (the *SLExtract* tool, with
  source released). Basis for [`hog_extract.py`](tools/hog_extract.py) / [`hog_pack.py`](tools/hog_pack.py).
- **Captain Foster / Starlancer ME** — `.DTE` mission opcode / trigger / ship-ID tables and observed
  in-game semantics — <https://starlancerme.blogspot.com/> ·
  [@CaptainFoster](https://www.youtube.com/@CaptainFoster). Fused into
  [`dte_parse.py`](tools/dte_parse.py) and the `.DTE` docs.
- **"Userunfriendly"** — the *hexcheat* known-delta stat pack that revealed the
  `SHIP/GUN/MISSILESTATS.BIN` field offsets — basis for [`slstats.py`](tools/slstats.py).
- **Dustin** — *SLEdit*, whose data-layer Coalition ship-switch mechanic is reimplemented by
  [`slswitch.py`](tools/slswitch.py).
- **Mario "HCl" Brito** — *SL Tool*, *LWO2SL*, and the *MilkShape* `.SHP` import/export plugins — the
  prior art for the `.SHP` 3D-model format (RE in progress).
- **Raidersoft** (*StarLancEdit*) and **Twister / Twisted Media** (*Saved Game Editor*) — the
  `MYGAME*.IFF` save and `profile.bin` formats (RE planned).
- The **game content reference** ([`docs/game-reference/`](docs/game-reference/)) is compiled from the
  community **[Starlancer Wiki on Fandom](https://starlancer.fandom.com/)** under
  **[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)** (those pages are offered under
  the same terms; the rest of the repo remains GPL-3.0). With thanks to the Starlancer Wiki editors.

Many of these tools are preserved in the
**[Starlancer-mod-tools](https://github.com/LordBlacksun/Starlancer-mod-tools)** mirror; each remains
under its original author's terms (typically freeware).

## License

Copyright (C) 2026 LordBlacksun.

Free software under the **GNU General Public License v3.0 only** — see [LICENSE](LICENSE). You may
use, modify, and redistribute it under those terms; derivative works must also be released under
the GPL, so improvements come back to the community.
