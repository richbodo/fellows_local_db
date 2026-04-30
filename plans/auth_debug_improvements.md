# Auth-flow debug improvements

Triggered by two tester reports that exposed real failure modes in the
email-gate / install-landing flow:

- **Todd** (MacBook Pro, Chrome and Safari): clicked the email link,
  hit the install landing, clicked **Install app**, got *"Your browser
  doesn't support install"*. Later opened the bare URL from Slack — it
  worked.
- **Anne-Marie** (iOS, Apple Mail): clicked the email link, got
  *"That link isn't valid. Enter your email to get a new one."*

Two distinct bugs, separate root causes.

---

## Bugs

### Bug A — install-landing dead-end (Todd)

**Symptom:** "Your browser doesn't support install" on a browser that
plainly does.

**Root cause:** the `#install-unsupported-hint` text
(`app/static/index.html:132-135`) is revealed by the click-fallback
branch in `app/static/app.js:2426-2428` when `beforeinstallprompt`
hasn't fired. The handler treats the missing event as a browser
limitation, but on Chrome/Edge it's frequently caused by:

1. PWA already installed on this profile (Chrome suppresses the event;
   the comment at `app.js:2400-2407` already calls this out).
2. Engagement heuristic not yet satisfied (Chrome may fire the prompt
   later in the session).
3. SW not yet activated on the very first load.

The current copy blames the browser for all three.

**Why it self-resolved for Todd later:** `startBrowserUx` calls
`markAuthenticatedOnce()` at `app.js:2668` *before* it renders the
install landing. So Todd's first verify-token success set
`fellows_authenticated_once`. His later bare-URL visit hit
`shouldActAsApp() === true` (`app.js:2125-2129`) and booted the
directory directly. Discoverable by accident, not by design.

### Bug B — Anne-Marie's "link isn't valid"

**Symptom:** verify-token returned `error: "invalid"` (not "expired")
and the gate banner read "That link isn't valid."

**Root cause:** `consume_token`
(`deploy/magic_link_auth.py:90-108`) returns `"invalid"` only when the
token is **not in `AuthState.tokens` at consume time**. Distinct from
"expired", which means it's still in the dict but past TTL. So her
click wasn't late — the token was *gone* by the time the server saw
it.

Three plausible explanations, ranked by how cheaply we can confirm
them:

- **B1 — service restart between send and click.** `AuthState.tokens`
  is process-local. Any `systemctl restart fellows-pwa` after issue
  invalidates every outstanding token.
- **B2 — bfcache restore / back-button replay re-fired
  `tryUnlockFromHash`.** iOS Safari's bfcache can resurrect a page
  with the original `#/unlock/<tok>` hash; second POST is "invalid"
  because the first consumed the token.
- **B3 — email-side scanner pre-consumed the token.** Less likely on
  the current hash-based flow (scanners typically don't execute JS),
  but iOS Mail / Outlook / corporate AV can vary.

We'll run a journald check to disambiguate, but the fix space (M2 +
M3 below) closes B2 and B3 regardless of which one bit her on the
day.

---

## Improvements to ship

Three independent changes, each one a net safety win, ordered by
risk-adjusted value.

### M1 — install-landing escape hatch (fixes Bug A)

**Change:** replace the dead-end "browser doesn't support install"
copy with a two-action message — open the already-installed app, *or*
use the directory in this tab — and add an always-visible **use the
directory in this tab** link to the install landing. Clicking the
in-tab link calls `markAuthenticatedOnce()` and `bootDirectoryAsApp()`
— the same path Todd discovered by accident from Slack.

**Files:**
- `app/static/index.html` — replace the `#install-unsupported-hint`
  copy; add `#install-use-in-tab` button inside the hint.
- `app/static/app.js` — wire the `use-in-tab` click in
  `initBrowserInstallMode`. Make the unsupported-hint visible by
  default (not just on click) on non-iOS browser-tab visits, so the
  escape hatch is discoverable without clicking Install first.
- `docs/users_manual.md` — note the new option in the *Installing the
  app* section.

**Risk:** low. Purely additive on UX. The Install button remains the
primary affordance; the in-tab link is secondary. No state
divergence — `markAuthenticatedOnce` is already called on the same
code path today.

**Test:** add an e2e in `tests/e2e/test_install_landing.py` that
simulates a verify-token success in Chromium with `beforeinstallprompt`
suppressed, clicks "use the directory in this tab", and asserts the
directory renders. (Existing `tests/e2e/test_install_landing.py`
covers the install-landing-rendered case; this extends it.)

### M2 — client-side double-fire guard (mitigates Bug B2 and B3)

**Change:** `tryUnlockFromHash` writes
`sessionStorage['redeeming:<token>'] = Date.now()` before the POST.
On entry it checks the key; if present, strip the hash and no-op.
sessionStorage is per-tab and cleared on tab close, so a fresh
visit always retries cleanly.

```js
function tryUnlockFromHash() {
  var hash = window.location.hash || '';
  var m = hash.match(/^#\/unlock\/(.+)$/);
  if (!m) return Promise.resolve();
  var token = m[1];
  var key = 'redeeming:' + token;
  try {
    if (sessionStorage.getItem(key)) {
      // Already in-flight or completed in this tab; strip and bail.
      window.history.replaceState(null, '', '/#/');
      return Promise.resolve();
    }
    sessionStorage.setItem(key, String(Date.now()));
  } catch (e) {}
  return fetch('/api/verify-token', { /* ...as today */ });
}
```

**Files:** `app/static/app.js` (`tryUnlockFromHash`).

**Risk:** low. sessionStorage is universally supported on browsers we
already gate at OPFS (Chrome 102+, Safari 16.4+, Firefox 111+ — all
predate sessionStorage by a decade). Worst-case failure is "tab can't
re-redeem after restore" — the user opens the email link in a fresh
tab and proceeds.

**Test:** unit test pattern via Playwright e2e — load the unlock URL,
intercept and *delay* `/api/verify-token`, fire a back-forward
navigation that would re-trigger boot, assert only one POST was
issued.

### M3 — server-side grace window for re-consume (mitigates Bug B2 cross-tab and Bug B3)

**Change:** in `deploy/magic_link_auth.py`, keep recently-consumed
tokens in a small dict for `GRACE_WINDOW = 60` seconds with their
`issued_at`. A second `consume_token` for the same token within that
window returns `{"status": "ok", "issued_at": ...}` again — same
session value, same install-window calculation.

```python
class AuthState:
    lock = threading.Lock()
    tokens: dict[str, float] = {}
    consumed: dict[str, dict] = {}   # tok -> {issued_at, consumed_at}
    rate_buckets: dict[str, list[float]] = {}

GRACE_WINDOW = 60

def consume_token(tok: str) -> dict:
    now = time.time()
    with AuthState.lock:
        # Fast path: token still active.
        exp = AuthState.tokens.pop(tok, None)
        if exp is not None:
            if exp < now:
                return {"status": "expired"}
            issued_at = exp - TOKEN_TTL
            AuthState.consumed[tok] = {"issued_at": issued_at, "consumed_at": now}
            return {"status": "ok", "issued_at": issued_at}
        # Grace path: was consumed recently?
        rec = AuthState.consumed.get(tok)
        if rec and (now - rec["consumed_at"]) < GRACE_WINDOW:
            return {"status": "ok", "issued_at": rec["issued_at"]}
        # Drop stale grace records opportunistically.
        if rec:
            AuthState.consumed.pop(tok, None)
        return {"status": "invalid"}
```

Add cleanup of `consumed` in `cleanup_stale_tokens()` (drop entries
older than `GRACE_WINDOW`). Bound on memory: at most one grace entry
per recent click — trivially small at this scale.

**Files:** `deploy/magic_link_auth.py`, `tests/test_magic_link_auth.py`.

**Risk discussion (the threat-model question, since we're widening the
single-use property):**

- *Today*: a leaked URL is single-use. First clicker wins. Passive
  scanner that prefetches before the user → user gets "invalid."
- *With M3*: a leaked URL is reusable for 60s by anyone who has it.
  Passive scanner that prefetches before the user → user's click
  within 60s succeeds.

The realistic adversary scenarios:
1. **Passive scanner** (corporate IT, AV). Prevalent; consumes the
   token on prefetch; breaks the legit user. M3 makes this case
   work, not break. **Net positive.**
2. **Email-account compromise.** Attacker reading the user's mail
   directly. They can request their own magic link; the 60s window
   doesn't help them. **No change.**
3. **URL leak to a co-located attacker** (same network, shoulder-surf,
   forwarded screenshot). Attacker has 60s to also consume. Today,
   they have one chance to beat the user; tomorrow, both succeed. The
   attacker still needs the URL within 60s — not a meaningful
   weakening compared to the existing 30-min token TTL during which
   they could already race the user.

Verdict: M3 is a net safety win in the threat model that actually
applies to this product (small-audience directory, distribution by
email, no high-value sessions).

**Test plan:** `tests/test_magic_link_auth.py` — three new cases:
1. Consume within grace window returns `ok` with the original
   `issued_at`.
2. Consume after grace window returns `invalid`.
3. `cleanup_stale_tokens` drops `consumed` entries past
   `GRACE_WINDOW`.

---

## Considered and rejected

### Path-based magic-link routing (`/unlock/<tok>` → `303 /`)

**Rejected.** The textbook pattern, but a worse fit here.

- A server-handled GET-redeem is consumed by *any* prefetcher — not
  just JS-running ones. Microsoft Safe Links, Outlook link preview,
  and most corporate AV happily issue GETs. Today's hash-based flow
  accidentally requires JS, which is mild but real scanner protection.
- The only robust mitigation against GET prefetchers is a
  **POST interstitial** ("Click here to continue") with a same-site
  cookie. That's an extra click for users — UX-hostile and the kind
  of thing testers complain about.
- A meta-refresh redirect from `/unlock/<tok>` → `/unlock/redeem?t=...`
  defeats simple GET prefetchers but not anything sophisticated;
  leaky security theater.
- With M2 + M3 in place, the hash flow's known failure modes
  (bfcache replay, scanner consumption, double-click) are closed.

So the rewrite would *create* a new failure mode (scanner consumption
becomes worse) to *solve* problems we already solved another way.
Doesn't clear the "catches more errors than it creates" bar.

### Proactive `getInstalledRelatedApps()` detection on the install landing

**Rejected for now.** Could potentially detect "PWA already installed
on this device" and skip the install landing entirely. Promising but:
- Chrome-only (Firefox / Safari don't implement).
- Requires `related_applications` configured in the manifest.
- Returns a Promise that resolves async — would need a loading state,
  more complexity than M1's in-tab link gives us.

If M1 doesn't fully resolve the dead-end after rollout, revisit as a
Chrome-only enhancement.

### Invalidate prior tokens on a new send

The chat-thread reply implied this is how the system works
(*"When you get a new link sent it invalidates any old links"*) —
but `issue_token` (`magic_link_auth.py:82-87`) doesn't do it; old
tokens stay valid until TTL or single-use consumption. **The current
behavior matches the email-gate spec; the chat reply was wrong. No
change.** If we ever want to enforce "newest send wins," that's a
separate feature, not a debug fix.

---

## Investigation (run before committing M3)

Confirm or rule out the restart theory for Bug B. Findings won't
change whether we ship M3, but may downgrade urgency or surface a
different root cause we haven't enumerated.

```bash
# 1. Service-state probe — was fellows-pwa restarted on the day of the report?
ssh -p 52221 rsb@fellows.globaldonut.com \
  'systemctl show fellows-pwa --property=ActiveEnterTimestamp,ActiveExitTimestamp,NRestarts'

# 2. Window query around Anne-Marie's send (replace dates if her send wasn't on 2026-04-29):
ssh -p 52221 rsb@fellows.globaldonut.com \
  'journalctl -u fellows-pwa --since "2026-04-29 08:50" --until "2026-04-29 10:30" --no-pager'

# 3. Anne-Marie's own send_unlock_email events (without typing her email here):
EMAIL=$(sqlite3 app/fellows.db \
  "SELECT contact_email FROM fellows WHERE name LIKE '%Anne-Marie%Brook%'")
just email-debug '2026-04-29 08:50' "$EMAIL"
```

Decision tree on findings:

- **`ActiveEnterTimestamp` is after Anne-Marie's send time** → Bug B1
  confirmed. M3 still valuable; also opens a separate question about
  token persistence across restarts (out of scope for this plan —
  would need a small SQLite-backed token store).
- **No restart, exactly one `send_unlock_email` with one
  verify-token attempt that returned 401 invalid** → Bug B2 (bfcache
  / replay) or Bug B3 (scanner). M2 + M3 close both.
- **Multiple verify-token attempts close together** → Bug B2 confirmed.
  M2 alone may be sufficient; M3 still cheap insurance.

---

## Rollout

Two PRs, in this order:

**PR-1: M1 + M2.** User-visible UX fix + cheap client guard. ~50 LoC
plus doc and one e2e. Ship via `just ship`. Ask Todd to retry the
flow that broke for him.

**PR-2: M3.** Server-side change with unit tests. Ship via `just ship`.
Ask Anne-Marie to retry on iOS.

Both are non-breaking — old clients keep working; new clients pick up
the improvements after the next SW activation cycle.

---

## Out of scope

- Token persistence across server restarts (would solve Bug B1
  durably). Material change to the auth model — separate plan.
- Routing rewrite (see "Considered and rejected").
- Any changes to the bug-reporter UX (the new bug-reporter shipping
  this week will catch the next round of reports more cleanly).
