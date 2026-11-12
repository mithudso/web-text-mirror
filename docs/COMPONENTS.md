# Components

## Layer: crawler (`scripts/text_mirror.py`)

| Component | Purpose | Inputs → outputs | Notes |
|---|---|---|---|
| `ensure_deps()` | Self-bootstrap trafilatura/lxml via pip (4 escalating strategies incl. `--user`, `--break-system-packages`) | env → installed modules | Runs at import; exits on total failure |
| `log(msg)` | Timestamped stdout + append to `crawl.log` | str → side effect | `LOG_LOCK`-guarded |
| `_throttle(delay)` | Global per-request rate limiter across worker threads | delay → blocking sleep | Monotonic clock; `_RATE_LOCK` |
| `norm(url)` / `norm_host(netloc)` | URL defrag/strip; netloc normalization (case, userinfo, :80/:443) | str → str | Host comparison basis |
| `wanted(url, host)` | Same-host + scheme + skip-list filter | url, host → bool | `SKIP_EXT`, `SKIP_SUBSTR` |
| `get_robots(host, scheme)` | Fetch+parse robots.txt with timeout; fail-open on network error; 4xx → allow; 5xx → disallow | host → `RobotFileParser` | 30 s timeout |
| `links_from(html, base, host)` | Harvest same-host `<a href>` links | html → [url] | lxml; parse errors logged |
| `get_out_file` / `client_out_file` | Resolve output path; confine browser-supplied names to base dir (basename-only; rejects empty/dot/traversal/null/dir-collision) | → abs path or None | Security boundary |
| `get_state_file` / `load_state` / `save_state` / `_load_queue` | Per-host resume state, schema-tolerant load, atomic write (`os.replace`) | ↔ `<host>.<destination-key>_state.json` | `STATE_LOCK` |
| `_mark_saved` / `_is_saved` / `_saved_snapshot` / `_reset_saved` | O(1) saved-URL set + ordered list for `/list` | ↔ `SAVED_URLS`/`_SAVED_SET` | `MIRROR_LOCK` |
| `append_to_file(path, text, url)` | Append one page block (`URL:` separator) | → output .md | `MIRROR_LOCK` |
| `process_single_url(...)` | `/save` path: extract supplied DOM (or fetch) → append | url/html → bool | Same extract options as crawl |
| `fetch_and_extract(...)` | Worker: throttled fetch → extract → link harvest | url → (url, text, links, raw_html) | No-content: (u,None,None,None) |
| `crawl(...)` → `_crawl_impl(...)` | BFS engine; wrapper guarantees `CRAWL_ACTIVE` reset on any exit | seed → n pages | Single-flight with server |
| `PluginServerHandler` | HTTP API: `/save` `/crawl` `/stop` `/list` + CORS/OPTIONS | JSON ↔ JSON | `_origin_ok` gate; 400/403/409/500 semantics |
| `run_server(delay)` | `ThreadingHTTPServer` on 127.0.0.1:8765 | — | Daemon thread |
| `main()` | argparse, log setup, serve thread, seed loop w/ single-flight interlock | argv → exit | |

## Layer: extension (`chrome-plugin/`)

| File | Purpose |
|---|---|
| `manifest.json` | MV3; permissions: sidePanel, activeTab, scripting; CORS-based loopback access; no broad host permissions |
| `background.js` | Opens the side panel on toolbar click (3 lines) |
| `sidepanel.html` | Panel UI: crawl checkbox, max-depth, force-refresh, out-file, saved list |
| `sidepanel.js` | Captures tab DOM via `chrome.scripting.executeScript`, POSTs `/save` or `/crawl`, polls `/list` at 1 Hz, toggles Stop button |

## Layer: tooling

| File | Purpose |
|---|---|
| `scripts/install.sh` | Optional pre-provisioning of trafilatura (`PYTHON=` override) |
| `tests/test_text_mirror.py` | Self-contained unit + functional harness (see docs/TESTING.md) |

## Dependency graph

`sidepanel.js → localhost:8765 → PluginServerHandler → process_single_url/crawl →
{trafilatura, lxml, urllib} → target sites`. The crawler imports only stdlib +
trafilatura + lxml. The extension has no build deps.


## Offline clone utility (`scripts/site_clone.py`)

`url_to_rel_path(url, host)` maps each fragment-free URL into `_resources/<sha256>.<ext>`.
`page_links` includes HTML links and explicit srcset candidates. `rewrite_css` preserves
import syntax and local fragments. `rewrite_html` serializes UTF-8 and normalizes charset
metadata. `fetch_bytes` returns `(bytes, content_type, effective_url)` with a 32 MiB body cap.
`SiteCloner(root, host, ua, log=..., max_assets=..., delay=...)` accepts pages through
`save_page`, drains assets with `fetch_assets`, and rewrites only available resources in
`write_manifest`. Failed/pending resources stay absolute. `index.html` opens the entry page;
`_clone-manifest.json` records results. Sharded clone construction is rejected.

Example (synthetic HTML, no asset requests):

```python
from scripts.site_clone import SiteCloner
clone = SiteCloner('/tmp/example-clone', 'example.org', 'local-example')
clone.save_page('https://example.org/', '<html><body>Example</body></html>')
clone.fetch_assets()
clone.write_manifest()
```

## Optional host integrations and tooling

`try_llms_acquire` is a guarded fast path; `_crawl_llms_txt_job` owns the optional
agent queue. `run_distill_job` invokes external semantic tools. Their contracts and
risks are [documented separately](integrations-and-assumptions.md); they are mocked
in tests. `scripts/maintain_docs.py` parses source without imports and owns generated
references; `scripts/rotate_workflow_logs.py` archives oversized workflow logs.
