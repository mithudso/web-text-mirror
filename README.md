# web-text-mirror

Turn one or more live websites into a **single consolidated Markdown file** — one page
after another, each preceded by a `URL:` header. Built for producing clean, LLM/search/
RAG-ready corpora from wikis, forums, docs sites, and blogs. Includes a Chrome side-panel
extension that saves the current tab (or kicks off a whole-site crawl) through a local
HTTP API.

## Quick start

```bash
# one-off crawl of a site (deps auto-install on first run)
python3 scripts/text_mirror.py https://wiki.example.org/

# custom output, depth-capped, slower
python3 scripts/text_mirror.py https://wiki.example.org/ --out out/mirror.md --max-depth 2 --delay 1.5

# start the local API for the Chrome extension (127.0.0.1:8765)
python3 scripts/text_mirror.py --serve
```

Output lands in `text-mirror/<hostname>.md` by default, with a resumable per-host
`<host>_state.json` and a `crawl.log` beside it.

## Features

- **BFS crawl** from each seed, same-host scoped (normalized host comparison — case,
  default ports, userinfo).
- **Readable-text extraction** via [trafilatura](https://trafilatura.readthedocs.io/)
  (Markdown; tables, comments, links, images kept; boilerplate stripped).
- **Polite:** robots.txt per host (fail-open on network error, honoring 401/403
  disallow), global per-request rate limiter (`--delay` / `--req-per-sec`),
  descriptive UA.
- **Public-only:** skips login/register/account/asset/action URLs.
- **Incremental + resumable:** appends after every page; atomic per-host state file
  lets an interrupted crawl resume.
- **Chrome extension** (`chrome-plugin/`): side panel to save the current tab's
  rendered DOM or start/stop/watch a crawl via `http://localhost:8765`.
- **Hardened local API:** binds 127.0.0.1 only, Origin allowlist (extension +
  loopback), browser-supplied output filenames confined to the output directory,
  single-flight crawl guard.

## Architecture

A single Python process runs the crawler; `--serve` adds a threading HTTP server on
127.0.0.1:8765 that the Chrome side-panel extension calls (`/save`, `/crawl`, `/stop`,
`/list`). Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Docs

- [Installation](docs/INSTALLATION.md)
- [Development](docs/DEVELOPMENT.md)
- [Testing](docs/TESTING.md)
- [Security](docs/SECURITY.md)
- [Components](docs/COMPONENTS.md)
- [Runbook: run a crawl](docs/runbooks/run-a-crawl.md)
- [Runbook: extension + server](docs/runbooks/extension-server.md)
- [Contributing](CONTRIBUTING.md)

## License

[MIT](LICENSE)
