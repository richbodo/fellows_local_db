# EHF Fellows Local Directory

Local web app to browse Edmund Hillary Fellowship fellow profiles and run experiments. Data and assets are local-first (SQLite + static files), served by Python stdlib.

## Table of Contents

- [Data Note](#data-note)
- [Architecture](#architecture)
- [Setup](#setup)
  - [What To Install](#what-to-install)
  - [First-Time Setup (Developers)](#first-time-setup-developers)
- [Run Locally](#run-locally)
  - [Server](#server)
  - [API Endpoints](#api-endpoints)
  - [Two-Phase Load](#two-phase-load)
- [Testing](#testing)
- [Build And Data Pipeline](#build-and-data-pipeline)
  - [JSON To SQLite + FTS5](#json-to-sqlite-fts5)
  - [PWA Static Bundle](#pwa-static-bundle)
- [Production / DevOps](#production--devops)
- [Local Dev Notes](#local-dev-notes)
- [Before Making This Repo Public](#before-making-this-repo-public)
- [Project Layout](#project-layout)

## Data Note

The app runs against a dump of fellows data (contact emails, mobile numbers, citizenship, location, free-text responses) plus profile photos. **This data is never committed.** The `final_fellows_set/` directory is gitignored; obtain the JSON and image directory out-of-band from the maintainer and drop them in locally:

```
final_fellows_set/
  ehf_fellow_profiles_deduped.json
  fellow_profile_images_by_name/*.{jpg,png}
```

Treat the contents as confidential regardless of demo status. Do not paste excerpts into issues, PRs, commit messages, or third-party tools.

## Architecture

See [`docs/Architecture.md`](docs/Architecture.md) for system design, data flow, and schema.

## Setup

### What To Install

| Goal | Install |
|------|---------|
| **Run the app only** | **Python 3.8+** and built **`app/fellows.db`**. No pip deps beyond stdlib. |
| **Run full test suite** (DB + API + Playwright e2e) | Python 3.8+, **`app/fellows.db`**, **`.venv`**, `pip install -r requirements-dev.txt`, and `playwright install chromium`. |

`requirements-dev.txt` only covers dev/test tools (pytest, Playwright). The app runtime itself does not need them.

### First-Time Setup (Developers)

From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install chromium
python build/import_json_to_sqlite.py
```

Use `python` from the activated `.venv` when running tests so `pytest` and Playwright are on PATH. `scripts/ensure_port_8765_free.sh` expects `.venv/bin/pytest`.

## Run Locally

### Server

```bash
python app/server.py
```

Then open `http://localhost:8765/`.

Launcher option:

```bash
chmod +x run.sh
./run.sh
```

### API Endpoints

- `GET /api/fellows` — list only (`record_id`, `slug`, `name`) for fast directory load.
- `GET /api/fellows?full=1` — full fellow rows.
- `GET /api/fellows/<slug>` — one fellow by slug or `record_id`.
- `GET /api/search?q=...` — FTS5 search.
- `GET /api/stats` — aggregates for About page.
- `GET /fellows.db` — raw SQLite file for installed PWA bootstrap.
- `GET /images/<slug>.jpg|.png` — profile image lookup by slug/name fallback.
- `GET /` — static app shell.

### Two-Phase Load

The UI requests `/api/fellows` first (instant list), then fetches `/api/fellows?full=1` in the background. Directory view is names/links only; images load on detail view only.

## Testing

Prereqs: `.venv` active, `requirements-dev.txt` installed, Playwright Chromium installed, and `app/fellows.db` present.

Recommended:

```bash
chmod +x scripts/ensure_port_8765_free.sh
./scripts/ensure_port_8765_free.sh tests/ -v
```

Free port only:

```bash
./scripts/ensure_port_8765_free.sh
```

Direct pytest:

```bash
pytest tests/ -v
```

By category:

```bash
pytest tests/test_database.py -v
pytest tests/test_api.py -v
pytest tests/e2e/ -v
```

## Build And Data Pipeline

### JSON To SQLite + FTS5

```bash
python build/import_json_to_sqlite.py
python build/import_json_to_sqlite.py /path/to/other.json
```

Writes `app/fellows.db` and backs up existing DB to `app/fellows.db.backup.YYYY-MM-DD`.

Verify:

```bash
sqlite3 app/fellows.db "SELECT COUNT(*) FROM fellows;"
sqlite3 app/fellows.db "SELECT name, slug FROM fellows WHERE name != '' ORDER BY name LIMIT 5;"
sqlite3 app/fellows.db "SELECT name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';"
```

### PWA Static Bundle

```bash
python build/build_pwa.py
```

`build/build_pwa.py` assembles `deploy/dist/` from `app/static/`, adds `fellows.db`, images, and writes `allowed_emails.json` (SHA-256 hashes of normalized `contact_email` values from the DB).

## Production / DevOps

Production runs one Ubuntu droplet behind Caddy TLS. The unix architecture (service account, operator sudo model, systemd hardening, filesystem layout) and routine ops (build + deploy, smoke, bootstrap) are in [`docs/DevOps.md`](docs/DevOps.md). Mechanical Ansible details (tags, galaxy install, logs, troubleshooting) are in [`ansible/README.md`](ansible/README.md). Magic-link auth operator steps (Postmark, env file, journald event schema) are in [`docs/email_system_management.md`](docs/email_system_management.md).

Most common command, from the repo root:

```bash
./scripts/deploy_pwa.sh --ask-become-pass
```

## Local Dev Notes

- **Port 8765:** Prefer `./scripts/ensure_port_8765_free.sh` before manual testing when the port is occupied. Equivalent one-liner: `lsof -ti:8765 | xargs kill -9`.
- **Automation hygiene:** test runs should not leave long-lived servers running. If the port is stuck, run the script above or re-run pytest (which also attempts cleanup in fixtures).
- **Virtualenv scope:** use `.venv` for dev/test tooling on your workstation; production server runtime uses system Python.
- **Debugging a stuck PWA / service worker:** when a bug reproduces on your own browser but not on a clean Playwright profile, see [`docs/debugging.md`](docs/debugging.md) for the chrome-devtools-mcp setup that attaches Claude Code to your running Chrome.

## Before Making This Repo Public

**The `final_fellows_set/` data was in git history from the initial commit through this branch point.** Gitignoring it now prevents future commits from leaking PII, but existing history still contains 515+ contact emails, mobile numbers, ethnicity, free-text responses, and 268 profile photos. Any fork or clone made before a history scrub retains that data.

**Do this exactly once, immediately before flipping the repo to public:**

1. **Scrub history:**
   ```bash
   # Install if needed: brew install git-filter-repo
   git filter-repo --path final_fellows_set/ --invert-paths --force
   ```
   This rewrites every commit on every branch. All commit SHAs change.

2. **Force-push every branch:**
   ```bash
   git push --force-with-lease origin --all
   git push --force-with-lease origin --tags
   ```
   All open PRs, in-flight branches, and clones will break — coordinate before running.

3. **Also scrub** (run `grep -r` before publishing):
   - Any historical `deploy/dist/` snapshots that might have slipped in (it's gitignored, but double-check).
   - `ansible/group_vars/fellows.yml` if it ever contained secrets (currently clean — only non-secret config).
   - Commit messages, author emails, and PR descriptions: GitHub retains these separately from git; audit via `gh pr list --state all` and redact or close anything sensitive.

4. **Rotate any credentials that ever touched the repo**, even if they were only in deleted files:
   - Postmark server token.
   - `FELLOWS_SESSION_SECRET` on the droplet.
   - Any SSH keys whose public parts were committed.

5. **Verify** with `git log --all --full-history -- final_fellows_set/` returning empty, and `git count-objects -v` showing a smaller repo.

6. **Republish the `allowed_emails.json` allowlist** after scrub by re-running `python build/build_pwa.py` and redeploying — the hash file is regenerated from the source JSON so scrubbing history doesn't affect what production serves.

## Project Layout

```text
build/import_json_to_sqlite.py   # JSON -> SQLite + FTS5
build/build_pwa.py               # app/static -> deploy/dist
app/
  fellows.db                     # Build artifact (gitignored)
  fellow_profile_images_by_name/ # Optional source images
  static/                        # Front-end (index.html, app.js, sw.js, manifest, icons)
  server.py                      # Local dev server
deploy/
  server.py                      # Production server (static + auth + API fallback)
  sqlite_api_support.py          # Shared SQLite query helper
  magic_link_auth.py             # Magic-link/session helper
  dist/                          # Build output (gitignored)
scripts/
  ensure_port_8765_free.sh
  deploy_pwa.sh
  smoke_prod.sh
  check_deploy_env.sh
ansible/
  site.yml
  roles/
  README.md
tests/
  test_database.py
  test_api.py
  test_magic_link_auth.py
  e2e/
```
