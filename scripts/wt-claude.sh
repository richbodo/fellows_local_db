#!/bin/bash

# scripts/wt-claude.sh

BRANCH_NAME=$1
if [ -z "$BRANCH_NAME" ]; then
    echo "❌ Please provide a branch name."
    exit 1
fi

# 1. Environment Setup Logic
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_VENV="$REPO_ROOT/.venv"

# 2. Determine if we need the -c flag
# Check if branch exists locally or on remote
if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1 || \
   git rev-parse --verify "origin/$BRANCH_NAME" >/dev/null 2>&1; then
    CREATE_FLAG=""
    echo "🌿 Branch '$BRANCH_NAME' exists. Switching..."
else
    CREATE_FLAG="-c"
    echo "✨ Creating new branch '$BRANCH_NAME'..."
fi

# 3. Use worktrunk with the dynamic flag
wt switch $CREATE_FLAG "$BRANCH_NAME"

# 4. Link the .venv (Absolute path)
# We check if it exists first to avoid 'File exists' errors on re-entry
if [ ! -L "./.venv" ] && [ ! -d "./.venv" ]; then
    ln -s "$SOURCE_VENV" ./.venv
    echo "✅ Symlinked .venv"
fi

# 5. Launch Claude
claude --dangerously-skip-permissions

