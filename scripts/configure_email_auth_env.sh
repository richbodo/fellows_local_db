#!/usr/bin/env bash
# Interactive helper to configure magic-link email auth env on app server.
# Run from local dev machine.

set -euo pipefail

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  if [[ -z "$value" ]]; then
    value="$default"
  fi
  printf '%s\n' "$value"
}

prompt_required() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt: " value
  done
  printf '%s\n' "$value"
}

prompt_secret_required() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -s -p "$prompt: " value
    echo
  done
  printf '%s\n' "$value"
}

generate_session_secret() {
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

require_cmd ssh
require_cmd scp
require_cmd python3

echo "Configure fellows email auth environment on app server"
echo "Use an SSH user that has full sudo privileges (typically your operator user)."
echo "Do not use deploy unless it has additional sudo rights beyond service restart/status."
echo

host="$(prompt_required "App server hostname or IP")"
port="$(prompt_default "SSH port" "52221")"
ssh_user="$(prompt_default "SSH user" "rsb")"

echo
echo "Environment values for /etc/fellows/fellows-pwa.env"
mail_from="$(prompt_required "FELLOWS_MAIL_FROM (verified Postmark sender)")"
public_origin="$(prompt_required "FELLOWS_PUBLIC_ORIGIN (https://your-domain)")"
postmark_token="$(prompt_secret_required "FELLOWS_POSTMARK_TOKEN (input hidden)")"

default_secret="$(generate_session_secret)"
read -r -p "Generate FELLOWS_SESSION_SECRET now? [Y/n]: " gen_secret
if [[ -z "${gen_secret}" || "${gen_secret}" =~ ^[Yy]$ ]]; then
  session_secret="$default_secret"
  echo "Generated session secret."
else
  session_secret="$(prompt_secret_required "FELLOWS_SESSION_SECRET (input hidden)")"
fi

echo
echo "Will configure host ${ssh_user}@${host}:${port}"
echo "  FELLOWS_MAIL_FROM=${mail_from}"
echo "  FELLOWS_PUBLIC_ORIGIN=${public_origin}"
echo "  FELLOWS_POSTMARK_TOKEN=<hidden>"
echo "  FELLOWS_SESSION_SECRET=<hidden>"
read -r -p "Continue? [y/N]: " confirm
if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

tmp_env="$(mktemp)"
trap 'rm -f "$tmp_env"' EXIT
chmod 600 "$tmp_env"

cat >"$tmp_env" <<EOF
FELLOWS_SESSION_SECRET=$session_secret
FELLOWS_POSTMARK_TOKEN=$postmark_token
FELLOWS_MAIL_FROM=$mail_from
FELLOWS_PUBLIC_ORIGIN=$public_origin
EOF

remote_tmp="/tmp/fellows-pwa.env.$$"

echo
echo "Uploading env file to app server..."
scp -P "$port" "$tmp_env" "${ssh_user}@${host}:${remote_tmp}"

echo "Installing env file, systemd drop-in, and restarting service..."
ssh -t -p "$port" "${ssh_user}@${host}" "set -euo pipefail; \
  sudo install -d -m 0750 -o root -g deploy /etc/fellows; \
  sudo mv \"$remote_tmp\" /etc/fellows/fellows-pwa.env; \
  sudo chown root:deploy /etc/fellows/fellows-pwa.env; \
  sudo chmod 0640 /etc/fellows/fellows-pwa.env; \
  sudo install -d -m 0755 /etc/systemd/system/fellows-pwa.service.d; \
  printf '[Service]\nEnvironmentFile=/etc/fellows/fellows-pwa.env\n' | sudo tee /etc/systemd/system/fellows-pwa.service.d/10-env-file.conf >/dev/null; \
  sudo systemctl daemon-reload; \
  sudo systemctl restart fellows-pwa; \
  sudo systemctl status fellows-pwa --no-pager"

echo
echo "Done. Auth env is configured and fellows-pwa has been restarted."
