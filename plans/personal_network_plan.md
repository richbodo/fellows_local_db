# personal_network — Release Plan

> **Status: DRAFT.** Assumptions applied are the author's leanings from the planning conversation of 2026-04-17, not yet confirmed. Revise freely on next pass.

## 1. What we're building

`personal_network` is a **single-user, local-first PWA** for managing one person's personal contact network. It is derived from the `fellows_local_db` codebase (the EHF Fellows directory) by stripping the group/auth features and generalizing the schema.

It is the first component of a broader initiative, previously discussed as **PRT** (Personal Relationship Tool), which will eventually comprise:

1. **`personal_network` (this project)** — local, read-only contact directory with FTS search and a visual directory UI. v1 scope.
2. **Relationship data layer** — tags and notes per contact, stored privately alongside contacts as a first-class searchable layer. Future release, groundwork only in v1.
3. **`community_protocol` integration** — a separate app (previously called CRT) that lets any community member send a notification requesting to **TALK about TOPIC at TIME**, with responses of **ACCEPT** or **SUGGEST** (alternate time). Future release, integration seams only in v1.

### Single-user model

- No multi-user concept, no auth, no Postmark, no session cookies, no allowed-emails, no magic links.
- You host it for yourself. Default deploy posture is `127.0.0.1:8765`; PWA installs from there and runs offline afterwards.
- "Remote hosting it yourself" (behind VPN, basic auth, etc.) is out of scope for v1 and will be a separate follow-up track.

### Contacts are read-only and rebuild-on-import

- v1 accepts a **normalized JSON fixture** that maps to the reduced schema.
- Re-importing rebuilds `contacts.db` and the FTS5 index.
- Future importers (Google Contacts, Apple Contacts, LinkedIn, Facebook exports) plug in as **adapters** that normalize their source format into the intermediate JSON. The adapter contract will be documented in v1; no adapters ship in v1.

### No branding

- "The personal network app for your personal network." Header shows `{Owner}'s network` (or `My network` if unset). No logo swap, no theme color env var.

### Carved out of v1 (but architectural seams reserved)

- **Relationship data layer** (tags, notes): DDL and API surface documented; not implemented.
- **`community_protocol`**: a documented hook point where the future app will integrate.
- **Contact CRUD in-app**: contacts are rebuilt from import only. No in-app edit/delete.
- **Remote hosting / multi-device sync**: not in v1.

## 2. Relationship to the fellows codebase

- **New repo `personal_network`, seeded from a copy of `fellows_local_db`.** Not a fork, not a rename — a parallel thread.
- The fellows app stays exactly as it is today and continues its own release schedule.
- Merging fellows over to the generic codebase is a **future, deliberate migration** that will happen after `community_protocol` is built and tested with decentralized developers. Not on this plan.

## 3. Locked-in decisions (from conversation)

- Single-user, no auth, no branding.
- Read-only contacts; CRUD (if ever) is a later concern.
- Reduced fixed schema + `extra_json` overflow; future expansion documented.
- Stats/About page kept, genericized, populated by fixture.
- Fixture for v1 is ~100 synthetic contacts.
- GPL-3.0, © Rich Bodo.
- New repo, parallel to fellows; no fellows migration in v1.

## 4. Draft decisions (author's leans, apply unless revised)

### 4.1 Contact stable ID

- Each contact gets an **app-generated UUID** at first sight.
- A `contact_aliases` table maps `(source, external_id) → contact_uuid` so re-imports from Google/Apple/etc. do not fork identities.
- Matching on re-import without a source ID falls back to normalized email, then to normalized `(given_name, family_name, primary_phone)` tuple.
- Rationale: the future relationship data layer (tags, notes) must anchor to an ID stable across re-imports.

### 4.2 Reduced schema (v1 fixed columns)

```
contact_id       TEXT PRIMARY KEY    -- UUID, app-generated
slug             TEXT NOT NULL       -- URL-safe, derived from display_name + disambiguator
display_name     TEXT
given_name       TEXT
family_name      TEXT
primary_email    TEXT
primary_phone    TEXT
location         TEXT                -- free-text, "City, Country" or similar
notes_public     TEXT                -- short bio / tagline (imported, not the private notes layer)
image_path       TEXT                -- relative path into fixtures/images, or null
source           TEXT                -- "fixture", "google", "apple", "linkedin", "facebook", "manual"
extra_json       TEXT                -- JSON object, all other imported fields
```

Plus:

```
CREATE UNIQUE INDEX idx_contacts_slug ON contacts(slug);

CREATE TABLE contact_aliases (
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    contact_id   TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);

CREATE VIRTUAL TABLE contacts_fts USING fts5(
    display_name, given_name, family_name, location, notes_public,
    content='contacts', content_rowid='rowid'
);
```

Reserved but not created in v1 (documented in `docs/Architecture.md`):

```
-- Relationship data layer (future):
-- contact_tags(contact_id, tag, created_at)
-- contact_notes(contact_id, body, created_at, updated_at)
```

### 4.3 Deploy posture

- Local only, bind `127.0.0.1:8765` by default.
- Drop `deploy/`, `ansible/`, `scripts/deploy_pwa.sh`, `scripts/smoke_prod.sh`, `scripts/check_deploy_env.sh`, `scripts/configure_email_auth_env.sh` entirely for v1.
- PWA install flow: run server locally → open in browser → install PWA → service worker caches static + `contacts.db` + images for offline use.

### 4.4 First-run identity

- Setup script writes a small `config.json` (owner name, port, DB path). Server reads it at startup.
- Setup script supports `--owner "Rich Bodo"` (and flags for other values) for unattended mode.
- Header falls back to `My network` if no owner is configured.

### 4.5 Avatar strategy

- **Initials rendered client-side** from `display_name` (monochrome circle, first letter of given + family name).
- No avatar files ship in the fixture.
- `image_path` is wired up in the schema for real imports (which bring their own photos) but empty for the v1 fixture.

### 4.6 Testing strategy

- Port the current `tests/test_database.py` and `tests/test_api.py` to the contacts schema (mostly field renames).
- Rewrite the three Playwright e2e tests (`test_directory.py`, `test_detail_view.py`, `test_install_landing.py`) against the generic UI.
- Drop `tests/test_magic_link_auth.py`, `tests/test_deploy_sqlite_api.py` entirely.

## 5. Milestones

### M1 — Repo bootstrap & strip

- New repo `personal_network`, initial commit = copy of `fellows_local_db` at a named commit SHA (recorded in README).
- Remove: `deploy/`, `ansible/`, deploy-related scripts, magic-link auth, Postmark, session cookies, `allowed_emails.json`, `/api/auth/*`, `/api/debug/diagnostics`, `build-meta.json` machinery, `configure_email_auth_env.sh`, `smoke_prod.sh`, `check_deploy_env.sh`, diagnostics UI.
- Global rename: `fellows` → `contacts`, `fellow` → `contact`, `FELLOWS_` env → `PN_` (if any survive), `fellows.db` → `contacts.db`.
- `LICENSE` = GPL-3.0, © Rich Bodo, 2026.
- `CLAUDE.md` updated: single-user, no auth, GPL-3, no frameworks still applies.

**Acceptance:** repo builds an empty `contacts.db` from an empty fixture, server boots on `127.0.0.1:8765`, `/api/contacts` returns `[]`, static shell loads.

### M2 — Schema + importer v1

- Finalize reduced columns per §4.2, including `contact_aliases`.
- `build/import_contacts.py` reads normalized JSON → writes `contacts.db` + FTS + aliases.
- UUID assignment + alias-based re-import dedupe logic with unit tests.
- Adapter contract documented in `docs/Architecture.md` (what a source-specific adapter must produce). No adapters shipped.

**Acceptance:** import a 3-contact JSON, re-import same JSON — no duplicates, UUIDs stable. Import same JSON with an added external_id — still one row. FTS returns expected rows for name and location queries.

### M3 — Fixture (100 contacts)

- Hand-shaped 100-contact persona set in `fixtures/contacts_seed.json`:
  - Variety in fields (some missing emails, some missing locations, varied `notes_public` lengths).
  - Locations span at least ~15 distinct cities/regions so stats groupings are interesting.
  - Source tagged as `"fixture"` uniformly.
- No avatar files.
- Build step: `python build/import_contacts.py fixtures/contacts_seed.json` produces `app/contacts.db`.

**Acceptance:** after running the build, stats page shows non-trivial groupings and the directory has ~100 rows with intentional gaps visible in the UI.

### M4 — UI genericize

- Header: `{Owner}'s network` (or `My network`) — reads `config.json`.
- Replace all "fellow"/"Fellowship"/"EHF" copy.
- Profile card: show the reduced schema fields plus anything from `extra_json` the fixture happens to populate.
- Initials-based avatar component (pure JS; color hash by contact_id).
- Stats/About page: genericize aggregations to `by_location`, `by_source`, field completeness, total count.

**Acceptance:** no remaining occurrences of "fellow" (grep-clean) in UI strings or test fixtures (except the repo-provenance note in README). Stats page renders charts with fixture data. Visual directory works end-to-end against `contacts.db`.

### M5 — Setup script + docs

- `scripts/setup.py`: interactive prompts for owner name, port, DB path. Writes `config.json`. `--unattended` mode accepts flags.
- New `README.md`: single-user framing, install, run, import-your-own-contacts, PWA install steps.
- New `docs/Architecture.md`: single-user model, reduced schema, UUID/alias scheme, stats page, **reserved seams for relationship data layer and community_protocol integration**.
- `CONTRIBUTING.md`: note that email-provider/import-adapter PRs are explicitly welcome targets for later tracks.
- `CHANGELOG.md` started.

**Acceptance:** `python scripts/setup.py --owner "Rich Bodo" --unattended` succeeds in CI with no prompts. README walkthrough reproducible from a clean clone.

### M6 — v0.1.0 tag

- CI smoke (GitHub Actions): `scripts/setup.py --unattended` → `build/import_contacts.py fixtures/contacts_seed.json` → boot server on 8765 → curl `/api/contacts`, `/api/search?q=...`, `/api/stats` → assert non-empty / structure.
- Port unit tests pass.
- Port e2e tests pass (headless Playwright).
- Tag `v0.1.0`, GitHub release with release notes.

**Acceptance:** green CI on a fresh clone, tag exists, release page published.

## 6. Out of scope for v1 (tracked here so we don't forget)

- **Relationship data layer** — tags + notes + search across both. Biggest future feature; schema reserved, DDL documented.
- **`community_protocol` integration** — TALK/TOPIC/TIME notifications with ACCEPT/SUGGEST replies. Hook point documented.
- **Source-specific importers** (Google, Apple, LinkedIn, Facebook export parsers).
- **Remote hosting track** — reverse-proxied, TLS, personal-auth. Likely reuses stripped Caddy/Ansible bits from the fellows repo when revived.
- **Fellows migration** — converting the fellows deploy onto the generic codebase. Deferred until after `community_protocol` is proven with decentralized developers.
- **In-app contact CRUD / sync** — deliberately avoided in v1 to sidestep the incumbent SaaS sync-barrier problem.

## 7. Open questions to confirm before starting M1

These are the six the author leaned on — listed here so the next session can revisit them explicitly:

1. Contact stable ID scheme (§4.1) — UUID + aliases?
2. Reduced schema columns (§4.2) — anything to add or remove?
3. Deploy posture (§4.3) — drop all of `deploy/` + Ansible for v1?
4. First-run identity (§4.4) — `config.json` written by setup script?
5. Avatar strategy (§4.5) — initials only, no files?
6. Testing strategy (§4.6) — port unit tests, rewrite e2e, drop auth/deploy tests?

## 8. Suggested first session tomorrow

1. Confirm or revise §4 leans.
2. Create the `personal_network` repo locally, seeded from a copy of this one at the current commit SHA. Record the SHA in the new repo's README.
3. Start M1 strip work on the new repo. Keep `fellows_local_db` untouched.
