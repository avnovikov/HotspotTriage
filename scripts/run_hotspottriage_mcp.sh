#!/bin/sh
# POSIX shell — avoids /usr/bin/env bash on hosts with no bash (some containers / minimal images).
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
VENV_BIN="$REPO_DIR/.venv/bin"

if [ ! -x "$VENV_BIN/python" ]; then
  echo "error: missing venv at $REPO_DIR/.venv (run: python3 -m venv .venv && .venv/bin/pip install -e .)" >&2
  exit 1
fi

# Serena-style deterministic runtime: always resolve tools from this venv first.
# Cursor (and other MCP hosts) often spawn subprocesses with a stripped PATH, so `git`
# is missing unless we include usual system locations (macOS Homebrew, Xcode CLT, Linux).
_HOTSPOTTRIAGE_SYSTEM_PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
export PATH="$VENV_BIN:$_HOTSPOTTRIAGE_SYSTEM_PATH:${PATH:-}"

exec "$VENV_BIN/hotspottriage" start-mcp-server "$@"
