# Architecture

## Tech Stack

- **Server**: Python stdlib `http.server` — single file, no framework
- **Database**: SQLite3 with FTS5 full-text search
- **Frontend**: Vanilla JS SPA with hash routing, no build step
- **Data source**: JSON dump from EHF wiki, imported via build script

## Data Flow

```
JSON source data                Build script                  SQLite DB
ehf_fellow_profiles_deduped.json  →  import_json_to_sqlite.py  →  fellows.db
                                                                     ↓
Browser (vanilla JS SPA)  ←  HTTP API (server.py)  ←  SQL queries
```

### Demo Data Filtering

`build/filter_demo_data.py` filters the full JSON source down to fellows suitable for demo:

1. **Name required** — records without a name are dropped
2. **Image required** — records without a matching local image file are dropped
3. **Placeholder detection** — images are checked against known placeholder hashes (MD5). The EHF wiki used a grey diamond logo as a default avatar; fellows with this placeholder are excluded so the demo only shows real profile photos.

The filtered output is written to `ehf_fellow_profiles_demo_data.json`, which can be passed to the import script.

### Build Phase

`build/import_json_to_sqlite.py` reads the JSON, deduplicates slugs, and writes two tables:

- **`fellows`** — 17 explicit TEXT columns + `extra_json` TEXT for overflow fields
- **`fellows_fts`** — FTS5 virtual table (external content) indexing name, bio_tagline, cohort, fellow_type, search_tags, key_links

The explicit columns cover the fields needed for display and filtering. Any JSON keys not in that list are serialized into `extra_json`, which `row_to_fellow()` in the server merges back into the API response. This means the API returns all original fields without needing schema changes for every new field.

### Runtime

The server opens a new SQLite connection per request (no connection pool — unnecessary at local scale). Responses are JSON for API routes and raw bytes for static files and images.

**HTTP API** (see README for the full list): besides fellows list/detail/search, `GET /api/stats` returns aggregate statistics for the About page: total fellow count, breakdowns by fellow type and cohort, per-region counts (splitting comma-separated `global_regions_currently_based_in`), and field completeness (non-empty column counts plus selected keys in `extra_json` via `json_extract`). Heavier than a simple row fetch; still fine at local scale.

## Two-Phase Load

The frontend uses two sequential fetches to minimize time-to-interactive:

1. `GET /api/fellows` — returns only `record_id`, `slug`, `name`. The directory renders immediately from this.
2. `GET /api/fellows?full=1` — returns all fields for all fellows. Fetched in the background after the directory is visible. Results are cached in a `Map` keyed by slug.

When a user clicks a fellow before phase 2 completes, the app falls back to `GET /api/fellows/<slug>` for that single record.

## Frontend Routing

Hash-based SPA routing with no history API and no router library:

- `#/` — directory (default when the hash is empty or not matched below)
- `#/about` — About page; loads fellowship statistics via `GET /api/stats`
- `#/fellow/<slug>` — fellow detail; `hashchange` runs `updateDetailFromHash()`, which resolves the fellow from the in-memory cache or `GET /api/fellows/<slug>`

## Database Schema

Produced by `build/import_json_to_sqlite.py` (matches `sqlite3 app/fellows.db ".schema"` for the app-defined objects). Slug uniqueness is enforced with an index rather than an inline `UNIQUE` column constraint.

```sql
CREATE TABLE fellows (
    record_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT,
    bio_tagline TEXT,
    fellow_type TEXT,
    cohort TEXT,
    contact_email TEXT,
    key_links TEXT,
    key_links_urls TEXT,       -- JSON array of URLs (stored as TEXT)
    image_url TEXT,
    currently_based_in TEXT,
    search_tags TEXT,
    fellow_status TEXT,
    gender_pronouns TEXT,
    ethnicity TEXT,
    primary_citizenship TEXT,
    global_regions_currently_based_in TEXT,
    extra_json TEXT            -- JSON object of all other fields
);

CREATE UNIQUE INDEX idx_fellows_slug ON fellows(slug);

CREATE VIRTUAL TABLE fellows_fts USING fts5(
    name,
    bio_tagline,
    cohort,
    fellow_type,
    search_tags,
    key_links,
    content='fellows',
    content_rowid='rowid'
);
```

FTS5 also creates internal shadow tables (`fellows_fts_data`, `fellows_fts_idx`, etc.); those are SQLite-managed and not altered by hand.

## Roadmap

See ROADMAP.md
