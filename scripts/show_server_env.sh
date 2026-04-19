#!/usr/bin/env bash
# Dump /etc/fellows/fellows-pwa.env from prod — values shown raw so you can
# copy-paste secrets (e.g. FELLOWS_POSTMARK_TOKEN) straight into a command.
# This is a single-dev local tool; there's no shoulder surfing to defend
# against. If you ever share your screen, close this terminal first.
#
# Prompts locally for your sudo password (hidden input) and pipes it to
# remote `sudo -S`. Surrounding quotes on values are stripped so the output
# is paste-ready.
#
# Environment overrides (match Ansible inventory):
#   FELLOWS_HOST       default: fellows.globaldonut.com
#   FELLOWS_SSH_PORT   default: 52221
#   FELLOWS_SSH_USER   default: rsb
#   FELLOWS_ENV_FILE   default: /etc/fellows/fellows-pwa.env
#
# Usage:
#   scripts/show_server_env.sh

set -euo pipefail

HOST="${FELLOWS_HOST:-fellows.globaldonut.com}"
PORT="${FELLOWS_SSH_PORT:-52221}"
USER_="${FELLOWS_SSH_USER:-rsb}"
ENV_FILE="${FELLOWS_ENV_FILE:-/etc/fellows/fellows-pwa.env}"

case "${1:-}" in
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

# Hidden-input read. -s suppresses echo; prompt on stderr so stdout stays
# clean for piping to clipboard tools.
printf "sudo password for %s@%s: " "$USER_" "$HOST" >&2
IFS= read -rs SUDO_PW
printf "\n" >&2

# `sudo -S` reads the password from stdin. `-p ''` silences sudo's prompt
# text so nothing lands in the env-file stream.
REMOTE_CMD="sudo -S -p '' cat $(printf '%q' "$ENV_FILE")"

printf '%s\n' "$SUDO_PW" \
  | ssh -o BatchMode=no -p "$PORT" "$USER_@$HOST" "$REMOTE_CMD" \
  | awk '
      BEGIN { FS = "=" }
      /^[[:space:]]*$/  { print; next }
      /^[[:space:]]*#/  { print; next }
      {
        key = $1
        val = substr($0, length(key) + 2)
        # strip surrounding single or double quotes so values are paste-ready
        if (val ~ /^".*"$/) val = substr(val, 2, length(val) - 2)
        else if (val ~ /^'"'"'.*'"'"'$/) val = substr(val, 2, length(val) - 2)
        printf "%s=%s\n", key, val
      }
    '
