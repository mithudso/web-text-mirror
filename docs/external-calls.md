# External Calls Inventory

Every place this codebase reaches outside its own process. (This repo is a Python
CLI, not an mdb-tam Node service — the five-standard auto-remediation contract
(CLI trigger / centralized error log / auto-remediation map / dashboard card /
datastore verification) is **not applicable**; the columns below cover the
politeness/error/test posture that applies here.)

| # | Call | Where | Transport | Error handling | Retry | Logged | Tested |
|---|---|---|---|---|---|---|---|
| 1 | Page fetch | `trafilatura.fetch_url` in `fetch_and_extract` | HTTP(S) GET, 30 s timeout, custom UA | caught → `fetch-error` log, URL skipped | none (BFS moves on) | yes | functional harness (localhost) |
| 2 | Page fetch (`/save` path) | `trafilatura.fetch_url` in `process_single_url` | as above | `no-content` log → False; handler wraps → HTTP 500 | none | yes | via harness helpers |
| 3 | robots.txt fetch | `urllib.request.urlopen` in `get_robots` | HTTPS/HTTP GET, 30 s timeout | 401/403 → disallow; other HTTPError → allow; network error → allow + `robots-read-error` log | none | yes | fail-open covered indirectly (crawl proceeds in harness) |
| 4 | pip install | `subprocess.check_call` in `ensure_deps` | subprocess → PyPI | per-strategy catch, 4 escalating attempts, then `sys.exit` | 4 strategies | `[bootstrap]` prints | not tested (import-time; requires missing-dep env) |
| 5 | Extension → local API | `fetch()` in `chrome-plugin/sidepanel.js` (`/save`, `/crawl`, `/stop`, `/list`) | HTTP JSON to 127.0.0.1:8765 | try/catch → user alert / console.error | 1 Hz `/list` poll re-syncs | console only | not tested (no extension harness) |

Gaps (tracked in docs/known-issues.md): #4 untestable without a disposable env;
#5 extension has no automated tests; live-socket API test pending (known-issues #5).
