# EHF Fellows Local Directory – Architecture Plan

## Current state

- **Data**: [final_fellows_set/ehf_fellow_profiles_deduped.json](final_fellows_set/ehf_fellow_profiles_deduped.json) – 442 records; each has `name`, `record_id`, `bio_tagline`, `image_url`, `cohort`, `fellow_type`, `contact_email`, `key_links` / `key_links_urls`, and many optional fields (some records have sparse fields).
- **Images**: The `fellow_profile_images_by_name` folder exists in the workspace with 268 images named by slug (e.g. `aaron_bird.jpg`, `alex_mccall.png`). Slug is derived from name (e.g. `"Aaron Bird"` → `aaron_bird`). Not all 442 fellows have an image; the app will show a placeholder when an image is missing.
- **Design reference**: You referenced a sample directory view at `final_fellows_set/aaron_bird_directory_view.png`; the plan assumes that image defines the desired detail-page layout when you add it.

---

## High-level architecture

- **One zip** contains: SQLite DB, images folder, static front-end (HTML/JS/CSS), and a small server (or launcher that runs it and opens the app).
- **No remote calls**: All data and assets are local; the server only reads from the DB and files.

---

## 1. SQLite schema and FTS5

**Main table: `fellows`**

- Store one row per fellow. Prefer a **normalized schema** (flat columns for the fields you display and search) to keep queries simple and FTS5 straightforward.
- **Primary key**: `record_id` (already unique in the JSON).
- **Stable slug**: Add a computed column or store `slug` (e.g. `aaron_bird`) for URLs and image lookup: lowercase, spaces → underscores, strip accents if you need to match image filenames consistently.
- **Columns**: Include at least: `record_id`, `slug`, `name`, `bio_tagline`, `fellow_type`, `cohort`, `contact_email`, `key_links`, `key_links_urls` (store as JSON text or separate table), `image_url`, `currently_based_in`, plus any other fields you want on the directory or detail view. Optional/rare fields can live in a single JSON column to avoid a huge number of columns.

**FTS5 for "super snappy" search**

- Create an FTS5 virtual table (e.g. `fellows_fts`) over the columns you want to search: at least `name`, `bio_tagline`, `cohort`, `fellow_type`, and optionally `search_tags`, `key_links`, etc.
- Use **external content** table: FTS5 indexes the content, but the actual data stays in `fellows`. This avoids duplicating large text and keeps FTS5 tables small and fast.
- **Sync**: Build the DB once from JSON and repopulate FTS at build time (no triggers) if the app is read-only.
- **Queries**: For directory search, run FTS5 queries (e.g. `MATCH ?`) and join to `fellows` on `rowid` or a mapped id to get full rows. For "browse by name" with no search term, query `fellows` ordered by `name`; FTS5 is only needed when the user types a search.

**Why this stays fast**

- FTS5 gives sub-ms full-text search on 442 rows.
- Directory list: single `SELECT ... FROM fellows ORDER BY name` with only the columns needed for the list (e.g. `record_id`, `slug`, `name`) — trivial for SQLite.
- Detail view: single row by `record_id` or `slug` — indexed, no full-text needed.

---

## 2. Making the front-end "almost instant" on link click

**Chosen approach: Preload all fellows (A)**

- On first load, the server exposes a single endpoint that returns **all 442 full records** (or all fields needed for the detail view) in one JSON response so the front-end can preload everything.
- Front-end: on app init, fetch the full dataset and keep it in memory (e.g. a `Map` by `slug` or `record_id`).
- **Directory**: render the list from the in-memory list; no per-name request.
- **Detail**: when a link is clicked, render the detail view from the in-memory object — **no network request**, so it feels instant.
- Trade-off: one slightly larger initial load (~1–2 MB for 442 records); in return, every navigation is instant and works offline after first load. This is the chosen approach for the first version.

---

## 3. Local server and API

- **Role**: Serve static assets (HTML, JS, CSS) and expose a small REST API that reads from SQLite and serves the images folder.
- **Stack**: **Python** for the server and all backend tooling (e.g. build script to import JSON → SQLite). Use as much Python as is practical to keep the stack simple and portable.
- **Endpoints**:
  - `GET /api/fellows?full=1` – return all 442 fellows in one JSON response for preloading (full records for instant detail view).
  - `GET /api/fellows/:id` – one fellow by `record_id` or `slug` (optional fallback if needed).
  - `GET /api/search?q=...` – FTS5 search; return matching fellows.
  - `GET /images/:slug.jpg` (and e.g. `.png`) – serve from `fellow_profile_images_by_name`; 404 when image missing (front-end shows placeholder).
- **SQLite**: Open the DB once at startup; FTS5 and indexed lookups keep responses very fast.

---

## 4. Front-end structure

- **Single-page app (SPA)**:
  - One HTML shell; directory view and fellow detail view are two "screens" or sections (e.g. list + detail panel, or list then scroll-to-detail).
  - Use **hash routing** (e.g. `#/fellow/aaron_bird`) or **history** with a base path so that a link to a fellow is shareable and refreshable; on load, read hash/path and render the corresponding fellow from in-memory data.
- **Directory (list)**: Render all names from the in-memory list; each name is a link to `#/fellow/<slug>`. Optional: search box that filters in memory (still very fast for 442 items).
- **Detail view**: Layout and fields follow the reference image. Image: request `/images/<slug>.jpg` or `.png`; on 404, show a placeholder. All data for the card comes from the preloaded fellow object so the only async part is the image.
- **Tech**: **Vanilla JS only** — no frameworks. Keeps the bundle small, the zip self-contained, and the app simple to maintain for distribution to ~500 users.

---

## 5. Packaging and portable distribution

**First version (chosen): Launcher + small server + system browser**

- **Rationale**: Using Chromium/Electron for v1 would slow development. A launcher that starts a small Python server and opens the system browser is the fastest path to a working, simple, and portable app. It can be wrapped in Electron or Tauri later for a single executable if desired.
- **Audience**: ~500 users; keeping the app simple and portable is a priority.
- **Zip contents**: Python server script(s), `fellows.db`, `fellow_profile_images_by_name/`, `static/` (index.html, app.js, styles.css).
- **Launcher**: Script (e.g. `run.sh` / `run.bat`) that starts the server on a fixed port (e.g. 8765) and opens `http://localhost:8765` in the default browser. Users run the launcher; no bundled Chromium. Works on any machine with Python installed, or ship a minimal Python runtime in the zip.
- **Later**: Optionally wrap in Electron/Tauri for a single executable and "double-click and go" for users who prefer not to run a launcher.

---

## 6. Build pipeline (one-time / when data changes)

1. **Import JSON → SQLite**: Parse the deduped JSON; for each record derive `slug` from `name`; insert into `fellows`; build FTS5 table at build time.
2. **Images**: Ensure images live in `fellow_profile_images_by_name/` with names like `<slug>.jpg` or `<slug>.png`; server maps slug to file (try .jpg then .png).
3. **Output**: One `fellows.db`, one images folder, one static front-end bundle — ready to zip.

---

## 7. Suggested project layout

```
fellows_local_db/
  build/
    import_json_to_sqlite.py
  app/
    server.py
    static/
      index.html
      app.js
      styles.css
    fellows.db
    fellow_profile_images_by_name/
  run.sh
  tests/
    e2e/
      playwright tests
  final_fellows_set/
    ehf_fellow_profiles_deduped.json
```

Deliverable zip: everything under `app/` plus `run.sh` (and optionally a minimal Python runtime for users without Python).

---

## 8. Summary

| Concern            | Approach |
| ------------------ | -------- |
| **Data**           | SQLite table `fellows` keyed by `record_id`; add `slug` for URLs and images. |
| **Search**         | FTS5 virtual table; use for search endpoint and/or optional search UI. |
| **Snappy list**    | Single `SELECT` for directory; preload full 442 records at startup. |
| **Instant detail** | Preload all fellows in memory; on link click, render from JS object (no request). |
| **Images**         | Serve from folder by slug; 404 → placeholder for fellows without images. |
| **Delivery**       | First version: one zip with launcher + Python server + DB + images + static files; open in system browser. Later: optional wrap in Electron/Tauri (~500 users). |

---

## 9. Development milestones (TDD-style, Playwright)

**Progress**: M1 and M2 are complete. M3 (directory list with links) and M4 (detail view and images) are implemented; M5 (search + launcher) and M6 (polish + packaging) are unchanged and on track.

Development is test-driven: write or extend Playwright e2e tests first (or just enough to define the behaviour), then implement until tests pass. Each milestone ends with a **testable output** you can run and verify with me.

**Test stack**: Playwright (e2e in Node or Python). Server runs on a fixed port (e.g. 8765) for tests; tests start the server (or assume it’s running) and drive the browser.

---

### Milestone 1: Build script and SQLite + FTS5

**Goal**: JSON → SQLite with `fellows` table and FTS5, plus slug derivation.

**TDD**:  
- (Optional) Pytest or script tests: run the build script, connect to output DB, assert row count (442), assert FTS5 table exists and returns rows for a sample query (e.g. `MATCH 'Aaron'`).

**Outputs to test**:
1. Run `python build/import_json_to_sqlite.py` (or equivalent). It reads `final_fellows_set/ehf_fellow_profiles_deduped.json` and writes `app/fellows.db`.
2. Open `app/fellows.db` in SQLite and run:  
   `SELECT COUNT(*) FROM fellows;` → 442.  
   `SELECT name, slug FROM fellows ORDER BY name LIMIT 3;` → e.g. Aaron Bird, aaron_bird; etc.  
   `SELECT rowid, name FROM fellows_fts WHERE fellows_fts MATCH 'Aaron';` → at least one row (e.g. Aaron Bird).

**Deliverables**: `build/import_json_to_sqlite.py`, `app/fellows.db` (gitignored or committed once for dev).

---

### Milestone 2: Python server and API

**Goal**: Local HTTP server that serves static files and exposes `/api/fellows?full=1`, `/api/fellows/<slug>`, `/api/search?q=...`, `/images/<slug>.<ext>`.

**TDD**:  
- Playwright or `requests`:  
  - `GET http://localhost:8765/api/fellows?full=1` → 200, JSON array of 442 objects, each has `slug`, `name`, `record_id`.  
  - `GET http://localhost:8765/api/fellows/aaron_bird` → 200, single fellow with `name` "Aaron Bird".  
  - `GET http://localhost:8765/api/search?q=Aaron` → 200, JSON array containing at least one fellow.  
  - `GET http://localhost:8765/images/aaron_bird.jpg` → 200 (or 404 if file missing).  
  - `GET http://localhost:8765/` → 200, HTML (static app shell).

**Outputs to test**:
1. Start server: `python app/server.py` (or `./run.sh` if launcher exists and only starts server).  
2. In browser or with curl:  
   - Open `http://localhost:8765/api/fellows?full=1` → see one big JSON array of 442 fellows.  
   - Open `http://localhost:8765/api/fellows/aaron_bird` → see one JSON object for Aaron Bird.  
   - Open `http://localhost:8765/images/aaron_bird.jpg` → see image or 404.  
   - Open `http://localhost:8765/` → see the app HTML (can be minimal at this step).

**Deliverables**: `app/server.py`, optional `run.sh` that starts server (and optionally opens browser). Playwright (or requests) tests in `tests/` that hit the API and static root.

---

### Milestone 3: Static shell and directory list (vanilla JS)

**Goal**: Single HTML page that fetches `/api/fellows?full=1`, stores fellows in memory, and renders the directory list (names only) with links to `#/fellow/<slug>`.

**TDD**:  
- Playwright:  
  - Load `http://localhost:8765/`.  
  - Wait for list to be visible (e.g. by role or test id).  
  - Assert at least 442 links (or list items).  
  - Assert one link has href ending with `#/fellow/aaron_bird` and text "Aaron Bird" (or similar).  
  - Click that link; assert URL hash is `#/fellow/aaron_bird` (and optionally that a detail section is visible).

**Outputs to test**:
1. Start server, open `http://localhost:8765/`.  
2. See a single-page app that loads and shows a scrollable list of fellow names (e.g. 442 names).  
3. Each name is a link; clicking "Aaron Bird" updates the URL to `#/fellow/aaron_bird` and (by end of M4) shows the detail for Aaron Bird.

**Deliverables**: `app/static/index.html`, `app/static/app.js`, minimal `app/static/styles.css`. Playwright test: load app, check list count, click one fellow, check hash.

---

### Milestone 4: Detail view and images

**Goal**: When hash is `#/fellow/<slug>`, render the fellow’s detail (name, bio_tagline, cohort, fellow_type, contact, etc.) and show profile image from `/images/<slug>.jpg` or `.png`, with placeholder on 404.

**TDD**:  
- Playwright:  
  - Navigate to `http://localhost:8765/#/fellow/aaron_bird`.  
  - Assert page shows "Aaron Bird" and at least one other field (e.g. bio_tagline or cohort).  
  - Assert an image is visible (either profile image or placeholder).  
  - Navigate to a fellow without an image; assert placeholder is shown (e.g. alt text or a placeholder element).

**Outputs to test**:
1. Open `http://localhost:8765/#/fellow/aaron_bird`. See Aaron Bird’s name, tagline, cohort, type, and profile image (or placeholder).  
2. Change slug to a fellow who has no image in `fellow_profile_images_by_name`; see placeholder.  
3. Click another name in the list; URL and detail update to that fellow (instant, no full reload).

**Deliverables**: Detail view logic in `app.js`, image + placeholder handling. Playwright tests for detail content and placeholder.

---

### Milestone 5: Search (optional) and launcher

**Goal**: (Optional) Search box that filters the directory list in memory by name/tagline/cohort/type. Launcher script that starts server and opens system browser.

**TDD**:  
- If search is implemented: Playwright — type in search box, assert list filters (e.g. "Aaron" shows only matching names).  
- Launcher: no e2e required; manual check that `./run.sh` starts server and opens browser to `http://localhost:8765`.

**Outputs to test**:
1. Run `./run.sh` (or `run.bat` on Windows): server starts and default browser opens to the app.  
2. (If search added) Type in search box; list filters in real time; clearing search restores full list.

**Deliverables**: `run.sh` (and optionally `run.bat`), optional search UI and in-memory filter. Optional Playwright test for search.

---

### Milestone 6: Polish and packaging

**Goal**: Match design reference (e.g. `aaron_bird_directory_view.png`), ensure all 442 fellows and 268 images work, document how to produce the zip.

**TDD**:  
- Playwright: smoke test — load app, check 442 names, open a few fellows with and without images, (optional) run a search.  
- Manual: produce zip (app + run.sh + optionally Python runtime), run from another folder to confirm portability.

**Outputs to test**:
1. Full run-through: launcher → directory → click several fellows → confirm images and placeholders.  
2. Zip created and documented (e.g. in README); unzip elsewhere and run launcher to confirm it runs.

**Deliverables**: README with build + run + zip instructions, any final CSS/layout tweaks, Playwright smoke test.

---

### Test setup (Playwright)

- **Location**: `tests/e2e/` (or `tests/` at repo root).  
- **Run**: e.g. `npx playwright test` (Node) or `pytest tests/` with playwright (Python).  
- **Server**: Tests assume server is running on port 8765, or use a fixture/script to start the server before tests and stop after.  
- **First run**: Start with Milestone 2 or 3: add Playwright, one test that hits the API or loads the page and asserts on the list; then implement until it passes.

---

You can start with **Milestone 1** (build script + SQLite + FTS5). When that’s done, we can run the listed checks together and then move to Milestone 2 (server and API) with Playwright in place.
