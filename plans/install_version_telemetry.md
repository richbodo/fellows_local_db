# Install-version telemetry

End goal: `just installed-versions` prints one row per fellow with
plaintext email, the build they installed on, the build their PWA is
currently running, and the last User-Agent we saw — so triage like
"Janine's photos won't load, what build is she on?" stops requiring a
screenshot from the user.

Tracking issue for the docs side: #147 (data retention docs — what the
server keeps and how a user wipes the app).

## Why this exists

Today journald carries only `auth_status`, `send_unlock_email`, and
`build_meta` — none of which capture a click, a User-Agent, or a
client's running build. Caddy access logs are off. So for any user
who installed before mid-2026-05, we can see *that* they were sent a
magic link and *roughly* what build was live then, but cannot
determine:

- Whether they actually clicked it (no `verify_token` event).
- What browser / iOS version they're on (no UA capture anywhere).
- What build their installed PWA is currently executing (no client
  boot beacon).

The instrumentation closes those three gaps with three small,
independent landings.

## Phase A — `event=verify_token` with UA capture

Smallest, deployable on its own, immediately useful for the next user
who clicks a magic link.

### Files

- `deploy/magic_link_auth.py` — add pure `verify_token_event()`
  helper alongside `consume_token` / `issue_token`. No I/O.
- `deploy/server.py` — in `_handle_verify_token`, after
  `consume_token` returns, `print(json.dumps(verify_token_event(...)),
  file=sys.stderr)`.
- `tests/test_magic_link_auth.py` — unit-test the helper.

### Event shape

```json
{"event": "verify_token",
 "result": "ok" | "expired" | "invalid",
 "token_prefix": "0ec744d4f319",
 "user_agent": "Mozilla/5.0 (iPhone; …)",
 "build_label": "2026-05-12-deadbeef"}
```

Notes:
- `email_hash_prefix` is intentionally NOT in this event — tokens
  aren't bound to emails in `AuthState`. The join key is
  `token_prefix`, which the matching `send_unlock_email` event
  already carries. Both events land in journald within minutes of
  each other, well inside any rotation window we care about.
- `user_agent` is length-capped at 240 chars (matches
  `client_error.ua`). No further sanitization at this layer.
- `build_label` is the server's currently-stamped build — that's
  the JS the client just ran. Falls back to `git_sha` if
  `build_label` is missing (older `build-meta.json` shapes).
- Event fires when `consume_token` runs, regardless of outcome.
  Skipped for early-return paths (`!AUTH_ACTIVE`, empty token),
  matching `send_unlock_email`'s "only log when the real work
  actually runs" pattern.

### Test plan

Unit tests in `tests/test_magic_link_auth.py`:
- happy-path event has all expected keys + values
- 240-char cap on UA
- None / empty inputs collapse to `""` rather than failing
- `result` clamps unknown statuses to `"invalid"`

No stderr-capture integration test — the in-process server fixture
makes that fragile, and the helper is pure.

### Out of scope for Phase A

- Backfilling old installs.
- Logging `email_hash_prefix` directly (the token-prefix join is
  cheaper than threading email through `AuthState.tokens`).

## Phase B — `kind=boot` client beacon

Tells us what build each installed PWA is *currently running* every
time the user opens the app.

### Files

- `deploy/client_error_sanitizer.py` — add `boot` to the
  `kind` allow-list.
- `app/static/app.js` — in `bootDirectoryAsApp`, after the
  `get_list_done` boot mark, fire a single `kind=boot` event via
  the existing `/api/client-errors` sink. Module-scope boolean
  prevents repeat fires within a page load.
- `docs/email_gate.md` — extend the `kind` table with `boot`
  semantics next to `kind=worker`.
- `tests/test_client_error_sanitizer.py` — unit-test the new
  kind.
- `tests/e2e/test_boot_beacon.py` (new) — assert exactly one
  POST per cold boot, with `build`, `displayMode`, and (when
  present in localStorage) `lastSubmitHashPrefix`.

### Event shape (within the existing `/api/client-errors` schema)

```jsonc
{
  "events": [{"kind": "boot", "msg": "cold_start",
              "extra": "displayMode=standalone opfsCapable=true provider=worker"}],
  "ua":    "...",
  "build": "2026-05-12-deadbeef",       // the JS that's actually running
  "route": "#/",
  "displayMode": "standalone",
  "online": true,
  "lastSubmitHashPrefix": "8151ea0a4fc9"  // the join key — same prefix verify_token logs
}
```

`lastSubmitHashPrefix` is the load-bearing field: without it, boot
events are anonymous; with it, every boot ties back to a specific
email_hash_prefix. The value is already stashed in localStorage at
gate-submit time, so existing installed users start populating once
they reload after Phase B ships.

### Cardinality / rate

One event per cold boot. Existing per-IP rate limit on
`/api/client-errors` (3 per window via `check_rate_limit`) is
already sufficient — a user can't generate more boot events than
they can open the app.

### Out of scope for Phase B

- Reporting on hot navigations (route changes within an open
  session). Boot-only.
- Reporting boot phase timings (we already have
  `fellows_last_slow_boot` in localStorage for that).
- Tying back to anonymous boots (no `lastSubmitHashPrefix` in
  localStorage). Acceptable — we report what we can.

## Phase C — `installed-versions` script + recipe

The user-visible deliverable.

### Files

- `scripts/installed_versions.py` (new) — journald reader + join.
- `ansible/roles/fellows_app/tasks/main.yml` — deploy alongside
  `prod_stats.py` to `/opt/fellows/bin/installed_versions`.
- `justfile` — `installed-versions:` recipe (`ssh ... /opt/fellows/bin/installed_versions`).
- `docs/justfile.md` — document the recipe.
- `docs/email_gate.md` — link the script from § Operator triage.

### Logic

1. `journalctl -u fellows-pwa --since <window> --no-pager` (default
   `30 days ago`; CLI flag for override).
2. For every `event=verify_token result=ok` line, capture
   `(token_prefix → (build_label, user_agent, ts))`.
3. For every `event=send_unlock_email result=sent` line, capture
   `(token_prefix → email_hash_prefix)`. Use this to translate the
   verify_token records' `token_prefix` into `email_hash_prefix`.
4. For every `event=client_error` line whose first event has
   `kind=boot` AND payload has `lastSubmitHashPrefix`, capture
   `(email_hash_prefix → (build, ua, ts, displayMode))`.
5. Join `email_hash_prefix → contact_email` via SQLite over
   `/opt/fellows/deploy/dist/fellows.db` — same join
   `prod_stats.py:_recipients()` already does.
6. Emit a single table sorted by most-recent activity:

   ```
   email                installed_build       seen_build           last_seen   ua
   ```

### Output flags

- Default: human-readable table, plaintext-confidential banner.
- `--csv`: machine-readable for downstream tooling.
- `--since '7 days ago'`: window override (matches `prod-stats`
  flag).

### Out of scope for Phase C

- Web UI / dashboard. Operator CLI only.
- Live tail. One-shot read against journald.
- Cross-referencing the install funnel (`kind=install` events).
  That's a `prod-stats` concern, not an install-version concern.

## Phase D — Caddy access logging *(deferred, optional)*

Not needed to ship the `installed-versions` recipe. Worth doing
later if we hit a triage case neither `verify_token` nor `boot`
events resolve — e.g. a user who can't get past the gate at all
and has nothing in the client-error sink either. When that happens:
turn on Caddy structured JSON access logs to journald,
`log_skip` for static assets to keep volume down.

## Sequencing

Land A → B → C, each as its own PR. A and B are independently
valuable; C is the operator-visible glue. Don't bundle.

## What this does NOT solve

- **Pre-instrumentation installs are forensically opaque.** Users
  who installed before Phase B ships only become attributable after
  their next cold boot.
- **Anonymous boots stay anonymous.** A user who Clear-App-Cache'd
  and then booted without re-authenticating has no
  `lastSubmitHashPrefix` in localStorage. Their boot event still
  reports the running build, but we can't tie it to an email.
- **No retroactive UA capture.** Janine's specific question
  ("what's she running right now") only gets a forensic answer if
  she boots once after Phase B is deployed. Until then, the
  cheaper path is a screenshot of the About → Build badge.
