# Browser Support

How we triage long-tail browser-compatibility issues for this app. The
audience is small (~hundreds of fellows) and the distribution model is
"by emailed magic link, install once" — but each one of those users
runs a different browser/OS combo, and we will keep meeting people
whose device falls outside what we tested. This doc captures the
policy so we react consistently when that happens.

## Stance

1. **Local-first.** User-authored data (groups, per-fellow notes,
   per-fellow tags, settings) lives in the browser's OPFS-backed
   `relationships.db`, not on a server. That gives us per-device
   privacy and offline-by-default — at the cost of needing a browser
   that supports OPFS + `FileSystemSyncAccessHandle`.
2. **Capability-detect, don't UA-sniff for gating.** We test the
   capability (`navigator.storage.getDirectory`,
   `globalThis.sqlite3InitModule`, `globalThis.isSecureContext`).
   UA strings are used **only** to render a more helpful unsupported
   message — never to allow/deny features.
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

## How a user without OPFS reaches the panel

1. They open the app — install landing or browser-tab.
2. `pickDataProvider()` runs the OPFS gates. They fail (older browser,
   insecure context, etc.).
3. Provider falls back to the API provider.
4. On dev, the API provider serves `/api/groups` and `/api/settings`,
   so groups/settings work for the dev round-trip.
5. **On prod** (`deploy/server.py`), those routes don't exist. The
   first call (typically `listGroups`) gets a 404, the API provider
   marks the route unsupported, and every subsequent groups/settings
   call rejects with `localDataUnavailableError`.
6. The render path catches the error and calls
   `renderLocalDataUnavailablePanel(feature)`, which builds an
   HTML panel keyed off `detectBrowserSupport()` — browser name,
   parsed version, and an iOS flag — and renders concrete next
   steps.

The directory itself, search, and fellow profiles still work. Only
the local-data features (groups, settings) show the panel.

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
