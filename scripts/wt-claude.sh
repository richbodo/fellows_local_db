#!/bin/bash

# scripts/wt-claude.sh

BRANCH_NAME=$1

if [ -z "$BRANCH_NAME" ]; then
    echo "❌ Please provide a branch name."
    exit 1
fi

# Get the absolute path to the directory where THIS script lives, 
# then go up one level to find the repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_VENV="$REPO_ROOT/.venv"

if [ ! -d "$SOURCE_VENV" ]; then
    echo "❌ Error: .venv not found at $SOURCE_VENV"
    exit 1
fi

echo "🚀 Preparing worktree for: $BRANCH_NAME"

# 2. Use worktrunk to create/switch
wt switch -c "$BRANCH_NAME"

# 3. Link the .venv (Absolute path is safest)
ln -s "$SOURCE_VENV" ./.venv
echo "✅ Symlinked .venv from $SOURCE_VENV"

# 4. Launch Claude
claude --dangerously-skip-permissions

