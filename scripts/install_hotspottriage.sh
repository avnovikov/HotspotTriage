#!/bin/sh
# Install HotspotTriage from a clone (editable). DeepCSIM is required; it only publishes
# wheels for Python >=3.11,<3.14 — using 3.14+ yields "No matching distribution" on pip.
#
# Usage:
#   ./scripts/install_hotspottriage.sh              # system/user Python from PATH
#   ./scripts/install_hotspottriage.sh --venv        # create or reuse .venv in repo root
#   ./scripts/install_hotspottriage.sh --uv          # uv sync (needs uv + uv.lock)
#   ./scripts/install_hotspottriage.sh --python /usr/local/bin/python3.13
#
# Env: PYTHON=path  same as --python
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

USE_VENV=0
USE_UV=0
PY_CMD=""

usage() {
  echo "usage: install_hotspottriage.sh [--venv] [--uv] [--python PATH]" >&2
  echo "  Requires Python >=3.11 and <3.14 (deepcsim). Windows: use Git Bash or create .venv manually." >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --venv) USE_VENV=1 ;;
    --uv) USE_UV=1 ;;
    --python)
      shift
      PY_CMD=${1:-}
      [ -n "$PY_CMD" ] || usage
      ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
  shift
done

if [ -n "${PYTHON:-}" ] && [ -z "$PY_CMD" ]; then
  PY_CMD=$PYTHON
elif [ -z "$PY_CMD" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_CMD=python3
  elif command -v python >/dev/null 2>&1; then
    PY_CMD=python
  else
    echo "install_hotspottriage: no python3/python on PATH; set PYTHON=/path/to/python3.13" >&2
    exit 1
  fi
fi

if ! command -v "$PY_CMD" >/dev/null 2>&1; then
  echo "install_hotspottriage: interpreter not found: $PY_CMD" >&2
  exit 1
fi

PY_REAL=$(command -v "$PY_CMD")

"$PY_REAL" -c "
import sys
v = sys.version_info[:2]
if v < (3, 11) or v >= (3, 14):
    sys.stderr.write(
        'install_hotspottriage: need Python >=3.11 and <3.14 (required by deepcsim on PyPI). '
        'This interpreter is %s.%s.\n'
        'Fix: install Python 3.13 / 3.12 / 3.11 and pass --python or set PYTHON.\n'
        % (sys.version_info.major, sys.version_info.minor)
    )
    sys.exit(1)
"

if [ "$USE_VENV" -eq 1 ]; then
  VENV_DIR="$REPO_ROOT/.venv"
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PY_REAL" -m venv "$VENV_DIR"
  fi
  PY_REAL="$VENV_DIR/bin/python"
fi

if [ "$USE_UV" -eq 1 ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "install_hotspottriage: --uv requested but uv is not on PATH" >&2
    exit 1
  fi
  if [ ! -f "$REPO_ROOT/uv.lock" ]; then
    echo "install_hotspottriage: uv.lock missing; run uv lock in the repo or omit --uv" >&2
    exit 1
  fi
  echo "install_hotspottriage: uv sync --python $PY_REAL" >&2
  uv sync --python "$PY_REAL"
  exit 0
fi

echo "install_hotspottriage: upgrading pip; installing package editable from $REPO_ROOT" >&2
"$PY_REAL" -m pip install --upgrade pip
"$PY_REAL" -m pip install -e "$REPO_ROOT"

echo "install_hotspottriage: done. Try: $PY_REAL -m hotspottriage --help" >&2
