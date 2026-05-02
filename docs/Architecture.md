# Architecture

## Tech Stack

- **Server**: Python stdlib `http.server` — single file, no framework
- **Database**: SQLite3 with FTS5 full-text search
- **Frontend**: Vanilla JS SPA with hash routing, no build step
- **Data source**: JSON dump from EHF wiki, imported via build script
- **Tests**: pytest for database and HTTP API tests; Playwright for browser e2e. Venv, dev dependencies, Playwright browsers, building `app/fellows.db`, and commands (including freeing port 8765) are documented in the root **README.md**.

## Data Flow

```
JSON source data                   Build script                          SQLite DB
knack_api_detail_dump.json  →  restore_from_knack_scrapefile.py  →  fellows.db
                                                                         ↓
Browser (vanilla JS SPA)  ←  HTTP API (server.py)  ←  SQL queries
```

### Build Phase

`build/restore_from_knack_scrapefile.py` reads the Knack API detail dump (with a fallback read of the list-view `raw_dump` for a few fields), deduplicates slugs, detects grey-diamond placeholder avatars by MD5, and writes two tables:

- **`fellows`** — 17 explicit TEXT columns + `extra_json` TEXT for overflow fields
- **`fellows_fts`** — FTS5 virtual table (external content) indexing name, bio_tagline, cohort, fellow_type, search_tags, key_links

The explicit columns cover the fields needed for display and filtering. Any JSON keys not in that list are serialized into `extra_json`, which `row_to_fellow()` in the server merges back into the API response. This means the API returns all original fields without needing schema changes for every new field.

### Runtime

The server opens a new SQLite connection per request (no connection pool — unnecessary at local scale). Responses are JSON for API routes and raw bytes for static files and images.

**HTTP API.** The dev server (`app/server.py`) exposes the table below. The production server (`deploy/server.py`) adds magic-link auth (`/api/send-unlock`, `/api/verify-token`, `/api/logout`), the unauthenticated client-error sink (`/api/client-errors`), build/diagnostics endpoints (`/healthz`, `/build-meta.json`, `/api/debug/diagnostics`, `/allowed_emails.json`), and gates directory `/api/*` paths behind a valid session cookie. The behavioral spec for the auth flow + client-error sanitization is [`email_gate.md`](email_gate.md).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/fellows` | Minimal list (record_id / slug / name / has_contact_email) for instant directory render. |
| GET | `/api/fellows?full=1` | Full fellow rows (phase 2 of the two-phase load). |
| GET | `/api/fellows/<slug>` | One fellow by `slug` or `record_id`. |
| GET | `/api/search?q=…` | FTS5 search across name / bio / cohort / fellow_type / search_tags / key_links. |
| GET | `/api/stats` | Aggregates for the About page: total, breakdowns by fellow_type / cohort / region, field completeness. |
| GET | `/api/groups` | List of saved groups with member counts (newest-touched first). |
| POST | `/api/groups` | Create a group (`{name, note?, fellow_record_ids?}`). Returns 201 with the new group. |
| GET | `/api/groups/<id>` | One group with members joined to fellows. 404 if missing. |
| PATCH | `/api/groups/<id>` | Partial update — any subset of `name`, `note`, `fellow_record_ids` (replaces members in full when given). |
| DELETE | `/api/groups/<id>` | Delete a group; FK cascade removes its `group_members`. Returns 204. |
| GET | `/api/settings` | Full settings key/value bag. |
| GET | `/api/settings/<key>` | One setting; 404 if unset. |
| PUT | `/api/settings/<key>` | Upsert (`{value: "…"}`). Empty value clears the key. |
| GET | `/api/auth/status` | Stub in dev (auth disabled). Real shape comes from `deploy/server.py`. |
| POST | `/api/client-errors` | Unauthenticated client-error sink. Always 204. Sanitized + rate-limited; logs `event=client_error` to journald. Schema + privacy boundary: [`email_gate.md` § Client error reporting](email_gate.md#client-error-reporting). Dev stub mirrors prod for round-trip. |
| GET | `/fellows.db` | Raw SQLite snapshot for the PWA's OPFS bootstrap. |
| GET | `/images/<slug>.{jpg,png}` | Profile image; alphanumeric-fallback filename match. |
| GET | `/` and other static paths | App shell from `app/static/`. |

`/api/stats` is heavier than a simple row fetch (region split + field-completeness pass over `extra_json` via `json_extract`); still fine at local scale. `/api/groups` and `/api/settings` open `relationships.db` per request and ATTACH `fellows.db` read-only — see [Persistence and upgrades](#persistence-and-upgrades).

### Persistence and upgrades

User-authored data (groups, tags, notes, settings) lives in
`app/relationships.db`, a separate SQLite file from `fellows.db`.
Cross-DB joins use SQLite `ATTACH DATABASE ... ?mode=ro`, which keeps
contact data read-only at the SQLite level. `relationships.db` is
durable across both app updates and Clear App Cache; `fellows.db` is
re-imported on every boot.

In the browser this lives in OPFS (`sqlite3.wasm` + `relationships.db`)
in **both** standalone PWA mode and browser-tab mode. Production's
`deploy/server.py` does not serve `/api/groups` or `/api/settings`;
OPFS is the canonical store there. The dev server's HTTP routes for
groups and settings exist only to support the dev round-trip — they
are not part of the production API surface. When a visitor's browser
can't run OPFS (older Safari, missing `FileSystemSyncAccessHandle`,
insecure context), the API provider tags those endpoints unreachable
and the UI surfaces an unsupported-browser panel via
`renderLocalDataUnavailablePanel()` — see
[`docs/browser_support.md`](browser_support.md).

The full state-survival matrix (which storage layers survive which
events, plus the standard upgrade flow) lives in
[`docs/persistence_and_upgrades.md`](persistence_and_upgrades.md).
Read that when adding a feature that touches storage, or when
triaging a "why did my X disappear?" report.

## Two-Phase Load

The frontend uses two sequential fetches to minimize time-to-interactive:

1. `GET /api/fellows` — returns only `record_id`, `slug`, `name`. The directory renders immediately from this.
2. `GET /api/fellows?full=1` — returns all fields for all fellows. Fetched in the background after the directory is visible. Results are cached in a `Map` keyed by slug.

When a user clicks a fellow before phase 2 completes, the app falls back to `GET /api/fellows/<slug>` for that single record.

## Frontend Routing

Hash-based SPA routing with no history API and no router library. Defined in `route()` in `app/static/app.js`.

| Route | Purpose |
|---|---|
| `#/` (default; empty or unmatched hash) | Directory. Two-phase load: minimal list, then full rows in the background. |
| `#/about` | About page. Loads fellowship statistics via `GET /api/stats`; links out to the user guide. |
| `#/fellow/<slug>` | Fellow detail. Resolves from the in-memory cache or `GET /api/fellows/<slug>`. |
| `#/groups` | Groups index — saved groups with member counts. |
| `#/groups/<id>` | Group detail. Action bar (Contact / Export / Edit), member list, inline note editor. |
| `#/groups/<id>/directory` | Visual portrait directory for the group; click a portrait → `#/fellow/<slug>`. |
| `#/edit/<id>` | Edit-mode entry. Re-uses the right-rail composer against an existing group; auto-saves on toggle, "Cancel edits" reverts to the entry snapshot. |
| `#/settings` | Settings page. The user's "me" email used for export `mailto:?to=…`; auto-captured from the magic-link gate, persisted to `relationships.settings` and mirrored to localStorage on boot. |

User-facing screen behavior, navigation, and UX flows live in [`users_manual.md`](users_manual.md). Treat the user guide as the source of truth for UI/UX from a user's perspective and keep it in sync when the UI changes.

## Manifest gotchas

`app/static/manifest.webmanifest` is intentionally minimal: `id`, `start_url`, and `scope` all `=/`; three icons (`any`, `any`, `maskable`); no `related_applications`, no `share_target`. Two reasons not to add either casually:

- **`related_applications`** — if a stale or wrong app ID lands here, Android's WebAPK pipeline tries to verify it against the Play Store and fails with the cryptic "Older Version of Android" install error. Don't add unless we actually ship a Play Store companion.
- **`share_target` with `method: "POST"`** — some Samsung/Chromium WebAPK servers reject POST share targets and the install silently fails. If a future feature needs a share target, use `method: "GET"`.

Longer treatment of these and other PWA-installability traps is in [`pwa_tips.md`](pwa_tips.md).

## Database Schema

Produced by `build/restore_from_knack_scrapefile.py` (matches `sqlite3 app/fellows.db ".schema"` for the app-defined objects). Slug uniqueness is enforced with an index rather than an inline `UNIQUE` column constraint.

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

### `relationships.db`

User-authored data. Created on first access by `app.relationships.open_db()`; the same schema is mirrored in the PWA via `RELATIONSHIPS_SCHEMA_SQL` in `app/static/app.js` so the OPFS-backed sqlite3.wasm path matches the dev server. ATTACHed read-only as `f` against `fellows.db` for cross-DB joins (e.g. resolving member names on `GET /api/groups/<id>`); any stray write to `f.*` raises `OperationalError`.

```sql
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    fellow_record_id TEXT NOT NULL,
    PRIMARY KEY (group_id, fellow_record_id)
);

CREATE INDEX idx_group_members_group ON group_members(group_id);

-- Reserved for tag/note CRUD UI (designed once, surfaced incrementally).
CREATE TABLE fellow_tags (
    fellow_record_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (fellow_record_id, tag)
);

CREATE INDEX idx_fellow_tags_tag ON fellow_tags(tag);

CREATE TABLE fellow_notes (
    fellow_record_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Single key/value bag (e.g. `self_email` override for export `mailto:?to=…`).
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

`PRAGMA user_version` is set to `SCHEMA_VERSION` (currently `1`) at bootstrap so future migrations can branch on it. The file is gitignored, per-user, and durable across both app updates and Clear App Cache — see [`persistence_and_upgrades.md`](persistence_and_upgrades.md) for the full state-survival matrix.

## Roadmap

See ROADMAP.md
