# EHF Fellows Local Directory

Local web app to quickly browse Edmund Hillary Fellowship fellow profiles and run experiments. 

Data and assets are local-first (SQLite + static files), served by Python stdlib.

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

The app runs against a dump of fellows data (contact emails, mobile numbers, citizenship, location, free-text responses) plus profile photos. **This data is never committed.**  If we need to write this from scratch and get all the data again: you will have obtain the JSON and image directory out-of-band from the old directory and drop them in locally:

```
final_fellows_set/
  ehf_fellow_profiles_deduped.json
  fellow_profile_images_by_name/*.{jpg,png}
```

The github tree is clean of PII.  Still, treat the contents of your app as confidential - you will be given all the info that you are entiled to by the fellows directory system. Do not paste excerpts of fellows data into issues, PRs, commit messages, or third-party tools.

## Architecture

See `[docs/Architecture.md](docs/Architecture.md)` for system design, data flow, and schema.

## Setup

### What To Install


| Goal                                                | Install                                                                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Run the app only**                                | **Python 3.8+** and built `**app/fellows.db`**. No pip deps beyond stdlib.                                                |
| **Run full test suite** (DB + API + Playwright e2e) | Python 3.8+, `**app/fellows.db`**, `**.venv`**, `pip install -r requirements-dev.txt`, and `playwright install chromium`. |


`requirements-dev.txt` only covers dev/test tools (pytest, Playwright). The app runtime itself does not need them.

> Commands below use the project's `just` command runner. See [`docs/justfile.md`](docs/justfile.md) for the full recipe list and what each one wraps. The long-form scripts still work — `just` is a shortcut, not a replacement.

### First-Time Setup (Developers)

From repo root:

```bash
just setup
```

That creates `.venv`, installs dev deps + Playwright Chromium + Ansible collections, and builds `app/fellows.db` from the canonical Knack dump.

Under the hood (run these directly if you don't have `just`):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install chromium
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
python build/restore_from_knack_scrapefile.py
```

Use `python` from the activated `.venv` when running tests so `pytest` and Playwright are on PATH. `scripts/ensure_port_8765_free.sh` expects `.venv/bin/pytest`. Run `just doctor` any time to sanity-check venv / DB / Playwright / collections / port 8765.

## Run Locally

### Server

```bash
just serve              # background + auto-opens browser (default)
just serve-fg           # foreground, watch request logs live
just stop               # stop background server
just status             # is it running?
just restart            # stop + start
just reset              # stop, canonical DB rebuild (with auto-backup), start
```

Then open `http://localhost:8765/` (the `just serve` recipe already does this).

Lower-level equivalents — useful for one-off debugging or understanding the plumbing:

```bash
python app/server.py    # raw foreground server
./run.sh                # the shell launcher just serve wraps (backgrounds with a PID file)
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

Prereqs: `.venv` active, `requirements-dev.txt` installed, Playwright Chromium installed, and `app/fellows.db` present. `just doctor` verifies all five in one shot.

```bash
just test               # full suite (port 8765 auto-freed first)
just test-fast          # DB + API only, skips Playwright (~10x faster)
just test-db            # just tests/test_database.py
just test-api           # just tests/test_api.py
just test-e2e           # just Playwright e2e
just test-e2e email     # e2e filtered by pytest -k email
just port               # free port 8765 without running tests
```

To forward pytest flags through `just test`, separate with `--`:

```bash
just test -- tests/e2e/ -v -k email_gate
```

Under the hood — what each recipe does:

```bash
./scripts/ensure_port_8765_free.sh           # frees port 8765
./scripts/ensure_port_8765_free.sh tests/ -v # frees port, runs pytest
pytest tests/test_database.py -v             # no server needed
pytest tests/test_api.py -v                  # fixture spawns the server
pytest tests/e2e/ -v                         # Playwright e2e
```

## Build And Data Pipeline

### JSON To SQLite + FTS5

```bash
just db-rebuild         # canonical Knack rebuild, auto-backup first, prints row counts
just db-stats           # row / email / image counts
just db-verify          # bytewise-diff vs app/fellows.db.backup.2026-04-08
just db-open            # open app/fellows.db in sqlite3
```

See [`docs/data_provenance.md`](docs/data_provenance.md) for the full data pipeline and why the canonical Knack rebuild is the right choice over the legacy demo importer.

Under the hood (the ETL scripts the recipes call):

```bash
python build/restore_from_knack_scrapefile.py                # canonical, what just db-rebuild runs
python build/restore_from_knack_scrapefile.py /path/to/other.json
python build/import_json_to_sqlite.py                        # legacy demo importer — see data_provenance.md
```

Raw SQL probes (for FTS5 experimentation beyond `just db-stats`):

```bash
sqlite3 app/fellows.db "SELECT COUNT(*) FROM fellows;"
sqlite3 app/fellows.db "SELECT name, slug FROM fellows WHERE name != '' ORDER BY name LIMIT 5;"
sqlite3 app/fellows.db "SELECT name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';"
```

### PWA Static Bundle

```bash
just build              # assemble deploy/dist/
just build-meta         # print the build-meta.json (timestamp + git sha) of the last build
```

Under the hood: `python build/build_pwa.py` assembles `deploy/dist/` from `app/static/`, adds `fellows.db`, images, and writes `allowed_emails.json` (SHA-256 hashes of normalized `contact_email` values from the DB).

## Production / DevOps

Production runs one Ubuntu droplet behind Caddy TLS. The unix architecture (service account, operator sudo model, systemd hardening, filesystem layout) and routine ops (build + deploy, smoke, bootstrap) are in `[docs/DevOps.md](docs/DevOps.md)`. Mechanical Ansible details (tags, galaxy install, logs, troubleshooting) are in `[ansible/README.md](ansible/README.md)`. Magic-link auth operator steps (Postmark, env file, journald event schema) are in `[docs/email_system_management.md](docs/email_system_management.md)`.

Most common commands, from the repo root:

```bash
just deploy             # test-agnostic deploy: build + ansible + HTTPS smoke
just ship               # test-fast → deploy (the full build-test-deploy-test sequence)
just ship-fast          # deploy-fast → smoke (reuse existing deploy/dist/, skip tests)
just drift              # prod X-Fellows-Build vs local HEAD + origin/main
just smoke              # HTTPS smoke check against prod
just prod-status        # systemctl status fellows-pwa caddy
just prod-logs          # journalctl -u fellows-pwa -f (over SSH)
```

Under the hood: `./scripts/deploy_pwa.sh --ask-become-pass` runs the `ansible/deploy_pwa.yml` playbook (build → rsync → restart → HTTPS smoke).

## Local Dev Notes

- **Port 8765:** Prefer `just port` (or `./scripts/ensure_port_8765_free.sh`) before manual testing when the port is occupied. Equivalent one-liner: `lsof -ti:8765 | xargs kill -9`. Every `just test*` recipe frees the port automatically.
- **Automation hygiene:** test runs should not leave long-lived servers running. If the port is stuck, run the script above or re-run pytest (which also attempts cleanup in fixtures).
- **Virtualenv scope:** use `.venv` for dev/test tooling on your workstation; production server runtime uses system Python.
- **Debugging a stuck PWA / service worker:** when a bug reproduces on your own browser but not on a clean Playwright profile, see `[docs/debugging.md](docs/debugging.md)` for the chrome-devtools-mcp setup that attaches Claude Code to your running Chrome.

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

