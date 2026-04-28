# Persistence and Upgrades

The PWA stores user state across several layers, each with different
survival semantics. This doc captures what survives what — so future
features can land without surprising existing users, and so we have a
shared mental model when triaging "why did my X disappear?" reports.

## Storage layers

| Layer | Holds | Replaced on app update | Cleared by **Clear App Cache** button |
|---|---|---|---|
| Cache API `fellows-app-shell-vN` | HTML, JS, CSS, SW, manifest, icons, sqlite3.wasm | Yes — every CACHE_VERSION bump | Yes |
| Cache API `fellows-images-v1` | Profile photos | No (separate cache name) — re-fetched as needed | Yes |
| IndexedDB `fellows-local-db` | Offline-fallback full fellow rows | Regenerated on every successful boot | Yes |
| OPFS `fellows.db` | Imported Knack contact data | **Re-imported** every boot from `/fellows.db` | **No** (gap; see "Open questions") |
| OPFS `relationships.db` (PR 2+) | Groups, group members, fellow_tags, fellow_notes, settings — all user-authored | **Never** — that's the whole point of this file | **No** |
| localStorage `fellows_authenticated_once` | "this origin has authenticated at least once" marker | Untouched | **Preserved by name** in `clearAllAppData` |
| localStorage `ehf_has_email_only` | Has-email filter pref | Untouched | Cleared |
| localStorage `ehf.group_draft` (PR 1+) | In-progress group composer state | Untouched | Cleared (acceptable: drafts are unsaved) |
| localStorage `fellows_self_email` (PR 5+) | User's "me" email for `mailto:?to=…` | Untouched | Cleared, but rehydrated from `relationships.settings` on next boot |
| Cookie `fellows_session` (HttpOnly) | HMAC'd session, 7-day TTL, contains `token_issued_at` | Untouched (still valid until TTL) | Cleared (best effort — see `clearCookiesBestEffort`) |

The key architectural decision behind PR 1: **`relationships.db` is a
separate OPFS file from `fellows.db`** rather than a set of new tables
inside `fellows.db`. That's because `fellows.db` is bundled with the
build and re-imported on every boot, while OPFS files we don't
explicitly touch are durable. Cross-DB joins use SQLite `ATTACH
DATABASE 'fellows.db' AS f ?mode=ro`, which also enforces read-only
access to contact data at the SQLite level (any stray write into `f.*`
raises `OperationalError`).

## Standard app update flow

1. Operator runs `just ship`. Bundle goes out to the droplet.
2. Existing user opens the installed PWA (or visits in a browser tab).
3. SW polls `/build-meta.json` and notices the new build SHA.
4. SW fetches new `sw.js` (which has bumped `CACHE_VERSION`); install
   event runs and pre-caches the new shell.
5. `app.js` shows the "New version available — Reload" banner.
6. User clicks Reload. New SW activates. Old shell cache deleted.
   Controlled tabs auto-navigate (see `sw.js`'s activate handler).
7. Fresh `app.js` runs against fresh shell against fresh `fellows.db`.

What survives the reload, end-to-end:
- The session cookie (still valid until its 7-day TTL).
- `fellows_authenticated_once` (the URL-just-works marker).
- `relationships.db` (the user's groups, tags, notes, and settings).
- The image cache.
- All localStorage keys (drafts, filter prefs, etc.).

What gets replaced (intentionally):
- App shell HTML, JS, CSS, SW, manifest.
- `fellows.db` in OPFS (re-imported from `/fellows.db`; this is how
  new fellow data reaches the user).
- IndexedDB cache (regenerated on next successful `getList`).

## Per-user customization (or lack thereof)

The deployed bundle is identical for everyone. There is no per-user
packaging — the build does not generate a custom artifact per
recipient.

What looks "custom per user" is purely client-side state:

- The user's email is captured into `localStorage[fellows_self_email]`
  the first time they submit the magic-link gate (PR 5).
- It is also written to the `relationships.settings` table so it
  survives Clear App Cache. On boot, `app.js` mirrors the settings
  value back into localStorage for fast read.
- The Settings page (`#/settings`, PR 5) lets the user override —
  useful when someone wants exports addressed to a different
  mailbox than the one they sign in with.

A user moving between browsers / devices re-enters their email at
sign-in (the magic-link form already requires it). After verify, the
gate handler stashes it client-side. No server-side per-user state
beyond what the magic-link allowlist already requires.

## Edge cases

### A user upgrades to PR 5 with no `self_email` stashed

On first PR 5 boot, `relationships.settings` has no `self_email`
row. Surface a one-line nudge on the group-detail Export panel:
"Set your email in Settings to enable 'email it to me'." Or
auto-prompt on first export attempt. No data loss; just a one-time
setup step. Users who installed before PR 5 will all hit this
exactly once.

### A user clicks Clear App Cache

- localStorage clears (except `fellows_authenticated_once`).
- IndexedDB clears.
- All Cache API entries clear (shell + images).
- Cookies clear.
- Service worker registrations are unregistered.
- **OPFS does not clear**, so `relationships.db` — and `fellows.db` —
  both survive.
- After reload: user re-prompted for a magic link (cookie gone), then
  comes back into the directory with their groups intact. Their
  `self_email` (PR 5) re-mirrors from `relationships.settings` on
  boot, so the Settings page already shows it.
- The in-progress group draft (`ehf.group_draft`) IS lost — drafts
  are by definition unsaved.

### A user installs on a brand-new device

OPFS is empty, so `relationships.db` is created fresh. Their groups
from the old device are NOT here — there is no cross-device sync.
This is consistent with the project's "local-only PWA, no SaaS
backend" stance. If sync becomes a requirement later, the relevant
data is already isolated in `relationships.db` (separate from
contact data, identifiable as user-authored), which makes
export/import a tractable feature.

### Browser-tab visit by an existing user

`fellows_authenticated_once` is preserved across upgrades, so
`shouldActAsApp()` returns true on browser-tab visits and the user
boots directly into the directory — no install-landing detour. The
"endless install loop" some devs see on `localhost` does **not**
affect production users; it's gated on
`authStatus.authEnabled === false`, which is a dev-only signal
(prod always returns true).

### A user with a stuck PWA on a stale shell

The "New version available — Reload" banner is the canonical recovery
path. If they ignore it, they keep running the old shell — fine.
If they hit a bug that's already fixed in `main`, route them to
either:
1. Click the in-app **Reload** banner.
2. Click **Clear App Cache & Reload** (red button, bottom right).
   Their groups, settings, and auth marker survive; only the shell
   is replaced.

## Open questions / future work

- **OPFS reset.** Clear App Cache does not touch OPFS. If a user ever
  ends up with a corrupt OPFS-stored `fellows.db`, there's no UI path
  to wipe just that file. If this surfaces, add a separate "wipe local
  data and re-download" hook that deletes `fellows.db` from OPFS but
  leaves `relationships.db` intact.
- **PR 5 self-email migration.** When `fellows_self_email` is
  introduced, decide: preserve it across `clearAllAppData` like
  `fellows_authenticated_once`, or rely on the boot-time mirror from
  `relationships.settings`. The latter is simpler (one less special
  case in `clearAllAppData`) and the user-facing behavior is identical.
- **Future cross-device sync.** Out of scope today, but the layering
  here keeps the door open: `relationships.db` is a single
  self-contained file with stable schemas, suitable for an
  export/import flow or an opt-in sync against a future backend.
