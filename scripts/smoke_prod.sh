#!/usr/bin/env bash
# Smoke-check production (or staging) HTTPS deploy. See plans/pwa_release_plan.md Phase 3.
# Usage:
#   ./scripts/smoke_prod.sh
#   FELLOWS_BASE_URL=https://fellows.globaldonut.com ./scripts/smoke_prod.sh
set -euo pipefail
BASE="${FELLOWS_BASE_URL:-https://fellows.globaldonut.com}"
BASE="${BASE%/}"

echo "GET ${BASE}/healthz"
code=$(curl -sS -o /tmp/fellows_smoke_healthz.txt -w "%{http_code}" "${BASE}/healthz" || true)
body=$(cat /tmp/fellows_smoke_healthz.txt 2>/dev/null || true)
rm -f /tmp/fellows_smoke_healthz.txt
if [[ "$code" != "200" ]]; then
  echo "FAIL: expected HTTP 200, got ${code}"
  echo "$body"
  exit 1
fi
echo "OK (${code})"

echo "GET ${BASE}/manifest.webmanifest"
code=$(curl -sS -D /tmp/fellows_smoke_mf.hdr -o /tmp/fellows_smoke_mf.txt -w "%{http_code}" "${BASE}/manifest.webmanifest" || true)
body_head=$(head -c 5 /tmp/fellows_smoke_mf.txt 2>/dev/null || true)
rm -f /tmp/fellows_smoke_mf.txt /tmp/fellows_smoke_mf.hdr
if [[ "$code" != "200" ]]; then
  echo "FAIL: manifest expected HTTP 200, got ${code}"
  exit 1
fi
if [[ "$body_head" != "{"* ]]; then
  echo "FAIL: manifest body does not look like JSON"
  exit 1
fi
echo "OK manifest (${code})"
