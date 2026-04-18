#!/usr/bin/env bash
# Read-only diagnostic for the deploy rsync permission issue.
#
# SSHes to the fellows host as the operator user (rsb) and reports everything
# we need to decide whether the failure is group membership, directory modes,
# ACLs, or something else. Does not modify remote state; the write probe
# creates and immediately deletes a single file under dist/ and dist/vendor/.
#
# Usage: ./scripts/diagnose_deploy_perms.sh [host]
#   host defaults to the ansible inventory target.

set -euo pipefail

HOST="${1:-170.64.243.67}"
PORT="${SSH_PORT:-52221}"
USER="${SSH_USER:-rsb}"

ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "$USER@$HOST" bash -s <<'REMOTE'
set -u
APP=/opt/fellows
DIST=$APP/deploy/dist

say() { printf '\n=== %s ===\n' "$1"; }

say "whoami / id"
whoami
id

say "getent group fellows"
getent group fellows || true

say "umask"
umask

say "mount options for /opt"
awk '$2 ~ /^\/opt($|\/)/ || $2 == "/" {print}' /proc/mounts

say "stat on key paths (mode / owner / group)"
for p in "$APP" "$APP/deploy" "$DIST" "$DIST/vendor" "$DIST/images"; do
  if [ -e "$p" ]; then
    stat -c '%a %U:%G  %n' "$p"
  else
    echo "MISSING  $p"
  fi
done

say "ls -la $DIST"
ls -la "$DIST" || true

say "ls -la $DIST/vendor"
ls -la "$DIST/vendor" 2>/dev/null || echo "(no vendor dir)"

say "ls -la $DIST/images  (first 5)"
ls -la "$DIST/images" 2>/dev/null | head -n 5 || echo "(no images dir)"

say "getfacl (if acl tools present)"
if command -v getfacl >/dev/null 2>&1; then
  getfacl -p "$DIST" 2>/dev/null || true
  getfacl -p "$DIST/vendor" 2>/dev/null || true
else
  echo "getfacl not installed"
fi

say "find dirs NOT mode 2775 under dist"
find "$DIST" -type d \! -perm 2775 -printf '%m %u:%g %p\n' | head -n 40

say "find files NOT group-writable under dist"
find "$DIST" -type f \! -perm -g+w -printf '%m %u:%g %p\n' | head -n 40

say "write probe: can rsb create a file under dist/ ?"
PROBE="$DIST/.__rsb_write_probe__.$$"
if ( : > "$PROBE" ) 2>/tmp/probe.err; then
  echo "OK: created $PROBE"
  rm -f "$PROBE"
else
  echo "FAIL: cannot create $PROBE"
  cat /tmp/probe.err
fi

say "write probe: can rsb create a file under dist/vendor/ ?"
PROBE="$DIST/vendor/.__rsb_write_probe__.$$"
if ( : > "$PROBE" ) 2>/tmp/probe.err; then
  echo "OK: created $PROBE"
  rm -f "$PROBE"
else
  echo "FAIL: cannot create $PROBE"
  cat /tmp/probe.err
fi

say "utime probe: can rsb set mtime on dist/vendor/sqlite3.js ?"
if [ -f "$DIST/vendor/sqlite3.js" ]; then
  if touch -d '2024-01-01 00:00' "$DIST/vendor/sqlite3.js" 2>/tmp/probe.err; then
    echo "OK"
  else
    echo "FAIL"
    cat /tmp/probe.err
  fi
else
  echo "(target file missing; skipping)"
fi

say "done"
REMOTE
