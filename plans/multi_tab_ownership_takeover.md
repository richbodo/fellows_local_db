# Multi-tab Ownership Takeover

A plan to add graceful multi-tab handling on top of the worker-owned OPFS architecture from `local_first_worker_architecture.md`. Today, opening the app in a second tab while the first is still open causes the second tab's worker `init` to fail with `NoModificationAllowedError: Access Handles cannot be created if there is another open Access Handle …`, which falls through to the API+IDB fallback and renders the generic "your browser doesn't support this" panel. The user is left guessing what's wrong.

This plan replaces that failure mode with a coordinated handoff: the second tab detects the conflict, surfaces a specific UI ("Directory is already open in another window"), and offers to take over — at which point the first tab releases OPFS and shows a deactivated overlay.

## Context

`docs/Architecture.md` § Worker-owned OPFS § Non-goals already states the bright line: "OPFS sync access handles serialize per file; two tabs both opening `relationships.db` race on the SAH. Today's behavior — second tab fails to acquire — is preserved. A graceful 'another instance is open' UI is a follow-up, not a goal." This plan is that follow-up.

A separate cheap-fix landed first: the second tab now classifies the SAH-conflict failure distinctly and renders a specific "directory is open in another tab/window — close it and reload here" panel instead of the misleading version-floor copy. That fix lives in `app/static/app.js` (`bootOwnershipConflict` flag + new branch in `renderLocalDataUnavailablePanel`) and `app/static/vendor/sqlite-worker.js` (`OWNERSHIP_CONFLICT` errorCode tagging). It does not coordinate; it just stops misleading the user. This plan supersedes it once shipped.

Background reading:
- `plans/local_first_worker_architecture.md` § Non-goals — architectural ("No multi-tab concurrent ownership").
- `docs/persistence_and_upgrades.md` § Storage layers (`relationships.db.bak.*` rotation; OPFS files only the worker touches).
- `docs/email_gate.md` invariants 9 and 10 (URL-just-works for returning visitors; stale-session fallback).
- Web Locks API on MDN — minimum browser versions: Chrome 69+, Firefox 96+, Safari 15.4+ (all comfortably below the OPFS floor in `docs/browser_support.md`).
- BroadcastChannel API on MDN — same envelope of support.

## Goals

Each goal is a runtime-falsifiable statement.

T1. **Second tab knows immediately.** A second tab opening on the same origin discovers another tab owns OPFS *before* attempting `installOpfsSAHPoolVfs()`. Discovery latency: under 200 ms from page load.

T2. **The user sees a specific message.** When ownership is contested, the panel reads "Directory is already open in another window" — not "Chrome 102+" and not "OPFS unsupported".

T3. **Takeover is a single click.** The contention panel offers a "Use here instead" affordance. Clicking it transfers OPFS ownership from the previous tab to the current one within 3 seconds of the click (under normal conditions; up to the timeout fallback otherwise).

T4. **Old tab degrades safely.** The previous owner, on receiving a takeover, releases OPFS handles, terminates its worker, and renders a non-interactive overlay so the user can't act on stale state. Single "Reload" button.

T5. **No zombie locks.** When a tab closes (Cmd-W, browser quit, OS kill), its lock auto-releases and the next tab to request can acquire without manual intervention.

T6. **Drafts are respected.** If the old tab has unsaved state (group draft in `localStorage[ehf.group_draft]`), takeover requires confirmation in the *old* tab before releasing.

T7. **PWA + browser tab is the common case.** Detect "the other tab is the installed PWA" and tell the user, since most contention is going to be PWA + browser tab on the same machine. We can't `window.focus()` across windows, but we can name the destination.

T8. **Test coverage.** Two-tab Playwright scenarios cover detection, takeover, deactivated overlay, draft-confirmation, lock auto-release on tab close.

## Non-goals

- **Concurrent multi-tab editing.** OPFS SAH-pool is one-writer-strictly; no readers. Even a "view-only second tab" mode is out of scope — there is no honest way to provide it.
- **Cross-device coordination.** Web Locks is per-origin per-browser-profile. Two browsers, two profiles, two devices: completely separate locks. We're not building distributed locking.
- **Auto-takeover on idle.** A heartbeat-based "if owner stops responding, just take over" is a polish item; defer until field reports show frozen-tab cases that don't recover.
- **Showing the *other* tab's group/route stack.** We can broadcast the current route as a hint, nothing more. No DOM peeking across tabs.

## Invariants this plan adds

Numbered to be peers of `local_first_worker_architecture.md`'s `L*` invariants.

- **M1.** Web Locks API is the single source of truth for OPFS ownership. The lock named `fellows-opfs-owner` is acquired by the worker before any `installOpfsSAHPoolVfs()` call, and held for the lifetime of the worker.
- **M2.** When a second tab can't acquire the lock, the page receives a structured `OWNERSHIP_CONFLICT` result from worker `init`, never a raw DOMException leaking out of the SAH-pool. (The cheap-fix already pattern-matches on the SAH error message; M2 hardens that into a structural check that runs *before* OPFS is touched.)
- **M3.** All cross-tab coordination is over `BroadcastChannel('fellows-tab-coord')`. No localStorage/sessionStorage signaling. (Storage events are unreliable across worker boundaries; BroadcastChannel is purpose-built.)
- **M4.** A tab that has been kicked by takeover renders a full-screen `.tab-deactivated` overlay that intercepts every interaction. The only operative control is "Reload" → `location.reload()`.
- **M5.** Takeover with an unsaved group draft requires explicit confirmation in the holder tab. A "Take over" click in the requester tab cannot silently discard a draft.

## Architecture

### Web Locks for ownership

The worker requests an exclusive lock on `'fellows-opfs-owner'` immediately at the start of `init`, *before* `installOpfsSAHPoolVfs()`:

```js
// vendor/sqlite-worker.js (sketch)
let _releaseLock = null;
async function acquireOwnershipLock() {
  return new Promise((resolveOuter, rejectOuter) => {
    navigator.locks.request(
      'fellows-opfs-owner',
      { mode: 'exclusive', ifAvailable: true },
      (lock) => {
        if (!lock) {
          resolveOuter({ acquired: false });
          return;  // don't return a Promise → lock immediately released
        }
        // Hold the lock by returning an unresolved Promise. The lock is
        // held until _releaseLock() is called or the worker terminates.
        return new Promise((release) => {
          _releaseLock = release;
          resolveOuter({ acquired: true });
        });
      }
    ).catch(rejectOuter);
  });
}
```

The lock is auto-released when:
- The worker calls `_releaseLock()` (graceful release for takeover or `wipeAll`).
- The worker terminates (page calls `worker.terminate()`).
- The tab closes (browser cleans up the worker).

If `acquireOwnershipLock` reports `{acquired: false}`, the worker's `init` handler returns `{ok: false, reason: 'OWNERSHIP_CONFLICT', otherTabActive: true}` *without* attempting `installOpfsSAHPoolVfs()`. M1 + M2 satisfied.

### BroadcastChannel for handshake

A single channel `fellows-tab-coord`. Message envelope:

```ts
type Msg =
  | { type: 'announce', tabId: string, route: string, isStandalone: boolean, hasUnsavedDraft: boolean }
  | { type: 'request_takeover', fromTabId: string, fromRoute: string }
  | { type: 'takeover_denied', toTabId: string, reason: 'user_kept_draft' }
  | { type: 'releasing', fromTabId: string }
  | { type: 'released', fromTabId: string }
  | { type: 'where_are_you', fromTabId: string };  // discovery probe
```

Roles:

- **Owner tab.** On worker `init` success, broadcasts `announce` once and again every 30 s (cheap heartbeat for late-arriving listeners; not a takeover trigger). On `request_takeover`:
  - If `localStorage[ehf.group_draft]` is non-empty: prompt the user via a non-blocking confirm — "Another window wants to open the directory. You have an unsaved group draft. [Let the other window take over] [Keep this one]". On "keep", broadcast `takeover_denied`; on "let go", proceed.
  - If no unsaved draft, or user accepted: broadcast `releasing`, call worker's `releaseOwnership` RPC, render the deactivated overlay, broadcast `released`.
  - On `where_are_you`: respond with `announce`.

- **Contesting tab.** On worker `init` returning `OWNERSHIP_CONFLICT`:
  - Broadcast `where_are_you` (in case the owner missed the initial `announce` it makes on its own boot).
  - Listen for `announce`; render the contention panel with the holder's route hint and "is the installed PWA" hint.
  - User clicks "Use here instead" → broadcast `request_takeover`, wait for `released` (or 3 s timeout).
  - On `released` or timeout: re-spawn the worker. Web Locks queue ensures the lock acquisition succeeds when the previous holder released it.
  - On `takeover_denied`: render an explanation ("The other window has unsaved work. Save or discard it there, then reload here.") + "Try again" button.

### Worker-side `releaseOwnership` RPC

New RPC handler in `vendor/sqlite-worker.js`:

```js
handlers.releaseOwnership = async function () {
  // Close all open DBs.
  if (relDb) { try { relDb.close(); } catch (e) {} relDb = null; }
  if (fellowsDb) { try { fellowsDb.close(); } catch (e) {} fellowsDb = null; }
  // Release the SAH-pool: this drops every capacity-file SAH so the
  // next tab's installOpfsSAHPoolVfs can acquire them.
  if (poolUtil) { try { await poolUtil.removeVfs(); } catch (e) {} poolUtil = null; }
  // Release the Web Lock so a queued waiter wakes up.
  if (_releaseLock) { _releaseLock(); _releaseLock = null; }
  return { released: true };
};
```

After `releaseOwnership` resolves, the page broadcasts `released`, terminates the worker, and renders the `.tab-deactivated` overlay (M4).

### Page-side state machine

Simplified:

```
                 ┌──────────────┐
                 │  page boot   │
                 └──────┬───────┘
                        │ worker.init
                  ┌─────┴─────┐
            ok=true            ok=false / OWNERSHIP_CONFLICT
              │                       │
              ▼                       ▼
     ┌────────────────┐      ┌──────────────────┐
     │  OWNER          │      │  CONTESTING      │
     │  - hold lock    │      │  - render panel  │
     │  - hb announce  │◀──┐  │  - listen        │
     └────┬───────────┘   │  └──────┬───────────┘
          │ request_takeover         │ user clicks "Use here"
          ▼                          ▼
   ┌────────────────┐          ┌────────────────┐
   │ HOLDER PROMPT  │          │ REQUESTING     │
   │ (if draft)     │          │ - broadcast    │
   └──┬─────────┬───┘          │   request      │
      │ keep   │ release       │ - wait ack     │
      ▼        ▼               └──────┬─────────┘
  takeover_   release+overlay         │ released | 3s timeout
  denied      releaseOwnership        ▼
              terminate worker  ┌─────────────────┐
                                │ RE-SPAWN WORKER │
                                │ → OWNER         │
                                └─────────────────┘
```

`tabId` is a `crypto.randomUUID()` minted at script load. Used only for matching messages back to senders; not persisted, not telemetered.

### Edge cases

1. **Owner is in the email gate / install landing.** The worker spawns warm but no DB has been opened yet — actually in `vendor/sqlite-worker.js` the `init` handler opens `relationships.db` immediately, so the lock *is* held. That's correct: the lock matches OPFS-pool ownership, not "current screen". A second tab arriving on the gate will still get the contention panel. Acceptable; the user wanted to open the app, the panel is the right answer.

2. **Owner tab is suspended/frozen** (browser threw it into background, JS halted). No `announce` heartbeat, no response to `where_are_you`. Contesting tab waits ~3 s after `request_takeover` and proceeds anyway. Web Locks itself will only resolve when the underlying process releases. Two cases:
   - Owner is genuinely dead → process exits, lock releases, requester wakes.
   - Owner is just frozen → lock still held. Requester's wait-for-released path times out, then it tries `worker.init` directly, which fails again with `OWNERSHIP_CONFLICT`. Render a softer message: "The other window appears to be unresponsive. Close it manually and reload."

3. **Three or more tabs.** Owner sees `request_takeover` from tab B. Meanwhile tab C also broadcasts `request_takeover`. We don't queue: owner releases (M-style "first ack wins"), the released event triggers both B and C to retry the lock; one wins, the other gets `OWNERSHIP_CONFLICT` against the new owner. New contention panel in the loser. Cycle continues until one tab is left. Fine.

4. **Refresh of the contesting tab during waiting.** The page navigated away; the BroadcastChannel listener is gone. Owner's release is wasted (channel still works for the survivor; they'll get `released` if they're listening). The new page load will re-arrive in CONTESTING and re-broadcast `request_takeover` if needed.

5. **Owner closes tab during takeover handshake** (between `request_takeover` and `releasing`). Web Locks releases, requester's lock acquisition wakes up. Contestant becomes owner. The deactivated-overlay path never runs in the closed tab (it's gone).

6. **iOS Safari quirk.** Web Locks API exists since 15.4, but Safari has historically returned the lock callback synchronously for `ifAvailable: true` rather than queuing — should still work for our use, but verify on iOS 16.4 baseline before merging.

7. **PWA + browser tab.** Owner's `announce` carries `isStandalone: true`. Contestant's panel reads "Directory is open in your installed app window. [Use here instead] [Cancel]". Same machinery, just a clearer message.

8. **Storage quota / OPFS write failure inside `releaseOwnership`.** The Web Lock release happens last; if `removeVfs()` throws, we still call `_releaseLock()` to avoid locking out future tabs. The owner's overlay still renders. The next tab's `installOpfsSAHPoolVfs()` may fail with stale state — which falls back to the cheap-fix's panel. Net: the worst case looks like the cheap-fix world, not worse.

## Implementation phases

### Phase 1 — Worker lock acquisition (no UI changes)

- Add `acquireOwnershipLock()` to `vendor/sqlite-worker.js`.
- Call before `installOpfsSAHPoolVfs()` in the `init` handler.
- On `{acquired: false}`: return a structured `{ok: false, reason: 'OWNERSHIP_CONFLICT', otherTabActive: true}` to the RPC.
- Page's `spawnWorkerAndInit` already classifies init failures; teach it to recognize the structured form (in addition to the string-match the cheap fix added).
- Ship behind a constant `MULTI_TAB_TAKEOVER_ENABLED = false` so the new lock acquisition is not yet enforced; this lets us merge the worker change before the page UI is ready.

Tests: one e2e that opens two tabs and verifies tab B sees `OWNERSHIP_CONFLICT` with the structural shape (not just the substring match). Worker-only test, no UI.

### Phase 2 — `releaseOwnership` RPC + page state machine

- Add `releaseOwnership` RPC handler to the worker. On call: close DBs, `removeVfs()`, release lock, return `{released: true}`.
- Add page-side `tabId`, BroadcastChannel setup, OWNER/CONTESTING/REQUESTING state.
- Owner tab: broadcast `announce` on init success. Listen for `request_takeover`, `where_are_you`.
- Contesting tab: broadcast `where_are_you` on init failure; render new contention panel (Phase 3 finalizes the panel HTML).
- Flip `MULTI_TAB_TAKEOVER_ENABLED = true`.

Tests:
- Tab A boots → owns. Tab B boots → contesting, sees announce, renders panel.
- Tab B clicks takeover → A releases → B re-spawns and owns.
- Tab A closes (page.close) → no lock, B can boot fresh into ownership.

### Phase 3 — Deactivated overlay + draft-respect

- Implement `renderTabDeactivatedOverlay()` in `app.js`. Full-screen, intercepts pointer/keyboard, single Reload button (M4).
- Owner tab on receiving `request_takeover` checks `localStorage[ehf.group_draft]`. If present: render a confirm dialog and broadcast `takeover_denied` if the user keeps the draft.
- Contesting tab handles `takeover_denied`: render a friendlier explanation ("The other window has unsaved work. Save or discard it there, then click Try again.") with a manual "Try again" button (re-broadcasts `request_takeover`).

Tests:
- Owner with `localStorage[ehf.group_draft]` set: B's takeover → A prompts, A keeps draft → B sees denied.
- A discards draft → B's takeover succeeds.
- Owner overlay: assert no clicks reach underlying UI; Reload reloads.

### Phase 4 — Polish + docs

- Owner tab: heartbeat `announce` every 30 s.
- Contesting tab: respect `isStandalone` in panel copy ("installed app window" vs "another browser tab").
- Update `docs/Architecture.md` § Non-goals — bright line still holds (no concurrent multi-tab) but cross-reference this plan from "A graceful 'another instance is open' UI is a follow-up".
- Update `docs/persistence_and_upgrades.md` to mention the takeover machinery in the storage-layer table footnotes.
- Update `docs/users_manual.md` with a short "Why does it say it's open in another window?" subsection in Troubleshooting.

### Phase 5 — Optional follow-up

- **Heartbeat liveness fallback.** Owner missed-beat threshold (e.g. 60 s) → contesting tab auto-takeover with a softer panel ("The other window is no longer responding"). Defer until field reports show frozen-tab cases.
- **Service-worker-driven coordination.** A SW could hold a per-origin "current owner tabId" and arbitrate. Avoided here because the SW is already constrained by Architecture.md non-goals to be app-shell + update only. Consider only if BroadcastChannel proves unreliable.

## Test plan

E2E (Playwright; new file `tests/e2e/test_multi_tab_ownership.py`):

1. `test_second_tab_sees_contention_panel` — open two pages, assert the second renders the new copy.
2. `test_takeover_promotes_second_tab` — second tab clicks takeover, asserts first tab shows the deactivated overlay and second tab can `createGroup`.
3. `test_first_tab_close_releases_lock` — close first, assert second can re-spawn worker without intervention.
4. `test_draft_blocks_takeover` — set `localStorage[ehf.group_draft]` in tab A, request takeover from B, assert A prompts, B receives denied.
5. `test_three_tab_chain` — open A, B, C in order; takeover from B (over A); takeover from C (over B); assert C ends up owning, A and B both deactivated.
6. `test_pwa_hint_in_panel` — fake `display-mode: standalone` in tab A; assert tab B's panel says "installed app window".

Unit / worker tests:

7. `test_worker_init_returns_ownership_conflict` — drive two worker boots, assert second returns the structured `OWNERSHIP_CONFLICT` shape, not a raw DOMException.
8. `test_release_ownership_lets_next_init_succeed` — drive worker A `init`, then A `releaseOwnership`, then worker B `init` → succeeds.

Manual smoke (post-merge, pre-deploy):

- Two browser tabs on prod; verify takeover round-trip.
- Installed PWA + browser tab on the same Mac; verify panel copy and takeover.
- Safari 16.4 sanity check (Web Locks `ifAvailable` quirk).

## Open questions

Q1. **Should `announce` carry the route as a navigation suggestion?** The contention panel could read "Open it here instead — currently on `#/groups/3`". Risk: if the user takes over and the new tab doesn't navigate to that route, the experience feels like a regression. Probably show the route as a hint, not as an auto-navigate target. Decide in Phase 3.

Q2. **Should the contesting tab pre-fetch resources while waiting for takeover?** The 1–3 s release window is dead time. We could spawn the worker in `WORKER_INIT_TIMEOUT_MS` mode while waiting. Optimization, not correctness. Defer.

Q3. **Can we detect which OPFS file the contention is on?** The Web Lock is on a single name (`fellows-opfs-owner`). If a future feature needs `fellows.db` and `relationships.db` to have separate locks (e.g. read-only `fellows.db` shared across tabs while `relationships.db` is exclusive), we'd split the lock name. Out of scope; flagged here so future-us knows the lock-name commitment is not load-bearing.

Q4. **Telemetry?** A successful takeover round-trip is interesting (proves the machinery works in the wild); a denied takeover is more interesting (shows users actively choosing one tab over another). Both are sub-events of a low-volume corner case, so the cardinality is fine. Add `kind=takeover` events to `/api/client-errors` (mirroring the existing `kind=install` install-funnel events). Confirm in Phase 4 with a docs update to `docs/email_gate.md` § Client error reporting.
