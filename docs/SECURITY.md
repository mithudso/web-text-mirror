# Security

## Trust boundaries and principals

| Boundary | Untrusted side | Trusted side |
|---|---|---|
| Local HTTP API (127.0.0.1:8765) | Anything that can reach loopback: other local processes, and — via the browser — any web page issuing cross-origin requests | The crawler process |
| Fetched web content | Target sites' HTML | lxml/trafilatura parsers |
| Filesystem | Browser-supplied `out_file` values | Output base directory |
| PyPI (bootstrap) | Package index | Local interpreter |

Principals: the operator (full trust), the bundled Chrome extension
(`chrome-extension://` origin — trusted client), everything else on the network
(untrusted).

## Authentication and authorization

The API has no credentials; it relies on three enforced invariants:

1. **Bind 127.0.0.1 only** (`run_server`) — nothing off-machine can connect.
2. **Origin allowlist** (`_origin_ok`) — requests with an `Origin` header are
   rejected unless it is `chrome-extension://`/`moz-extension://` or loopback
   (`localhost`/`127.0.0.1`/`::1`). `Origin: null` (sandboxed iframes) is rejected;
   header-less clients (curl, scripts) are allowed. Browsers always attach `Origin`
   to cross-origin requests and extensions cannot be impersonated by web pages, so
   drive-by pages cannot command the API.
3. **Output confinement** (`client_out_file`) — browser-supplied `out_file` is
   reduced to a basename inside the output base dir; empty/dot/traversal/null-byte
   names and collisions with existing directories are rejected.

## Secret management

No secrets exist in this project. `.env` is gitignored defensively; never log or
commit tokens.

## Input validation

- HTTP bodies: JSON parse + required-field checks → 400; non-integer `max_depth`
  coerced to 0; `/save` failures → 500 with logged reason.
- URLs: scheme restricted to http/https and host-matched in `wanted()`; skip lists
  drop auth/asset/action URLs.
- Fetched HTML: parsed by lxml/trafilatura; parse failures are caught and logged.

## STRIDE mitigations

| Threat | Mitigation |
|---|---|
| Spoofing (web page posing as extension) | Origin allowlist; extensions' origins are browser-enforced |
| Tampering (state/output corruption) | Atomic state writes (`os.replace`); locks around shared state |
| Repudiation | `crawl.log` records every save/skip/error with timestamps |
| Information disclosure | Server binds loopback; responses expose only crawl metadata |
| DoS (wedging the crawler) | Single-flight guard with guaranteed `CRAWL_ACTIVE` reset; handler exceptions → HTTP errors, not crashes |
| Elevation (arbitrary file write) | `client_out_file` confinement; CLI `--out` is operator-trusted by design |

Residual risk (accepted): any *local* process can drive the API — the API's
capability equals what the same local user could do anyway. SSRF-style fetches of
internal URLs are inherent to a crawler; the Origin gate blocks the browser as a
confused deputy, and header-less local callers are already trusted.

## Bootstrap supply chain

`ensure_deps()` pip-installs unpinned trafilatura/lxml at first import, escalating to
`--break-system-packages`. This is a deliberate usability trade-off for the
skill-packaging use case; `requirements.txt` documents floor versions and
`scripts/install.sh` is the explicit alternative. Pin exact versions if you need
reproducibility.

## Contributor checklist

- [ ] Does the change touch `run_server`, `_origin_ok`, or `client_out_file`? →
      security review + tests.
- [ ] New shared state → which lock guards it?
- [ ] New external input (HTTP field, env var, file) → validated where it enters?
- [ ] Nothing sensitive logged.

## Incident response

Logs: stdout + `crawl.log` next to the output file. Contact: repository owner
(@mithudso) via GitHub security advisory (see `.github/SECURITY.md`).

## Compliance

Crawls public content only; obeys robots.txt (401/403 → disallow); no PII is
collected beyond what target pages publish.
