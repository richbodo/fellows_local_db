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

# Security headers the edge MUST preserve. COOP/COEP are load-bearing:
# the OPFS-SAH-Pool VFS that holds relationships.db + fellows.db refuses
# to install without crossOriginIsolated=true, and a reverse-proxy that
# strips them is a silent "Settings has no backup/restore" failure
# (docs/DevOps.md § Architecture). HSTS is part of the prod TLS contract
# (Caddy sets it; the Python server does not) — only asserted for https
# targets so this stays valid against the plain-http local-staging server.
# Use GET with header dump (-D -) rather than HEAD: the stdlib server
# implements do_GET, not do_HEAD.
echo "GET ${BASE}/ (security headers)"
hdrs=$(curl -sS -D - -o /dev/null "${BASE}/" || true)
missing=""
echo "$hdrs" | grep -qiE '^cross-origin-opener-policy:[[:space:]]*same-origin' \
  || missing="${missing} Cross-Origin-Opener-Policy"
echo "$hdrs" | grep -qiE '^cross-origin-embedder-policy:[[:space:]]*require-corp' \
  || missing="${missing} Cross-Origin-Embedder-Policy"
if [[ "$BASE" == https://* ]]; then
  echo "$hdrs" | grep -qiE '^strict-transport-security:.*max-age=' \
    || missing="${missing} Strict-Transport-Security"
fi
if [[ -n "$missing" ]]; then
  echo "FAIL: missing/unexpected security headers:${missing}"
  echo "$hdrs" | grep -iE 'strict-transport|cross-origin' || echo "(none present)"
  exit 1
fi
echo "OK security headers (COOP + COEP$([[ "$BASE" == https://* ]] && echo ' + HSTS'))"
