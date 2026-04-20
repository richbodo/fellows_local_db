# Email Gate

Authoritative specification of the email-gate / install-landing algorithm. The runtime (`app/static/app.js`, `deploy/server.py`, `deploy/magic_link_auth.py`) must match this document; if they drift, this document is what's right and the runtime is a bug.

Operator procedures (Postmark, env file, Postmark response interpretation) stay in [`email_system_management.md`](email_system_management.md). This file is the behavioral spec.

## Goals

- The default view is the **email gate** — an empty form for requesting a magic link. Everything else requires affirmative state to appear.
- The **install landing** exists only to capture a one-shot "install the PWA" gesture, inside a bounded window after a token was issued. It is not a logged-in home page.
- A dev must always be able to return to the gate in one click, even if auth state is confusing.

## Definitions

- **Session cookie** — `fellows_session`, HttpOnly, HMAC-signed, carrying `token_issued_at` (epoch seconds). v2 format; v1 cookies are rejected on sight so prior sessions re-login cleanly after this ships.
- **Magic-link token** — single-use, `TOKEN_TTL = 30 min` from issue. Random 32-byte hex.
- **Install window** — `INSTALL_WINDOW = 30 min` measured from token issue (not from click). Same duration as token TTL by design: a user has 30 min from the email being sent to finish clicking and installing.
- **Display mode** — *browser* (`display-mode != standalone`) vs *PWA* (`display-mode: standalone`).

## Invariants

1. **Email gate is the default.** The only exits from it are: (a) a URL carrying an unexpired magic-link token, or (b) an authenticated session *within* the install window, or (c) PWA mode with a valid session (→ directory).
2. **Install landing never repeats.** It shows only inside the install window. Once the window closes, or the user explicitly logs out, the only path back is a fresh magic link.
3. **Expired links are explicit.** Clicking an expired token lands on the email gate with a visible "that link expired" banner.
4. **Invalid links are explicit.** Clicking a tampered or already-consumed token lands on the email gate with "that link isn't valid".
5. **Magic-link emails state the TTL.** Body includes: "This link will expire in 30 minutes."
6. **Session cookie TTL is long** (`SESSION_MAX_AGE = 7 days`) so installed PWAs persist; the install window is decoupled and short.
7. **Dev escape hatch is always reachable.** Two layers:
   - A **"Back to email gate"** control on the install landing, which `POST`s `/api/logout` (clears the cookie server-side) then navigates to `/?gate=1`.
   - A **hardcoded URL override** `/?gate=1` that forces the gate UI regardless of cookie state. Works even when JS-driven logout fails.
8. **Unsupported browsers are told so — on click, not eagerly.** If a user clicks "Install app" and `beforeinstallprompt` never fired (and they're not on iOS Safari), the install landing swaps in a panel asking them to use Chrome, Edge, Safari, or another browser that supports PWA install. No auto-timer: Chrome suppresses `beforeinstallprompt` when the PWA is already installed on the device, and an eager timer would false-positive on those users.
9. **URL-just-works for returning visitors.** A browser-tab visit with `fellows_authenticated_once` set *acts as the app* (directory via API) instead of forcing the install landing. The installed standalone PWA remains the preferred launcher; this is a graceful fallback for users who type/bookmark the URL. `?gate=1` still wins in every case.
10. **A stale session does not lock users out of cached data.** If `/api/fellows` (or `/api/fellows?full=1`) returns 401 during boot, the app falls back to the IndexedDB cache populated by the last successful boot. The build badge flips to `server: offline · using cache` so users know the state. The user can still browse the directory, read profiles, and use the search over cached data. Fresh data requires an explicit `?gate=1` visit to request a new magic link. Rationale: "install once, works forever" — a long-lived local copy should not fail shut when the server session expires.

## Browser-mode decision tree

Evaluated on every page render (after auth-status fetch). Order matters — first match wins.

```
1. URL hash == "#/unlock/<token>"?
     POST /api/verify-token {token}
       → 200 ok        : cookie{token_issued_at=now} set by server; strip hash; fall through to #2
       → 401 expired   : location.replace("/?gate=1&reason=expired")
       → 401 invalid   : location.replace("/?gate=1&reason=invalid")
       → network err   : location.replace("/?gate=1&reason=invalid")

2. localStorage[fellows_authenticated_once] == "1"  AND  ?gate=1 NOT in URL?
     → ACT AS APP (directory via API, same code path as standalone PWA)
       - This is "URL-just-works": a returning user who already installed the
         PWA once sees the directory in a regular browser tab instead of
         being pushed through the install landing again. The installed
         standalone copy remains the preferred launcher; this path is a
         graceful fallback when they type/bookmark the URL.
       - If the API refuses (session expired, 5xx), fall through to
         startBrowserUx (item #3+) so the email gate can appear.

3. ?gate=1 in URL?
     → EMAIL GATE
       ?reason=expired → banner "That link expired. Enter your email to get a new one."
       ?reason=invalid → banner "That link isn't valid. Enter your email to get a new one."
       otherwise       → no banner

4. authStatus.authEnabled == false  (local dev passthrough)
     → INSTALL LANDING (dev has no real gate; this preserves the developer UX)

5. authStatus.authenticated && authStatus.installRecentlyAllowed
     → INSTALL LANDING
       - Install button wired to beforeinstallprompt
       - Unsupported-browser hint only shows on click when prompt isn't
         available (no 3s auto-timer — see PR #47).
       - "Back to email gate" link: POST /api/logout then navigate /?gate=1

6. default
     → EMAIL GATE (no banner)
```

### `fellows_authenticated_once` marker

Set in two places:

- `startBrowserUx` when `/api/auth/status` returns `authenticated: true` — the browser has a valid session, so even if the install window has closed we know this origin has been cleared before.
- Successful `getList()` in app-mode boot (standalone PWA, or browser-tab-acting-as-app) — proves the API accepted our session.

Preserved across `clearAllAppData` (the only localStorage key that survives Clear App Cache). Rationale: "Clear App Cache" exists to fix a broken app, not to log users out of an install they were happily using.

## PWA-mode decision tree

Installed PWAs never see the install landing.

```
1. authStatus.authenticated?  → DIRECTORY
2. otherwise                  → EMAIL GATE (same component as browser mode)
```

## State diagram

```
                      ┌──────────────────────┐
                      │   EMAIL GATE         │◀────────────────────────┐
                      │   (default)          │                         │
                      └──────────┬───────────┘                         │
            submit email         │                                     │
                                 ▼                                     │
                    Postmark sends magic link                          │
                      (expires 30 min)                                 │
                                 │                                     │
     click link within 30 min    │     click expired link              │
                                 │            │                        │
                                 ▼            ▼                        │
                  ┌───────────────────┐   gate + "expired" banner      │
                  │ verify-token: ok  │                                │
                  │ cookie{tia=now}   │                                │
                  └──────────┬────────┘                                │
                             ▼                                         │
                  ┌──────────────────────────┐  logout / window expiry │
                  │  INSTALL LANDING         │  / ?gate=1 URL          │
                  │  (install window)        ├─────────────────────────┘
                  │  [Back to email gate]    │
                  └──────────┬───────────────┘
                             │ click "Install app" → browser installs PWA
                             ▼
                  ┌────────────────────┐
                  │  PWA (standalone)  │
                  │  → DIRECTORY       │
                  └────────────────────┘
```

## Endpoints

| Method | Path                   | Purpose                                                       |
|--------|------------------------|---------------------------------------------------------------|
| GET    | `/api/auth/status`     | Returns `{authEnabled, authenticated, installRecentlyAllowed, hasSessionCookie, build, buildGitSha}`. Never gated. |
| POST   | `/api/send-unlock`     | Accepts `{email}`. Always returns `{sent: true}` (anti-enumeration). Internally: validates shape, checks rate limit, checks allowlist, issues token, sends Postmark email. |
| POST   | `/api/verify-token`    | Accepts `{token}`. Returns `{ok: true}` + Set-Cookie on success; `{ok: false, error: "expired"\|"invalid"}` otherwise (401). |
| POST   | `/api/logout`          | Clears session cookie (Max-Age=0). Always returns `{ok: true}`. |

## Cookie format (v2)

Plaintext payload (utf-8): `v2:<session_expires_at>:<token_issued_at>:<nonce>`
Cookie value: `base64url(payload) + "." + hex(hmac_sha256(secret, payload))`

- `session_expires_at` = `int(time.time()) + SESSION_MAX_AGE`
- `token_issued_at` = the `issued_at` of the magic-link token that granted this session (epoch seconds). `0` only in legacy/test paths.
- Sig = `hmac_sha256(FELLOWS_SESSION_SECRET, payload)`.

On every request the server recomputes HMAC, rejects on mismatch, and rejects if `session_expires_at < now`. The install-window check is *separate*: `now - token_issued_at < INSTALL_WINDOW`.

## Security notes

- Anti-enumeration: `/api/send-unlock` never reveals whether the email is on the allowlist.
- Distinguishing "expired" vs "invalid" in verify-token leaks only the fact that the token existed at some point. Negligible vs UX win.
- `/api/logout` is idempotent and doesn't require a valid session. That's intentional — the endpoint's job is to guarantee the cookie is cleared, not to validate the caller.
- The URL override `?gate=1` does not bypass auth; it only forces the **UI** to render the gate. Protected endpoints (`/fellows.db`, `/images/*`, directory `/api/*`) still require a valid session.
