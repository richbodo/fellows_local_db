# EHF Fellows Local Directory

Local web app to browse 442 Edmund Hillary Fellowship fellow profiles. Data and assets are fully local (SQLite + static files); first version uses a Python server and system browser.

## Data note

The app uses `final_fellows_set/ehf_fellow_profiles_deduped.json`. In that file, work-related fields (ventures, industries, career_highlights, key_networks, how_im_looking_to_support_the_nz_ecosystem, what_is_your_main_mode_of_working) are often **empty** for many fellows, including Aaron Bird. If your reference “Internal Directory” profile shows richer work details, that data likely comes from a different or fuller export; when those fields are present in the JSON they are stored in the DB and shown in the Work column.

## Plan

See [PLAN.md](PLAN.md) for architecture and development milestones.

## Setup

- **Python 3** (3.8+).
- Optional (for tests): create a venv and install dev deps:

```bash
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
```

## Milestone 2: Python server and API

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
- `GET /api/fellows?full=1` – all 442 fellows as full JSON array (used in background after directory is shown)
- `GET /api/fellows/<slug>` – one fellow by slug or `record_id` (e.g. `/api/fellows/aaron_bird`)
- `GET /api/search?q=...` – FTS5 search (e.g. `?q=Aaron`)
- `GET /images/<slug>.jpg` or `.png` – profile image. The server looks in `app/fellow_profile_images_by_name/` first; if that folder is missing, it uses `final_fellows_set/fellow_profile_images_by_name/` (so images work without copying). Files should be named by slug (e.g. `aaron_bird.jpg`) or by name (e.g. "Aaron Bird.jpg"); the server matches both.
- `GET /` – static app (index.html)

### Two-phase load (instant directory)

The app loads the directory quickly by requesting only the minimal list first (`GET /api/fellows`), then fetches full data in the background (`GET /api/fellows?full=1`). The directory page shows **names and links only**—no images. Profile images are requested only when you open a fellow’s detail (`#/fellow/<slug>`), one image at a time.

### Run M2 tests

Port 8765 is freed automatically before the server starts. Run:

```bash
pytest tests/test_milestone2_server.py -v
```

### Run E2E tests (Playwright)

Regression tests that load the app in a real browser, check the directory list, and click through to a fellow’s detail. **No MCP server or extra setup is required**—run the same commands in your dev environment (or in CI).

1. Install dev deps and Playwright browsers (one-time):

```bash
pip install -r requirements-dev.txt
playwright install chromium
```

2. Run (port 8765 is freed automatically if something is using it):

```bash
pytest tests/e2e/ -v
```

The e2e suite starts the app server in the background, then uses Chromium to open the homepage, wait for the directory list, assert there are no images on the directory, click “Aaron Bird”, and verify the detail view. **Run this after each implementation step** to confirm everything works from an end-user perspective.

---

### Dev coordination (you + AI)

- **You run tests**: When you run `pytest tests/e2e/` or `pytest tests/test_milestone2_server.py`, the test run **frees port 8765** before starting the server, so you don’t have to shut down anything first. If the AI left a server running from a previous session, it will be killed automatically.
- **AI note**: When the AI implements a change, it will remind you to run the relevant tests (e2e and/or M2) so you can verify from an end-user perspective. The AI will not leave a long-lived server running in your terminal; if something is still on 8765, the next `pytest` run will free it.
- **Manual free (optional)**: To free the port yourself (e.g. to run the app server manually), run:  
  `lsof -ti:8765 | xargs kill -9`  
  or use `./scripts/ensure_port_8765_free.sh` if that script is present.

---

## Milestone 1: Build script and SQLite + FTS5

### Run the import

From the repo root:

```bash
python build/import_json_to_sqlite.py
```

This reads `final_fellows_set/ehf_fellow_profiles_deduped.json` and writes `app/fellows.db` (table `fellows` + FTS5 table `fellows_fts`).

### Verify

```bash
# Row count
sqlite3 app/fellows.db "SELECT COUNT(*) FROM fellows;"
# → 442

# Sample names and slugs
sqlite3 app/fellows.db "SELECT name, slug FROM fellows WHERE name != '' ORDER BY name LIMIT 5;"

# FTS5 search
sqlite3 app/fellows.db "SELECT name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';"
```

### Run tests

```bash
# With venv active:
pytest tests/test_milestone1_build.py -v
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
  test_milestone1_build.py       # M1 DB tests
  test_milestone2_server.py      # M2 API tests
  e2e/
    conftest.py                  # Start server on 8765 for e2e
    test_app_e2e.py              # Playwright: directory + detail
```

## Next: Milestone 3

Static shell and directory list are done (with two-phase load). Remaining: optional search UI, polish.
