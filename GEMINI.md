# GEMINI.md

Gemini CLI instructions for this repo. Canonical conventions live in `CLAUDE.md` —
follow its **Key conventions** and **Commands** sections verbatim.

Quick facts:
- Python CLI crawler (`scripts/text_mirror.py`) + Chrome MV3 side-panel extension
  (`chrome-plugin/`). No build step.
- Tests: `python3 tests/test_text_mirror.py` (self-contained, no external network).
- Lint: `ruff check scripts/ tests/`.
- Security invariants (127.0.0.1 bind, Origin allowlist, output-filename confinement)
  must not be weakened — see `docs/SECURITY.md`.
