# Testing

## Commands and layers

Install `python -m pip install -r requirements-dev.txt`; use Python 3.11+ and Node 22+.
No build step exists.

| Command | Coverage |
|---|---|
| `python tests/test_text_mirror.py` | Existing helper assertions and two-page localhost crawl; bounded local fetch adapter isolates the fixture from upstream response suitability thresholds |
| `python -m unittest discover -s tests -p test_regressions.py -v` | Destination identity, cancellation/resume, refresh, duplicate writes, API validation/status, optional-job cleanup, clone mapping/CSS/HTML/assets/limits/symlinks and tooling |
| `node --test tests/test_sidepanel.js` | Mock DOM/Chrome/fetch; HTTP rejection, capture errors, depth validation, duplicate clicks, safe rendering and background rejection |
| `ruff check scripts/ tests/` | Python lint |
| `python -m compileall -q scripts tests` | Python syntax across maintained components |
| `bash -n scripts/install.sh` | Installer syntax |
| `node --check chrome-plugin/background.js` and `node --check chrome-plugin/sidepanel.js` | Extension JavaScript syntax |
| `python scripts/maintain_docs.py --check` | Static reference path/content drift |

Run a single regression with `python -m unittest discover -s tests -p test_regressions.py -k output_state -v`.
GitHub CI runs all gates on Python 3.11 and 3.13, with Node 22. A failure blocks delivery.

## Fixture and assertion rules

Tests preblock the optional host module before importing the crawler. Optional
subprocess/model/indexing integrations are mocked. Network fixtures bind only a
throwaway loopback port and use synthetic HTML; no public site, private corpus,
API token, model or semantic service participates. Preinstall dependencies so import
cannot invoke the fallback pip bootstrap.

Assert observable results: output banners, saved/queued identities, local file bytes,
HTTP statuses, DOM text, error events and resource bounds. Every important changed
path needs a failure-sensitive assertion. No numeric coverage percentage is enforced.
Add isolated `unittest` cases to `test_regressions.py`; temporary directories and mocks
must clean up. The original harness remains a standalone process because it uses
module globals and exits. Independent Node test contexts isolate DOM state. There
are no real sleeps in the regression suites; fixture server shutdown may wait for
its bounded polling interval.

## Limits and empirical eligibility

No held-out evaluation corpus, benchmark score or promotion surface exists. Ordinary
unit/smoke checks are the must-pass gate, not an empirical optimization metric. No
champion is persisted. Real browser installation, private host tool correctness,
Windows no-follow support, large-site performance and live model/embedding integration
are not verified by these fixtures. Dependency metadata auditing may access official
package/advisory services separately from tests.
