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
| **Private data folder** (stable file on disk for `relationships.db`) | yes | no[^3] | no[^3] | no | no | no |
| **Claude Desktop AI integration — easy path** | yes | no | no | N/A[^4] | N/A | N/A |
| **Claude Desktop AI integration — secondary path** | yes | yes (manual re-export per change) | yes (manual re-export per change) | N/A | N/A | N/A |
| **Per-install codename** (debugging multi-install confusion) | yes | yes | yes | yes | yes | yes |
| **Install name in window title** | yes | yes | yes | tab title only | tab title only | tab title only |

[^1]: Chromium-family browsers: Chrome, Edge, Brave, Arc, Opera, Vivaldi.
[^2]: Firefox dropped PWA install on desktop in 2021. You can use the app in a tab.
[^3]: `window.showDirectoryPicker` is Chromium-only. Without it, the app uses in-browser OPFS storage with the manual backup / restore path for durability.
[^4]: Claude Desktop is macOS / Windows / Linux only. Mobile platforms can't host MCP servers.

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

## See also

- [User Guide](users_manual.md) — full reference + troubleshooting.
- [Use with Claude Desktop](use_with_claude_desktop.md) — AI integration walkthrough.
- [Never-SaaS](never-saas.md) — why the app is architected this way; the platform caveats above are a consequence.
