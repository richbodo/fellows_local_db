# EHF Fellows Local Directory

Local web app to browse Edmund Hillary Fellowship fellow profiles and run experiments. Data and assets are fully local (SQLite + static files); uses a Python server and system browser.

## Data note

The app uses a dump of the fellows data from their wiki in json: `final_fellows_set/ehf_fellow_profiles_deduped.json`, and some profile images that were retrieved from it. Not all fellows data came across, so some records are incomplete at the time of this writing.
Even though it's demo data, and incomplete as of this writing, it's still confidential.

## Architecture

See [docs/Architecture.md](docs/Architecture.md) for system design, data flow, and database schema.

## Setup

- **Python 3** (3.8+).
- Optional (for tests): create a venv and install dev deps:

```bash
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
```

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

Port 8765 is freed automatically before the server starts. Tests are organized by function:

```bash
# All tests
pytest tests/ -v

# By category
pytest tests/test_database.py -v   # DB schema, FTS5, data integrity
pytest tests/test_api.py -v        # HTTP API endpoints
pytest tests/e2e/ -v               # Playwright browser tests (directory + detail view)
```

For e2e tests, install Playwright browsers once:

```bash
pip install -r requirements-dev.txt
playwright install chromium
```

The e2e suite starts the app server in the background, loads the app in Chromium, checks the directory list, and clicks through to a fellow’s detail view.

---

### Dev coordination (you + AI)

- **You run tests**: When you run `pytest tests/`, the test run **frees port 8765** before starting the server, so you don’t have to shut down anything first. If a server was left running from a previous session, it will be killed automatically.
- **AI note**: When the AI implements a change, it will remind you to run the relevant tests so you can verify. The AI will not leave a long-lived server running in your terminal; if something is still on 8765, the next `pytest` run will free it.
- **Manual free (optional)**: To free the port yourself (e.g. to run the app server manually), run:  
  `lsof -ti:8765 | xargs kill -9`  
  or use `./scripts/ensure_port_8765_free.sh` if that script is present.

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

## Project layout

```
build/import_json_to_sqlite.py   # JSON → SQLite + FTS5
app/
  fellows.db                     # Produced by build (gitignored)
  fellow_profile_images_by_name/ # 268 images, slug-named (optional)
  static/                        # Front-end (index.html, app.js, styles.css)
  server.py                      # Python server
run.sh                           # Launcher: start server + open browser
tests/
  conftest.py                    # Shared fixtures (app_server, db)
  test_database.py               # DB schema, FTS5, data integrity
  test_api.py                    # HTTP API endpoints
  e2e/
    conftest.py                  # e2e server + base_url fixture
    test_directory.py            # Playwright: directory page
    test_detail_view.py          # Playwright: detail view
```
