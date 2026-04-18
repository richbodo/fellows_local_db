#!/usr/bin/env bash
# Reference repair for /etc/fellows/fellows-pwa.env on the app server.
#
# Kept as a template for future env-file incidents. The original incident
# (April 2026) was a malformed file where FELLOWS_POSTMARK_TOKEN= sat on
# its own line with the value on the following line, so systemd loaded an
# empty token and /api/send-unlock silently no-op'd after the
# anti-enumeration 200 for several days. Root cause of the malformation
# was never identified - scripts/configure_email_auth_env.sh uses
# `read -r -s` and a heredoc that shouldn't produce this shape, so a
# manual edit (e.g. during a token rotation) is the working hypothesis.
# If you see /api/debug/diagnostics reporting postmarkTokenConfigured
# false despite a populated env file, adapt this script.
#
# Uploads a small remote script to /tmp, runs it with sudo on an interactive
# ssh session (so sudo gets a real tty to prompt for the password), then
# cleans up. Requires your sudo password on the droplet; you'll be prompted.

set -euo pipefail

HOST="${FELLOWS_HOST:-170.64.243.67}"
PORT="${FELLOWS_SSH_PORT:-52221}"
USER="${FELLOWS_SSH_USER:-rsb}"

LOCAL_REMOTE_SCRIPT="$(mktemp -t fellows-repair.XXXXXX.sh)"
trap 'rm -f "$LOCAL_REMOTE_SCRIPT"' EXIT

cat >"$LOCAL_REMOTE_SCRIPT" <<'REMOTE'
#!/usr/bin/env bash
set -euo pipefail
ts=$(date +%Y%m%d-%H%M%S)
cp -p /etc/fellows/fellows-pwa.env "/etc/fellows/fellows-pwa.env.bak.${ts}"
sed -i -E '/^FELLOWS_POSTMARK_TOKEN=$/{N;s/=\n/=/}' /etc/fellows/fellows-pwa.env
echo "--- shape after fix (no values printed) ---"
awk -F= 'NF>=2{printf "%s= [len=%d]\n", $1, length($0)-length($1)-1} NF<2{print "ORPHAN: "$0}' /etc/fellows/fellows-pwa.env
ls -l /etc/fellows/fellows-pwa.env "/etc/fellows/fellows-pwa.env.bak.${ts}"
systemctl restart fellows-pwa
sleep 2
echo "--- service status ---"
systemctl is-active fellows-pwa
REMOTE

REMOTE_PATH="/tmp/fellows-repair.$$.sh"

echo "Uploading repair script to ${USER}@${HOST}:${REMOTE_PATH}..."
scp -P "${PORT}" "$LOCAL_REMOTE_SCRIPT" "${USER}@${HOST}:${REMOTE_PATH}"

echo "Running remote script with sudo (will prompt for password)..."
ssh -t -p "${PORT}" "${USER}@${HOST}" "sudo bash '${REMOTE_PATH}'; rm -f '${REMOTE_PATH}'"

echo
echo "Done. Paste the output above and I'll verify /api/debug/diagnostics."
