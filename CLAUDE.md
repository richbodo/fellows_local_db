# CLAUDE.md

Read README.md for project setup, API docs, and test commands. Read docs/Architecture.md for fellows_local_db's specialization and PNA-spec conformance (axis picks, fellows-specific schema, HTTP routes, debug placeholders); docs/Architecture.md cross-links into the [personal_network_toolkit](https://github.com/richbodo/personal_network_toolkit) repo for the universal PNA architecture.

## Constraints

- **No frameworks.** Python stdlib only (http.server, sqlite3, json, pathlib). No Flask, Django, Express, etc.
- **No frontend build tools.** Vanilla JS, no npm, no bundlers, no transpilers.
- **No new pip dependencies** for the app. Dev deps go in requirements-dev.txt. The `mcp_servers/` directory is the only exception — its servers may pull in non-stdlib runtime deps (the official `mcp` SDK), isolated in `mcp_servers/.venv` so the app's stdlib-only boundary stays clean. `mcp_servers/` imports from `app/` only via pure-logic helpers (e.g. `app/fellows_queries.py`).
- **No authentication.** Local-only tool.
- **Port 8765.** Do not change.

## Conventions

- Keep the server as a single file (`app/server.py`). Pure-logic helpers (e.g. `app/relationships.py`) may live alongside.
- Frontend is a single IIFE in `app/static/app.js`. No modules, no classes.
- `escapeHtml()` for all user data rendered into HTML.
- Parameterized `?` placeholders for all SQL queries.
- Validate image paths against traversal (`..` checks).
- Do not leave a long-lived server running in the terminal.
- The DB file `app/fellows.db` is gitignored; rebuild from JSON source.
- Always run relevant tests after changes.
- For deploy- or infra-related work, put **manual QA steps for the maintainer** (smoke scripts, DNS/TLS checks, browser install flow) in the **PR description**, not only in commits or docs.
- **UI/UX changes belong in `docs/users_manual.md`.** When a feature PR changes user-visible behavior (new screen, new flow, changed control, new option), include the corresponding users-manual update in the same PR — accepting the PR accepts the doc change with it. The user guide is the source of truth for UI/UX from a user's perspective; the app links to it from the About page.
- **OPFS access only via the dedicated worker; main thread is an RPC client.** All `relationships.db` and `fellows.db` reads/writes go through `app/static/vendor/sqlite-worker.js`. The main thread does not call `navigator.storage.getDirectory`, does not load `sqlite3.wasm`, and does not hold any `FileSystemSyncAccessHandle`. (Phase 1 of `plans/local_first_worker_architecture.md` enforces this in code; until then `app/static/app.js` still has the legacy main-thread paths and this convention applies to *new* code.)

## Workflow (git, PRs, shipping)

- **PR/issue bodies via `--body-file`, never inline.** Pass `gh pr create` / `gh issue create` a file (or a heredoc to a temp file). Backticks and `$(…)` in an inline `--body` get shell-interpreted and silently drop content — a commit hash has been lost this way.
- **Branch new work off `main`** (confirm with `git branch --show-current` first), and **after a PR merges, verify every intended commit actually landed.** A dropped commit is silent; recover it in a follow-up PR.
- **Before shipping, run the suite and triage every failure as pre-existing vs. newly-introduced.** A red that reproduces on a clean branch/`main` HEAD (stash your changes to check) is pre-existing — say so explicitly and fix it as its own scoped change; never silently absorb it into unrelated work, and never claim green while a known red stands. This is § Conformance discipline's *everything fails loudly* applied to the test run itself.
- **Multiple agents on one host → one git worktree each.** When more than one Claude Code / agent works on this checkout's host concurrently, give each its own worktree so a `git checkout` in one can't yank the branch (or uncommitted work) out from under another. Spin up with `just wt <branch>`, or `git worktree add ../fellows-wt-<branch> -b <branch> && scripts/wt-setup.sh ../fellows-wt-<branch>` (the setup script symlinks the heavy gitignored artifacts — `.venv`, `app/fellows.db`, `mcp_servers/.venv` — so the worktree is test-ready instantly). Worktrees isolate the *filesystem*, **not port 8765**: edits / `just test-db` / conformance lints run in parallel, but **server-based runs (`serve`, `test-api` / `test-e2e` / `test-mobile`) must be serialized across worktrees** — `ensure_port_8765_free.sh` kills whatever holds 8765, so a sibling's e2e run dies mid-flight and looks like a flaky test. The symlinked `app/fellows.db` is *shared*, so don't `db-rebuild`/`reset` while a sibling is testing. `just wtclean <branch>` when done. Full rationale: [`docs/worktrees.md`](docs/worktrees.md).

## Conformance discipline

These rules keep `docs/Architecture.md`'s AC/CST attestation (the Security
Target) honest. See [`plans/conformance_discipline.md`](plans/conformance_discipline.md).

- **A `conformant` attestation row needs executable evidence.** It must cite a
  resolvable test ref (`path/to/test.py[::name]`) or an explicitly declared
  verification kind (`human-review` / `LLM rubric` / `code inspection` /
  `by architecture` / `by bounding` / `by construction`). A bare doc pointer is
  not evidence — a doc that *asserts* a property does not *prove* it.
  `tests/test_attestation_has_evidence.py` enforces this; run it after touching
  the attestation.
- **Negative invariants need negative tests.** "X must NOT happen off-folder" is
  not covered by the test that X happens on-folder.
- **Deferred or not-yet-true invariants are `@pytest.mark.xfail(strict=True)`
  tests that name the plan PR which will satisfy them — never a `// TODO`, a
  prose "lands later," or an `INERT` code comment.** A strict-xfail is a deferral
  with a tripwire: it goes red the day someone implements it, and
  `grep "xfail(strict"` is the live list of claimed-but-unproven invariants. The
  only other home for a deferral is the attestation table with an honest
  `partial`/`Open` status.
- **Capability reductions enforce at the data layer, never UI-only.** Hiding or
  graying a surface and redirecting a route is the cosmetic half; the reduction
  is that the *write does not happen* — refuse the mutating op at the worker (the
  OPFS owner) and, defensively, at the `dataProvider`. A gated capability whose
  RPC still succeeds from the DevTools console is not reduced.
- **Everything fails loudly.** Convert an absent guarantee into a red test or a
  blocking hook — never a silent pass.

## Two-DB architecture

User-authored data (groups, per-fellow tags, per-fellow notes, settings) lives in `app/relationships.db`, a separate SQLite file from the imported contact data in `app/fellows.db`. Cross-DB joins use SQLite `ATTACH DATABASE` with `?mode=ro` on the fellows side — read-only-ness of contact tables is enforced at the SQLite level, not just the app layer. See `app/relationships.py` (Python) and the `RELATIONSHIPS_SCHEMA_SQL` mirror in `app/static/app.js` (PWA / OPFS). `relationships.db` is gitignored, per-user, and persists across app updates; `fellows.db` is regenerated from source on every build.
