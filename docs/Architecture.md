# Architecture

## Design constraint: local-only, not SaaS

**This app is single-user and local-only by design. It must never become a SaaS.** The PWA + magic-link distribution exists so a fellow can pull down the bundle and contact DB once, then run the app indefinitely against that local copy. Production is a delivery channel, not a service.

Operationally that means server contact is restricted to two responsibilities:

1. **Authorize a download** (magic-link gate, allowlist check, session cookie) so the bundle and `fellows.db` only reach EHF fellows.
2. **Serve fresh bytes on update** (new bundle when the SHA changes; re-imported `fellows.db` only when its content SHA changes, gated by `fellows_db_sha` in `/build-meta.json`).

Everything else runs on the device:

- **No per-user resources on the server.** `deploy/server.py` does not implement `/api/groups` or `/api/settings` — the dev server's routes for those exist only for the local round-trip. The canonical store for user-authored data is OPFS (`relationships.db`).
- **Stale-session must not lock users out of cached data.** A 401 on `/api/fellows` falls back to the IndexedDB cache; the directory, search, and profile views keep working. See `email_gate.md` invariant 10.
- **No server-side persistence of anything user-authored.** No backups of `relationships.db`, no server-stored notes, no shared groups, no cross-device sync. The unauthenticated client-error sink (`/api/client-errors`) is the only structured journald write driven by client behavior, and it is sanitized to remove identifiers.

What this rules out as features, even when individually attractive: cross-device sync, "share this group with another fellow", an admin console, server-side activity history, analytics beyond the install-funnel events already documented in `email_gate.md`. Adding any per-user RW endpoint on prod is the bright line that turns this from a delivery channel into a SaaS — don't cross it without a deliberate change to this section.

The architectural decisions below — separate `relationships.db` file, `ATTACH DATABASE ?mode=ro`, OPFS in both standalone and browser-tab modes, the unsupported-browser panel for missing OPFS — all flow from this constraint.

## Tech Stack

- **Server**: Python stdlib `http.server` — single file, no framework
- **Cross-origin isolation**: Both servers send `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. **Required** — the OPFS-SAH-Pool VFS that backs `relationships.db` and `fellows.db` in the browser gates `SharedArrayBuffer` / `Atomics` on `crossOriginIsolated=true`. A reverse proxy that strips these headers makes the worker silently fall back to the `api+idb` provider; the symptom is "Settings has no backup/restore section," diagnosable via `?diag=1` showing `dataProvider.kind: api+idb` instead of `worker`.
- **Strict CSP + adjacent hardening**: Both servers send `Content-Security-Policy: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none';` plus `Permissions-Policy` (geolocation/camera/mic/payment/sensors/USB/etc. all `=()`), `Cross-Origin-Resource-Policy: same-origin`, `Referrer-Policy: strict-origin-when-cross-origin`, and `X-Content-Type-Options: nosniff`. The CSP is the load-bearing one — without it a single XSS exfiltrates the entire OPFS to an attacker-controlled origin. `'wasm-unsafe-eval'` is the modern carve-out for the `sqlite3.wasm` runtime. The dev and prod headers must stay byte-identical so a CSP-incompatible pattern can't slip past local development. The HSTS header is added by Caddy at the edge (`ansible/roles/caddy/templates/Caddyfile.j2`) rather than by the Python server.
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

**HTTP API.** The dev server (`app/server.py`) exposes the table below. The production server (`deploy/server.py`) adds magic-link auth (`/api/send-unlock`, `/api/verify-token`, `/api/logout`), the unauthenticated client-error sink (`/api/client-errors`), build/diagnostics endpoints (`/healthz`, `/build-meta.json`, `/api/debug/diagnostics`), and gates directory `/api/*` paths behind a valid session cookie. The allowlist is built in memory at startup by HMAC-ing every distinct `contact_email` from `fellows.db` (`FELLOWS_ALLOWLIST_HMAC_KEY` env var); no `allowed_emails.json` artifact ships in `dist/`. The behavioral spec for the auth flow + client-error sanitization is [`email_gate.md`](email_gate.md).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/fellows` | Minimal list (record_id / slug / name / has_contact_email) for instant directory render. |
| GET | `/api/fellows?full=1` | Full fellow rows (phase 2 of the two-phase load). |
| GET | `/api/fellows/<slug>` | One fellow by `slug` or `record_id`. |
| GET | `/api/search?q=…` | FTS5 search across name / bio / cohort / fellow_type / search_tags / key_links. |
| GET | `/api/stats` | Aggregates for the About page: total, breakdowns by fellow_type / cohort / region, field completeness. |
| GET | `/api/auth/status` | Stub in dev (auth disabled). Real shape comes from `deploy/server.py`. |
| POST | `/api/client-errors` | Unauthenticated client-error sink. Always 204. Sanitized + rate-limited; logs `event=client_error` to journald. Schema + privacy boundary: [`email_gate.md` § Client error reporting](email_gate.md#client-error-reporting). Dev stub mirrors prod for round-trip. |
| GET | `/fellows.db` | Raw SQLite snapshot for the PWA's OPFS bootstrap. |
| GET | `/images/<slug>.{jpg,png}` | Profile image; alphanumeric-fallback filename match. |
| GET | `/` and other static paths | App shell from `app/static/`. |

`/api/stats` is heavier than a simple row fetch (region split + field-completeness pass over `extra_json` via `json_extract`); still fine at local scale. Per-user state (groups, settings, tags, notes) does not appear above — `/api/groups` and `/api/settings` were retired in Phase 1 of the local-first worker plan; see [Persistence and upgrades](#persistence-and-upgrades) and [Worker-owned OPFS](#worker-owned-opfs).

### Persistence and upgrades

User-authored data (groups, tags, notes, settings) lives in
`app/relationships.db`, a separate SQLite file from `fellows.db`.
Cross-DB joins happen inside the dedicated worker, attached once per
worker `init` via `ATTACH DATABASE 'fellows.db' AS f ?mode=ro` — *not*
per request. The `?mode=ro` suffix enforces read-only access at the
SQLite level; any stray write into `f.*` raises `OperationalError`.
(Pre-Phase-1 the dev server did per-request ATTACHes for `/api/groups`
and friends; those routes are retired and the worker now does it once
per session.) `relationships.db`
is durable across both app updates and Clear App Cache; `fellows.db`
is re-imported **on user request** when its server-reported content SHA
differs from the SHA recorded in OPFS-side `fellows.db.meta.json` —
the boot path is install-only and never auto-refreshes a returning
visitor. The user-driven swap path lives on the About page (*Update
directory data*) and is gated by a pre-swap impact preview that lists
any group members who would no longer have a profile after the
update. See `plans/opt_in_directory_data_updates.md` for the policy
and `plans/local_first_worker_architecture.md` for the underlying
SHA-keyed-refresh mechanism (now wrapped behind the opt-in UI).

In the browser this lives in OPFS (`sqlite3.wasm` + `relationships.db`
+ `fellows.db` + `fellows.db.meta.json`) in **both** standalone PWA mode
and browser-tab mode. Neither the production server nor the dev server
exposes per-user state HTTP routes — `/api/groups` and `/api/settings`
were retired in Phase 1 and OPFS is the only canonical store. When a
visitor's browser can't run OPFS (older Safari, missing
`FileSystemSyncAccessHandle`, insecure context), the worker reports
`opfsCapable: false` during init and the page surfaces an
unsupported-browser panel via `renderLocalDataUnavailablePanel()` — see
[`docs/browser_support.md`](browser_support.md).

The full state-survival matrix (which storage layers survive which
events, plus the standard upgrade flow) lives in
[`docs/persistence_and_upgrades.md`](persistence_and_upgrades.md).
Read that when adding a feature that touches storage, or when
triaging a "why did my X disappear?" report.

### Worker-owned OPFS

A single dedicated worker
(`app/static/vendor/sqlite-worker.js`) owns every OPFS handle and
every `sqlite3.wasm` instance. The main thread is an RPC client: it
posts `{id, op, args}` messages and awaits `{id, ok, result|error}`
responses. The same worker handles both `relationships.db`
(read-write user-authored data) and `fellows.db` (read-only contact
data, re-imported only when its server-reported content SHA in
`/build-meta.json:fellows_db_sha` differs from the SHA recorded in
worker-owned `fellows.db.meta.json`). No other context — not the main
thread, not the service worker, not a future render worker — is
permitted to call `navigator.storage.getDirectory` or open a
`FileSystemSyncAccessHandle`.

This single-owner rule lets us reason about the database without
worrying about cross-context coordination, and makes the SAH-pool's
per-file serialization a non-issue: there is exactly one opener.

**Why a worker rather than the main thread.** Real-browser evidence
(Safari, intermittent Firefox, vanilla Chrome 147 — see PRs #95–#99)
shows the main-thread OPFS path is the brittle layer. Several
browser configurations strip
`FileSystemFileHandle.prototype.createSyncAccessHandle` from the
main-thread prototype while still exposing it inside dedicated
workers. The worker context is also easier to keep network-free and
gate-aware: the worker's `init` op does sqlite3 init, OPFS attach,
and the auto-backup pass with no HTTP traffic, while a separate
page-driven `ensureFellowsDb` op covers the bundle fetch only after
the gate decision tree resolves to directory mode.

**Compatibility gates between page and worker.** Two narrow,
worker-internal constants govern whether a mismatched page may
mutate state:

- `WORKER_RPC_VERSION` — bumped only when the request/response
  shape of any RPC changes.
- `RELATIONSHIPS_SCHEMA_VERSION` — same value as
  `relationships.db`'s `PRAGMA user_version` (currently `1`); bumped
  only on schema migrations.

The page reads both during the worker `init` handshake and refuses
mutating RPCs (`createGroup`, `setSetting`,
`importRelationshipsBytes`, …) on mismatch. Reads still work so the
user can browse cached data while the service worker's existing
"New version available — Reload" banner does its job. The build
label is **not** consulted for this gate — see [the plan's "Why
build label is not the gate" section](../plans/local_first_worker_architecture.md#why-build-label-is-not-the-gate).

**Cross-DB joins still happen, but in the worker.** What the dev
server used to do via `ATTACH DATABASE 'fellows.db' AS f ?mode=ro`
on a per-request basis, the worker now does once per init. The
read-only enforcement at the SQLite layer is preserved.

**Capability detection runs in the worker.** When OPFS or
`FileSystemSyncAccessHandle` is unavailable (older Safari, missing
SAH, insecure context), the worker reports `opfsCapable: false`
during `init`; the main thread reads that field and surfaces the
unsupported-browser panel via `renderLocalDataUnavailablePanel()`.
See [`docs/browser_support.md`](browser_support.md).

### Non-goals (worker-owned OPFS)

Bright lines for the codebase, not just the plan:

- **The service worker never owns a SQLite DB.** SW lifecycle
  (idle eviction, multi-instance, restart on push) is hostile to
  storage ownership. SW is app-shell + update detection only.
- **No parallel main-thread OPFS access.** After the Phase 1
  cutover, opening OPFS from anywhere other than the dedicated
  worker is a bug.
- **No server-side per-user state.** Production never gains
  `/api/groups`, `/api/settings`, server-side `relationships.db`
  storage, server-side backup, cross-device sync, or admin views.
  The dev-server routes for groups/settings (`app/server.py`) are
  retired in Phase 1 — they were only ever a dev-round-trip
  scaffold and become dead code once the worker is sole owner.
- **No silent cross-device sync substrate.** Any future sync
  becomes an explicit, opt-in feature with its own design doc.
- **No multi-tab concurrent ownership.** OPFS sync access handles
  serialize per file; two tabs both opening `relationships.db`
  race on the SAH. Today's behavior — second tab fails to acquire
  — is preserved. A graceful "another instance is open" UI is a
  follow-up, not a goal.

## Workspace data providers (three tiers, mid-boot hot-swap)

The workspace's data layer is a tiered abstraction with three
implementations and an explicit fall-through path. The active
provider is the runtime contract every render path consults; it's
exposed at `window.__dataProvider` for tests and diagnostics.

The tiers, in preference order:

1. **`worker`** — happy path. RPC into the dedicated OPFS-owning
   worker (see [Worker-owned OPFS](#worker-owned-opfs)). Full reads +
   writes on both `relationships.db` and `fellows.db` (the latter
   read-only).
2. **`api+idb`** — auth-failure / OPFS-incapable fallback. Directory
   reads come from `/api/fellows` when the session is valid, or from
   the IndexedDB cache populated by a prior successful boot when it
   isn't (per [`email_gate.md` invariant 10](email_gate.md)). Writes
   to relationship-shaped methods (`createGroup`, `setSetting`, …)
   reject with `localDataUnavailableError` so render paths catch it
   and surface the unsupported-browser panel.
3. **`api`** — deepest fallback. Same as `api+idb` without the
   IndexedDB layer. Used in environments without IndexedDB (rare)
   and as the dev passthrough.

**Hot-swap on auth failure.** `bootDirectoryAsApp` starts with the
worker provider; if the worker's `ensureFellowsDb` returns 401 / 403
(stale session), the boot path swaps to `api+idb` mid-flight without
unwinding. The worker process stays alive (it still owns OPFS;
`clearEverything` reaches it through `warmWorker.rpc` for the wipe).
The build badge flips to `server: offline · using cache`. The user
keeps browsing the cached directory until they explicitly re-authenticate
via `/?gate=1`.

This is what makes "stale session must not lock users out of cached
data" testable: a 401 on `/api/fellows` doesn't propagate as a boot
failure; it transparently routes through the IDB cache.

## Boot orchestration (named marks + watchdog + slow-boot persistence)

The workspace runs a watchdog (default 20s) over a sequence of named
boot phase marks: `script_start`, `pick_provider_start`,
`worker_init_done`, `provider_ready`, `get_list_done`, `get_full_done`,
`image_prewarm_done`, `summary`. If `get_list_done` doesn't arrive in
time, a recovery panel (`#boot-stuck-panel`) renders naming the last
completed mark — diagnostic enough that a stuck-boot report identifies
which phase stalled before any backtrace. Same recovery affordances as
the boot-error panel: Reload, Clear App Cache & Reload, send a bug
report.

Slow boots persist to localStorage:

- **Trigger:** total >3000 ms or any single phase >2000 ms.
- **Storage key:** `fellows_last_slow_boot`. Single record, overwritten
  on each new slow boot. Survives Clear App Cache by being preserved
  alongside `fellows_authenticated_once`.
- **Surface:** the `?diag=1` panel shows it under "Last slow boot
  recorded" on the next session. A regression captured one session
  is readable in the next without depending on the user keeping the
  slow tab open.

`bootMarks` is exposed at `window.__bootMarks` for e2e tests; the
chronological trace is at `window.__bootDebugLines`. Both are
read-only by convention.

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
