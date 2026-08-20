#!/usr/bin/env bash
# Ensure the web-text-mirror runtime dependency (trafilatura, which pulls lxml) is
# installed. The Python crawler also self-bootstraps, so this is optional but handy
# for pre-provisioning an environment.
set -euo pipefail

PY="${PYTHON:-python3}"

if "$PY" -c "import trafilatura" >/dev/null 2>&1; then
  echo "[install] trafilatura already present: $("$PY" -c 'import trafilatura; print(trafilatura.__version__)')"
else
  echo "[install] installing trafilatura (+lxml) via pip..."
  "$PY" -m pip install --quiet --upgrade trafilatura
  echo "[install] done: $("$PY" -c 'import trafilatura; print(trafilatura.__version__)')"
fi
