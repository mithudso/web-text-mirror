---
name: web-text-mirror
description: >-
  Recursively mirror one or more websites into a single text/Markdown file using trafilatura — BFS crawl, same-host scoping, robots.txt-respecting, rate-limited, public-only, incremental write. Auto-installs trafilatura/lxml if missing. TRIGGER "text-only mirror of a site", "scrape a whole wiki/forum/site to one text file", "recursively extract all page text with trafilatura", "archive a site as clean Markdown for LLM/search/RAG ingestion", "crawl and dump a site's readable content". SKIP high-fidelity HTML + assets/CSS/JS offline mirror → use httrack (brew) or single-file-cli (npm); a single page → call trafilatura -u URL directly; JS-rendered SPA that needs a real browser → single-file-cli; managed multi-source web-research report → firecrawl / deep-research; login-gated content → this skill is public-only by design.
---

# web-text-mirror

Turn one or more live websites into a **single consolidated text/Markdown file**, one
page after another, each preceded by a `URL:` header. Built for producing clean,
LLM/search-ready corpora from wikis, forums, docs sites, and blogs.

## What it does
- **BFS crawl** from each seed URL, staying on that seed's host.
- **Extracts readable text** with `trafilatura` (Markdown output; tables + comments kept, boilerplate stripped).
- **Single-file output** with a `====… / URL: <url> / ====…` separator before every page.
- **Polite by default:** checks `robots.txt` per URL, rate-limits (1s), sets a descriptive UA.
- **Public-only:** skips login/register/account/action/asset URLs to avoid auth walls and crawl explosions.
- **Incremental + crash-tolerant:** flushes after every page, so partial output is already usable.

## Requirements (auto-installed)
The runtime dependency is **trafilatura** (which pulls in **lxml**). The crawler
self-bootstraps: on start it checks for these modules and `pip install`s them into the
current interpreter if missing. To pre-provision instead:

```bash
bash scripts/install.sh          # or: PYTHON=/path/to/python bash scripts/install.sh
```

## Usage

```bash
# one site, uncapped, default output ./text-mirror/mirror.md
python scripts/text_mirror.py https://wiki.example.org/

# multiple seeds, capped, custom output
python scripts/text_mirror.py https://wiki.example.org/ https://forum.example.org/board/ \
  --out out/mirror.md --max-pages 500 --delay 1.5
```

### Options
| Flag | Env | Default | Meaning |
|---|---|---|---|
| `seeds` (positional) | — | required | one or more seed URLs; each is crawled within its own host |
| `--out` | `OUT_FILE` | `text-mirror/mirror.md` | consolidated Markdown output path |
| `--delay` | `CRAWL_DELAY` | `1.0` | seconds between requests (politeness) |
| `--max-pages` | `MAX_PAGES` | `0` | per-site page cap; `0` = unlimited |

A sibling `crawl.log` is written next to `--out` with per-25-page progress and any
`robots-skip` / `no-content` / `fetch-error` notes.

## Output format
```
##########  SITE: wiki.example.org  (seed: https://wiki.example.org/)  ##########

==========================================================================================
URL: https://wiki.example.org/Some_Page
==========================================================================================

# Some Page
...extracted Markdown...
```

## Operational notes
- **Uncapped forum crawls can explode.** XenForo/MediaWiki generate huge URL spaces
  (reactions, pagination, permalinks). For large forums prefer a `--max-pages` cap or
  run in the background and monitor `crawl.log`. The `SKIP_SUBSTR` list trims the worst
  offenders but cannot bound an inherently unbounded site.
- **Login-gated content is intentionally skipped.** This tool does not authenticate.
- **Same-host only.** Links to other hosts are not followed; pass each host as its own seed.
- Long runs: launch with `nohup … &` and `tail -f crawl.log`.

## Files
- `scripts/text_mirror.py` — the crawler (CLI; auto-installs deps).
- `scripts/install.sh` — optional pre-provisioning of trafilatura/lxml.
