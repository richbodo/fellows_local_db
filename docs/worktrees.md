# Git worktrees (parallel agents on one host)

When more than one Claude Code instance — or one orchestrator spawning subagents
— works on this repo's host at the same time, give each its own **git worktree**.
A worktree is a second working directory backed by the same `.git`, checked out
to its own branch. The hazard it removes is the common one: two agents sharing a
single working tree means a `git checkout` (or `reset`, or a stash pop) in one
yanks the branch and uncommitted changes out from under the other. Worktrees make
that impossible — each agent has its own files and its own branch.

This is opt-in, not mandatory. For a single agent, work in the primary checkout
as usual. Reach for a worktree the day you know two or more agents will run here.

## Create one

```bash
just wt <branch>          # worktrunk: create/switch worktree, symlink .venv, launch claude
just wtclean <branch>     # remove the worktree (and the branch if merged)
```

Plain git, no worktrunk:

```bash
git worktree add ../fellows-wt-<branch> -b <branch>
scripts/wt-setup.sh ../fellows-wt-<branch>     # symlink the heavy gitignored artifacts
git worktree remove ../fellows-wt-<branch>     # when done; then: git worktree prune
```

`scripts/wt-setup.sh` symlinks `.venv`, `app/fellows.db`, and `mcp_servers/.venv`
from the primary checkout. A bare worktree shares `.git` but gets **no** gitignored
files, so without this it can't run tests without a slow `just setup`. We symlink
rather than copy on purpose: a copied `.venv` breaks because its `bin/` shebangs
hardcode the original absolute path; a symlink resolves back to the real venv.
Playwright browsers live in a per-user global cache, so they're shared for free.

## The one rule that matters: port 8765 is host-global

Worktrees isolate the **filesystem, not the network.** The app's port (`8765`,
fixed — see CLAUDE.md) is shared across every worktree on the host. So:

| Activity | Across worktrees |
|---|---|
| Editing, reading, committing | parallel-safe |
| `just test-db`, conformance lints, pure-logic tests | parallel-safe |
| `just serve`, `test-api`, `test-e2e`, `test-mobile`, `serve-prod` | **must be serialized** |

The failure mode is sharper than a polite "address in use": every server-based
`just` recipe runs `scripts/ensure_port_8765_free.sh` first, which **kills**
whatever holds 8765. Start an e2e run in worktree B while worktree A is mid-e2e
and A's server is killed under it — A's run fails in a way that looks like a flaky
test, not a conflict. Stagger the server/e2e step; let everything else run in
parallel. Don't try to "fix" this by changing the port — 8765 is load-bearing for
the service-worker, manifest, and auth assumptions.

## Shared artifacts are shared

Because `wt-setup.sh` *symlinks* rather than copies:

- **`app/fellows.db`** is one file behind all worktrees. Reads are fine (that's
  the common case), but a `just db-rebuild`/`reset` in one worktree rewrites it
  for all of them — don't rebuild the directory DB while a sibling is testing.
- **`.venv`** is shared. Fine for this stdlib-only app; just know a `pip install`
  in one worktree affects all.
- **`relationships.db`** is *not* a concern: it lives in the browser's OPFS, and
  Playwright uses an ephemeral context per test, so there's no on-disk file to
  collide across worktrees.

## Subagents with harness worktree isolation

The Agent/Workflow `isolation: "worktree"` option creates a throwaway worktree per
subagent. Those share `.git` but, like any bare worktree, get **none** of the
gitignored artifacts — so a subagent that only reads/searches/edits is fine, but
one that needs to *run the test suite* must have `scripts/wt-setup.sh` pointed at
its worktree first. For human-launched parallel instances, `just wt` is the lever;
for an orchestrator spawning subagents, the harness option is.

## Cleanup

Worktrees and their branches accumulate. `just wtclean <branch>` (or
`git worktree remove … && git worktree prune`) when a lane is finished.
`git worktree list` shows what's currently checked out where.
