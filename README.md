# EHF Fellows Local Directory

Local web app to quickly browse Edmund Hillary Fellowship fellow profiles, organize them into saved groups, and export sub-directories — and to run experiments. (data only available to EHF fellows)

Data and assets are local-first (SQLite + static files), served by Python stdlib. User-authored data (groups, notes, settings) lives in a separate per-user SQLite file (`app/relationships.db`) that's durable across app updates.

## Design Stance: Local-Only, Not SaaS

**This app is Never-SaaS.** It is a single-user, local-only directory. The PWA + magic-link delivery is a *distribution and update channel*, not a service: production exists to hand a fellow the bundle and the contact DB, then get out of the way.

After install, the app must keep working without further server contact. Concretely:

- **All user-authored state** (groups, notes, tags, settings) lives in the user's browser (`relationships.db` in OPFS). Production's `deploy/server.py` does not expose `/api/groups` or `/api/settings` — there are no per-user resources on the server, no per-user storage to back up, no multi-tenant model to defend.
- **Reads of contact data** run against the locally-cached `fellows.db` (OPFS) and the IndexedDB fallback cache. A stale session or an offline server must not lock the user out of data they've already downloaded — see `[docs/email_gate.md](docs/email_gate.md)` invariant 10.
- **Server contact is bounded to two purposes only:** (1) the magic-link gate that authorizes a download, and (2) fetching new bundle / DB bytes when the user opts in to an update (app-shell updates auto-prompt via the *New version available — Reload* banner; directory-data updates are user-initiated from the About page — see `[docs/users_manual.md` § Updates](docs/users_manual.md#updates)). Anything else added server-side needs a strong justification against this constraint.

## Table of Contents

- [Design Stance: Local-Only, Not SaaS](#design-stance-local-only-not-saas)
- [Data Note](#data-note)
- [Architecture](#architecture)
- [Setup](#setup)
  - [What To Install](#what-to-install)
  - [First-Time Setup (Developers)](#first-time-setup-developers)
- [Run Locally](#run-locally)
  - [Server](#server)
  - [API Endpoints](#api-endpoints)
  - [Two-Phase Load](#two-phase-load)
- [Testing The Latest Code In A Browser](#testing-the-latest-code-in-a-browser)
  - [1. Local Dev — See The Latest `main](#1-local-dev--see-the-latest-main)`
  - [2. Local Dev — Exercise The Email-Gate UI](#2-local-dev--exercise-the-email-gate-ui)
  - [3. Prod — First-Time Visitor Simulation](#3-prod--first-time-visitor-simulation)
  - [4. Prod — Reset State In An Existing Tab](#4-prod--reset-state-in-an-existing-tab)
- [Testing](#testing)
- [Build And Data Pipeline](#build-and-data-pipeline)
  - [JSON To SQLite + FTS5](#json-to-sqlite-fts5)
  - [PWA Static Bundle](#pwa-static-bundle)
- [Production / DevOps](#production--devops)
  - [Shipping a change (the standard rubric)](#shipping-a-change-the-standard-rubric)
- [Local Dev Notes](#local-dev-notes)
- [Before Making This Repo Public](#before-making-this-repo-public)
- [Project Layout](#project-layout)

## Data Note

This document is primarily written for developers.  The end-user documentation is here: [User Guide](docs/users_manual.md)

The app runs against a dump of fellows data (contact emails, mobile numbers, citizenship, location, free-text responses) plus profile photos. **This data is never committed.**  If we need to write this from scratch and get all the data again: you will have obtain the JSON and image directory out-of-band from the old directory and drop them in locally:

```
final_fellows_set/
  ehf_fellow_profiles_deduped.json
  fellow_profile_images_by_name/*.{jpg,png}
```

The github tree is clean of PII.  Still, treat the contents of your app as confidential - you will be given all the info that you are entiled to by the fellows directory system. Do not paste excerpts of fellows data into issues, PRs, commit messages, or third-party tools.

## Architecture

See `[docs/Architecture.md](docs/Architecture.md)` for system design, data flow, and schema.

The origin of this app was [prt](https://github.com/richbodo/prt) and the next version of prt that will be able to build apps like this is [personal_network_toolkit](https://github.com/richbodo/personal_network_toolkit)

## Setup

### What To Install


| Goal                                                | Install                                                                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Run the app only**                                | **Python 3.8+** and built `**app/fellows.db`**. No pip deps beyond stdlib.                                                |
| **Run full test suite** (DB + API + Playwright e2e) | Python 3.8+, `**app/fellows.db`**, `**.venv`**, `pip install -r requirements-dev.txt`, and `playwright install chromium`. |


`requirements-dev.txt` only covers dev/test tools (pytest, Playwright). The app runtime itself does not need them.

> Commands below use the project's `just` command runner. **Run `just` (or `just --list`) at the repo root for a grouped menu of every recipe**; run `just <recipe>` to invoke one (e.g. `just doctor`). Full reference with what each recipe wraps: `[docs/justfile.md](docs/justfile.md)`. The long-form scripts still work — `just` is a shortcut, not a replacement.

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

Fellow data (read-only, served from `app/fellows.db`):

- `GET /api/fellows` — list only (`record_id`, `slug`, `name`, `has_contact_email`) for fast directory load.
- `GET /api/fellows?full=1` — full fellow rows.
- `GET /api/fellows/<slug>` — one fellow by slug or `record_id`.
- `GET /api/search?q=...` — FTS5 search.
- `GET /api/stats` — aggregates for About page.

Groups (read-write, served from `app/relationships.db` with `app/fellows.db` ATTACHed read-only):

- `GET /api/groups` — list of saved groups with member counts (newest-touched first).
- `POST /api/groups` — create a group (`{name, note?, fellow_record_ids?}`); 201.
- `GET /api/groups/<id>` — one group with members joined to fellow names.
- `PATCH /api/groups/<id>` — partial update (any subset of `name`, `note`, `fellow_record_ids`).
- `DELETE /api/groups/<id>` — delete; cascades to `group_members`. 204.

Settings (read-write, key/value bag in `app/relationships.db`):

- `GET /api/settings` — full bag.
- `GET /api/settings/<key>` — one setting; 404 if unset.
- `PUT /api/settings/<key>` — upsert (`{value: "…"}`); empty value clears.

Static / bootstrap:

- `GET /fellows.db` — raw SQLite file for installed PWA bootstrap.
- `GET /images/<slug>.jpg|.png` — profile image lookup by slug/name fallback.
- `GET /` — static app shell.

Production (`deploy/server.py`) adds magic-link auth (`/api/send-unlock`, `/api/verify-token`, `/api/logout`), an unauthenticated client-error sink (`POST /api/client-errors` — sanitized, rate-limited, always 204; see `[docs/email_gate.md` § Client error reporting](docs/email_gate.md#client-error-reporting) for the schema and privacy boundary), and build/diagnostics endpoints (`/healthz`, `/build-meta.json`, `/api/debug/diagnostics`); see `[docs/email_gate.md](docs/email_gate.md)`.

### Two-Phase Load

The UI requests `/api/fellows` first (instant list), then fetches `/api/fellows?full=1` in the background. Directory view is names/links only; images load on detail view only.

## Testing The Latest Code In A Browser

This is about manual QA — driving the running app in a browser to verify a change. For the pytest / Playwright suite see [Testing](#testing) below.

The trap is **stale state**. The PWA's service worker, OPFS (`relationships.db`, `fellows.db`), IndexedDB, the `fellows_session` HttpOnly cookie, and the `fellows_authenticated_once` localStorage marker all persist by design. DevTools' "Clear site data" misses several layers, and the in-app **Clear App Cache** button intentionally preserves OPFS + the auth-once marker. Below is what actually works for each scenario.

### 1. Local Dev — See The Latest `main`

```bash
git checkout main && git pull
just stop
just serve-fg            # foreground; you can watch request logs live
```

Then **hard-reload** the localhost tab (Cmd-Shift-R / Ctrl-Shift-R). Restarting the server bumps `BUILD_META`, which knocks the SW into fetching a fresh shell on next load. The localhost passthrough (PR #63) means you won't get trapped on the install landing.

If the page still feels stale, open an **incognito/private window** at `http://localhost:8765/` — no SW registered, no localStorage, no OPFS for that profile; you're guaranteed to see the latest bundle.

What persists across this flow on localhost (intentionally):

- `relationships.db` in OPFS — your saved groups and notes.
- `fellows.db` in OPFS — re-imported on every boot anyway.

### 2. Local Dev — Exercise The Email-Gate UI

```bash
just gate                 # opens http://localhost:8765/?gate=1
```

The gate UI renders, but the dev server has **no `/api/send-unlock`** — submitting the form fails. To exercise the actual magic-link round-trip, either run the e2e suite (`just test-e2e -- -k email_gate`, which spins up `deploy/server.py` in-process with a fake Postmark) or test against prod (scenarios 3 / 4).

### 3. Prod — First-Time Visitor Simulation

The cleanest "what does a fresh fellow see?" test is a **new incognito/private window** pointed at `https://fellows.globaldonut.com/`. Nothing carries over: no SW, no OPFS, no cookies, no localStorage. This is the canonical pre-deploy smoke for any UX change touching the install landing or gate.

Pair with:

```bash
just smoke                # HTTPS health-check + manifest probe
just drift                # confirm prod is on current main
```

### 4. Prod — Reset State In An Existing Tab

When you need to test from inside a tab you've already used (an installed PWA, a session locked into a stale shell, a debugging trail you don't want to abandon), DevTools' "Clear site data" misses the HttpOnly session cookie *and* OPFS. Use this sequence:

1. **Drop the HttpOnly session cookie.** It's HttpOnly — JS can't see or unset it. Only the server can. Paste into the DevTools console:
  ```js
   await fetch('/api/logout', { method: 'POST', credentials: 'include' });
  ```
2. **Nuke every browser-side persistence layer (except OPFS).** Paste into the DevTools console:
  ```js
   localStorage.clear();
   sessionStorage.clear();
   indexedDB.deleteDatabase('fellows-local-db');
   caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k))))
     .then(() => navigator.serviceWorker.getRegistrations())
     .then(rs => Promise.all(rs.map(r => r.unregister())))
     .then(() => location.reload());
  ```
3. After the reload you land at the **email gate** as a first-time visitor.

What this does *not* clear:

- **OPFS** (`relationships.db`, `fellows.db`). There is no JS API to wipe per-origin OPFS. To clear OPFS too, use **chrome://settings → Cookies and site data → fellows.globaldonut.com → Delete** (clears OPFS along with everything else), or just open a fresh incognito window (scenario 3).
- HTTP/disk cache for static assets — but the SW unregister + Cache API delete in step 2 makes this moot; the next load re-fetches from the server.

If you only need to **force the gate UI** without nuking state — for example, to test the gate's banner copy — append `?gate=1` to the URL. That overrides the decision tree at the UI layer but leaves the cookie and OPFS intact.

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

See `[docs/data_provenance.md](docs/data_provenance.md)` for the full data pipeline.

Under the hood (the ETL script the recipes call):

```bash
python build/restore_from_knack_scrapefile.py                # canonical, what just db-rebuild runs
python build/restore_from_knack_scrapefile.py /path/to/other.json
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
just drift              # prod git SHA vs local HEAD + origin/main (SHA-aligned)
just smoke              # HTTPS smoke check against prod
just prod-status        # systemctl status fellows-pwa caddy
just prod-logs          # journalctl -u fellows-pwa -f (over SSH)
just prod-stats         # 24h summary: page loads, magic-link sends/verifies, 5xx, disk
just prod-stats-long    # full-history tally + plaintext list of every magic-link recipient
```

Under the hood: `./scripts/deploy_pwa.sh --ask-become-pass` runs the `ansible/deploy_pwa.yml` playbook (build → rsync → restart → HTTPS smoke).

### Shipping a change (the standard rubric)

After PRs merge to `main`, deploy with:

```bash
git checkout main && git pull         # confirm merges are local
just ship                             # build → test → deploy → smoke
just whats-running                    # confirm prod's git SHA matches local HEAD
```

That's the whole flow. The build label (`<YYYY-MM-DD>-<short-sha>`) is stamped into `FELLOWS_UI_DIAG` and `CACHE_VERSION` automatically by `build/build_pwa.py` from the current `git HEAD`, so every deploy gets a unique label tied to the code being shipped — no separate bump step, no `chore(version):` commit.

A few notes:

- **The dev server stamps the same label.** `python app/server.py` (and `just serve`) substitutes the placeholder when serving `app.js` and `sw.js`, using the current `git HEAD` short SHA. So the build badge in dev shows the live source SHA. If you see the literal `__FELLOWS_UI_DIAG__` in the badge, something is wrong with the substitution path — likely a stale `deploy/dist/` served raw or an unbuilt bundle in front of you.
- **Test on prod, not localhost, when the change touches auth or session state.** The dev server returns `authEnabled: false` and skips the email gate entirely — checks like "Clear App Cache lands me at the gate" don't reproduce locally. The Playwright e2e suite (`just test-e2e ...`) mocks the prod auth path; `https://fellows.globaldonut.com` is the real verification.
- **What's deployed lives in the response, not in `git log`.** Use `just drift` to compare prod's `git_sha` (read from `/build-meta.json`) to local `HEAD` and `origin/main` — three SHA-aligned lines so a glance tells you whether all three match. The `X-Fellows-Build` response header still exists for DevTools / journald correlation; it's just not the canonical no-drift signal any more. `just whats-running` is the fuller local + prod snapshot.

## Local Dev Notes

- **Port 8765:** Prefer `just port` (or `./scripts/ensure_port_8765_free.sh`) before manual testing when the port is occupied. Equivalent one-liner: `lsof -ti:8765 | xargs kill -9`. Every `just test`* recipe frees the port automatically.
- **Automation hygiene:** test runs should not leave long-lived servers running. If the port is stuck, run the script above or re-run pytest (which also attempts cleanup in fixtures).
- **Virtualenv scope:** use `.venv` for dev/test tooling on your workstation; production server runtime uses system Python.
- **Debugging a stuck PWA / service worker:** when a bug reproduces on your own browser but not on a clean Playwright profile, see `[docs/debugging.md](docs/debugging.md)` for the chrome-devtools-mcp setup that attaches Claude Code to your running Chrome.

## Project Layout

```text
build/restore_from_knack_scrapefile.py  # Knack JSON -> SQLite + FTS5
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

