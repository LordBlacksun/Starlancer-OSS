# Starlancer Open-Source Project

Open-source reverse-engineering tools and documentation for **Starlancer**
(Digital Anvil / Microsoft, 2000) — the space-combat flight sim.

> ⚖️ **You must own a legal copy of Starlancer to use these tools with the game.**
> This repository contains **only original code and documentation** — no game
> binaries, assets, or other copyrighted material, and none should ever be committed
> here (see `.gitignore`).

## Documentation

| Path | Description |
|------|-------------|
| [`docs/hog-format.md`](docs/hog-format.md) | `.HOG` archive format (Electronic Arts `BIGF`). |
| [`docs/stats-format.md`](docs/stats-format.md) | `SHIP/GUN/MISSILESTATS.BIN` — 352-byte stat record layout. |
| [`docs/dte-format.md`](docs/dte-format.md) | `.DTE` mission format: **RefPack** container, trigger system, scripting VM. |
| [`docs/dte-scripting-reference.md`](docs/dte-scripting-reference.md) | Complete trigger / Executor-command / AI-code / opcode tables. |
| [`docs/campaign-flow.md`](docs/campaign-flow.md) | Campaign mission flow: progression rule, in-game↔`.dte` numbering, the 24-mission map. |
| [`docs/engine-map.md`](docs/engine-map.md) | Engine architecture: middleware stack + per-subsystem address map. |
| [`docs/modding-scene.md`](docs/modding-scene.md) | Community modding tools, the widescreen gap, and DRM notes. |
| [`docs/modern-fixes.md`](docs/modern-fixes.md) | Modern-Windows fix catalogue (boot-video skip, wrappers, widescreen, DRM, audio …) — RE-backed. |
| [`docs/game-reference/`](docs/game-reference/) | **Game content reference** — ships, fighters, characters, the full campaign, factions and weapons. Compiled from the [Starlancer Fandom Wiki](https://starlancer.fandom.com/) (CC BY-SA 3.0) and cross-checked against our RE. |

See also the [project wiki](https://github.com/LordBlacksun/Starlancer-OSS/wiki) for the engine reference.

## Tools

Dependency-free Python 3 (plus one PowerShell + Ghidra-script pair). The tools operate on
files from your own copy of the game; none contain or redistribute game data.

| Path | Description |
|------|-------------|
| [`tools/hog_extract.py`](tools/hog_extract.py) | List / extract `.HOG` archives. |
| [`tools/hog_pack.py`](tools/hog_pack.py) | Write / repack `.HOG` (BIGF) archives (byte-identical round-trip). |
| [`tools/slstats.py`](tools/slstats.py) | Ship / weapon **stat editor** (the stat `.BIN` tables). |
| [`tools/slswitch.py`](tools/slswitch.py) | **Coalition ship-switcher** (data-layer `.shp` swap in the HOG). |
| [`tools/slstudio.py`](tools/slstudio.py) | Tkinter **GUI** over the stat editor + ship switcher. |
| [`tools/dte_parse.py`](tools/dte_parse.py) | `.DTE` mission **decoder** (RefPack + 27-section directory + script disasm) + reference tables. |
| [`tools/blank_boot_videos.py`](tools/blank_boot_videos.py) | Skip the boot Bink movies by blanking them in a `.HOG` (static — never runs the game). |
| [`tools/pe_inspect.py`](tools/pe_inspect.py) | Read-only PE header / section / entropy / imports inspector. |
| [`tools/bin_explore.py`](tools/bin_explore.py) · [`tools/bin_diff.py`](tools/bin_diff.py) | Generic binary explore / diff helpers. |
| [`tools/map_engine.py`](tools/map_engine.py) | Cluster decompiled functions into subsystems (builds the engine map). |
| [`tools/ghidra_headless.ps1`](tools/ghidra_headless.ps1) + [`tools/ghidra_scripts/ExportAll.java`](tools/ghidra_scripts/ExportAll.java) | Headless Ghidra import / analyze / export automation. |
| [`tests/hog_selftest.py`](tests/hog_selftest.py) | Extractor self-test (no game files needed). |

## Quick start

```sh
python tools/hog_extract.py path/to/resource.hog            # list contents
python tools/hog_extract.py path/to/resource.hog -o out/    # extract everything
python tools/slstats.py --help                              # ship/weapon stat editor
python tools/dte_parse.py ref exec                          # print the Executor command table
python tools/dte_parse.py decode mission1.dte               # decompress (RefPack) + decode a mission
python tests/hog_selftest.py                                # run the self-test
```

## Status

Documented & tooled: the `.HOG`/BIGF archive format (extractor + packer), the ship/weapon stat
tables (editor + GUI), the Coalition ship-switcher, and the `.DTE` mission format — the **RefPack
container is decoded end-to-end** (`dte_parse.py` decodes all 44 missions: directory, ships,
triggers, and the script bytecode) plus the full scripting opcode/command reference. A
**modern-Windows fix catalogue** ([`docs/modern-fixes.md`](docs/modern-fixes.md)), fusing
community fixes with our RE, ships with a boot-video-skip tool. In progress: widescreen (Hor+)
work on the Direct3D 7 renderer, and the `.SHP` ship-model format.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The one hard rule: **never
commit game data** (binaries, assets, or decrypted/derivative game files); a `.gitignore` plus a
pre-commit guard enforce it.

## AI transparency

This project is, by design, **AI-assisted reverse engineering** — essentially all of its code and
documentation were written by Anthropic's Claude under human direction. See
[AI-TRANSPARENCY.md](AI-TRANSPARENCY.md) for the full implementation disclosure.

## Credits

- `.HOG` / `BIGF` format originally reverse-engineered by **DraconPern & KingLord** (the *SLExtract* tool).
- Mission (`.DTE`) opcode / trigger / ship-ID tables and observed in-game semantics by
  **Captain Foster / Starlancer ME** — <https://starlancerme.blogspot.com/> ·
  [@CaptainFoster](https://www.youtube.com/@CaptainFoster).
- The **game content reference** ([`docs/game-reference/`](docs/game-reference/)) — ship/weapon
  stats, the character roster, mission/campaign details, faction lore, ranks and medals — is compiled
  from the community-run **[Starlancer Wiki on Fandom](https://starlancer.fandom.com/)** and its
  contributors, used under **[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)**. Those
  reference pages are offered under the same CC BY-SA 3.0 terms; the rest of the repository remains
  GPL-3.0. With thanks to the Starlancer Wiki editors.

## License

Copyright (C) 2026 LordBlacksun.

Free software under the **GNU General Public License v3.0 only** — see [LICENSE](LICENSE). You may
use, modify, and redistribute it under those terms; derivative works must also be released under
the GPL, so improvements come back to the community.
