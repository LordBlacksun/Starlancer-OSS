# Contributing to Starlancer-OSS

Thanks for your interest. This project documents and tools the data formats and engine of
**Starlancer** (2000) through original reverse engineering. Contributions — corrections, new
format findings, tools, and docs — are welcome.

## ⚖️ The one hard rule: never commit game data

This repository must contain **only original code and documentation**. **Never** add, commit, or
push any of the following:

- game binaries / libraries (`.exe`, `.dll`, `.icd`), archives (`.hog`, `.cab`), disc images
  (`.iso`, `.cue`, `.mds`, `.mdf`);
- game assets (`.shp`, `.spr`, `.tga`, `.bik`, `.wav`, `.mp3`, `.fat`, …);
- save / profile / pilot files (`.iff`, `.sav`, `.fm8`), stat tables (`*stats.bin`), `dmodes.bin`;
- any **decrypted or derivative** game data — decompiled C, a decrypted executable, Ghidra
  projects, or extracted assets.

These are excluded by [`.gitignore`](.gitignore) and rejected by the
[`.githooks/pre-commit`](.githooks/pre-commit) guard. Enable the guard once after cloning:

```sh
git config core.hooksPath .githooks
```

It is defense-in-depth — don't bypass it with `--no-verify` unless you're certain a match is a
false positive (e.g. a doc filename that merely *contains* a blocked word).

You must **own a legal copy** of Starlancer to use these tools with the game. This project does
not distribute the game, its assets, or any means of circumventing protection it may still require.

## Methodology

Reverse engineering here is **static** — read and disassemble binaries as data (Ghidra, PE
inspection); the game does not need to be run to analyze it. Document findings with:

- **addresses** as VA/RVA for ImageBase `0x400000` in the analyzed build;
- a clear **[verified] vs [inferred]** distinction — *verified* = read directly in the code,
  *inferred* = deduced from debug strings / imported APIs / struct access;
- the **evidence** behind each claim, so others can check it.

## Code style

- **Python 3, standard-library only** where possible. Match the existing files' structure and
  module docstrings.
- Tools should be **read-only by default** and must not require game data to run their self-tests.
- Keep tools small, single-purpose, and documented at the top.

## Docs style

- Markdown, one format/subsystem per file under [`docs/`](docs/); cross-reference related docs.
- Credit prior art (below).

## Credit prior art

If your finding builds on someone else's research, credit them by name and link. Current examples:
the `.HOG` format (**DraconPern & KingLord** / *SLExtract*) and the `.DTE` mission tables
(**Captain Foster** / *Starlancer ME*, <https://starlancerme.blogspot.com/>).

## AI-assisted contributions

This project is openly AI-assisted — see [AI-TRANSPARENCY.md](AI-TRANSPARENCY.md). If your
contribution was substantially AI-generated, please say so in the PR description and add a
`Co-Authored-By:` trailer for the assistant. Same spirit of disclosure either way.

## Submitting

1. Fork, branch, and open a pull request with a clear description.
2. Confirm the pre-commit guard is enabled and your diff contains **no game data**.
3. For RE findings, include your evidence so reviewers can verify against the decompilation.
