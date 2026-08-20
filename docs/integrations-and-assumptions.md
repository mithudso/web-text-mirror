# Integrations and Assumptions

## External services and calls

| What | Where in code | Data in/out |
|---|---|---|
| Target websites (HTTP GET) | `trafilatura.fetch_url` in `fetch_and_extract` / `process_single_url` | URL out; HTML in |
| Per-host `robots.txt` | `urllib.request.urlopen` in `get_robots` (30 s timeout) | robots rules in |
| PyPI (pip) | `subprocess.check_call` in `ensure_deps` (import-time, only when deps missing) | packages in |
| Local API ⇄ Chrome extension | `PluginServerHandler` ⇄ `chrome-plugin/sidepanel.js` on `http://localhost:8765` | JSON both ways |

Full per-call inventory with policies: `docs/external-calls.md`.

## External tools

- `python3` ≥ 3.9, `pip`
- Chrome (extension only)
- `ruff` (dev lint)

## Hardcoded assumptions

| Value | Where | Breaks if |
|---|---|---|
| Port `8765`, bind `127.0.0.1` (`PORT`) | `run_server` | Another process owns the port (server thread dies with `Address already in use`) |
| `MAX_WORKERS = 10` | module const | Very slow hosts → long tail per batch |
| `ROBOTS_TIMEOUT = 30`, `DOWNLOAD_TIMEOUT = 30` | module const / CFG | Extremely slow sites time out |
| `STATE_SAVE_INTERVAL = 30` s | module const | Crash loses ≤30 s of crawl bookkeeping (output itself is append-per-page) |
| Default out `text-mirror/<host>.md` | `get_out_file` | — |
| UA `trafilatura-text-mirror/1.0 (+public-archive)` | `UA` | Sites that block unknown UAs |
| Extension talks to `http://localhost:8765` | `sidepanel.js` (hardcoded) | Port/host changes must be made in both places |

## Environment-specific behavior

- `ensure_deps` escalates pip strategies (`--user`, `--break-system-packages`) for
  PEP 668 externally-managed environments (e.g. Homebrew Python).
- No dev/prod split — single-machine operator tool.
- Windows: untested; paths use `os.path` throughout, but file-encoding defaults and
  the `install.sh` script assume a POSIX shell. `# TODO:` verify on Windows if ever needed.
