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
