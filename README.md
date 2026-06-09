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
| [`docs/dte-format.md`](docs/dte-format.md) | `.DTE` mission format: file container, trigger system, scripting VM. |
| [`docs/dte-scripting-reference.md`](docs/dte-scripting-reference.md) | Complete trigger / Executor-command / AI-code / opcode tables. |
| [`docs/engine-map.md`](docs/engine-map.md) | Engine architecture: middleware stack + per-subsystem address map. |
| [`docs/modding-scene.md`](docs/modding-scene.md) | Community modding tools, the widescreen gap, and DRM notes. |

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
| [`tools/dte_parse.py`](tools/dte_parse.py) | `.DTE` mission reference tables + read-only inspector. |
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
python tests/hog_selftest.py                                # run the self-test
```

## Status

Documented & tooled: the `.HOG`/BIGF archive format (extractor + packer), the ship/weapon stat
tables (editor + GUI), the Coalition ship-switcher, and the `.DTE` mission format (container +
trigger VM + the full scripting opcode/command reference). In progress: modern-Windows /
widescreen (Hor+) work on the Direct3D 7 renderer, and the `.SHP` ship-model format.

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

## License

[MIT](LICENSE).
