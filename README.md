# EHF Fellows Local Directory

Local web app to browse Edmund Hillary Fellowship fellow profiles and run experiments. Data and assets are fully local (SQLite + static files); uses a Python server and system browser.

## Data note

The app uses a dump of the fellows data from their wiki in json: `final_fellows_set/ehf_fellow_profiles_deduped.json`, and some profile images that were retrieved from it. Not all fellows data came across, so some records are incomplete at the time of this writing.
Even though it's demo data, and incomplete as of this writing, it's still confidential.

## Architecture

See [docs/Architecture.md](docs/Architecture.md) for system design, data flow, and database schema.

## What to install

| Goal | Install |
|------|---------|
| **Run the app only** | **Python 3.8+** and a built **`app/fellows.db`** (see [Build script](#build-script-json-to-sqlite--fts5)). No pip packages beyond the stdlib. |
| **Run the full test suite** (database + HTTP API + Playwright e2e) | Python 3.8+, **`app/fellows.db`**, a **virtualenv** (this README uses **`.venv`**), **`pip install -r requirements-dev.txt`**, and **Playwright’s Chromium** (`playwright install chromium` once per machine). |

**`requirements-dev.txt`** pins pytest, Playwright, and pytest-playwright. After installing it, you must download browsers; the app itself does not need Playwright.

## First-time setup (developers)

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
playwright install chromium        # required for tests under tests/e2e/
python build/import_json_to_sqlite.py   # creates app/fellows.db (see below)
```

Then start the server:

```bash
python app/server.py
```

Use **`python`** from the activated venv when running tests so `pytest` and Playwright are on your PATH. The helper script [`scripts/ensure_port_8765_free.sh`](scripts/ensure_port_8765_free.sh) expects pytest at **`.venv/bin/pytest`** (same layout as above).

## Server

### Run the server

From the repo root:

```bash
python app/server.py
```

Then open http://localhost:8765/ in your browser.

Or use the launcher (starts server and opens browser):

```bash
chmod +x run.sh
./run.sh
```

### API endpoints

- `GET /api/fellows` – **list only** (record_id, slug, name) for instant directory load
- `GET /api/fellows?full=1` – all fellows as full JSON array (used in background after directory is shown)
- `GET /api/fellows/<slug>` – one fellow by slug or `record_id` (e.g. `/api/fellows/aaron_bird`)
- `GET /api/search?q=...` – FTS5 search (e.g. `?q=Aaron`)
- `GET /api/stats` – JSON aggregates for the About page (counts by type, cohort, region, field completeness)
- `GET /images/<slug>.jpg` or `.png` – profile image. The server looks in `app/fellow_profile_images_by_name/` first; if that folder is missing, it uses `final_fellows_set/fellow_profile_images_by_name/` (so images work without copying). Files should be named by slug (e.g. `aaron_bird.jpg`) or by name (e.g. "Aaron Bird.jpg"); the server matches both.
- `GET /` – static app (index.html)

### Two-phase load (instant directory)

The app loads the directory quickly by requesting only the minimal list first (`GET /api/fellows`), then fetches full data in the background (`GET /api/fellows?full=1`). The directory page shows **names and links only**—no images. Profile images are requested only when you open a fellow’s detail (`#/fellow/<slug>`), one image at a time. The About page (`#/about`) loads statistics from `GET /api/stats`.

### Run tests

**Prerequisites:** virtualenv activated, **`requirements-dev.txt`** installed, **`playwright install chromium`** done, and **`app/fellows.db`** present.

**Port 8765:** API and e2e tests start a local HTTP server on **8765**. `tests/conftest.py` tries to kill whatever is listening before binding; if bind still fails (“address already in use”), free the port first.

**Recommended (free port, then run all tests):**

```bash
chmod +x scripts/ensure_port_8765_free.sh    # once
./scripts/ensure_port_8765_free.sh tests/ -v
```

With no arguments, the script only frees the port and exits:

```bash
./scripts/ensure_port_8765_free.sh
```

**Or** run pytest directly (after freeing the port manually if needed):

```bash
pytest tests/ -v
```

**By category:**

```bash
pytest tests/test_database.py -v   # DB schema, FTS5, data integrity
pytest tests/test_api.py -v        # HTTP API (uses session server on 8765)
pytest tests/e2e/ -v               # Playwright: directory + detail UI
```

The e2e suite starts the app in the background, opens Chromium, and exercises the directory and detail flows.

---

### Dev coordination (you + AI)

- **Port 8765**: Prefer **`./scripts/ensure_port_8765_free.sh`** before manual testing if something else is bound to the port. Equivalent one-liner: `lsof -ti:8765 | xargs kill -9` (macOS/Linux with `lsof`).
- **AI note**: Automated test runs should not leave a long-lived server running; if the port is stuck, run the script above or `pytest` (which attempts to free the port first).

---

## Build script (JSON to SQLite + FTS5)

Import fellow profiles into the database:

```bash
python build/import_json_to_sqlite.py                       # default JSON path
python build/import_json_to_sqlite.py /path/to/other.json   # custom JSON path
```

This reads the JSON and writes `app/fellows.db` (table `fellows` + FTS5 table `fellows_fts`). If `fellows.db` already exists, it is backed up to `app/fellows.db.backup.YYYY-MM-DD` before overwriting.

### Verify

```bash
sqlite3 app/fellows.db "SELECT COUNT(*) FROM fellows;"
sqlite3 app/fellows.db "SELECT name, slug FROM fellows WHERE name != '' ORDER BY name LIMIT 5;"
sqlite3 app/fellows.db "SELECT name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';"
```

### PWA static bundle (production)

Copy the current `app/static/` tree into `deploy/dist/` before Ansible or manual upload:

```bash
python build/build_pwa.py
```

See `ansible/README.md` for deploy. Phase 2 extends this script with `fellows.db` and images.

## Project layout

```
build/import_json_to_sqlite.py   # JSON → SQLite + FTS5
build/build_pwa.py               # app/static → deploy/dist (PWA deploy bundle)
app/
  fellows.db                     # Produced by build (gitignored)
  fellow_profile_images_by_name/ # 268 images, slug-named (optional)
  static/                        # Front-end (index.html, app.js, manifest, icons, …)
  server.py                      # Python server
run.sh                           # Launcher: start server + open browser
scripts/
  ensure_port_8765_free.sh       # Free 8765; optional: pass pytest args (uses .venv/bin/pytest)
tests/
  conftest.py                    # Shared fixtures (app_server, db)
  test_database.py               # DB schema, FTS5, data integrity
  test_api.py                    # HTTP API endpoints
  e2e/
    conftest.py                  # e2e server + base_url fixture
    test_directory.py            # Playwright: directory page
    test_detail_view.py          # Playwright: detail view
```
