# Requirements

## Functional

1. Crawl one or more seed URLs breadth-first, scoped to each seed's (normalized) host.
2. Extract each page's readable content to Markdown (tables, comments, links, images
   preserved; boilerplate stripped).
3. Append all pages to a single output file with `URL:` separators; flush per page so
   partial output is usable.
4. Honor robots.txt per host (401/403 → disallow; unreachable → allow with logged
   warning); skip login/register/account/asset/action URLs; identify with a
   descriptive UA.
5. Rate-limit globally to one request per `--delay` seconds (or `--req-per-sec`).
6. Support depth caps (`--max-depth`), custom output (`--out`), multiple seeds.
7. Persist per-host resume state atomically; resume interrupted crawls.
8. Serve a local HTTP API (`--serve`, 127.0.0.1:8765) with `/save`, `/crawl`,
   `/stop`, `/list` for the bundled Chrome side-panel extension, which can submit the
   active tab's rendered DOM.
9. Self-bootstrap missing dependencies via pip on first run.

## Non-functional

- **Security:** API reachable from loopback only; Origin allowlist; browser-supplied
  output filenames confined to the output directory; no auth walls crossed, ever.
- **Politeness:** default 1 req/s; robots compliance as above.
- **Robustness:** per-URL failures logged and skipped, never fatal; crashed crawls
  resumable; single-flight guard cannot wedge.
- **Portability:** Python ≥ 3.9, stdlib + two packages; no build step.
- **Performance:** 10-way fetch concurrency within the rate limit; O(1) dedup.

## External dependencies

| Package | Floor | Purpose |
|---|---|---|
| trafilatura | ≥ 2.0 | Fetching + readable-text extraction |
| lxml | ≥ 5.0 | Link harvesting (also a trafilatura dep) |
| ruff (dev) | any | Linting |

## System requirements

Any machine that runs CPython ≥ 3.9; disk proportional to mirrored text; network
egress to target sites. Chrome for the extension.
