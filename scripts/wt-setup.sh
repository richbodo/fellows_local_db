#!/usr/bin/env bash
# scripts/wt-setup.sh — make a git worktree test-ready by sharing the heavy
# gitignored build artifacts from the primary checkout.
#
# Git worktrees share .git but get a working tree with NO gitignored files. The
# test suite needs .venv (dev deps + Playwright) and app/fellows.db (the built
# SQLite snapshot) — both gitignored — so a bare worktree can't run tests
# without a slow `just setup`. This symlinks them from the primary checkout so a
# fresh worktree is test-ready in milliseconds.
#
# Playwright browsers live in a per-user global cache (~/Library/Caches/
# ms-playwright on macOS); once .venv is linked they're shared automatically.
#
# Usage:
#   git worktree add ../fellows-wt-mybranch -b mybranch
#   scripts/wt-setup.sh ../fellows-wt-mybranch
#
# Higher-level shortcut (creates the worktree + launches Claude): `just wt <branch>`.
# When to use worktrees + the port-8765 serialization rule: docs/worktrees.md.
#
# Re-runnable; skips links that already exist. (scripts/wt-claude.sh links .venv
# via the `wt`/worktrunk flow; this script is the plain-git equivalent and also
# carries app/fellows.db + mcp_servers/.venv.)
#
# CONCURRENCY WARNING: the test suite binds the FIXED port 8765 (CLAUDE.md).
# Server-based test runs (just test-api / test-e2e / test-mobile) in two
# worktrees AT THE SAME TIME will collide on that port. Serialize server-based
# runs across worktrees; pure-DB tests (tests/test_database.py) are parallel-safe.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY_ROOT="$(dirname "$SCRIPT_DIR")"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Usage: scripts/wt-setup.sh <worktree-path>"
  echo "  e.g. scripts/wt-setup.sh ../fellows-wt-worker-lane"
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"

if [ "$TARGET" = "$PRIMARY_ROOT" ]; then
  echo "Refusing to run against the primary checkout ($PRIMARY_ROOT)."
  echo "Pass a worktree path, e.g. scripts/wt-setup.sh ../fellows-wt-mybranch"
  exit 1
fi

link() {
  local rel="$1"
  local src="$PRIMARY_ROOT/$rel"
  local dst="$TARGET/$rel"
  if [ ! -e "$src" ]; then
    echo "skip   $rel  (not in primary checkout — run 'just setup' there first?)"
    return
  fi
  if [ -L "$dst" ] || [ -e "$dst" ]; then
    echo "skip   $rel  (already present in worktree)"
    return
  fi
  mkdir -p "$(dirname "$dst")"
  ln -s "$src" "$dst"
  echo "link   $rel  ->  $src"
}

link ".venv"
link "app/fellows.db"
link "mcp_servers/.venv"

# Activate the pre-commit leak guard in this worktree. core.hooksPath is shared
# via the common .git config, but set it explicitly so a worktree is guarded even
# if the primary never ran `just setup`/`just hooks`. Path is relative to the
# worktree root, which has the tracked .githooks/.
git -C "$TARGET" config core.hooksPath .githooks
echo "link   core.hooksPath -> .githooks (pre-commit leak guard)"

echo "Worktree ready: $TARGET"
echo "Reminder: don't run server-based tests here while another worktree is (port 8765)."
