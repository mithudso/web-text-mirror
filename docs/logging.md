# Logging

## Approach

Single `log(msg)` helper: timestamped line (`[HH:MM:SS] message`) to stdout
(flushed) and appended to `crawl.log` (lock-guarded) once `LOG_FILE` is set by
`main()`. No log levels — every line is operational signal; verbosity is bounded by
crawl politeness (request-paced progress plus clone request/outcome events).

## Where logs go

- stdout (always)
- `crawl.log` next to the output file (`text-mirror/` by default; gitignored)
- HTTP request lines are suppressed (`log_message` pass) — API activity shows up as
  the crawl events it triggers, plus `save-error` lines

## Event vocabulary

| Line | Meaning |
|---|---|
| `Saved: <url> -> <file>` | Page extracted + appended (`/save` path) |
| `<host>: N pages saved, queue=…, seen=…` | Periodic crawl progress (state-save tick) |
| `<host>: DONE N pages, …` | Crawl finished |
| `robots-skip <url>` | robots.txt disallowed |
| `robots-unreachable <host>: … (assuming allow-all)` | robots.txt unreachable — fail-open |
| `skip-already-saved <url>` | Dedup hit |
| `no-content <url>` | Fetch returned nothing |
| `fetch-error` / `extract-error` / `link-parse-error` | Per-URL failures (crawl continues) |
| `state-load-error` / `force-refresh-remove-error` / `save-error` / `crawl-error` | Recoverable lifecycle failures |
| `Crawl cancelled by user.` | `/stop` honored |
| `[bootstrap] …` | Dependency self-install (print, pre-log) |

Important new failure paths emit observable errors; optional host-tool diagnostics remain local. See the external-call inventory for exact coverage.

## Adding logging

Call `log(f"...")` with a lowercase `kind <subject>: detail` shape matching the
table. Log every external call outcome and every state transition you add. The test
harness may assert on these lines — keep wording stable.

## Sensitive-data rules

Never log: env values, file contents, extracted page text, or anything from `.env`.
URLs may contain sensitive query parameters. Use public URLs without credentials or sensitive queries; local logs are operator data. The API logs request
*outcomes*, not request bodies.

Clone asset events are `clone-asset-request`, `clone-asset-ok` and `clone-asset-error <exception-type>`; tests assert failures and pacing. Optional agent jobs log start/finish and expose bounded history. No page body or model response is logged by new error paths. Existing core URL/path diagnostics remain local operator data.
