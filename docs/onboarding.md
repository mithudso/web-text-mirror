# Onboarding

Welcome. This repo is small on purpose: one Python file does everything, a four-file
Chrome extension drives it, one test harness guards it.

## 30-minute tour

1. **Read `README.md`** (5 min) — what the tool does and the CLI surface.
2. **Skim `docs/ARCHITECTURE.md`** (5 min) — the container diagram and the six ADRs
   explain every "why is it built this way".
3. **Run it** (5 min):
   ```bash
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   python3 scripts/text_mirror.py https://example.org/ --max-depth 1
   less text-mirror/example.org.md
   ```
4. **Run the tests** (2 min): `python3 tests/test_text_mirror.py` → `ALL PASS`.
5. **Read `scripts/text_mirror.py` top to bottom** (10 min, ~670 lines). Reading
   order: constants/locks → helpers (`norm_host`, `wanted`, `get_robots`) →
   `client_out_file`/`_origin_ok` (security) → `crawl`/`_crawl_impl` →
   `PluginServerHandler` → `main`.
6. **Try the extension** (3 min): `python3 scripts/text_mirror.py --serve`, then
   `chrome://extensions` → Load unpacked → `chrome-plugin/`.

## The three rules you must not break

1. Politeness rails (robots.txt, rate limiter, public-only skip lists) stay on.
2. Local-API security invariants (127.0.0.1, `_origin_ok`, `client_out_file`) stay on.
3. Tests never touch the public internet.

Everything else: `CLAUDE.md` → Key conventions, and `CONTRIBUTING.md` for the PR
gates.
