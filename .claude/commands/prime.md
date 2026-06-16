# Prime
> Read-only orientation: understand the codebase and where you are, then
> summarize. Do NOT switch branches, pull, or create a worktree while priming —
> just orient. (See CLAUDE.md § Workflow for when to branch / `just wt`.)

## Run
git ls-files
git status -sb          # current branch + ahead/behind + dirty state
git worktree list       # sibling worktrees other agents may be using

## Read
README.md
CLAUDE.md
app/server.py
docs/*
