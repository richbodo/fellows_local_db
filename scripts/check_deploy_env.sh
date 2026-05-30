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
echo "== CAA records (authorize only Let's Encrypt for ${HOST}) =="
# CAA resolution walks UP from the queried name and the FIRST record set found
# is authoritative (it does not merge with ancestors). We scope CAA to the host
# itself rather than the apex, because the apex zone may legitimately use other
# CAs for other subdomains — see docs/DevOps.md § Supporting DNS: CAA records.
# Check the host first; if it has no records, report that it inherits the apex.
APEX="$(echo "${HOST}" | rev | cut -d. -f1,2 | rev)"
host_caa="$(dig +short CAA "${HOST}" || true)"
if [ -n "${host_caa}" ]; then
  level="${HOST}"; caa="${host_caa}"
else
  level="${APEX} (inherited — ${HOST} has no CAA of its own)"
  caa="$(dig +short CAA "${APEX}" || true)"
fi
if [ -z "${caa}" ]; then
  echo "WARNING: no CAA records effective for ${HOST} — ANY CA may issue its cert."
  echo "  Fix: add the records in docs/DevOps.md § Supporting DNS: CAA records (scope: ${HOST})."
else
  echo "effective at: ${level}"
  echo "${caa}"
  if echo "${caa}" | grep -q 'issue "letsencrypt.org"'; then
    echo "OK: Let's Encrypt is authorized."
  else
    echo "WARNING: CAA present but does NOT authorize letsencrypt.org — Caddy renewals may fail."
  fi
  others="$(echo "${caa}" | grep -E 'issue(wild)? ' | grep -vE 'letsencrypt.org|issue(wild)? ";"' || true)"
  if [ -n "${others}" ]; then
    echo "NOTE: another CA is also authorized to issue for this name:"
    echo "${others}"
  fi
fi

echo ""
echo "== /healthz =="
curl -fsS "https://${HOST}/healthz" && echo ""
