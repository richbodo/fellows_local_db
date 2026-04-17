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
- [Production Operations](#production-operations)
  - [Deploy Model](#deploy-model)
  - [Routine Deploy](#routine-deploy)
  - [Magic-Link Auth And Email](#magic-link-auth-and-email)
  - [Debugging Installed PWA](#debugging-installed-pwa)
- [DevOps Notes](#devops-notes)
- [Project Layout](#project-layout)

## Data Note

The app uses a dump of fellows data from `final_fellows_set/ehf_fellow_profiles_deduped.json` plus retrieved profile images. Some records are incomplete. Even as demo data, treat it as confidential.

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

## Production Operations

### Deploy Model

The VPS serves `deploy/dist/` via `deploy/server.py` on `127.0.0.1:8765` behind Caddy TLS.

- Caddy site example: `deploy/Caddyfile.example` (templated in `ansible/roles/caddy/templates/Caddyfile.j2`).
- Smoke: `./scripts/smoke_prod.sh` (`FELLOWS_BASE_URL=...` override).
- DNS/TLS check: `./scripts/check_deploy_env.sh` (`FELLOWS_HOST=...` override).

`deploy/server.py` supports `FELLOWS_DIST_ROOT`. Logs go to stdout/stderr and are collected by journald under systemd.

### Routine Deploy

Preferred:

```bash
./scripts/deploy_pwa.sh --ask-become-pass
```

Equivalent manual flow:

```bash
python build/build_pwa.py
ansible-playbook ansible/site.yml --tags deploy --ask-become-pass
```

For inventory/bootstrap/systemd details, use [`ansible/README.md`](ansible/README.md).

### Magic-Link Auth And Email

Browser access can be gated by email magic links when:

- `deploy/dist/allowed_emails.json` exists and is non-empty (built by `build/build_pwa.py`), and
- server env includes `FELLOWS_SESSION_SECRET` and `FELLOWS_POSTMARK_TOKEN`.

When enabled, `deploy/server.py`:

- accepts `POST /api/send-unlock` and `POST /api/verify-token`,
- sets a signed session cookie after token verification, and
- requires session auth for `/fellows.db`, `/images/*`, and directory `/api/*` endpoints.

Detailed operator steps, production setup, and debugging are in [`docs/email_system_management.md`](docs/email_system_management.md).

### Debugging Installed PWA

If standalone app fails to load, the UI shows a developer report with boot trace and HTTP probe status. Also check Chrome DevTools:

- Application → Service Workers / Storage
- Network (verify `/fellows.db` and `/api/*` responses and cache behavior)

**Browser vs server bundle drift (stale `app.js`):** In the deployed app, open the **Diagnostics** control (fixed button, or add **`?diag=1`** to the URL). It fetches `/api/auth/status`, `/api/debug/diagnostics`, and `/build-meta.json`, and lists service worker and Cache API state. Compare **response headers** `X-Fellows-Build` / `X-Fellows-Auth-Active` with the JSON body. The session cookie is **HttpOnly**, so **Application → Cookies** may show `fellows_session` even when `document.cookie` looks empty.

**Server logs (production):** `deploy/server.py` logs structured lines to stderr for each `GET /api/auth/status` (`event=auth_status`, …) and once at startup for `build-meta` (`event=build_meta`). View with `journalctl -u fellows-pwa -f` on the app server (see [`ansible/README.md`](ansible/README.md)).

## DevOps Notes

- **Port 8765:** Prefer `./scripts/ensure_port_8765_free.sh` before manual testing when the port is occupied. Equivalent one-liner: `lsof -ti:8765 | xargs kill -9`.
- **Automation hygiene:** test runs should not leave long-lived servers running. If the port is stuck, run the script above or re-run pytest (which also attempts cleanup in fixtures).
- **Virtualenv scope:** use `.venv` for dev/test tooling on your workstation; production server runtime uses system Python.

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
