#!/usr/bin/env bash
# Smoke-check production (or staging) HTTPS deploy.
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

# /api/send-unlock returns {sent:true} for anti-enumeration regardless of
# whether the send path is actually functional, so a silently-broken
# magic-link send can sit in production for days. Fail loud when auth is
# active but the dependent config is missing.
echo "GET ${BASE}/api/debug/diagnostics"
code=$(curl -sS -o /tmp/fellows_smoke_diag.txt -w "%{http_code}" "${BASE}/api/debug/diagnostics" || true)
if [[ "$code" != "200" ]]; then
  echo "FAIL: diagnostics expected HTTP 200, got ${code}"
  cat /tmp/fellows_smoke_diag.txt 2>/dev/null || true
  rm -f /tmp/fellows_smoke_diag.txt
  exit 1
fi
if ! python3 -c '
import json, sys
d = json.loads(open(sys.argv[1]).read())
if not d.get("fellowsDbPresent"):
    print("FAIL: fellows.db missing in dist")
    sys.exit(1)
if d.get("authActive"):
    miss = [k for k in ("sessionSecretConfigured", "postmarkTokenConfigured") if not d.get(k)]
    if miss:
        print("FAIL: authActive but missing: " + ", ".join(miss))
        sys.exit(1)
print("diagnostics OK (authActive=%s)" % d.get("authActive"))
' /tmp/fellows_smoke_diag.txt; then
  rm -f /tmp/fellows_smoke_diag.txt
  exit 1
fi
rm -f /tmp/fellows_smoke_diag.txt
