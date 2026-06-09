# Security & data-integrity policy

Starlancer-OSS is a set of **reverse-engineering tools and documentation**. It ships no networked
service or security-critical runtime, so "security" here is mostly about **protecting the project's
copyright boundary** — the guarantee that no game binaries or assets ever enter the repository.

## What to report

Please report privately if you find:

- a way to **bypass the game-data guard** (`tools/check_no_game_data.py`, `.githooks/pre-commit`, or
  the CI workflow) so that copyrighted game data could be committed without being caught;
- game data, a decrypted/derivative binary, or a copyrighted asset that has **already** been
  committed (so it can be purged from history);
- a genuine flaw in one of the tools (for example, a path-traversal in archive extraction that could
  write outside the target directory).

Out of scope: the game's own copy protection, and anything that requires the game to be run.

## How to report

Use **GitHub's private vulnerability reporting** on this repository (the *Security* tab → "Report a
vulnerability") if it's available, or contact the maintainer
**[@LordBlacksun](https://github.com/LordBlacksun)** privately. Please **don't** open a public issue
for an unpatched guard bypass, and **never attach game data** to a report. We'll acknowledge and work
a fix as quickly as we reasonably can.

<!-- Maintainer: you may add a dedicated security contact email here. -->
