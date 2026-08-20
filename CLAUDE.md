# CLAUDE.md

## Repository shape

Single-package Python CLI + a static Chrome MV3 extension. No build step.

| Path | What it is |
|---|---|
| `scripts/text_mirror.py` | The crawler + local HTTP API (single file, stdlib + trafilatura/lxml) |
| `scripts/install.sh` | Optional pre-provisioning of trafilatura (crawler also self-bootstraps) |
| `chrome-plugin/` | Chrome side-panel extension calling `http://localhost:8765` |
| `tests/test_text_mirror.py` | Self-contained smoke/unit harness (no external network) |
| `docs/` | Full documentation suite |
| `text-mirror/` | Default output dir (gitignored) |
| `SKILL.md` | Claude-skill packaging of this tool (kept in sync with actual flags) |

## Commands

```bash
# run a crawl (deps auto-install into the current interpreter on first run)
python3 scripts/text_mirror.py <seed-url> [--out FILE] [--delay N | --req-per-sec N] [--max-depth N]

# serve the extension API only (127.0.0.1:8765)
python3 scripts/text_mirror.py --serve

# tests (needs trafilatura+lxml importable; exits non-zero on failure)
python3 tests/test_text_mirror.py

# lint + syntax
ruff check scripts/ tests/
python3 -m py_compile scripts/text_mirror.py
```

## Runtime architecture

One Python process. CLI seeds run `crawl()` in the main thread; `--serve` starts a
`ThreadingHTTPServer` daemon thread; `POST /crawl` spawns one crawl thread (single-flight
guarded); each crawl fans fetches out to a 10-worker `ThreadPoolExecutor` throttled by a
global rate limiter. Shared state (`SAVED_URLS`/`_SAVED_SET`, `CRAWL_*` flags) is guarded
by module locks. See `docs/ARCHITECTURE.md` for the diagram.

## Key conventions

1. **Single file by design** — the crawler stays one dependency-light script so the
   Claude skill can ship it verbatim. Don't split modules without strong reason.
2. **Never lift the politeness rails** — robots.txt gate, rate limiter, and the
   public-only `SKIP_SUBSTR`/`SKIP_EXT` lists are product behavior, not tunables.
3. **Server security invariants** — bind 127.0.0.1 only; Origin allowlist
   (`_origin_ok`); browser-supplied `out_file` must pass `client_out_file`
   (basename-only, no dir collisions). Changing any of these is a security review.
4. **All shared mutable state behind its lock** — `MIRROR_LOCK` for output +
   saved-URL set, `STATE_LOCK` for state files, `CRAWL_START_LOCK` for single-flight.
5. **State files are atomic** — write tmp + `os.replace`. Keep it that way.
6. **`SKILL.md` mirrors real flags** — if you change the CLI surface, update
   `SKILL.md`, `README.md`, and `docs/` in the same change.
7. **Tests are network-free** — the harness spins its own localhost HTTP server;
   never add a test that fetches the public internet.
8. **Blind `except Exception` in fetch/parse paths is intentional** (crawler
   resilience) — don't "fix" it to narrow exceptions without a failure analysis.

## MCP servers

None configured for this repo (`docs/MCP.md`).

## Workflow log rule

Append every user request to `prompts.md`
(`## Prompt vN - <ISO timestamp>` / `- User request:` / `  - <text>`), keep
`memory.md` current (active task / completed / next steps), and bump the version in
`chrome-plugin/manifest.json` when the extension changes.
