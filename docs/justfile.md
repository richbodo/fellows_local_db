# Justfile

The `justfile` at the repo root is a thin command runner over the existing
scripts in `scripts/`, `build/`, `run.sh`, and the `ansible/` playbooks. It
does not replace any of them — every recipe shells out to the underlying
script. You can keep typing the long forms; `just` exists to save typing.

Install: `brew install just` (already present on the maintainer's laptop).
Run `just` with no arguments for the live menu.

## Conventions

- **Groups** organize recipes in `just --list` output. The group names are
  stable labels, not part of the recipe name — you still just type `just deploy`.
- **Dependencies** run before the named recipe. `just reset` = `stop` →
  `db-rebuild` → `serve`.
- **Parameters** use the shell form `just recipe arg1 arg2`. Defaults are
  shown in the list (e.g. `prod-logs unit="fellows-pwa"`).
- **Forwarding flags** to pytest needs a `--` separator so `just` itself
  doesn't try to parse them: `just test -- tests/e2e/ -v -k email_gate`.
- **Confirmations** — nothing prompts besides whatever the underlying
  script already prompts for (e.g. `data-restore`'s y/N,
  `prod-configure-env`'s entry flow, `--ask-become-pass` for Ansible).

## Environment overrides

A few recipes respect the same env vars the underlying scripts do:

| Variable | Default | Affects |
|---|---|---|
| `FELLOWS_HOST` | `fellows.globaldonut.com` | `check-env`, SSH targets |
| `FELLOWS_SSH_PORT` | `52221` | `prod-logs`, `prod-status`, `prod-stats` |
| `FELLOWS_SSH_USER` | `rsb` | `prod-logs`, `prod-status`, `prod-stats` |
| `FELLOWS_BASE_URL` | `https://fellows.globaldonut.com` | `smoke`, `drift` |

Export them or inline: `FELLOWS_BASE_URL=https://staging.example.com just smoke`.

## Recipes by group

### setup

- **`setup`** — create `.venv`, `pip install -r requirements-dev.txt`, install
  Playwright Chromium, install Ansible collections, build the DB if missing.
  Equivalent to the "First-Time Setup" block in `README.md`.
- **`doctor`** — sanity-check the dev environment. Reports venv, DB,
  Playwright, Ansible collections, and port 8765. Non-destructive.
- **`clean`** — stop the dev server and remove `.venv`. Leaves
  `app/fellows.db` and `final_fellows_set/` alone.

### dev

- **`serve`** — start the dev server in the background and open a browser tab.
  Wraps `./run.sh start`.
- **`serve-fg`** — start the server in the foreground; Ctrl-C to stop. Good
  when you want to watch request logs live.
- **`stop`** / **`status`** / **`restart`** — server lifecycle. Wraps `./run.sh`.
- **`reset`** — stop, canonical DB rebuild (Knack, with auto-backup), start.
  Unlike `./run.sh reset` (which uses the demo JSON), this uses
  `build/restore_from_knack_scrapefile.py` — the canonical rebuild per
  `docs/data_provenance.md`.
- **`port`** — free port 8765. Wraps `./scripts/ensure_port_8765_free.sh`.
- **`gate`** — open `http://localhost:8765/?gate=1` in a browser to force
  the email gate UI (handy when testing auth paths locally).

### db

- **`db-rebuild`** — canonical rebuild from `final_fellows_set/knack_api_detail_dump.json`,
  **automatically snapshotting** to `backup/` first (via `data-backup`
  dependency). Prints row/email/image counts when done.
- **`db-verify`** — bytewise-diff `app/fellows.db` against
  `app/fellows.db.backup.2026-04-08` (the reference known-good DB). Expected
  output: `✓ bytewise match on all columns`.
- **`db-diff OTHER`** — same, but against any file you pass.
- **`db-stats`** — row count, email count, image count. Quick sanity check.
- **`db-open`** — open `app/fellows.db` in `sqlite3` for ad-hoc queries.
- **`images-fetch`** / **`images-fetch-dry`** — download missing profile
  images from Knack S3 (wraps `build/fetch_missing_images.py`).

### data

- **`data-backup`** — snapshot DB + source JSONs + images to
  `backup/fellows_data_<ts>_<sha>.zip`. Wraps `scripts/backup_fellows_data.sh`.
  Called automatically by `db-rebuild`.
- **`data-restore ZIP`** — restore from a backup zip. `ZIP` defaults to
  `--latest`. Interactive — the underlying script prompts y/N after showing
  the manifest.
- **`data-restore-dry ZIP`** — same but `--dry-run`: prints the manifest
  and file list, doesn't touch anything.

### test

- **`test [ARGS]`** — free port 8765, then run pytest with `ARGS` (default
  `tests/ -v`). To pass pytest flags, separate with `--`:
  `just test -- tests/e2e/ -v -k email`.
- **`test-db`** — database unit tests (no server needed).
- **`test-api`** — HTTP API tests. Frees port first; pytest fixture spawns
  the server.
- **`test-e2e [FILTER]`** — Playwright e2e tests. If `FILTER` is non-empty,
  it's passed to pytest as `-k FILTER`: `just test-e2e email_gate`.
- **`test-fast`** — DB + API only. Skips Playwright; ~10× faster than `test`.

### build

- **`build`** — assemble `deploy/dist/` (runs `build/build_pwa.py`).
- **`build-meta`** — print `deploy/dist/build-meta.json` (timestamp + git sha
  of the last build). Useful to pair with `drift`.

### deploy

- **`deploy`** — full prod deploy. Wraps `./scripts/deploy_pwa.sh --ask-become-pass`,
  which runs `ansible/deploy_pwa.yml`: build → rsync → restart → HTTPS smoke.
- **`deploy-fast`** — deploy without rebuilding `deploy/dist/` (sets
  `fellows_skip_build=true`). Use when the bundle is already fresh.
- **`deploy-check`** — Ansible `--check` mode: reports what would change, but
  doesn't touch anything. Good before a risky deploy.
- **`ship`** — **`test-fast` → `deploy`**. The full "build-test-deploy-test"
  ceremony (build and smoke are inside the ansible playbook, not duplicated
  here). Use this for production pushes.
- **`ship-fast`** — **`deploy-fast` → `smoke`**. For when you've already
  built, tested, and just need to push to prod.
- **`bootstrap`** — first-time provisioning: `ansible-playbook ansible/site.yml
  --tags bootstrap --ask-become-pass`.
- **`ansible-collections`** — install the Ansible collections
  (`ansible-galaxy collection install -r ansible/collections/requirements.yml
  -p ansible/collections`). Run once per workstation.
- **`ansible-ping`** — `ANSIBLE_BECOME=false ansible fellows -m ping`. Quick
  reachability check (no sudo prompt).

### prod

- **`smoke [URL]`** — HTTPS smoke check against `FELLOWS_BASE_URL` (or `URL`
  if passed). Hits `/healthz`, `/manifest.webmanifest`, and
  `/api/debug/diagnostics`; fails loud if any are broken.
- **`check-env`** — DNS A record + HTTPS headers + `/healthz` for
  `FELLOWS_HOST`. Non-intrusive pre-/post-deploy probe.
- **`drift`** — compare prod's `X-Fellows-Build` response header with local
  `HEAD` and `origin/main`. One glance tells you whether prod is current.
- **`prod-logs [UNIT]`** — SSH + `journalctl -u UNIT -f`. Default unit
  `fellows-pwa`; try `just prod-logs caddy` for the reverse proxy.
- **`prod-stats [SINCE]`** — summary of page views, magic-link send/verify
  counts, 5xx errors, and disk usage over the window (default `24 hours
  ago`). Runs `/opt/fellows/bin/prod_stats` on the droplet via SSH; reads
  journald directly (no sudo needed — the operator is in the
  `systemd-journal` and `adm` groups). Examples: `just prod-stats`,
  `just prod-stats '7 days ago'`. Source: `scripts/prod_stats.py`, deployed
  by the `fellows_app` Ansible role.
- **`prod-stats-long`** — same tally as `prod-stats`, but over the full
  retained journal (`--since '@0'`), plus a plaintext list of every
  magic-link recipient (email, name, send count, first/last send time).
  Plaintext is resolved by hashing each `contact_email` in
  `/opt/fellows/deploy/dist/fellows.db` and matching against the
  `email_hash_prefix` the server logs per send event. Treat output as
  confidential — it contains fellow email addresses.
- **`prod-status`** — SSH + `systemctl status fellows-pwa caddy --no-pager`.
- **`prod-env`** — dump remote `/etc/fellows/fellows-pwa.env` (prompts for
  sudo password — values shown raw for paste-ready rotation). Wraps
  `scripts/show_server_env.sh`.
- **`prod-configure-env`** — interactive wizard to set Postmark / session
  secret / mail-from on a fresh droplet (or rotate). Wraps
  `scripts/configure_email_auth_env.sh`.
- **`prod-repair-env`** — reference repair for a malformed env file. Wraps
  `scripts/repair_email_auth_env.sh`. Background in the script header.
- **`prod-diag-perms [HOST]`** — read-only audit of `/opt/fellows/` perms
  (group membership, mode bits, setgid, write probes). Wraps
  `scripts/diagnose_deploy_perms.sh`.
- **`email-debug [SINCE] [EMAIL]`** — mine `journalctl` for
  `event=send_unlock_email` entries, optionally resolve Postmark `MessageID`s.
  Wraps `scripts/debug_email_delivery.py`. Examples:
  - `just email-debug` — last 24 hours.
  - `just email-debug '2 hours ago'` — narrow window.
  - `just email-debug '24 hours ago' me@example.com` — filter by email.

## Common sequences

- **First time on this laptop**: `just setup` → `just serve`.
- **Reset after dev-DB got weird**: `just reset` (stop, snapshot, canonical
  rebuild, start, open browser).
- **Before merging to main**: `just test` (all tests, port-safe).
- **Ship a PR to prod**: `just ship` (fast tests, then ansible build+deploy+smoke).
- **Check whether prod is current**: `just drift`.
- **How is prod doing?** `just prod-stats` (last 24h of page loads,
  magic-link sends, verifies, 5xx, disk). For a weekly view:
  `just prod-stats '7 days ago'`.
- **Investigate a bug a user reported**: `just prod-logs` in one terminal,
  `just email-debug '2 hours ago' bug-reporter@example.com` in another.
- **Prod seems wrong, want a recent snapshot of its auth env**: `just prod-env`.
- **Someone reports the install landing is blank**: `just drift` first; if
  prod is behind, `just deploy-fast`.

## Design notes

- **No new dependencies.** `just` is a single Go-ish binary; nothing touches
  `requirements-dev.txt`. Uninstalling `just` leaves the project intact —
  every underlying script still works.
- **No logic lives in the justfile.** It's a dispatcher. If a recipe grows a
  body beyond a few lines, that's a signal to move logic into a script.
- **Recipes are idempotent where the underlying script is.** `setup` checks
  for `.venv` before creating; `db-rebuild` always snapshots first;
  `serve` detects a running server and no-ops.
- **Production recipes are identified by the `prod-` prefix** so a careless
  tab-complete doesn't fire something destructive. The one exception is
  `smoke` (it's read-only and hits prod by default).

## Source

`justfile` at the repo root. ~270 lines, comments included. The recipe
descriptions above are derived from the `# ...` comments in the file — keep
them in sync.
