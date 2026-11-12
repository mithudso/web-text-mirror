# Requirements

## Functional

1. Crawl one or more seed URLs breadth-first, scoped to each seed's (normalized) host.
2. Extract each page's readable content to Markdown (tables, comments, links, images
   preserved; boilerplate stripped).
3. Append all pages to a single output file with `URL:` separators; flush per page so
   partial output is usable.
4. Honor robots.txt per host (4xx → allow; 5xx → disallow; unreachable → allow with logged
   warning); skip login/register/account/asset/action URLs; identify with a
   descriptive UA.
5. Rate-limit globally to one page request per `--delay` seconds (or `--req-per-sec`).
6. Support depth caps (`--max-depth`), custom output (`--out`), multiple seeds.
7. Persist per-host resume state atomically; resume interrupted crawls.
8. Serve a local HTTP API (`--serve`, 127.0.0.1:8765) with `/save`, `/crawl`,
   `/stop`, `/list` for the bundled Chrome side-panel extension, which can submit the
   active tab's rendered DOM.
9. Self-bootstrap missing dependencies via pip on first run.

## Non-functional

- **Security:** API reachable from loopback only; Origin allowlist; browser-supplied
  output filenames confined to the output directory; the tool performs no site authentication; skip lists are heuristics.
- **Politeness:** default 1 req/s; robots compliance as above.
- **Robustness:** per-URL failures logged and skipped, never fatal; crashed crawls
  resumable; single-flight guard cannot wedge.
- **Portability:** Python ≥ 3.11, stdlib + two packages; no build step.
- **Performance:** 10-way fetch concurrency within the rate limit; O(1) dedup.

## External dependencies

| Package | Floor | Purpose |
|---|---|---|
| trafilatura | ≥ 2.3.1 | Fetching + readable-text extraction |
| lxml | ≥ 6.1.3 | Link harvesting (also a trafilatura dep) |
| ruff (dev) | any | Linting |

## System requirements

Any machine that runs CPython ≥ 3.11; disk proportional to mirrored text; network
egress to target sites. Chrome for the extension.

Clone acquisition requires POSIX directory-descriptor/no-follow file APIs. Assets have bounded bodies/attempts; sharded HTML cloning is rejected. Tests additionally require Node 22+; runtime itself has no Node requirement.
