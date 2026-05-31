# Feature ↔ platform matrix

What works where. The app is browser-based, so capability varies by
browser, OS, and (for AI integration) whether you have Claude Desktop
installed. **Recommended platform: Chrome (or any Chromium browser)
on macOS desktop, with Claude Desktop for AI integration.**

## TL;DR

| | Best on | Works on | Limited / no |
|---|---|---|---|
| **Browse the directory + save groups** | Anything | Every desktop + mobile browser | — |
| **Private data folder** (stable file on disk) | Chromium desktop | — | Safari, Firefox, all mobile |
| **Claude Desktop AI integration** | Chrome on macOS | Other Chromium desktop | Safari/Firefox (secondary path); mobile (N/A) |

If you're going to create groups and want a smooth experience, **install in one browser only**. See *[Multiple installs on the same device](users_manual.md#multiple-installs-on-the-same-device)*.

## Detailed matrix

| Feature | Chromium desktop[^1] | Safari (macOS) | Firefox (desktop) | iOS Safari | Android Chromium | Android Firefox |
|---|---|---|---|---|---|---|
| **Install as app** | yes | yes (Add to Dock, macOS 14+) | no[^2] | yes (Add to Home Screen) | yes | no[^2] |
| **Browse directory + search** | yes | yes | yes | yes | yes | yes |
| **Save groups, tags, notes** | yes | yes | yes | yes | yes | yes |
| **Manual backup download** | yes | yes | yes | yes (share sheet) | yes | yes |
| **Auto-backups** (in browser storage) | yes | yes | yes | yes | yes | yes |
| **Private data folder** (stable file on disk for `relationships.db`) | yes | no[^3] | no[^3] | no | no[^5] | no[^5] |
| **Claude Desktop AI integration — easy path** | yes | no | no | N/A[^4] | N/A | N/A |
| **Claude Desktop AI integration — secondary path** | yes | yes (manual re-export per change) | yes (manual re-export per change) | N/A | N/A | N/A |
| **Per-install codename** (debugging multi-install confusion) | yes | yes | yes | yes | yes | yes |
| **Install name in window title** | yes | yes | yes | tab title only | tab title only | tab title only |

[^1]: Chromium-family browsers: Chrome, Edge, Brave, Arc, Opera, Vivaldi.
[^2]: Firefox dropped PWA install on desktop in 2021. You can use the app in a tab.
[^3]: `window.showDirectoryPicker` is Chromium-only. Without it, the app uses in-browser OPFS storage with the manual backup / restore path for durability.
[^4]: Claude Desktop is macOS / Windows / Linux only. Mobile platforms can't host MCP servers.
[^5]: **Intentionally gated off on mobile, not an API gap.** Android Chrome *does* expose `showDirectoryPicker`, but it routes through the Storage Access Framework, which forces the file into a Downloads subfolder the OS can clear at will — so the folder can't keep the feature's core promise of *durable* storage, and offering the choice is misleading. On mobile (both Android and iOS) the app is OPFS-only; durability comes from the manual backup download. See *[The mobile contract](#the-mobile-contract)*.

## What "easy path" vs "secondary path" means

The Claude Desktop integration needs a stable file at a known path on
your disk for the *Your saved groups (Private)* extension to read.
- **Easy path** (Chromium desktop): the app's data folder *is* that
  stable file. Auto-saved on every change. Set up once, edit groups
  whenever — Claude sees the latest immediately.
- **Secondary path** (Safari / Firefox): no `showDirectoryPicker`,
  so you manage `relationships.db` by hand. Re-export every time
  you change a group, otherwise Claude sees the version current at
  install time. See *[Use with Claude Desktop](use_with_claude_desktop.md#secondary-path-safari-firefox-and-other-browsers)*.

## What "Multiple installs" caveats apply

Browsers don't share storage. If you install the app in two
browsers on the same device, you get two independent data stores.
Recommended: **install in one browser only**. If you've already
done multiple installs, see *[Migrating from another browser](users_manual.md#migrating-from-another-browser)*.

## The mobile contract

Phones and tablets can't provide a **stable, externally-readable file at a
known path** — and several features are built on exactly that. So the mobile
experience is deliberately narrower than desktop, and the line is
architectural, not a "not yet":

**What mobile does** — browse the directory, search, save groups / tags /
notes, and **download a manual backup** of your data. That's the whole
contract. Your `relationships.db` lives in the browser's private storage
(OPFS); durability comes from exporting a backup file you store yourself.

**What mobile can't do, and why:**

- **Durable data folder** — Android's picker only reaches a Downloads
  subfolder the OS can clear; iOS has no picker. A folder we can't trust to
  persist would be worse than honest browser-only storage, because the
  "saved to disk" badge would imply a safety that isn't there. Gated off on
  both. (Footnote 5 above.)
- **Claude Desktop / MCP integration** — Claude Desktop is desktop-only and
  phones can't host an MCP server. (Footnote 4.)
- **Anything that assumes external tools can read your data file** —
  command-line `sqlite3`, a sync agent (Dropbox / iCloud / Syncthing)
  replicating the folder, multi-client reads. All need a durable local file
  mobile doesn't have.

A note on OPFS durability on mobile: browser storage can be evicted (iOS
notably reclaims it after long periods of non-use, and Android's *Clear
Storage* wipes it). **The manual backup is the floor** — encourage it, and it
must keep working. That's why the *Download my private data* button stays
available on every mobile browser even though the data-folder feature is
hidden.

## See also

- [User Guide](users_manual.md) — full reference + troubleshooting.
- [Use with Claude Desktop](use_with_claude_desktop.md) — AI integration walkthrough.
- [Never-SaaS](never-saas.md) — why the app is architected this way; the platform caveats above are a consequence.
