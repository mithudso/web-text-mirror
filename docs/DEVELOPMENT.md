# Development

## Prerequisites

- Python ≥ 3.9 (CI runs 3.11 and 3.13; developed on 3.14)
- pip; optionally a venv
- Chrome (only for extension work)
- `ruff` for linting (`pip install ruff`)

## First-run setup

```bash
git clone https://github.com/mithudso/web-text-mirror.git
cd web-text-mirror
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt ruff
python3 tests/test_text_mirror.py   # should end with ALL PASS
```

The crawler also self-bootstraps trafilatura/lxml via pip on first run if you skip
the install step (see `ensure_deps()`); `scripts/install.sh` pre-provisions instead.

## Local workflow

```bash
# quick functional run against a small site
python3 scripts/text_mirror.py https://example.org/ --max-depth 1

# serve the extension API
python3 scripts/text_mirror.py --serve
# then: chrome://extensions → Developer mode → Load unpacked → chrome-plugin/
```

No watch mode / live reload — it's a single script; rerun it.

## Tests

```bash
python3 tests/test_text_mirror.py
```

One self-contained harness: unit checks on the pure helpers plus a functional
two-page crawl against a throwaway localhost server. Exit code 0 = pass. There is no
finer-grained runner; to iterate on one check, comment others out locally (or port
the harness to pytest — see `docs/TESTING.md` known limitations).

## Lint / syntax

```bash
ruff check scripts/ tests/
python3 -m py_compile scripts/text_mirror.py
```

## CI

`.github/workflows/ci.yml` — on every PR and push to main: syntax check, ruff, and
the test harness on Python 3.11 and 3.13.

## Branch and commit conventions

Work on feature branches; PR into `main`. Never commit crawl output (`text-mirror/`,
`crawl.log`, `*_state.json` are gitignored). Short imperative commit subjects.

## Adding a feature (walkthrough)

1. Read `CLAUDE.md` Key conventions (security invariants, single-file rule).
2. Change `scripts/text_mirror.py`; keep new shared state behind a lock.
3. Add checks to `tests/test_text_mirror.py` (localhost only).
4. Update `SKILL.md` + `README.md` + relevant docs if the CLI surface changed.
5. Run the three gates above; open a PR.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `CRAWL_DELAY` | `1.0` | Seconds between requests (CLI `--delay` overrides) |
| `MAX_DEPTH` | `0` | Depth cap in hops, 0 = unlimited (CLI `--max-depth` overrides) |
| `PYTHON` | `python3` | `scripts/install.sh` only: interpreter to provision |

## Troubleshooting

- **`[bootstrap] ERROR: could not install deps`** — pip can't install into the
  current interpreter; create a venv or run `scripts/install.sh` with `PYTHON=` set.
- **Extension shows "Error communicating with crawler"** — the API isn't running;
  start `python3 scripts/text_mirror.py --serve` (port 8765).
- **Crawl saves 0 pages** — check `crawl.log` for `robots-skip` (site disallows) vs
  `no-content` (fetch/extract failures).
- **`409 busy` from `/crawl`** — another crawl is running; `/stop` it first.
