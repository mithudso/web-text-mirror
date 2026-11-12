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
python3 scripts/text_mirror.py --serve      # or just: python3 scripts/text_mirror.py
                                            # (no args defaults to serve mode)
```

Output lands in `text-mirror/<hostname>.md` by default, with a resumable per-host
`<host>.<destination-key>_state.json` and a `crawl.log` beside it.

## Features

- **BFS crawl** from each seed, same-host scoped (normalized host comparison — case,
  default ports, userinfo).
- **Readable-text extraction** via [trafilatura](https://trafilatura.readthedocs.io/)
  (Markdown; tables, comments, links, images kept; boilerplate stripped).
- **Polite:** robots.txt per host (fail-open on network error, honoring 4xx allow and 5xx disallow), global per-request rate limiter (`--delay` / `--req-per-sec`),
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

Start with the maintained [project wiki](docs/wiki/README.md).

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

## Offline clone and optional integrations

`--clone` writes HTML and assets alongside Markdown. Open the clone's `index.html`;
`_clone-manifest.json` lists written, failed and pending resources. Resource filenames
use fragment-free URL hashes to prevent collisions. Missing resources retain live
absolute links. Clone acquisition is unsharded; `--clone` with `--shard-count > 1`
is rejected because asset discovery cannot safely cross shards.

Text crawls support `--max-pages`, `--shard-index` and `--shard-count`.
`--no-prefer-llms` disables the optional workstation `llms_acquire` fast path.
Cloning always uses HTML acquisition. See [integration details](docs/integrations-and-assumptions.md).
The optional `/crawl_llms_txt` and `/distill` API routes can invoke external models
or semantic indexing. They are not used by the bundled panel and are never run
live by the offline tests.
