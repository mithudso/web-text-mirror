# Caching and Optimization

## Cache layers

| Layer | What | Invalidation |
|---|---|---|
| Destination-scoped saved sets (`_SAVED_BY_FILE`), plus global UI list | O(1) in-memory dedup of already-mirrored pages | `force_refresh` clears only the selected host and replaces its banner blocks |
| Per-host state file (`<host>.<destination-key>_state.json`) | Crawled map + frontier queue for resume | `force_refresh` bypasses; invalid schema falls back to fresh |
| `seen` set (per crawl) | Prevents re-enqueueing discovered URLs | Per-crawl lifetime |

No HTTP response caching — every fetch is live (politeness-limited), by design:
mirrors should reflect the site at crawl time.

## Performance patterns in use

- **Batched parallel fetches** — one persistent 10-worker `ThreadPoolExecutor` per
  crawl (not per batch), throttled by the global rate limiter.
- **O(1) membership** everywhere URL dedup happens (set alongside the ordered list).
- **Append-per-page output** — explicit host refresh streams an atomic replacement, preserving other hosts and unknown bytes.
- **Atomic, throttled state saves** — every 30 s (`STATE_SAVE_INTERVAL`), not every
  page, and compact JSON (no indent).
- **Depth-boundary retention** — over-depth links remain queued without fetching; a later higher limit resumes them.

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

Clone assets use a deque and one URL identity per resource. Failed attempts are paced; finalization rewrites only written resources. No persistent HTTP response cache or semantic cache is created.
