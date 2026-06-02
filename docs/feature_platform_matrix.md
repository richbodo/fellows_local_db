# Feature ↔ platform matrix

What works where. The app is browser-based, so capability varies by
browser, OS, and (for AI integration) whether you have Claude Desktop
installed. **Recommended platform: Chrome (or any Chromium browser)
on macOS desktop, with a verified data folder attached and Claude
Desktop for AI integration.**

## TL;DR

| | Best on | Works on | Limited / no |
|---|---|---|---|
| **Browse the directory + search + open a fellow + email / call** | Anything | Every desktop + mobile browser | — |
| **Private data** (groups, members, tags, notes, group settings, MCP) | Chromium desktop **with a verified folder attached** | — | Chromium desktop *without* a folder, Safari, Firefox (grayed + "Enable on Chrome desktop"); all mobile (hidden) |
| **Claude Desktop AI integration** | Chrome on macOS, folder attached | Other Chromium desktop, folder attached | Safari / Firefox / no-folder (N/A — no private store to read); mobile (N/A) |

Private data is **available only when a verified folder is attached** —
a real file on disk the app has proven it can write and read back (see
the *verified folder* footnote[^6]). Until then, every install runs in
**browse-only mode**: browse the directory, search, open a fellow,
email or call them. Nothing private. The unlock happens at any time on
a Chromium desktop browser. See *[Multiple installs on the same
device](users_manual.md#multiple-installs-on-the-same-device)*.

## Detailed matrix

| Feature | Chromium desktop[^1] + verified folder | Chromium desktop, no folder | Safari (macOS) | Firefox (desktop) | iOS Safari | Android Chromium | Android Firefox |
|---|---|---|---|---|---|---|---|
| **Install as app** | yes | yes | yes (Add to Dock, macOS 14+) | no[^2] | yes (Add to Home Screen) | yes | no[^2] |
| **Browse directory + search** | yes | yes | yes | yes | yes | yes | yes |
| **Open a fellow + email / call** | yes | yes | yes | yes | yes | yes | yes |
| **Private data** (groups, group members, fellow tags, fellow notes, group settings, MCP) — gated on a *verified folder attached*[^3] | **full** | grayed + "Enable on Chrome desktop →"[^7] | grayed + "Enable on Chrome desktop →"[^7] | grayed + "Enable on Chrome desktop →"[^7] | hidden[^5] | hidden[^5] | hidden[^5] |
| **Manual `.db` export** (portability bridge) | yes | yes | yes | yes | yes (share sheet) | yes | yes |
| **Per-install codename** (debugging multi-install confusion) | yes | yes | yes | yes | yes | yes | yes |
| **Install name in window title** | yes | yes | yes | yes | tab title only | tab title only | tab title only |

[^1]: Chromium-family browsers: Chrome, Edge, Brave, Arc, Opera, Vivaldi.
[^2]: Firefox dropped PWA install on desktop in 2021. You can use the app in a tab.
[^3]: The File System Access API (`window.showDirectoryPicker`) is Chromium-desktop-only — but having the API is **necessary, not sufficient**. Off-folder there is **no durable private store** (not a degraded one): the app does not write groups/tags/notes anywhere it can't guarantee survival, so without a verified folder it runs **browse-only**. The manual `.db` export is the portability bridge between installs, not a live store. See [`browser_support.md` § Folder mode — required for private data](browser_support.md#folder-mode--required-for-private-data) and [`architectural_findings.md` § 2026-06-01](architectural_findings.md) (`CST-PWA-PRIVATE-SNAPSHOT`).
[^5]: **Hidden on phones, not an API gap on its own.** Android Chrome *does* expose `showDirectoryPicker`, but it routes through the Storage Access Framework, which forces the file into a Downloads subfolder the OS can clear at will — so the folder can't keep the *durable* promise, and `readback_mismatch`-class failures are the norm. iOS has no picker at all. On a phone there is no action the user can take to unlock private data on that device, so the controls are **hidden** (not grayed) and the screen is reclaimed. See *[The mobile contract](#the-mobile-contract)*.
[^6]: **"Verified folder"** means all five of: the user **picked** a parent folder; the app **created** (or adopted) a `Fellows/` subfolder; the app **wrote** a sentinel file; it **read that sentinel back and the bytes matched**; and the browser **persisted the permission** so it survives a restart. Only when every stage passes does `privateDataEnabled()` flip true and the private store go live. Any failure leaves the install in browse-only mode with a reasoned message; see [`folder_troubleshooting.md`](folder_troubleshooting.md).
[^7]: On a Chromium desktop browser the unlock affordance is live — tap a grayed control or **Settings → Private data → pick a folder**. On Safari / Firefox desktop (no File System Access API) the same control routes to [`folder_troubleshooting.md` § which browsers support this](folder_troubleshooting.md#which-browsers-support-this) — the documented migration path is *back up your `.db` → install Chrome → restore into a new folder*.

## Browse-only mode vs. full

The Claude Desktop integration needs a **live, durable file at a known
path** on your disk for the *Your saved groups (Private)* MCP extension
to read. That file only exists in **full mode** (Chromium desktop, a
verified folder attached): the folder's `relationships.db` *is* that
file, auto-saved on every change, so the MCP server and Claude see the
latest immediately.

In **browse-only mode** there is **no live private store at all** —
groups/tags/notes are not written to any durable location, so there is
nothing for an MCP server to read. There is no "secondary path" that
re-exports `relationships.db` by hand for Claude on Safari / Firefox:
off-folder there is no private store to export from. The path to AI
integration on those browsers is the migration path — back up, install
Chrome, restore into a folder — not a parallel manual-export workflow.

## What "Multiple installs" caveats apply

Browsers don't share storage, and only one verified folder backs one
install's private data at a time. If you install the app in two
browsers on the same device, you get two independent installs;
only the Chromium one with a folder holds live private data.
Recommended: **install in one Chromium desktop browser, attach one
folder, and stay there**. If you've already done multiple installs, see
*[Migrating from another browser](users_manual.md#migrating-from-another-browser)*.

## The mobile contract

Phones and tablets can't provide a **verified, durable folder** — a real
file on disk we have proven we can write and read back at a known path.
Several features are built on exactly that. So the mobile experience is
deliberately narrower than desktop, and the line is architectural, not a
"not yet":

**What mobile does** — browse the directory, search, open a fellow, email
or call them, and **download a manual `.db` export** of any data you
brought across. That's the whole contract.

**What mobile can't do, and why:**

- **Private data (groups, members, tags, notes, group settings)** —
  there is no verified-folder path on mobile (Android's picker only
  reaches an OS-clearable Downloads subfolder; iOS has no picker), so
  there is no durable private store. Rather than show a control the user
  cannot act on, the private surfaces are **hidden** and the screen is
  reclaimed. (Footnote 5 above.)
- **Claude Desktop / MCP integration** — Claude Desktop is desktop-only,
  phones can't host an MCP server, and there is no private store to read
  anyway. (Browse-only has no live private data.)
- **Anything that assumes external tools can read your data file** —
  command-line `sqlite3`, a sync agent (Dropbox / iCloud / Syncthing)
  replicating the folder, multi-client reads. All need a durable local
  file — i.e. full mode on a Chromium desktop.

A note on durability: browser storage (OPFS) can be evicted (iOS notably
reclaims it after long periods of non-use, and Android's *Clear Storage*
wipes it). The app **avoids** relying on it for private data entirely —
in browse-only mode nothing private is stored in evictable browser
storage in the first place. The manual `.db` export is the only durable
artifact in browse-only mode, which is why the *Download my private data*
control stays available on every browser even where private data is
hidden or grayed.

## See also

- [User Guide](users_manual.md) — full reference + troubleshooting.
- [Folder troubleshooting](folder_troubleshooting.md) — what each unlock-probe failure means and what to do.
- [Use with Claude Desktop](use_with_claude_desktop.md) — AI integration walkthrough (full mode only).
- [Browser support](browser_support.md) — the verified-folder gate and capability detection.
- [Architectural findings § 2026-06-01](architectural_findings.md) — *why* private data requires a verified folder (the `CST-PWA-*` constraints); the platform caveats above are a consequence.
- [Never-SaaS](never-saas.md) — why the app is architected this way.
