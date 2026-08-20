# Installation

## Prerequisites

- macOS or Linux (Windows unverified — see docs/known-issues.md #8)
- Python ≥ 3.9 with pip
- Chrome (only if you want the extension)

## Install

**Option A — zero-install (self-bootstrap).** Just run it; on first start it pip-installs
trafilatura/lxml into the current interpreter if missing:

```bash
python3 scripts/text_mirror.py https://example.org/ --max-depth 1
```

**Option B — venv (recommended for development):**

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

**Option C — pre-provision an interpreter:**

```bash
bash scripts/install.sh                      # uses python3
PYTHON=/path/to/python bash scripts/install.sh
```

## Chrome extension

1. `python3 scripts/text_mirror.py --serve` (leaves the API on 127.0.0.1:8765)
2. `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select
   `chrome-plugin/`
3. Click the toolbar icon → side panel opens.

## Verify

```bash
python3 -m py_compile scripts/text_mirror.py           # no output = OK
python3 tests/test_text_mirror.py                      # ends with ALL PASS
python3 scripts/text_mirror.py https://example.org/ --max-depth 1
ls text-mirror/                                        # example.org.md + crawl.log
```

## Upgrade

```bash
git pull
pip install -U -r requirements.txt
```

Extension: `chrome://extensions` → reload the unpacked extension.

## Uninstall

Delete the repo clone; remove the unpacked extension in `chrome://extensions`;
`pip uninstall trafilatura lxml` if you installed them globally. Crawl output lives
only under your chosen `--out` locations.
