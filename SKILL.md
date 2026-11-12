---
name: web-text-mirror
version: 1.0.1
updated: '2026-11-12'
description: >-
  Mirror public websites to URL-banner Markdown, with optional HTML/assets cloning and a local Chrome side panel. TRIGGER: "mirror a wiki to one Markdown file", "crawl a public site with trafilatura", "save rendered page text", "make an offline HTML clone". SKIP: authenticated sites; browser-rendered full-site capture → single-file-cli; condensed llms.txt reference → llms-txt-tooling (references/crawl-to-llms-txt.md); managed web research → firecrawl or deep-research. Core installs trafilatura/lxml when absent; prefer a preprovisioned venv.

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
- **Polite by default:** robots.txt per host (4xx → allow; 5xx → disallow; unreachable →
  proceed with a logged warning), one request per `--delay` seconds enforced globally
  across workers, descriptive UA.
- **Public-only:** skips login/register/account/action/asset URLs.
- **Incremental + resumable:** appends after every page; atomic per-host
  `<host>.<destination-key>_state.json` resumes interrupted crawls automatically.
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

# serve the Chrome-extension API only (running with no arguments does the same)
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
| `--serve` | — | on when no args given | local HTTP API for the Chrome extension on 127.0.0.1:8765; running with no seeds/--out/--serve defaults to serve mode |

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
- **Resume:** re-running the same command continues from `<host>.<destination-key>_state.json`; the
  extension's Force refresh starts over (restarts selected-host state and replaces only its URL blocks).
- **Login-gated content is intentionally skipped.** This tool does not authenticate.
- **Same-host only.** Pass each host as its own seed.
- Long runs: `nohup … &` and `tail -f crawl.log`.

## Files
- `scripts/text_mirror.py` — crawler + local HTTP API (CLI; auto-installs deps).
- `scripts/install.sh` — optional pre-provisioning of trafilatura/lxml.
- `chrome-plugin/` — MV3 side-panel extension (Load unpacked; needs `--serve`).
- `tests/test_text_mirror.py` — self-contained harness (`python3 tests/test_text_mirror.py`).

## Routing detail

- SKIP: a condensed llms.txt reference, not a mirror → llms-txt-tooling (references/crawl-to-llms-txt.md). (seeded 2026-09-02 by /sko crawl-to-llms-txt)


## Additional supported flags and limits

| Flag | Default | Meaning |
|---|---|---|
| `--max-pages` | 0 | Maximum fetched pages for this shard; 0 unlimited |
| `--shard-index`, `--shard-count` | 0, 1 | Stable text-only crawl partition |
| `--clone` | false | Also write browsable HTML/assets and manifest |
| `--clone-dir` | host-derived | Operator-selected clone root |
| `--clone-same-host-assets` | false | Exclude off-host assets |
| `--max-assets` | 0 | Bound asset attempts; 0 unlimited; body cap 32 MiB each |
| `--prefer-llms`, `--no-prefer-llms` | true | Optional workstation Markdown acquisition; bypassed for clones |

Use `--clone --max-pages 5 --max-assets 30` for a bounded clone. Open its index.html
and inspect the manifest: failed/pending resources retain live URLs. HTML cloning
with multiple shards is rejected. The optional API model/distill routes are separate
operator capabilities and must not be invoked for ordinary mirroring tests. They may
incur charges or perform semantic indexing. No semantic generation is part of static
reference maintenance.

Before running a crawl, verify the operator authorized acquisition of the named public
site and selected output. Do not crawl a private browser DOM, start a daemon, or call
optional model/indexing routes as a test. Use docs/TESTING.md for offline verification.
