# CLAUDE.md

Read README.md for project setup, API docs, and test commands. Read docs/Architecture.md for system design and database schema.

## Constraints

- **No frameworks.** Python stdlib only (http.server, sqlite3, json, pathlib). No Flask, Django, Express, etc.
- **No frontend build tools.** Vanilla JS, no npm, no bundlers, no transpilers.
- **No new pip dependencies** for the app. Dev deps go in requirements-dev.txt.
- **No authentication.** Local-only tool.
- **Port 8765.** Do not change.

## Conventions

- Keep the server as a single file (`app/server.py`).
- Frontend is a single IIFE in `app/static/app.js`. No modules, no classes.
- `escapeHtml()` for all user data rendered into HTML.
- Parameterized `?` placeholders for all SQL queries.
- Validate image paths against traversal (`..` checks).
- Do not leave a long-lived server running in the terminal.
- The DB file `app/fellows.db` is gitignored; rebuild from JSON source.
- Always run relevant tests after changes.
