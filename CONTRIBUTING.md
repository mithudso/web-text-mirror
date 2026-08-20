# Contributing

## Setup

```bash
git clone https://github.com/mithudso/web-text-mirror.git
cd web-text-mirror
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt ruff
```

## Before you open a PR

```bash
python3 -m py_compile scripts/text_mirror.py
ruff check scripts/ tests/
python3 tests/test_text_mirror.py
```

All three must pass. CI runs the same gates on Python 3.11 and 3.13.

## Ground rules

- Read `CLAUDE.md` → **Key conventions**. In particular: the crawler stays a single
  file; politeness rails (robots.txt, rate limiter, public-only skip lists) and the
  local-API security invariants are not tunables.
- If you change the CLI surface, update `SKILL.md`, `README.md`, and the relevant
  `docs/` pages in the same PR.
- Tests must not touch the public internet — spin a localhost server like the
  existing harness does.

## Commits

Short imperative subject (≤72 chars); body explains why when non-obvious.
