# AI Transparency & Full Implementation Disclosure

This document is an honest, complete disclosure of how this project was built.

## Summary

**Essentially all of the code and documentation in this repository was written by an AI
assistant — Anthropic's Claude (the Opus and Fable model families, primarily via Claude Code) — working
under the direction and review of the repository owner, LordBlacksun.** This is, by design, an experiment in
AI-assisted reverse engineering, published in that spirit. We state it plainly so users and
contributors can calibrate trust accordingly.

## Who did what

**Human — LordBlacksun (repository owner):**
- Owns a legal copy of Starlancer and provided the legally-owned files used for analysis.
- Set the goals, priorities, and scope; made the decisions and judgment calls.
- Directed the work, reviewed the output, ran the local tooling (e.g. Ghidra), and approved each
  commit. Responsible for what is published here.

**AI (Claude):**
- Wrote the format specifications, the Python tools, and the analysis / documentation.
- Did the static reverse-engineering reasoning — reading decompiled output, identifying structures,
  cross-referencing debug strings and imported APIs.
- Drafted the docs, the README, and the commit messages. Commits it co-authored carry a
  `Co-Authored-By: Claude …` trailer.

## Method, and what is *not* here

The reverse engineering is **static only**: it reads and disassembles a binary as data (Ghidra
decompilation of an executable derived from a legally-owned copy). Running the game is not part of
the method.

This repository contains **only original analysis, specifications, and tooling**. It contains **no
game source code, binaries, assets, disc images, or decrypted / derivative game data** — those are
excluded by [`.gitignore`](.gitignore) and a [pre-commit guard](.githooks/pre-commit), and must
never be committed (see [CONTRIBUTING.md](CONTRIBUTING.md)).

One exception is deliberate and worth naming: the mission-scripting reference and
[`dte_parse.py`](tools/dte_parse.py) quote the developers' own **command names and parameter labels**
as recovered from the executable, because a scripting interface cannot be documented without naming
its identifiers. Those are functional interface names, not game code, story text, or content.

## Accuracy & limitations

- The analyzed binary is **stripped**: function and data names are tool-generated placeholders
  (`FUN_<addr>`, `DAT_<addr>`), and stated purposes are largely **inferred** from diagnostic
  strings and imported APIs. The docs mark claims **[verified]** (read in code) vs **[inferred]**
  where it matters.
- AI-generated reverse engineering can contain mistakes, mis-attributions, and over-confident
  inferences. **Treat specifics as well-evidenced hypotheses, not gospel** — verify against the
  decompilation before relying on them for patches.
- Addresses are specific to the analyzed build (ImageBase `0x400000`).

## Third-party research (neither AI nor ours)

Some knowledge here was reverse-engineered by other people and is used **with credit**:

- The `.HOG` / `BIGF` archive format — **DraconPern & KingLord** (the *SLExtract* tool).
- The `.DTE` mission opcode / trigger / ship-ID tables and observed in-game semantics —
  **Captain Foster / "Starlancer ME"** (<https://starlancerme.blogspot.com/>,
  [@CaptainFoster](https://www.youtube.com/@CaptainFoster)). The documentation fuses our static
  analysis with their black-box research and notes which side each fact comes from.

## Why disclose this

Transparency about AI authorship lets people calibrate trust, reproduce or challenge the findings,
and properly credit the humans whose prior work made it possible. If you build on this work, please
carry the same disclosure forward.
