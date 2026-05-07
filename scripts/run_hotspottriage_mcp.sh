#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/alexei/HotspotTriage"
VENV_BIN="$REPO_DIR/.venv/bin"

if [[ ! -x "$VENV_BIN/python" ]]; then
  echo "error: missing venv at $REPO_DIR/.venv (run: python3 -m venv .venv && .venv/bin/pip install -e .)" >&2
  exit 1
fi

# Serena-style deterministic runtime: always resolve tools from this venv first.
export PATH="$VENV_BIN:$PATH"

exec "$VENV_BIN/hotspottriage" start-mcp-server "$@"
