#!/usr/bin/env bash
# Explicitly provision the chosen interpreter using the repository requirements.
set -euo pipefail
PY="${PYTHON:-python3}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$PY" -m pip install -r "$SCRIPT_DIR/../requirements.txt"
"$PY" -c 'import trafilatura, lxml; print("[install] trafilatura", trafilatura.__version__, "lxml", lxml.__version__)'
