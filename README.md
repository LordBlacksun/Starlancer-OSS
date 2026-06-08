# Starlancer Open-Source Project

Open-source reverse-engineering tools and documentation for **Starlancer**
(Digital Anvil / Microsoft, 2000) — the space-combat flight sim.

> ⚖️ **You must own a legal copy of Starlancer to use these tools with the game.**
> This repository contains **only original code and documentation** — no game
> binaries, assets, or other copyrighted material, and none should ever be committed
> here (see `.gitignore`).

## What's here

| Path | Description |
|------|-------------|
| [`docs/hog-format.md`](docs/hog-format.md) | Full spec of Starlancer's `.HOG` archive format (Electronic Arts `BIGF`), reverse-engineered from SLExtract's source. |
| [`tools/hog_extract.py`](tools/hog_extract.py) | Modern, dependency-free Python 3 lister/extractor for `.HOG` archives. |
| [`tests/hog_selftest.py`](tests/hog_selftest.py) | Validates the extractor against a synthetic archive (no game files needed). |

## Quick start

```sh
python tools/hog_extract.py path/to/cd1.hog            # list contents
python tools/hog_extract.py path/to/cd1.hog -o out/    # extract everything
python tests/hog_selftest.py                           # run the self-test
```

## Status

Early days. Done: `.HOG`/BIGF archive format documented and a working extractor.
Planned: `.SHP` ship-model format, mission (`.DTE`) format, and modern-Windows
compatibility work (the original game uses Direct3D 7 + SafeDisc v1).

## Credits

- `.HOG` / `BIGF` format originally reverse-engineered by **DraconPern & KingLord** (the *SLExtract* tool).
- Mission (`.DTE`) format research by the author of the **Starlancer ME** blog — <https://starlancerme.blogspot.com/>.

## License

[MIT](LICENSE).
