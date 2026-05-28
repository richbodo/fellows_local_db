# Use with Claude Desktop

This is an optional add-on to the EHF Fellows Directory app. Once set
up, you can ask **Claude Desktop** questions about the directory and
your saved groups, and have it draft outreach emails for you to
review and send.

Example things you can ask:

- *"How many fellows are based in Aotearoa?"*
- *"Find the fellow who runs that climate finance fund — I forget the
  name."*
- *"List my saved groups."*
- *"Who's in my Climate Action group?"*
- *"Draft an email to my Climate Action group inviting them to meet
  Thursday at 1pm NZ time — don't send, just stage it for me to
  review."*

Claude reads your **local** copy of the directory to answer. For the
email demo, it hands the draft back to you as a pre-filled compose
window in your mail app — you always click Send.

This is optional. The Fellows app works perfectly well without it.

---

## Before you start

You should already have:

- The **Fellows Directory app** installed and working (you've used it,
  you have groups saved).
- **Claude Desktop** installed.
- A **private data folder set up** in the Fellows app (Settings →
  Private data folder → Choose folder…). See *[Where your data is stored](users_manual.md#where-your-data-is-stored)*.
- About **5 minutes**.

### Best with: Chrome, Edge, Brave, Arc on macOS

The easy install path works on Chromium-family browsers (Chrome,
Edge, Brave, Arc) running on macOS Sonoma 14 or newer. This is the
combination that supports the data-folder feature the integration
depends on.

**Safari and Firefox:** If you are not very technical, it is unlikely that you will be able to interface with claude desktop using these other browsers.  If you must get this going, please download and use Chrome, Edge, Brave, or Arc for this app.  If you still want to try - there's a [secondary path](#secondary-path-safari-firefox-and-other-browsers)
below. It works but needs a few extra steps.

**Already installed the Fellows app in two browsers on the same Mac?**
Each browser has its own data store; see *[Multiple installs on the
same device](users_manual.md#multiple-installs-on-the-same-device)*
to consolidate before you set up Claude Desktop integration.

---

## The 3-step easy path

The Fellows app downloads three small extensions for Claude Desktop;
Claude Desktop installs them with two clicks each. Total active time
~3 minutes.

### Step 1 — Open Settings → "Set up Claude Desktop integration"

In the Fellows app:

1. Click **Settings** (gear icon, or `#/settings`).
2. Scroll to **Claude Desktop integration (beta)**.
3. Click **Set up Claude Desktop integration**.

A dialog opens explaining what the three extensions do and previews
the warning banner Claude Desktop will show during install (see
*[About that red warning banner](#about-that-red-warning-banner)*
below).

### Step 2 — Read the preamble, click Continue

The dialog covers three extensions:

- **Fellows directory (Shared)** — Claude reads the public fellows
  directory (names, bios, contact info).
- **Your saved groups (Private)** — Claude reads your saved groups
  and notes. *Privacy note*: this data is private to you and never
  leaves your device through the Fellows app — but when Claude reads
  it, it goes to Claude's servers. If that's not OK for you, skip
  this extension and Claude will only have access to the directory.
- **Email staging (Communications)** — Claude prepares draft emails
  and hands them back to your mail app. Claude never sends mail
  itself.

When you click **Continue**, three `.mcpb` installer files download
into your Downloads folder:

- `shared_data_ops.mcpb`
- `private_data_ops.mcpb`
- `comms.mcpb`

### Step 3 — Open each .mcpb, approve in Claude Desktop, restart

For each of the three files:

1. **Open the file** (Finder → double-click, or `Downloads → open`).
   Claude Desktop pops up an Install dialog.
2. **For `private_data_ops.mcpb` only**: the install dialog asks you
   to pick a file. Navigate to your **data folder → Fellows →
   `relationships.db`** and select it. (This is the file the
   extension reads to find your saved groups; the data folder you
   set up in *Before you start* is where it lives.)
3. **Click Install**. Approve the red warning banner — see below.

When all three are done:

4. **Quit Claude Desktop** (⌘Q) and reopen it. (This is the only
   reliable way to get it to load freshly-installed extensions.)
5. Open a new chat and ask: *"How many fellows are in the
   directory?"*

If you get a count back, you're set up.

---

## About that red warning banner

When you click **Install** in Claude Desktop, you'll see a red banner
that says:

> "Installing will grant this extension access to everything on your
> computer. Any developer information shown has not been verified by
> Anthropic."

That banner fires for **any extension that isn't Anthropic-verified**
— it's not specific to ours and doesn't mean anything is wrong with
the Fellows integration. The extensions only read the data files
they were configured with; they don't have wider access than you
grant them in the install dialog.

Click **Install** to proceed past the banner. This is tracked
upstream as [issue #186](https://github.com/richbodo/fellows_local_db/issues/186)
— we'd prefer a less alarming UX but it's Claude Desktop's
load-bearing trust check, so it stays until Anthropic ships
verification for community extensions.

---

## Refreshing your data

You don't need to redo this setup for normal updates. Three
scenarios:

### You changed your saved groups

Nothing to do. The **Your saved groups** extension reads
`relationships.db` directly from your data folder. The Fellows app
auto-saves to that folder whenever you change a group, so Claude
sees your latest groups on its next read.

### The Fellows directory has new fellows

The Fellows app surfaces a *"Directory data update available"*
status in the About page. When you click *Update directory data*,
the app downloads a new `fellows.db`. **You'll also need to
re-install the `shared_data_ops` extension** so Claude sees the new
snapshot.

Settings → Claude Desktop integration (beta) shows a banner when
this is needed:

> **Directory data update available.** A newer snapshot of the
> public fellows directory is on the server. Re-install the Fellows
> directory extension to pick it up.

Click **Re-install Fellows directory** to download just
`shared_data_ops.mcpb`. Open the file when it downloads to re-install
in Claude Desktop, then restart Claude Desktop.

### You want to fully re-download everything

Click **Re-download all extensions** in Settings → Claude Desktop
integration (beta). Repeats Steps 2-3 above.

---

## Secondary path (Safari, Firefox, and other browsers)

Safari and Firefox don't support the data-folder feature
(`window.showDirectoryPicker`) the easy path depends on, so the file
picker in Claude Desktop's `private_data_ops` install dialog has no
stable location to land on. You can still set it up; you just need
to manage the `relationships.db` file by hand.

### Once-only setup

1. In the Fellows app: **Settings → Private data folder → ⬇ Download
   my private data**. Save the file somewhere stable on your disk —
   `~/Documents/` works well. Note the file's location.
2. Visit each of these URLs in turn while signed in to the Fellows
   app (the magic-link gate must already be open in this browser):
   - <https://fellows.globaldonut.com/mcpb/shared_data_ops.mcpb>
   - <https://fellows.globaldonut.com/mcpb/private_data_ops.mcpb>
   - <https://fellows.globaldonut.com/mcpb/comms.mcpb>

   Each one downloads as an `.mcpb` file.
3. Follow **Step 3** of the easy path above (open each, approve,
   restart Claude Desktop). For `private_data_ops.mcpb`'s file
   picker, navigate to wherever you saved `relationships.db` in
   step 1.

### Re-export discipline

**Every time you change a group**, you need to redo step 1 (download
your user data, save it over the previous `relationships.db`).
Otherwise Claude sees the version that was current at install time.

The Chromium easy path doesn't have this problem because the data
folder *is* `relationships.db` — auto-save handles it. If you find
yourself doing this re-export more than once or twice a week, the
honest answer is: try the Fellows app in Chrome instead. See
*[Migrating from another browser](users_manual.md#migrating-from-another-browser)*
for how to bring your data along.

---

## Troubleshooting

### Claude Desktop doesn't see my groups

Most likely cause: `private_data_ops.mcpb` was pointed at the wrong
`relationships.db` during install (or you're on the secondary path
and your exported file is stale).

1. In Claude Desktop: **Settings → Extensions**. Find *Your saved
   groups* (or `private_data_ops`).
2. Confirm the **Configuration** field points at the
   `relationships.db` from your current data folder (Chromium) or
   your latest export (Safari/Firefox).
3. If wrong, uninstall and re-run the appropriate setup step.

### "Extension failed to start"

Usually means Claude Desktop's bundled Node runtime had trouble
loading the extension. Quit Claude Desktop fully (⌘Q, then check
Activity Monitor for stray processes), reopen, and try again. If
that doesn't help, file a bug report from the Fellows app
(Settings → Report a bug…); the diagnostics include your
[install name](users_manual.md#install-name) so the maintainer can
correlate.

### I'm not sure which install of the Fellows app I'm using

Check the **About** page — it shows the install name
(`giraffe-gorilla-mouse` or similar). See *[Install name](users_manual.md#install-name)*.

### Other issues

The integration is in beta — if something doesn't work and isn't
covered above, file a [GitHub issue](https://github.com/richbodo/fellows_local_db/issues)
or use the in-app **Report a bug** button.

---

## What gets installed where

For the curious (or for cleanup):

- The three `.mcpb` files unpack into Claude Desktop's internal
  extensions directory. **Settings → Extensions** in Claude Desktop
  lists them with **Uninstall** buttons.
- `relationships.db` lives in **your data folder** (Chromium easy
  path) or wherever you saved it (Safari/Firefox secondary path).
  Uninstalling Claude Desktop doesn't touch this file — it's yours.
- `fellows.db` ships **inside** `shared_data_ops.mcpb` (~3 MB).
  Uninstalling that extension removes it.
- No environment variables, no Terminal commands, no
  hand-edited config files. The `claude_desktop_config.json` flow
  the previous version of this doc used is gone.

---

## Removing the integration

**Settings → Extensions** in Claude Desktop → click **Uninstall** on
each of the three extensions. That fully removes them. Your data
folder is untouched.
