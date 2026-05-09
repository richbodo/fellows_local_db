#!/usr/bin/env bash
# Interactive helper to configure magic-link email auth env on app server.
# Run from local dev machine.
#
# When the env file already exists on the target host, this script
# fetches it (via sudo cat) and offers each current value as the
# default at the corresponding prompt. Press Enter to keep what's
# there; type a new value to replace. This avoids the "retype the
# whole 64-char Postmark token correctly" failure mode that has
# bitten the maintainer at least once — paste artefacts and one-off
# typos are how `/etc/fellows/fellows-pwa.env` ends up malformed.
#
# Also validates FELLOWS_MAIL_FROM up front: bare address or
# RFC 5322 mailbox (`Display Name <addr>`). Quoted-display-name
# without angle-bracketed address — the format that mangled into
# `EHF Local Directory <Appadmin@…>` on 2026-05-09 — is rejected
# at the prompt rather than uploaded and mailed from broken.

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

# Required-with-default variant: shows the default in the prompt; an
# empty response keeps the default. If the default is empty the
# prompt loops until the user types something — same as
# prompt_required.
prompt_required_with_default() {
  local prompt="$1"
  local default="$2"
  local value
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value
    if [[ -z "$value" ]]; then
      value="$default"
    fi
  else
    while [[ -z "$value" ]]; do
      read -r -p "$prompt: " value
    done
  fi
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

# Secret-or-keep: prompts hidden; empty response means "keep the
# existing value" (which the caller has already loaded). Never
# echoes the existing value to the terminal.
prompt_secret_or_keep() {
  local prompt="$1"
  local value
  read -r -s -p "$prompt (Enter to keep current): " value
  echo
  printf '%s\n' "$value"
}

generate_session_secret() {
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

# The allowlist HMAC key is symmetric and only needs to be unguessable.
# Same generation as the session secret (urlsafe base64 of 48 random bytes).
generate_hmac_key() {
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

# True if VALUE is a usable From-header: either a bare RFC 5322
# addr-spec (`local@domain.tld`) or a display name followed by an
# angle-bracketed addr-spec (`Display Name <local@domain.tld>`).
# Display name may contain spaces; quotes are not required and not
# typical (Postmark accepts unquoted display names just fine).
#
# Reject pattern: a quoted display name followed by an UN-bracketed
# address — Postmark's parser silently mangles this (concatenates
# the last word of the display name with the address local-part,
# observed 2026-05-09).
is_valid_mail_from() {
  local v="$1"
  # Trim leading/trailing whitespace.
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  # Bare address.
  if [[ "$v" =~ ^[^[:space:]\<\>@]+@[^[:space:]\<\>@]+\.[^[:space:]\<\>@]+$ ]]; then
    return 0
  fi
  # Display name (possibly with spaces) + angle-bracketed address.
  if [[ "$v" =~ ^.+[[:space:]]\<[^[:space:]\<\>@]+@[^[:space:]\<\>@]+\.[^[:space:]\<\>@]+\>$ ]]; then
    return 0
  fi
  return 1
}

# Extract the value of a `VAR=...` line from a multi-line env blob.
# Empty output if VAR isn't present. Trims surrounding whitespace.
# Doesn't try to strip outer quotes — if a value is quoted in the
# file, the script shows the quoted form as the default and the
# is_valid_mail_from check will reject it for FELLOWS_MAIL_FROM if
# it doesn't match a sane From shape.
extract_env_var() {
  local var="$1"
  local content="$2"
  printf '%s\n' "$content" | awk -F= -v v="$var" '
    $1 == v {
      sub(/^[^=]*=/, "")
      sub(/^[[:space:]]+/, "")
      sub(/[[:space:]]+$/, "")
      print
      exit
    }
  '
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

# Fetch the current env file so we can offer existing values as
# defaults below. Requires sudo on the remote — the operator's
# sudo password is prompted by ssh -t. A missing file or denied
# read is treated as "no existing values" and the script falls
# through to first-time prompts.
echo
echo "Fetching current /etc/fellows/fellows-pwa.env (sudo password may be prompted)..."
existing_env="$(
  ssh -t -p "$port" "${ssh_user}@${host}" \
    "sudo -n cat /etc/fellows/fellows-pwa.env 2>/dev/null || sudo cat /etc/fellows/fellows-pwa.env 2>/dev/null" \
    2>/dev/null || true
)"
# ssh -t can pollute stdout with carriage returns; strip them so
# extract_env_var sees clean lines.
existing_env="$(printf '%s\n' "$existing_env" | tr -d '\r')"

existing_mail_from="$(extract_env_var FELLOWS_MAIL_FROM "$existing_env")"
existing_public_origin="$(extract_env_var FELLOWS_PUBLIC_ORIGIN "$existing_env")"
existing_reply_to="$(extract_env_var FELLOWS_REPLY_TO "$existing_env")"
existing_postmark_token="$(extract_env_var FELLOWS_POSTMARK_TOKEN "$existing_env")"
existing_session_secret="$(extract_env_var FELLOWS_SESSION_SECRET "$existing_env")"
existing_hmac_key="$(extract_env_var FELLOWS_ALLOWLIST_HMAC_KEY "$existing_env")"

if [[ -n "$existing_env" ]]; then
  echo "Found existing env file. Press Enter at any prompt to keep the current value."
else
  echo "No existing env file found (first-time setup, or file unreadable)."
fi

echo
echo "Environment values for /etc/fellows/fellows-pwa.env"

# FELLOWS_MAIL_FROM: bare address OR `Display Name <addr>`. Loops
# until the value passes is_valid_mail_from to catch the quoted-
# name-without-brackets footgun before it reaches Postmark.
mail_from_default="${existing_mail_from:-EHF Directory App <admin@fellows.globaldonut.com>}"
while true; do
  mail_from="$(prompt_required_with_default "FELLOWS_MAIL_FROM (verified Postmark sender)" "$mail_from_default")"
  if is_valid_mail_from "$mail_from"; then
    break
  fi
  echo
  echo "  ✗ '${mail_from}'"
  echo "    doesn't look like a valid From header. Use one of:"
  echo "      bare address:           admin@fellows.globaldonut.com"
  echo "      display + bracketed:    EHF Directory App <admin@fellows.globaldonut.com>"
  echo "    No quotes around the display name; angle brackets are required."
  echo
done

# FELLOWS_PUBLIC_ORIGIN
public_origin_default="${existing_public_origin:-https://fellows.globaldonut.com}"
public_origin="$(prompt_required_with_default "FELLOWS_PUBLIC_ORIGIN (https://your-domain)" "$public_origin_default")"

# FELLOWS_REPLY_TO (optional; "-" clears it)
read -r -p "FELLOWS_REPLY_TO (Enter to keep '${existing_reply_to:-<unset>}', '-' to clear): " reply_to_input
if [[ "$reply_to_input" = "-" ]]; then
  reply_to=""
elif [[ -z "$reply_to_input" ]]; then
  reply_to="$existing_reply_to"
else
  reply_to="$reply_to_input"
fi

# FELLOWS_POSTMARK_TOKEN — secret. Existing value kept by default.
if [[ -n "$existing_postmark_token" ]]; then
  postmark_input="$(prompt_secret_or_keep "FELLOWS_POSTMARK_TOKEN (input hidden)")"
  postmark_token="${postmark_input:-$existing_postmark_token}"
else
  postmark_token="$(prompt_secret_required "FELLOWS_POSTMARK_TOKEN (input hidden)")"
fi

# FELLOWS_SESSION_SECRET — keep, regenerate, or paste a new one.
# Rotation logs every fellow out (cookies signed with the old
# secret no longer verify), so default is to KEEP existing.
if [[ -n "$existing_session_secret" ]]; then
  echo "FELLOWS_SESSION_SECRET is currently set. Rotating logs every fellow out."
  read -r -p "Rotate FELLOWS_SESSION_SECRET? [y/N]: " rotate_secret
  if [[ "${rotate_secret}" =~ ^[Yy]$ ]]; then
    session_secret="$(generate_session_secret)"
    echo "Generated new session secret."
  else
    session_secret="$existing_session_secret"
  fi
else
  default_secret="$(generate_session_secret)"
  read -r -p "Generate FELLOWS_SESSION_SECRET now? [Y/n]: " gen_secret
  if [[ -z "${gen_secret}" || "${gen_secret}" =~ ^[Yy]$ ]]; then
    session_secret="$default_secret"
    echo "Generated session secret."
  else
    session_secret="$(prompt_secret_required "FELLOWS_SESSION_SECRET (input hidden)")"
  fi
fi

# FELLOWS_ALLOWLIST_HMAC_KEY — keep, rotate, or paste. Rotation here
# is non-disruptive: the in-memory allowlist is rebuilt from
# fellows.db at next start using the new key. No fellow gets logged
# out; existing v3 cookies still verify. Default is still KEEP, to
# minimise churn.
if [[ -n "$existing_hmac_key" ]]; then
  read -r -p "Rotate FELLOWS_ALLOWLIST_HMAC_KEY? [y/N]: " rotate_hmac
  if [[ "${rotate_hmac}" =~ ^[Yy]$ ]]; then
    hmac_key="$(generate_hmac_key)"
    echo "Generated new allowlist HMAC key."
  else
    hmac_key="$existing_hmac_key"
  fi
else
  default_hmac_key="$(generate_hmac_key)"
  read -r -p "Generate FELLOWS_ALLOWLIST_HMAC_KEY now? [Y/n]: " gen_hmac
  if [[ -z "${gen_hmac}" || "${gen_hmac}" =~ ^[Yy]$ ]]; then
    hmac_key="$default_hmac_key"
    echo "Generated allowlist HMAC key."
  else
    hmac_key="$(prompt_secret_required "FELLOWS_ALLOWLIST_HMAC_KEY (input hidden)")"
  fi
fi

echo
echo "Will configure host ${ssh_user}@${host}:${port}"
echo "  FELLOWS_MAIL_FROM=${mail_from}"
echo "  FELLOWS_PUBLIC_ORIGIN=${public_origin}"
echo "  FELLOWS_REPLY_TO=${reply_to:-<unset>}"
echo "  FELLOWS_POSTMARK_TOKEN=<hidden>"
echo "  FELLOWS_SESSION_SECRET=<hidden>"
echo "  FELLOWS_ALLOWLIST_HMAC_KEY=<hidden>"
read -r -p "Continue? [y/N]: " confirm
if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

tmp_env="$(mktemp)"
trap 'rm -f "$tmp_env"' EXIT
chmod 600 "$tmp_env"

# printf %s (not heredoc) so values containing $, `, or quoting
# aren't interpreted by the shell on the way through.
{
  printf 'FELLOWS_SESSION_SECRET=%s\n' "$session_secret"
  printf 'FELLOWS_ALLOWLIST_HMAC_KEY=%s\n' "$hmac_key"
  printf 'FELLOWS_POSTMARK_TOKEN=%s\n' "$postmark_token"
  printf 'FELLOWS_MAIL_FROM=%s\n' "$mail_from"
  printf 'FELLOWS_PUBLIC_ORIGIN=%s\n' "$public_origin"
  if [[ -n "$reply_to" ]]; then
    printf 'FELLOWS_REPLY_TO=%s\n' "$reply_to"
  fi
} >"$tmp_env"

# Defence in depth against the malformation we hit on 2026-05-09
# (a stray newline split FELLOWS_POSTMARK_TOKEN across two lines,
# silently disabling sends). Each non-empty line in the staged file
# must look like FOO=... — bail loudly rather than uploading.
if ! awk 'NF == 0 { next } /^[A-Z_][A-Z0-9_]*=/ { next } { exit 1 }' "$tmp_env"; then
  echo "ERROR: staged env file looks malformed (a value contains a newline?). Aborting." >&2
  exit 1
fi

remote_tmp="/tmp/fellows-pwa.env.$$"

echo
echo "Uploading env file to app server..."
scp -P "$port" "$tmp_env" "${ssh_user}@${host}:${remote_tmp}"

echo "Installing env file, systemd drop-in, and restarting service..."
ssh -t -p "$port" "${ssh_user}@${host}" "set -euo pipefail; \
  sudo install -d -m 0750 -o root -g fellows /etc/fellows; \
  sudo mv \"$remote_tmp\" /etc/fellows/fellows-pwa.env; \
  sudo chown root:fellows /etc/fellows/fellows-pwa.env; \
  sudo chmod 0640 /etc/fellows/fellows-pwa.env; \
  sudo install -d -m 0755 /etc/systemd/system/fellows-pwa.service.d; \
  printf '[Service]\nEnvironmentFile=/etc/fellows/fellows-pwa.env\n' | sudo tee /etc/systemd/system/fellows-pwa.service.d/10-env-file.conf >/dev/null; \
  sudo systemctl daemon-reload; \
  sudo systemctl restart fellows-pwa; \
  sudo systemctl status fellows-pwa --no-pager"

echo
echo "Done. Auth env is configured and fellows-pwa has been restarted."
