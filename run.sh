#!/usr/bin/env sh
# EHF Fellows directory server management.
# Usage: ./run.sh [start|stop|status|reset]
#   start  - Start server in background and open browser (default)
#   stop   - Stop the running server
#   status - Show whether the server is running
#   reset  - Rebuild DB from JSON, restart server

set -e
cd "$(dirname "$0")"

PIDFILE=".server.pid"
PORT=8765
DB="app/fellows.db"
# Prefer the venv's Python when `just setup` has been run. Bare `python3`
# (system) won't see dev-only deps like `cryptography` (needed for SW
# bundle-signing in dev — added in PR #146). Falls back to system
# `python3` when the venv isn't materialised yet (fresh clone).
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

server_pid() {
  # Return PID if server is running on our port, empty otherwise
  if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return
    fi
    rm -f "$PIDFILE"
  fi
  # Fallback: check port directly
  lsof -ti:"$PORT" 2>/dev/null | head -1
}

do_stop() {
  pid=$(server_pid)
  if [ -n "$pid" ]; then
    echo "Stopping server (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    # Force kill if still running
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    echo "Server stopped."
  else
    echo "Server is not running."
  fi
}

do_start() {
  pid=$(server_pid)
  if [ -n "$pid" ]; then
    echo "Server already running (PID $pid) at http://localhost:$PORT/"
    return
  fi
  if [ ! -f "$DB" ]; then
    echo "Database not found. Building from JSON..."
    "$PY" build/restore_from_knack_scrapefile.py
  fi
  "$PY" app/server.py &
  echo $! > "$PIDFILE"
  echo "Server started (PID $!) at http://localhost:$PORT/"
  sleep 1
  open "http://localhost:$PORT/" 2>/dev/null || true
}

do_status() {
  pid=$(server_pid)
  if [ -n "$pid" ]; then
    echo "Server is running (PID $pid) at http://localhost:$PORT/"
  else
    echo "Server is not running."
  fi
}

do_reset() {
  echo "Rebuilding database..."
  do_stop
  "$PY" build/restore_from_knack_scrapefile.py
  do_start
}

case "${1:-start}" in
  start)  do_start  ;;
  stop)   do_stop   ;;
  status) do_status ;;
  reset)  do_reset  ;;
  *)
    echo "Usage: $0 [start|stop|status|reset]"
    exit 1
    ;;
esac
