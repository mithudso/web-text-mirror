# Architecture

## Context

web-text-mirror converts public websites into a single consolidated Markdown file for
LLM/search/RAG ingestion. Actors: an operator running the CLI, and optionally the
bundled Chrome side-panel extension driving the same engine through a local HTTP API.
External integrations: the target websites themselves (HTTP GET), each host's
`robots.txt`, and PyPI (one-time self-bootstrap of trafilatura/lxml).

## Container diagram

```
┌────────────────────────── Operator machine ──────────────────────────┐
│                                                                      │
│  Chrome ──────────────┐            ┌──────── python3 text_mirror.py ─┴──┐
│  ┌─────────────────┐  │  HTTP JSON │  ┌────────────────────────────┐    │
│  │ chrome-plugin/  │──┼───────────▶│  │ ThreadingHTTPServer        │    │
│  │ side panel      │  │ 127.0.0.1  │  │ /save /crawl /stop /list   │    │
│  │ (sidepanel.js)  │◀─┼── :8765 ───│  └──────────┬─────────────────┘    │
│  └─────────────────┘  │            │             │ spawns (single-flight)│
│                       │            │  ┌──────────▼─────────────────┐    │
│                       │            │  │ crawl(): BFS queue          │    │
│                       │            │  │  ├ robots.txt gate          │    │
│                       │            │  │  ├ rate limiter (_throttle) │    │
│                       │            │  │  └ ThreadPoolExecutor (10)  │───────▶ target sites
│                       │            │  └──────────┬─────────────────┘    │   (HTTP GET)
│                       │            │             │ appends              │
│                       │            │   text-mirror/<host>.md            │
│                       │            │   <host>_state.json (atomic)       │
│                       │            │   crawl.log                        │
│                       │            └────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────────┘
```

## Components per container

- **CLI / entrypoint** (`main()`): argparse, log setup, seed loop, serve-mode wait loop.
- **Crawl engine** (`crawl()` → `_crawl_impl()`): BFS queue, batching, depth limit,
  resume-from-state, cancel handling; `fetch_and_extract()` per URL.
- **Extraction**: trafilatura `fetch_url` + `extract` (Markdown, tables/comments/
  links/images, favor_recall) with `lxml` link harvesting (`links_from`).
- **Politeness**: `get_robots()` (timeout, fail-open on network error, 401/403
  disallow), `_throttle()` global rate limiter, `SKIP_EXT`/`SKIP_SUBSTR` public-only
  filters, descriptive UA.
- **Persistence**: `append_to_file()` (single Markdown file, `URL:` separators),
  `save_state()`/`load_state()` (atomic per-host JSON: crawled map, discovered set,
  queue).
- **Local API** (`PluginServerHandler`): `/save` (extension-supplied DOM → extract →
  append), `/crawl` (spawn crawl thread), `/stop` (cancel flag), `/list` (saved URLs +
  live stats). Guards: 127.0.0.1 bind, `_origin_ok` allowlist, `client_out_file`
  filename confinement, single-flight via `CRAWL_START_LOCK`/`CRAWL_ACTIVE`.
- **Chrome extension** (`chrome-plugin/`): MV3 side panel; captures
  `document.documentElement.outerHTML` of the active tab via `chrome.scripting`,
  posts to the API, polls `/list` at 1 Hz.

## Runtime views

**CLI crawl:** 1) parse args → 2) acquire single-flight reservation → 3) fetch
robots.txt → 4) load/resume state → 5) pop ≤10 URLs, filter (depth/saved/robots) →
6) throttled parallel fetch+extract → 7) append pages, harvest same-host links →
8) periodic atomic state save → 9) repeat until queue empty/cancelled → 10) final save.

**Extension save:** 1) user clicks Save → 2) side panel grabs rendered DOM →
3) `POST /save {url, html, out_file?}` → 4) origin check → filename confinement →
extract → append → 5) response includes updated saved-URL list.

## Deployment topology

Single machine, no daemon: run ad hoc from a shell. The API server binds
`127.0.0.1:8765` only. Output tree defaults to `./text-mirror/`.

## Architectural decisions (ADRs)

1. **Single-file crawler** — ships verbatim inside a Claude skill; no packaging.
2. **Threads over asyncio** — stdlib `http.server` + `ThreadPoolExecutor` keep the
   file dependency-light; concurrency needs are modest (10 workers).
3. **Fail-open robots on network error** — an unreachable robots.txt must not
   silently zero out a crawl; HTTP 401/403 still disallow (stdlib-compatible policy).
4. **Append-only output + atomic state** — partial output stays usable after a
   crash; `os.replace` guarantees the resume file is never truncated JSON.
5. **Global rate limiter** — politeness is enforced per request across all worker
   threads, matching the documented `--delay`/`--req-per-sec` contract.
6. **Local-API hardening as product behavior** — 127.0.0.1 bind, Origin allowlist,
   and output-filename confinement are invariants, not options.

## Constraints and quality attributes

- Politeness: default 1 req/s; robots.txt honored per host.
- Unbounded sites (forums/wikis) can explode — `--max-depth` is the operator's cap.
- Memory: BFS `seen` set and state grow with the URL space; large crawls are
  disk/RAM-linear.
- Public-only by design: no authentication, ever.
