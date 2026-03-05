#!/usr/bin/env sh
# Start EHF Fellows directory server and open browser.
# Run from repo root.

cd "$(dirname "$0")"
(sleep 1 && open "http://localhost:8765/" 2>/dev/null) &
exec python3 app/server.py
