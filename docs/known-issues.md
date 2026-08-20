# Known Issues

| # | Symptom | Root cause | Workaround | Files |
|---|---|---|---|---|
| 1 | No LICENSE file | Deliberately left as an operator decision during bootstrap | Choose one (MIT/Apache-2.0/…) and commit it | `LICENSE` (missing) |
| 2 | Uncapped forum/wiki crawls can explode (huge URL spaces: pagination, permalinks, reactions) | Inherently unbounded sites; `SKIP_SUBSTR` trims only the worst offenders | Use `--max-depth`; monitor `crawl.log`; `/stop` via API | `scripts/text_mirror.py` |
| 3 | JS-rendered SPAs mirror poorly from CLI | Crawler fetches raw HTML, no browser | Use the Chrome extension `/save` path (captures rendered DOM), or single-file-cli | `scripts/text_mirror.py` |
| 4 | First import may modify the interpreter's site-packages (pip install, up to `--break-system-packages`) | `ensure_deps()` self-bootstrap is a skill-packaging feature | Pre-provision via `scripts/install.sh` or venv | `scripts/text_mirror.py` |
| 5 | HTTP handlers not covered end-to-end by tests | Harness unit-tests their helpers only | Planned: live-socket test of `/save`+`/crawl` (docs/TESTING.md) | `tests/test_text_mirror.py` |
| 6 | Deps unpinned (floor versions only) | Reproducibility traded for skill portability | Pin exact versions locally if needed | `requirements.txt` |
| 7 | Extension hardcodes `localhost:8765` | No config surface in the panel | Change both `sidepanel.js` and `PORT` together | `chrome-plugin/sidepanel.js` |
| 8 | Windows support unverified | Developed/tested on macOS/Linux | `# TODO:` verify encodings + install.sh alternative | repo-wide |
| 9 | Uncommitted local changes to `scripts/text_mirror.py` + PyInstaller artifacts (`build/`, `dist/`, `text_mirror.spec`) exist in the main working tree | Local packaging experiments predating the bootstrap branch | Reconcile or discard when merging the bootstrap PR | main worktree |
