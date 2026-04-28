# CLAUDE.md

Read README.md for project setup, API docs, and test commands. Read docs/Architecture.md for system design and database schema.

## Constraints

- **No frameworks.** Python stdlib only (http.server, sqlite3, json, pathlib). No Flask, Django, Express, etc.
- **No frontend build tools.** Vanilla JS, no npm, no bundlers, no transpilers.
- **No new pip dependencies** for the app. Dev deps go in requirements-dev.txt.
- **No authentication.** Local-only tool.
- **Port 8765.** Do not change.

## Conventions

- Keep the server as a single file (`app/server.py`). Pure-logic helpers (e.g. `app/relationships.py`) may live alongside.
- Frontend is a single IIFE in `app/static/app.js`. No modules, no classes.
- `escapeHtml()` for all user data rendered into HTML.
- Parameterized `?` placeholders for all SQL queries.
- Validate image paths against traversal (`..` checks).
- Do not leave a long-lived server running in the terminal.
- The DB file `app/fellows.db` is gitignored; rebuild from JSON source.
- Always run relevant tests after changes.
- For deploy- or infra-related work, put **manual QA steps for the maintainer** (smoke scripts, DNS/TLS checks, browser install flow) in the **PR description**, not only in commits or docs.

## Two-DB architecture

User-authored data (groups, per-fellow tags, per-fellow notes, settings) lives in `app/relationships.db`, a separate SQLite file from the imported contact data in `app/fellows.db`. Cross-DB joins use SQLite `ATTACH DATABASE` with `?mode=ro` on the fellows side — read-only-ness of contact tables is enforced at the SQLite level, not just the app layer. See `app/relationships.py` (Python) and the `RELATIONSHIPS_SCHEMA_SQL` mirror in `app/static/app.js` (PWA / OPFS). `relationships.db` is gitignored, per-user, and persists across app updates; `fellows.db` is regenerated from source on every build.
