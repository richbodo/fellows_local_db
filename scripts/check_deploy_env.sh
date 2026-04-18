#!/usr/bin/env bash
# Optional DNS + TLS sanity check before or after deploy.
# Usage:
#   ./scripts/check_deploy_env.sh
#   FELLOWS_HOST=fellows.globaldonut.com ./scripts/check_deploy_env.sh
set -euo pipefail
HOST="${FELLOWS_HOST:-fellows.globaldonut.com}"

echo "== A record for ${HOST} =="
dig +short "${HOST}" A || true

echo ""
echo "== HTTPS response headers (first lines) =="
curl -fsSI "https://${HOST}/" 2>/dev/null | head -20 || {
  echo "curl failed (DNS, TLS, or origin not reachable)."
  exit 1
}

echo ""
echo "== /healthz =="
curl -fsS "https://${HOST}/healthz" && echo ""
