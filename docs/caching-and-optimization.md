# Caching and Optimization

## Cache layers

| Layer | What | Invalidation |
|---|---|---|
| Saved-URL set (`_SAVED_SET` + `SAVED_URLS`) | O(1) in-memory dedup of already-mirrored pages | `force_refresh` clears it (and removes the output file) |
| Per-host state file (`<host>_state.json`) | Crawled map + frontier queue for resume | `force_refresh` bypasses; schema-mismatch falls back to fresh |
| `seen` set (per crawl) | Prevents re-enqueueing discovered URLs | Per-crawl lifetime |

No HTTP response caching — every fetch is live (politeness-limited), by design:
mirrors should reflect the site at crawl time.

## Performance patterns in use

- **Batched parallel fetches** — one persistent 10-worker `ThreadPoolExecutor` per
  crawl (not per batch), throttled by the global rate limiter.
- **O(1) membership** everywhere URL dedup happens (set alongside the ordered list).
- **Append-only output** — no rewrite of the growing mirror file.
- **Atomic, throttled state saves** — every 30 s (`STATE_SAVE_INTERVAL`), not every
  page, and compact JSON (no indent).
- **Depth-boundary pruning** — over-depth links are never enqueued.

## Known bottlenecks

| Bottleneck | Impact | Mitigation |
|---|---|---|
| Rate limiter (by design) | Throughput ≈ 1/`--delay` pages/s | Raise `--req-per-sec` only when the target site allows |
| Batch head-of-line blocking (results consumed per batch) | Slowest fetch in a batch delays link discovery | Acceptable at 10 workers; `as_completed` streaming is the upgrade path |
| State file grows with crawl size (full rewrite each save) | Large crawls rewrite MBs every 30 s | Interval already bounds it; JSONL append is the upgrade path |
| Per-line `crawl.log` open/append | Syscall per event | Negligible at politeness rates |

## Profiling

```bash
python3 -m cProfile -s cumtime scripts/text_mirror.py https://example.org/ --max-depth 1 | head -40
```

Expect wall-clock dominated by network + `time.sleep` (the throttle); anything else
rising to the top is a regression.
