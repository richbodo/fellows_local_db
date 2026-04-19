#!/usr/bin/env bash
# Dump /etc/fellows/fellows-pwa.env from prod, with secrets masked.
#
# Requires sudo on the droplet (same permissions as restarting the service).
# Reads the env file via `ssh -tt sudo cat`, then masks values whose KEY
# matches TOKEN/SECRET/PASSWORD/KEY/CREDENTIAL patterns. Pass --raw to
# show secrets in full.
#
# Environment overrides (match Ansible inventory):
#   FELLOWS_HOST       default: fellows.globaldonut.com
#   FELLOWS_SSH_PORT   default: 52221
#   FELLOWS_SSH_USER   default: rsb
#   FELLOWS_ENV_FILE   default: /etc/fellows/fellows-pwa.env
#
# Usage:
#   scripts/show_server_env.sh           # masked
#   scripts/show_server_env.sh --raw     # unmasked (careful — prints secrets)

set -euo pipefail

HOST="${FELLOWS_HOST:-fellows.globaldonut.com}"
PORT="${FELLOWS_SSH_PORT:-52221}"
USER_="${FELLOWS_SSH_USER:-rsb}"
ENV_FILE="${FELLOWS_ENV_FILE:-/etc/fellows/fellows-pwa.env}"

RAW=0
case "${1:-}" in
  --raw) RAW=1 ;;
  -h|--help)
    sed -n '1,/^set -euo/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") : ;;
  *)
    echo "unknown argument: $1" >&2
    exit 2
    ;;
esac

# -tt forces a pty so sudo's password prompt reaches the terminal.
# tr -d '\r' strips the CRs the pty introduces so we can parse cleanly.
ssh -tt -p "$PORT" "$USER_@$HOST" "sudo cat $(printf '%q' "$ENV_FILE")" \
  | tr -d '\r' \
  | awk -v raw="$RAW" '
      BEGIN { FS = "=" }
      /^[[:space:]]*$/  { print; next }
      /^[[:space:]]*#/  { print; next }
      {
        key = $1
        val = substr($0, length(key) + 2)
        # strip surrounding single or double quotes
        if (val ~ /^".*"$/) val = substr(val, 2, length(val) - 2)
        else if (val ~ /^'"'"'.*'"'"'$/) val = substr(val, 2, length(val) - 2)

        if (raw == 0 && key ~ /(TOKEN|SECRET|PASSWORD|CREDENTIAL|_KEY$)/) {
          n = length(val)
          if (n > 8)      masked = substr(val, 1, 4) "…" substr(val, n - 2, 3)
          else if (n > 0) masked = "[REDACTED:" n "chars]"
          else            masked = ""
          val = masked
        }
        printf "%s=%s\n", key, val
      }
    '
