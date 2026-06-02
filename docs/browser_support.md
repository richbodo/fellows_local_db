# Browser Support

> **Annex to [`Architecture.md`](Architecture.md).** Specializes the **Storage** slot's capability-detection sub-contract (ST-2 + AC-12) and the Workspace's unsupported-browser surfacing (WS-6) for fellows_local_db's `opfs-sqlite-wasm` flavor — required browser versions, the worker-internal capability check, the policy stance on UA-sniffing vs. capability detection. Read [`Architecture.md`](Architecture.md) first; this file is the depth-doc for browser-compatibility triage.

How we triage long-tail browser-compatibility issues for this app. The
audience is small (~hundreds of fellows) and the distribution model is
"by emailed magic link, install once" — but each one of those users
runs a different browser/OS combo, and we will keep meeting people
whose device falls outside what we tested. This doc captures the
policy so we react consistently when that happens.

## Stance

1. **Local-first.** User-authored data (groups, per-fellow notes,
   per-fellow tags, settings) lives in `relationships.db`, not on a
   server. That gives us per-device privacy and offline-by-default. But
   that store is only **durable** when it is backed by a verified folder
   on disk (Chromium desktop) — so private data is gated on that folder,
   not merely on OPFS. Off-folder the app runs **browse-only** (directory
   + search + open a fellow + email/call), with no durable private store.
   See *[Folder mode — required for private data](#folder-mode--required-for-private-data)*.
2. **Capability-detect, don't UA-sniff for gating.** We test the
   capability (`navigator.storage.getDirectory`,
   `globalThis.sqlite3InitModule`, `globalThis.isSecureContext`).
   UA strings are used **only** to render a more helpful unsupported
   message — never to allow/deny features. **Nuance (the two gates):**
   the *layout* gate (`body.is-phone`) may be UA-based, because it is
   cosmetic only — a phone shell vs. a desktop shell, never a data-loss
   decision. The *feature* gate (`body.no-private-data`) is the
   verified-folder probe below (feature-detect **plus** an empirical
   write/readback). **No data-loss consequence ever rides on the UA
   signal**; it rides on the probe.
3. **Be specific in the message.** "Your browser doesn't support this"
   is unactionable. "You're on Safari 15.6; this needs Safari 16.4 or
   newer; here's how to upgrade or which browser to switch to"
   converts a 0% recovery rate to something useful. The
   unsupported-browser panel exists because we hit this with a real
   user on Safari and "Could not load groups." was the message.
4. **Don't polyfill what we can't test.** OPFS doesn't have a
   reasonable polyfill path; building one would mean shipping a
   server-backed groups feature for a handful of users on browsers
   we can't soak-test. Better to tell the user clearly and route them
   to a working device.
5. **Failure should never look like a bug.** A user with no fix
   available should still understand their situation isn't broken —
   it's the limit of what their device can do.

## Required versions

Driven by what `sqlite3.wasm` needs to use OPFS — specifically
`FileSystemSyncAccessHandle`, which the wasm runtime requires for
durable writes:

| Browser  | Minimum | Released | Notes                                              |
|----------|---------|----------|----------------------------------------------------|
| Chrome   | 102     | May 2022 | First version with `FileSystemSyncAccessHandle`.   |
| Edge     | 102     | May 2022 | Same engine as Chrome.                             |
| Safari   | 16.4    | Mar 2023 | Requires iOS 16.4+ / macOS 13.3+.                  |
| Firefox  | 111     | Mar 2023 | OPFS + SAH landed together.                        |
| Opera    | —       | —        | Untested. UA branch in detect; routes user away.   |
| Samsung  | —       | —        | Untested. UA branch in detect; routes user away.   |

These floors live in `OPFS_MIN_VERSIONS` in `app/static/app.js`. If
you bump `sqlite3.wasm` and the floors shift, update both places
together.

iOS deserves a callout: every browser on iOS uses Safari's WebKit
engine, so installing Chrome/Firefox on an iPhone will not help.
The only fix on iOS is to upgrade iOS itself. iPhone 8 and newer
support iOS 16.4+; iPhone 7 and older do not. The unsupported-browser
panel says this explicitly when it detects iOS.

## Folder mode — required for private data

A verified folder on disk is **not an opt-in upgrade — it is the gate**
for all private data (groups, group members, fellow tags, fellow notes,
group-related settings, and MCP). Without it the app runs **browse-only**:
directory + search + open a fellow + email/call, and a manual `.db`
export as the portability bridge. Off-folder there is **no durable
private store** (not a degraded one) — the app does not write private
data anywhere it can't prove will survive.

Folder mode requires the **File System Access API** on top of the OPFS
floor:

| API | Floor | Browsers |
|---|---|---|
| `window.showDirectoryPicker` | Chromium-based, desktop | Chrome, Edge, Brave, Arc, Opera (desktop) |
| Persistent handle via IndexedDB | Same | Same |

### `'showDirectoryPicker' in window` is necessary but NOT sufficient

Per **M1** (capability presence ≠ usefulness ≠ permanence), having the
API does not mean a *durable* folder is reachable. A cloud-only /
online-only placeholder folder (OneDrive Files-On-Demand, Dropbox
online-only, a virtual mount) can satisfy the feature-detect yet fail
to durably store bytes. So the feature gate is **feature-detect plus an
empirical probe**: on folder pick the app writes a sentinel file and
**reads it back**; if the bytes don't match (`readback_mismatch`), the
folder is rejected and the install stays browse-only. The full staged
probe — and the stable `reason` code each stage emits — is:

| Stage | Reason on failure | Meaning |
|---|---|---|
| Picker returns a handle | `picker_cancelled` | user dismissed the picker |
| `getDirectoryHandle({create:true})` for `Fellows/` | `subfolder_create_failed` | couldn't create the data subfolder |
| Write a sentinel file | `write_failed` | read-only folder, denied permission, or disk full |
| Read the sentinel back, bytes match | `readback_mismatch` | **cloud-only / virtual folder — pick a real local folder** (the durability proof) |
| Permission persists / re-query `granted` | `permission_not_persisted` | the browser won't remember this folder |

Each reason maps to an anchor in
[`folder_troubleshooting.md`](folder_troubleshooting.md). Only when
**every** stage passes does `privateDataEnabled()` flip true and the
private store go live; any failure leaves browse-only mode with a
reasoned message and the help link.

### Off-Chromium and phones = browse-only

Safari, Firefox, all iOS browsers, and Android (Chrome's SAF-routed
picker can't keep the durable promise — `readback_mismatch`-class
failures are the norm there) cannot reach a verified folder, so they run
**browse-only**:

- **Desktop without a verified folder** (Chromium-no-folder, Safari,
  Firefox): private surfaces render **grayed out** with an **"Enable on
  Chrome desktop →"** affordance. On Chromium this opens the folder
  picker; on Safari / Firefox it routes to the help page (no API to
  invoke).
- **Phones** (Android + iOS): private surfaces are **hidden** entirely —
  there is no action the user can take to unlock on that device, so a
  grayed control would be noise. The screen is reclaimed.

Capability-detection for the *offer*: `'showDirectoryPicker' in window`
+ `!isMobileDevice()` inside the page (no separate worker probe — a
page-side gesture is required anyway). Capability-decision for the
*feature*: the verified-folder probe above.

### Migration path off-Chromium

There is no in-app unlock on Safari / Firefox / phones. The documented
path to private data is:

1. **Back up** — download your `.db` export (works everywhere).
2. **Install Chrome** (or any Chromium desktop browser).
3. **Restore** the `.db` into a new verified folder there.

This is the same shipped backup/restore machinery; the self-describing
export name (`ehf-fellows-private-data-<date>.db`) and the restore
preview's row-count delta make the right file recognizable.

The *why* behind this gate — that the File System Access gap is a
class-level architectural ceiling for web-distributed PNAs, not a
fellows quirk, and that off-folder there is **no** private store at all
(not a read-only snapshot of one) — is captured as a lesson-learned in
[`architectural_findings.md` § 2026-06-01](architectural_findings.md)
(the `CST-PWA-*` constraints). See also
[`../plans/user_folder_storage.md`](../plans/user_folder_storage.md)
§ Browser compatibility matrix and
[`../plans/private_data_capability_gate.md`](../plans/private_data_capability_gate.md)
for the gate decision.

### Pre-install recommendation (not a blocklist)

Consistent with *capability-detect, don't UA-sniff*, we do not block any
browser. The honest recommendation, surfaced before install: **for saved
groups you control as a real file (and for Claude Desktop integration),
use a Chromium desktop browser and attach a folder; on Safari / Firefox /
phones the app is browse-and-contact.** Every browser still gets the full
directory, search, and contact flows.

## Two distinct "can't do private data" states — don't conflate them

There are now two different reasons a browser shows reduced private-data
capability, and they surface differently:

- **OPFS-incapable** (older Safari < 16.4, Chrome/Edge < 102, Firefox <
  111, insecure context, missing `FileSystemSyncAccessHandle`): the
  browser can't run `relationships.db` *at all*. This is the
  **unsupported-browser panel** (`renderLocalDataUnavailablePanel`) —
  named browser, version floor, what to upgrade or switch to.
- **OPFS-capable but no verified folder** (Chromium desktop that hasn't
  picked a folder; Safari / Firefox desktop; all phones): the browser
  *can* run, but there is no durable folder backing a private store, so
  private data is gated off. This is **not** the unsupported panel — it's
  the gate state: **grayed + "Enable on Chrome desktop →"** on desktop,
  **hidden** on phones. The directory, search, and contact flows work
  fully.

The unsupported panel is about *the browser being too old to run at all*;
the gate state is about *durability not being achievable here* on a
perfectly capable browser. Different cause, different message, different
recovery.

## How a user without OPFS reaches the panel

Capability detection happens in the worker, not the main thread —
`navigator.storage.getDirectory` and `installOpfsSAHPoolVfs` run
inside `vendor/sqlite-worker.js`'s `init` op, which reports an
`opfsCapable` boolean back to the page in the init handshake. This
mirrors PRs #95–#99: several browser configurations strip
`createSyncAccessHandle` from the main-thread prototype while
exposing it inside dedicated workers, so the worker is the only
context where the answer to "can we run SAH-pool?" is reliable.

1. The user opens the app — install landing or browser-tab.
2. The page spawns the dedicated worker and posts `init`.
3. Inside `init`, the worker runs the OPFS gates. They fail (older
   browser, insecure context, missing `FileSystemSyncAccessHandle`,
   `crossOriginIsolated` false, etc.). The worker returns
   `{opfsCapable: false, reason: "<short identifier>"}`.
4. The main thread reads the handshake. For any feature that
   depends on `relationships.db` (groups, settings) — and, after
   the Phase 6 IndexedDB retirement, the directory itself — the
   render path calls
   `renderLocalDataUnavailablePanel(feature)`, which builds an
   HTML panel keyed off `detectBrowserSupport()` — browser name,
   parsed version, and an iOS flag — and renders concrete next
   steps.
5. The browser-mode "URL-just-works" path
   ([`email_gate.md` invariant 9](email_gate.md#invariants))
   still reaches the directory while the IndexedDB fallback exists
   (Phase 1–5). Once Phase 6 retires that fallback, an
   OPFS-incapable browser sees the panel for the directory too.

The transitional Phase 1–5 behavior: worker is sole owner of
`relationships.db` and (cached) `fellows.db`, but the IndexedDB
cache stays as a third-tier offline-read fallback for invariant 10.
So an OPFS-incapable browser still has a usable directory if it has
ever successfully booted before; only groups and settings show the
panel. After Phase 6, the panel covers everything.

## Adding a new local-data feature: checklist

When you add a feature backed by `relationships.db` (tags, notes UI,
saved searches, …):

- [ ] Surface it through the same `dataProvider` pattern; reuse
      `rejectIfUnsupported()` in the API provider so 404s on prod
      become `localDataUnavailableError`s.
- [ ] In every render path that calls the new method, catch the error
      and render `renderLocalDataUnavailablePanel('<feature label>')`.
- [ ] Pick a `feature` label that completes the headline naturally:
      "Can't open <label> on this browser." Good: `'tags'`,
      `'this group'`, `'saved searches'`. Bad: `'the tags feature'`.
- [ ] Add a small e2e in `tests/e2e/` that exercises the happy path
      with the OPFS provider; we don't have a clean way to e2e the
      panel itself yet, so cover the regression by smoke testing on
      Safari < 16.4 manually before each release.

## Adding a non-OPFS capability check

When a feature depends on a Web API outside OPFS (e.g. clipboard,
mailto fallback, share target):

- [ ] Capability-detect the API directly. Don't UA-sniff.
- [ ] If the API is missing, decide between three responses up front:
      (a) **degrade silently** when there's a genuinely usable
      fallback (e.g. "click to copy" instead of "share to…");
      (b) **show an inline note** when there's a workaround the user
      can take (e.g. open in Chrome);
      (c) **surface the unsupported panel** when the feature is
      blocked entirely. Default to (b) when in doubt — most "missing
      API" cases have a workaround.
- [ ] Document the floor in this table if it's a new floor we're
      committing to.

## What we deliberately don't do

- **No server-side storage of user-authored data.** Adding it for a
  handful of older-browser users would create per-user RW state on
  prod with no notion of ownership, plus a sync surface we'd have
  to maintain forever. Not worth it at this scale.
- **No browser blocklist.** Capability gates are the gate; UA strings
  inform messaging only.
- **No silent degradation for blocked features.** When groups or
  settings can't run, we tell the user — explicitly — rather than
  showing an empty/no-op UI. The audience is small enough that the
  cost of confusion outweighs the cost of a panel.
- **No polyfill investment** for OPFS, IndexedDB-as-OPFS shims, etc.
  We'd be shipping untested code to the smallest sliver of users.

## When you find a new long-tail bug

The likely sequence:

1. A user reports something doesn't work. Get their browser version,
   OS version, and one screenshot.
2. Reproduce in `chrome-devtools-mcp` against your own Chrome (see
   `docs/debugging.md`) if you can — or have them run a one-line
   probe in their console (`navigator.userAgent`,
   `'storage' in navigator && 'getDirectory' in navigator.storage`,
   `globalThis.isSecureContext`).
3. Decide which of the three outcomes above applies (degrade / note /
   panel).
4. If a panel is right and the existing one covers it, you're done —
   the user just needs to land on it.
5. If the existing panel doesn't cover the case, add a new branch in
   `renderLocalDataUnavailablePanel()` — keep messages concrete
   (named browser, version floor, what to upgrade or switch to).
6. Update this doc's table or section if the floor moved.

The cost of getting this right per case is low; the cost of a user
giving up because the message was generic is high.
