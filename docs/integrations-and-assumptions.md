# Integrations and assumptions

## Core runtime

Python 3.11+ runs `scripts/text_mirror.py` and imports `site_clone.py`, trafilatura and
lxml. The CLI fetches operator-selected HTTP(S) URLs; robots uses urllib with a 30s
timeout. Markdown pages append with the exact existing 90-equals / `URL:` / 90-equals
banner. Clone assets use urllib, a 30s timeout, a 32 MiB body cap, and effective redirect
URLs for CSS. Assets may come from other hosts unless same-host-assets is selected.
The local API binds 127.0.0.1:8765. The panel uses localhost:8765 with server CORS.
No third-party backend, database, package build or MCP server is shipped.

## Optional workstation integrations

| Entry | Dependency / default location | Side effects / verification |
|---|---|---|
| Fresh crawl, prefer-llms on | `llms_acquire` from `~/.global-ai-hub/scripts` when present | HTTP acquisition and local Markdown output; read URL headers; bypassed for cloning/sharding/refresh or existing output |
| POST `/crawl_llms_txt` | `claude` CLI and crawl-to-llms-txt skill | Headless editing agent; may use network/models and incur charges; bounded FIFO, 3600s timeout, changed-directory check; no guarantee of semantic correctness |
| POST `/distill` | `~/dev/distillers/distill_offline.py` | Semantic distill subprocess with `--semantic`; 600s timeout; scratch under the installed skill's text-mirror tree |
| Same distill job | `~/.global-ai-hub/.venv/bin/python` and `~/.global-ai-hub/scripts/docset_indexer.py` | Indexes master; 120s timeout; only subprocess exit is checked, independent backend readback is unavailable here |

These are operator-only optional capabilities, not dependencies of the bundled panel.
Tests block host module imports and mock subprocesses. Maintenance does not invoke
these capabilities, activate services or generate semantic embeddings.

## Configuration and boundaries

`CRAWL_DELAY` defaults to 1.0; `MAX_DEPTH` defaults to 0; CLI flags override them.
`PYTHON` selects the explicit installer's interpreter. `.env` is not loaded by Python;
use exported variables (see `.env.example`). Port, worker count, timeouts, API body cap,
queue bounds and optional-tool paths are named module constants. There is no UI for
all operator settings. This small single-file CLI intentionally keeps constants with
their owner rather than adding a settings service.

No authentication is performed against crawled sites. Skip lists are heuristics, not
a proof that content is public. A rendered browser DOM may contain private data; the
operator must select suitable content. URLs can expose sensitive query data in local
logs; avoid credentials, tokens and sensitive URLs. Clone output retains original
active page scripts; open only trusted captured content.
