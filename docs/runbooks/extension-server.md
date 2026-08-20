# Runbook: Extension + Server

## Start

```bash
python3 scripts/text_mirror.py --serve
# → "Started Chrome extension server on http://127.0.0.1:8765"
```

Load the extension once: `chrome://extensions` → Developer mode → Load unpacked →
`chrome-plugin/`. Toolbar icon opens the side panel.

## Operations

| Action | How |
|---|---|
| Save current page (rendered DOM) | Panel → **Save Current Page** |
| Crawl whole site from current page | Tick **Crawl**, set max depth → **Start Crawl** |
| Stop a crawl | Panel button turns red **Stop Crawl** → click (POSTs `/stop`) |
| Watch progress | Panel stats (discovered/downloaded/queue), 1 Hz |
| Custom output file | Panel **out file** field — basename only; it is confined to the output dir |

## API surface (also curl-able)

```bash
curl -s http://127.0.0.1:8765/list | python3 -m json.tool
curl -s -X POST http://127.0.0.1:8765/crawl -H 'Content-Type: application/json' \
  -d '{"url": "https://example.org/", "max_depth": 1}'
curl -s -X POST http://127.0.0.1:8765/stop
```

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Panel alert "Error communicating with crawler" | Server not running → start `--serve` |
| `403` responses | Request carried a non-allowlisted `Origin` (web page / sandboxed iframe) — by design; use the extension or a header-less client |
| `409 {"status":"busy"}` on `/crawl` | A crawl is already running → `/stop` first (single-flight by design) |
| `400` on `/save` | Malformed JSON or missing `url` |
| Server won't start / port in use | Another process owns 8765: `lsof -i :8765` → kill it, or change `PORT` in `scripts/text_mirror.py` **and** `chrome-plugin/sidepanel.js` together |
| Saves land in an unexpected file | Panel out-file is basename-confined to the output dir (`client_out_file`) — full paths are intentionally not honored |

## Stop the server

Ctrl+C in its terminal (serve-only mode), or kill the process. In-flight crawls
save state on exit paths; worst case a resume re-fetches ≤30 s of bookkeeping.
