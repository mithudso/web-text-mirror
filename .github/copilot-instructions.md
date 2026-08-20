# Copilot Instructions

## Default Execution Strategy

**Always apply these rules to every task without being asked:**
- **Parallelism first:** decompose every multi-part task into independent subtasks.
  Launch independent subtasks as parallel background agents simultaneously using the
  task tool. Only serialize where a later step genuinely depends on a prior result.
  Prefer 3–6 focused parallel agents over one large sequential one. Each agent must
  receive complete, self-contained context.
- **No truncation, ever:** never use `// ... rest of file` or any placeholder.
  If a file would exceed ~300 lines, split into numbered batches and auto-continue
  without waiting for user input.
- **Auto-continue:** never stop mid-task asking the user to say "continue".
- **Completion summary:** after all work is done, output a table of every file
  produced, its line count, and status.

## Orientation

Read in this order: `README.md` → `CLAUDE.md` → `docs/ARCHITECTURE.md` →
`docs/COMPONENTS.md` → `docs/DEVELOPMENT.md`. Security-sensitive changes:
`docs/SECURITY.md` first.

## Build, Test, and Validation Commands

- Run crawler: `python3 scripts/text_mirror.py <seed-url>`
- Serve extension API: `python3 scripts/text_mirror.py --serve`
- Tests: `python3 tests/test_text_mirror.py` (self-contained; non-zero exit on failure)
- Lint: `ruff check scripts/ tests/`
- Syntax: `python3 -m py_compile scripts/text_mirror.py`
- No build step; the Chrome extension loads unpacked from `chrome-plugin/`.

## High-level Architecture

- Single Python process: BFS crawler (`crawl()`), trafilatura extraction, incremental
  Markdown append, atomic per-host JSON state.
- `--serve`: `ThreadingHTTPServer` on 127.0.0.1:8765 → `/save`, `/crawl`, `/stop`,
  `/list`; Chrome side panel (`chrome-plugin/sidepanel.js`) is the client and polls
  `/list` every second.
- Concurrency: 10-worker `ThreadPoolExecutor` per crawl, global rate limiter,
  module-level locks around shared state.

## Key Conventions

- Keep the crawler a single file; keep politeness rails (robots, rate limit,
  public-only skip lists) intact.
- Server invariants: 127.0.0.1 bind, `_origin_ok` allowlist, `client_out_file`
  filename confinement — treat changes as security reviews.
- Guard all shared mutable state with the existing locks; state writes stay atomic
  (`os.replace`).
- CLI surface changes must update `SKILL.md`, `README.md`, and `docs/` in the same PR.
- Tests never touch the public internet.
