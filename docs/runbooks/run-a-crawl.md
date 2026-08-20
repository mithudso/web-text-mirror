# Runbook: Run a Crawl

## Standard crawl

```bash
python3 scripts/text_mirror.py https://wiki.example.org/
# output: text-mirror/wiki.example.org.md, crawl.log, wiki.example.org_state.json
```

## Long / large site

```bash
nohup python3 scripts/text_mirror.py https://forum.example.org/ --max-depth 3 \
  --out out/forum.md --delay 1.5 > /dev/null 2>&1 &
tail -f out/crawl.log
```

- Prefer a `--max-depth` cap on forums/wikis (URL spaces explode).
- Watch for `robots-skip` floods (site disallows crawling — stop) and
  `no-content` floods (site blocking the UA or JS-only pages).

## Interrupt / resume

- Ctrl+C (or kill) any time — output is append-per-page; state saves every 30 s.
- Re-run the same command: `Resumed from state: N in queue, M crawled.` continues
  the frontier and skips saved pages.

## Redo from scratch

Via the extension, tick **Force refresh** (clears saved set, removes the output
file). CLI equivalent: delete the output file and `<host>_state.json`, then re-run.

## Multiple sites into one file

```bash
python3 scripts/text_mirror.py https://a.example/ https://b.example/ --out corpus.md
```

Each host keeps its own state file; crawls run sequentially (single-flight).

## Health checks during a run

- `tail -f` the `crawl.log`: progress lines every 30 s (`N pages saved, queue=…`).
- `curl -s http://127.0.0.1:8765/list | python3 -m json.tool` when running with
  `--serve` — live stats.

## When it goes wrong

| Symptom | Do |
|---|---|
| `DONE 0 pages` + robots-skips | Site disallows; respect it |
| `robots-read-error … assuming allow-all` | Expected for http-only/unreachable robots — crawl proceeds |
| Only 1 page saved | Seed likely redirects off-host; pass the canonical host as seed |
| Output has `[no extractable text]` blocks | Pages are JS-rendered — use the extension `/save` path |
