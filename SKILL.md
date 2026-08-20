---
name: web-text-mirror
description: >-
  Recursively mirror one or more websites into a single text/Markdown file using trafilatura — BFS crawl, same-host scoping, robots.txt-respecting, rate-limited, public-only, incremental write, resumable. Auto-installs trafilatura/lxml if missing. Includes a Chrome side-panel extension + local HTTP API (--serve) for saving rendered DOMs. TRIGGER "text-only mirror of a site", "scrape a whole wiki/forum/site to one text file", "recursively extract all page text with trafilatura", "archive a site as clean Markdown for LLM/search/RAG ingestion", "crawl and dump a site's readable content". SKIP high-fidelity HTML + assets/CSS/JS offline mirror → use httrack (brew) or single-file-cli (npm); a single page → call trafilatura -u URL directly; JS-rendered SPA that needs a real browser → single-file-cli or this skill's Chrome extension /save path; managed multi-source web-research report → firecrawl / deep-research; login-gated content → this skill is public-only by design.
---

# web-text-mirror

Turn one or more live websites into a **single consolidated text/Markdown file**, one
page after another, each preceded by a `URL:` header. Built for producing clean,
LLM/search-ready corpora from wikis, forums, docs sites, and blogs.

## What it does
- **BFS crawl** from each seed URL, staying on that seed's host (normalized: case,
  default ports, userinfo).
- **Extracts readable text** with `trafilatura` (Markdown output; tables, comments,
  links + images kept, boilerplate stripped).
- **Single-file output** with a `====… / URL: <url> / ====…` separator before every page.
- **Polite by default:** robots.txt per host (401/403 → disallow; unreachable →
  proceed with a logged warning), one request per `--delay` seconds enforced globally
  across workers, descriptive UA.
- **Public-only:** skips login/register/account/action/asset URLs.
- **Incremental + resumable:** appends after every page; atomic per-host
  `<host>_state.json` resumes interrupted crawls automatically.
- **Chrome extension + local API:** `--serve` starts `127.0.0.1:8765`; the side panel
  saves the current tab's *rendered* DOM (JS-rendered pages!) or starts/stops/watches
  a crawl.

## Requirements (auto-installed)
Runtime dependency: **trafilatura** (pulls **lxml**). The crawler self-bootstraps via
pip on first run. To pre-provision instead:

```bash
bash scripts/install.sh          # or: PYTHON=/path/to/python bash scripts/install.sh
```

## Usage

```bash
# one site, uncapped, default output ./text-mirror/<hostname>.md
python scripts/text_mirror.py https://wiki.example.org/

# multiple seeds, depth-capped, custom output, slower
python scripts/text_mirror.py https://wiki.example.org/ https://forum.example.org/ \
  --out out/mirror.md --max-depth 3 --delay 1.5

# serve the Chrome-extension API only
python scripts/text_mirror.py --serve
```

### Options
| Flag | Env | Default | Meaning |
|---|---|---|---|
| `seeds` (positional) | — | — | one or more seed URLs; each crawled within its own host |
| `--out` | — | `text-mirror/<hostname>.md` | consolidated Markdown output path |
| `--delay` | `CRAWL_DELAY` | `1.0` | seconds between requests (global, per-request) |
| `--req-per-sec` | — | `0` | requests/sec; overrides `--delay` when > 0 |
| `--max-depth` | `MAX_DEPTH` | `0` | per-site depth limit in hops; `0` = unlimited |
| `--serve` | — | off | local HTTP API for the Chrome extension on 127.0.0.1:8765 |

A sibling `crawl.log` is written next to `--out` with progress lines (every ~30 s
state save) and any `robots-skip` / `no-content` / `fetch-error` notes.

## Output format
```
==========================================================================================
URL: https://wiki.example.org/Some_Page
==========================================================================================

# Some Page
...extracted Markdown...
```

## Operational notes
- **Uncapped forum crawls can explode.** XenForo/MediaWiki generate huge URL spaces.
  Prefer `--max-depth` for large sites; monitor `crawl.log`. The `SKIP_SUBSTR` list
  trims the worst offenders but cannot bound an inherently unbounded site.
- **Resume:** re-running the same command continues from `<host>_state.json`; the
  extension's Force refresh starts over (clears state + output).
- **Login-gated content is intentionally skipped.** This tool does not authenticate.
- **Same-host only.** Pass each host as its own seed.
- Long runs: `nohup … &` and `tail -f crawl.log`.

## Files
- `scripts/text_mirror.py` — crawler + local HTTP API (CLI; auto-installs deps).
- `scripts/install.sh` — optional pre-provisioning of trafilatura/lxml.
- `chrome-plugin/` — MV3 side-panel extension (Load unpacked; needs `--serve`).
- `tests/test_text_mirror.py` — self-contained harness (`python3 tests/test_text_mirror.py`).
