#!/usr/bin/env bash
# Print a single "drift: ..." line (plus an optional branch line) comparing
# prod's git SHA to local HEAD. Handles four cases:
#
#   1. prod_sha == head_sha             — no drift
#   2. prod is an ancestor of HEAD      — HEAD ahead by N (normal pre-deploy state)
#   3. HEAD is an ancestor of prod      — prod ahead by N (side-branch deploy)
#   4. both have unique commits         — diverged
#
# Plus the degenerate case where prod_sha isn't in the local clone yet
# ("did you fetch?"). Called from `just whats-running` and `just drift`.
#
# Usage: show_prod_drift.sh <prod_sha> <head_sha> [label_prefix]
#   label_prefix defaults to "drift:" and is left-padded by the caller.
set -uo pipefail

prod_sha="${1:-}"
head_sha="${2:-}"
prefix="${3:-drift:}"

if [ -z "$prod_sha" ] || [ -z "$head_sha" ]; then
    echo "${prefix} (missing sha)"
    exit 0
fi

if [ "$prod_sha" = "$head_sha" ]; then
    echo "${prefix} none — prod matches local HEAD"
    exit 0
fi

if ! git cat-file -e "${prod_sha}^{commit}" 2>/dev/null; then
    echo "${prefix} prod sha ${prod_sha} not in local clone — try 'git fetch --all'"
    exit 0
fi

prod_to_head=$(git rev-list "${prod_sha}..${head_sha}" --count 2>/dev/null || echo '?')
head_to_prod=$(git rev-list "${head_sha}..${prod_sha}" --count 2>/dev/null || echo '?')

if [ "$prod_to_head" != "0" ] && [ "$head_to_prod" = "0" ]; then
    # prod is an ancestor of HEAD — the normal "ready to deploy" state.
    echo "${prefix} local HEAD is ${prod_to_head} commits ahead of prod"
elif [ "$head_to_prod" != "0" ] && [ "$prod_to_head" = "0" ]; then
    # HEAD is an ancestor of prod — prod was deployed from a branch
    # that's ahead of where HEAD currently sits. Surface the branch
    # name (prefer a non-main branch, since main was just shown to be
    # behind).
    prod_branch=$(git branch -a --contains "$prod_sha" 2>/dev/null \
        | sed 's|^[ *]*||; s|^remotes/||' \
        | grep -v '^HEAD' \
        | grep -v '^origin/HEAD' \
        | grep -vE '^(origin/)?main$' \
        | head -1 || echo '')
    echo "${prefix} prod is ${head_to_prod} commits ahead of HEAD (side-branch deploy?)"
    if [ -n "$prod_branch" ]; then
        # Match the indent of the drift line so the branch hint lines up.
        printf '%*s prod sha is on: %s\n' "${#prefix}" '' "$prod_branch"
    fi
elif [ "$prod_to_head" != "0" ] && [ "$head_to_prod" != "0" ]; then
    # Genuinely diverged — both have unique commits relative to merge-base.
    echo "${prefix} diverged — HEAD ahead by ${prod_to_head}, prod ahead by ${head_to_prod}"
else
    echo "${prefix} (could not compute)"
fi
