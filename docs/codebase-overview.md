# Codebase Overview

## / (root)

| File | Purpose | Layer |
|---|---|---|
| `README.md` | Entry point: features, quick start, doc links | docs |
| `SKILL.md` | Claude-skill packaging (frontmatter + usage) — mirrors real CLI flags | docs |
| `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md` | Agent workflow rules (CLAUDE.md canonical) | tooling |
| `memory.md` / `prompts.md` | Operator work log / prompt log | tooling |
| `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` | Community | docs |
| `requirements.txt` | trafilatura + lxml floor pins | config |
| `.editorconfig` / `.gitattributes` / `.gitignore` / `.env.example` | Repo hygiene | config |

## /scripts

| File | Purpose | Layer |
|---|---|---|
| `text_mirror.py` | The whole engine: BFS crawler, trafilatura extraction, atomic per-host state, local HTTP API (127.0.0.1:8765), CLI. Key functions: `crawl`/`_crawl_impl`, `fetch_and_extract`, `process_single_url`, `PluginServerHandler`, `get_robots`, `_throttle`, `client_out_file`, `_origin_ok` | backend |
| `install.sh` | Optional pre-provisioning of trafilatura (`PYTHON=` override) | tooling |

## /chrome-plugin

| File | Purpose | Layer |
|---|---|---|
| `manifest.json` | MV3 manifest: sidePanel + activeTab + scripting | frontend |
| `background.js` | Toolbar click → open side panel | frontend |
| `sidepanel.html` | Panel UI (crawl toggle, depth, force-refresh, out-file, saved list) | frontend |
| `sidepanel.js` | Captures tab DOM, POSTs `/save`//`/crawl`, polls `/list` @1 Hz | frontend |

## /tests

| File | Purpose | Layer |
|---|---|---|
| `test_text_mirror.py` | Self-contained unit + functional harness (localhost only) | test |

## /docs

This documentation suite (see `README.md` for the index). `docs/runbooks/` holds
operational procedures.

## Generated / ignored

`text-mirror/` (crawl output + `crawl.log` + `*_state.json`), `venv/`, `build/`,
`dist/`, `*.spec` — all gitignored, never edit by hand.
