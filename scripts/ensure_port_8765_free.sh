#!/usr/bin/env sh
# Free port 8765 so server-dependent tests can run (M2 API tests, e2e Playwright).
# Run from repo root. Safe to run even if nothing is listening.
# Usage: ./scripts/ensure_port_8765_free.sh [pytest args...]
#   No args: just free the port and exit.
#   With args: free port, then run pytest with those args (e.g. tests/e2e/ -v).

set -e
cd "$(dirname "$0")/.."
if lsof -ti:8765 >/dev/null 2>&1; then
  echo "Stopping process on port 8765..."
  lsof -ti:8765 | xargs kill -9 2>/dev/null || true
  sleep 1
fi
if [ $# -gt 0 ]; then
  exec .venv/bin/pytest "$@"
fi
