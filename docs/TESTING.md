# Testing

## Strategy

One self-contained harness (`tests/test_text_mirror.py`) covering two layers:

- **Unit** — pure helpers with security or correctness weight: `norm_host`,
  `wanted`, `client_out_file` (traversal/dir-collision/null-byte containment),
  `get_state_file` (per-host keying), `_origin_ok` (allowlist incl. `null`-origin
  rejection).
- **Functional** — a real two-page crawl against a throwaway localhost
  `ThreadingHTTPServer`: asserts page count, output `URL:` blocks, and crawl-state
  flags; plus a crash-path regression (a raising crawl must reset `CRAWL_ACTIVE`).

No mocking framework: the "mock" is an actual local HTTP server. **Nothing in the
suite touches the public internet** — keep it that way.

## Running

```bash
python3 tests/test_text_mirror.py     # needs trafilatura+lxml importable
```

Prints one `PASS`/`FAIL` line per check; exits non-zero listing failures. CI runs it
on Python 3.11 and 3.13.

## Writing a new test

Add a `check("name", condition)` call near its subject area. Functional additions
should extend the `PAGES` dict served by the embedded server. Import the module via
its file path (see harness header) — the script self-bootstraps deps at import, so
run inside an env where trafilatura is already present to avoid pip side effects.

## Coverage target

Meaningful coverage of important and changed/risky paths with real behavioral
assertions — not a blanket line percentage. Concretely: every security invariant
(`_origin_ok`, `client_out_file`, bind address), every crawl-lifecycle transition
(start/cancel/crash/resume), and any changed code path must have a check that would
fail if the behavior regressed. Assertion-free "coverage" does not count. There is
currently **no numeric coverage gate** in CI; the gate is the harness passing.

## CI gates (must pass before merge)

1. `python -m py_compile scripts/text_mirror.py`
2. `ruff check scripts/ tests/`
3. `python tests/test_text_mirror.py`

## Known limitations

- The HTTP handlers are exercised only via unit checks on their helpers, not
  end-to-end (`/save`/`/crawl` over a live socket) — a live-API test would be the
  highest-value addition.
- No pytest integration (single-script harness); porting would enable single-test
  selection and fixtures.
- robots.txt behavior is covered by the fail-open unit path only; no fixture server
  serving actual robots.txt variants.
