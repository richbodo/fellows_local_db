# EHF Fellows Directory — User Guide

A fast local-only directory for EHF fellows.

It's a private, installable web app. Once installed it runs entirely on your
device — fellow data lives in your browser's local storage, so it works
offline. You can group fellows, email a whole group in one click, and
export sub-directories.

The app is distributed only by emailed magic link. Keep the data and any
screenshots inside the fellowship.

---

## Recommended platform

**Chrome (or any Chromium browser) on desktop, with a data folder
attached, plus Claude Desktop for AI integration.** That combination
gets every feature — your private data (saved groups, tags, notes) as a
real file on your disk, MCP integration, the works.

**Saved groups need a folder.** Private data is only available once you
attach a folder the app can verify it can write to — on a Chromium
desktop browser. Everywhere else (Safari, Firefox, phones), and on
Chrome before you've picked a folder, the app runs in **browse-only
mode**: browse the directory, search, open a fellow, and email or call
them. You can turn private data on at any time on Chromium desktop (see
*[Turning on saved groups](#turning-on-saved-groups-private-data)*).
Check the [feature ↔ platform matrix](feature_platform_matrix.md) for the
full breakdown.

Also: **install in one Chromium desktop browser per device and attach one
folder** — browsers don't share storage, so two installs = two separate
sets of groups that can't auto-sync.

---

## Installing the app

You'll get a magic link in email. Click it.

1. On the install landing, click **Install app**.
2. Confirm your browser's prompt:
   - **Desktop Chrome / Edge / Brave** — small prompt near the address bar; the
     app opens in its own window.
   - **Android Chrome** — *Add to Home screen*; appears in your launcher.
   - **iOS Safari** — *Share → Add to Home Screen*. (iOS has no one-click
     prompt.)
   - **macOS Safari** — *File → Add to Dock…* (macOS Sonoma 14 or newer).
     Safari doesn't show an in-page install button; the install path is in
     the menu bar.
3. Open the app from its icon. First launch downloads fellow data in the
   background.

Because this app isn't OS-registered, your OS may warn you. Look for
**More info / Details / down-arrow** to install anyway. Ask for help if
stuck.

If **Install app** does nothing, the landing page shows a hint:

- Already installed? Open it from your dock / Applications / home screen.
- Otherwise, click **Use the directory in this tab** — you get the same
  app inside the current tab. Come back later for the install button.

---

## Can't find the app after installing?

Almost always: it installed fine, your OS just put it somewhere unexpected.
**Spotlight** on macOS, **Start menu** on Windows, or your **app launcher**
on Linux is the most reliable way to find it — search for "EHF" and it'll
surface.

The specific gotcha worth knowing: on **macOS with Chrome or Edge**, the app
installs to `~/Applications/Chrome Apps/` — *not* the main Applications
folder. That's a Chromium quirk, not a bug; installing into `/Applications`
would need admin rights. Spotlight (`⌘-Space → "EHF"`) finds it; you can
also drag the icon from `~/Applications/Chrome Apps/` onto your Dock to
keep it one click away.

If Spotlight / Start menu / launcher all come up empty, it probably didn't
install — try *Can't install at all?* below. If that doesn't help either,
file a [GitHub issue](https://github.com/richbodo/fellows_local_db/issues)
(ask Rich for repo access if you don't have it).

And remember: `https://fellows.globaldonut.com` always works in a browser
tab. Once you've installed, the URL skips the install landing and opens
the directory directly — no icon-hunting required.

See *Where the installed app lives* for the full per-platform breakdown.

---

## Can't install at all?

Likely a device-side quirk. Two third-party tools that triage before you
ask for help:

- **[PWAHero](https://pwahero.com/)** — paste the URL; walks you through
  install steps for your specific browser/OS.
- **[Progressier's PWA diagnostic](https://progressier.com/pwa-testing-tool)**
  — green/red checklist of what's missing.

Both are free and don't require sign-in. Send the report to the EHF
Communications Working Group along with what you tried, or file a
[GitHub issue](https://github.com/richbodo/fellows_local_db/issues)
(ask Rich for repo access first if you don't have it).

---

## Where the installed app lives

Launch it like any other app — no browser needed.

| OS | Where the icon shows up |
|---|---|
| **macOS** | Applications folder, Spotlight (`⌘-Space → "EHF"`), `chrome://apps` |
| **Windows** | Start menu → "EHF Fellows Directory"; Edge can pin to taskbar |
| **Linux** | Application launcher (GNOME / KDE), `~/.local/share/applications/` |
| **Android** | Home screen + app drawer |
| **iOS** | Home screen (no app drawer) |

`https://fellows.globaldonut.com` also works in any browser tab; once
you've installed once, the URL skips the install landing and opens the
directory.

---

## Multiple installs on the same device

Each browser installs the app as its own copy with its own private
data. If you install in **Safari**, then later in **Chrome**, your
Mac has *two* "EHF Fellows Directory" apps — same name, same icon,
different homes on disk, different data.

This is intentional browser isolation, not a bug: there's no API
that lets a PWA reach across browser sandboxes. But it can be
confusing if you weren't expecting it.

### What you'll see

- **Spotlight (`⌘-Space → "EHF"`)** shows two (or more) results,
  all identical-looking.
- **Each install has its own data.** Groups, notes, and tags you
  created in Safari aren't visible to the Chrome copy and vice
  versa.
- **The window title** (and the **About** page) shows a unique
  *install name* per copy — something like `giraffe-gorilla-mouse`.
  That's the easiest way to tell which one you opened.

### Tell installs apart in Finder

Each browser puts the `.app` bundle in a different folder, so you
can rename them visibly:

- **Safari** → `~/Applications/EHF Fellows Directory.app`
- **Chrome / Brave / Edge** → `~/Applications/Chrome Apps/EHF Fellows Directory.app`
- **Arc** → managed by Arc, accessed through Arc's sidebar

Right-click each bundle in Finder → **Rename** → give them
distinctive labels like `EHF Fellows — Safari.app` and
`EHF Fellows — Chrome.app`. The renamed labels surface in Spotlight
on subsequent searches.

### Consolidate to one install

If you've accumulated copies and want to keep just one:

1. Open each copy in turn. The **About** page shows its install
   name (and so does the window title).
2. Identify the copy with the data you want to keep (groups
   visible, notes intact).
3. From the copy you're keeping, **Settings → Private data →
   Choose folder…**, and pick a folder under your home
   directory. This creates a stable file you can later re-attach
   from any new install. (Folder mode also makes
   [Use with Claude Desktop](use_with_claude_desktop.md) easier.)
4. Uninstall the other copies (steps below).

### Uninstall a copy

Each browser uninstalls its own PWA differently. Below is the short
form; if a step is out of date for your browser version, check the
browser's official help — that's always the canonical reference:

- **Safari (macOS)** — drag `~/Applications/EHF Fellows Directory.app`
  to the Trash. →
  [Apple's Web Apps doc](https://support.apple.com/guide/safari/manage-web-apps-pdsuc1d62cd4/mac)
- **Chrome** — visit `chrome://apps`, right-click the app, **Remove
  from Chrome…**. →
  [Google's PWA management doc](https://support.google.com/chrome/answer/9658361)
- **Edge** — visit `edge://apps`, click **⋯** on the app,
  **Uninstall**.
- **Brave** — same as Chrome but at `brave://apps`.
- **Arc** — right-click in Arc's sidebar, **Delete**.
- **Firefox** — no PWA install on desktop; close the tab and remove
  the bookmark.

**Important:** uninstalling a copy does **not** delete a private data folder
you set up. The folder lives on your disk and stays put. To remove
the data too, separately drag the `Fellows/` subfolder you picked
to the Trash. (Auto-backups inside it go with it.)

If you've uninstalled what you thought was the last copy and now
the app appears to be gone, see *Where the installed app lives*
above — Spotlight may surface a copy you forgot about, and the
`https://fellows.globaldonut.com` URL always opens fresh in a
browser tab.

---

## Migrating from another browser

If you've been using the app in one browser (say, Safari) and want
to switch to another (Chrome, for the Claude Desktop integration —
see *[Use with Claude Desktop](use_with_claude_desktop.md)*), your
saved groups and notes don't follow automatically. Browsers don't
share storage; each install starts empty.

Bringing your data across is a two-step copy:

### Step 1 — Export from the source browser

1. Open the app **in the browser where your data currently lives**
   (Safari, in this example).
2. **Settings → Private data → ⬇ Download my private data**. The file
   is named so you can recognize it later —
   `ehf-fellows-private-data-<date>.db`. Save it somewhere stable on your
   disk — `~/Documents/` works well, or anywhere you can find again.
   **Don't put it in Downloads** if you regularly empty that folder.

### Step 2 — Import into the new browser

1. Open the app **in the new browser** (Chrome, in this example). If
   you haven't installed there yet, do that first. Chrome (or any
   Chromium desktop browser) is required — it's the only place private
   data can be turned on.
2. **Settings → Private data → Choose folder…**. Pick a real local folder
   under your home directory and let the app verify it (see *[Turning on
   saved groups](#turning-on-saved-groups-private-data)*). This is what
   makes private data work at all in the new browser, keeps your
   `relationships.db` at a stable path on disk, makes the Claude Desktop
   integration possible, and survives clearing site data.
3. **Settings → ⬆ Restore from a file…**, then pick the
   `ehf-fellows-private-data-<date>.db` you saved in Step 1.

That's it. Your groups, notes, and tags are now visible in the new
browser. The source browser still has its copy — you can keep both
in sync by re-exporting / re-importing, but it's usually simpler to
[uninstall the source copy](#uninstall-a-copy) once you're confident
the new one is working.

**Finding the right file later.** Inside your data folder the app leaves
a plain-text `HOW-TO-MOVE-THIS-DATA.txt` marker explaining that the folder
is your EHF private data and that copying the whole folder (or the
`relationships.db` inside it) is how you move it between computers. The
self-describing export name and the restore preview's row-count summary
("4 groups, 12 notes → 7 groups, 23 notes") help you recognize the right
file in a pile of downloads.

**A note for the future.** Doing this two-step migration regularly
is a sign you should pick one browser and stay there. PWAs don't
have a cross-browser sync API, so there's no automatic way to keep
two installs aligned. Pick whichever browser you prefer and treat
the other as a backup.

---

## Where your data is stored

Your groups, notes, tags, and settings — your **private data** — live
**on your device only**, never sent to any server, never visible to other
apps or websites. And they live in **a real folder on your disk that you
pick**: a file visible in Finder/Explorer, durable across clearing site
data or switching browsers.

**Private data requires that folder.** This isn't an optional upgrade —
it's the gate. Until you attach a folder the app has verified it can write
to (and read back from), the app runs in **browse-only mode**: you can
browse the directory, search, open a fellow, and email or call them, but
there are no saved groups, tags, or notes. There is no hidden,
losable copy in browser storage — off-folder, the app simply doesn't
store private data, so there's nothing to lose.

You turn private data on by attaching a folder, on a **Chromium desktop
browser** (Chrome, Edge, Brave, Arc, Opera). See *[Turning on saved
groups](#turning-on-saved-groups-private-data)* below.

**On Safari, Firefox, and phones, browse-only is the only mode.** Safari
and Firefox don't have the folder API; Android's folder picker can only
reach a Downloads subfolder the system clears at will, and iOS has no
picker at all — so a verified, durable folder isn't reachable there. On
**desktop Safari / Firefox** the private controls appear **grayed out**
with an **"Enable on Chrome desktop"** link; on **phones and tablets**
they're **hidden** entirely (there's no action you could take on the phone
to turn them on). To get private data on those devices, migrate to Chrome
— see *[Migrating from another browser](#migrating-from-another-browser)*.

### Turning on saved groups (private data)

On a **Chromium desktop browser** (Chrome / Edge / Brave / Arc / Opera),
turning on private data is one short flow:

1. **Start the unlock.** Either **tap any grayed-out private control**
   (for example **Create group**) or go to **Settings → Private data →
   Choose folder…**. The app explains that saved groups live in a folder
   on your computer.
2. **Pick a folder.** Your OS pops a folder picker. Pick a real, local
   folder you own — your **Documents** folder is the safe default. (You
   *can* pick a sync folder like Dropbox / iCloud / OneDrive, but only if
   it's set to keep files on this device — see the readback note below.)
3. **The app verifies it.** Before turning anything on, the app creates a
   `Fellows/` subfolder, writes a small test file, **reads it back to
   confirm it matches**, and checks the browser will remember the folder.
   Only if every step passes do your saved groups light up.
4. **Done.** The badge flips to **Saved** with the path and a timestamp,
   the private controls become active, and from now on **every change is
   automatically saved to the folder** — no Save button.

**If verification fails**, the app stays in browse-only mode and shows a
short reason — most often that you picked a **cloud-only / online-only
folder** (OneDrive Files-On-Demand, Dropbox online-only) that doesn't
actually keep files on this machine. Pick a real local folder instead.
Each reason is explained, with the fix, on the
[folder troubleshooting page](folder_troubleshooting.md) —
[cloud-only folder](folder_troubleshooting.md#readback_mismatch),
[couldn't write](folder_troubleshooting.md#write_failed),
[browser won't remember it](folder_troubleshooting.md#permission_not_persisted).

**On Safari / Firefox desktop and on phones** there's no folder API, so
this flow isn't available — the controls are grayed (desktop) or hidden
(phone). See *[Migrating from another browser](#migrating-from-another-browser)*
to bring private data to Chrome.

**If `Fellows/` already exists in the folder you picked**, the app
asks before doing anything: open the existing data (the typical case —
reinstalling, or pointing a second browser at a synced folder), or save
into a new `Fellows 2/` subfolder (the safe choice when you don't
recognize what's there). The app defaults to **using the existing data**,
since a second store is almost never what you want. Cancel leaves both
untouched.

Backups (the `relationships.db.bak.<timestamp>` files in the same
`Fellows/` subfolder) are also automatic — the app keeps the most recent
few alongside the live file. Visible in Finder so you can copy them out if
you want extra safety.

**If your groups end up "only in browser storage"** — for example after a
browser restart drops the folder connection — a reminder banner appears at the
top: *"Your saved groups are only in browser storage."* Browser storage can be
cleared by the browser without warning, so tap **Move my data to a folder** to
put a copy back on disk where it's safe. (That button, and the **Set up data
folder** banner, open the folder picker directly — one tap, no detour.)

### Reconnecting vs. re-picking your folder

Sometimes the app loses access to your folder — usually after a browser
restart or an idle timeout revokes permission. **Your data is never
hidden or deleted when this happens** — the file is still on your disk.

- **Reconnect (the common case).** The app still remembers *which* folder
  it was using, so it shows **"Reconnect your folder to use groups"** and
  re-grants the **same folder in one click**. No folder-picking, no
  guessing. Your groups come right back.
- **Re-pick (rarer).** If the app has lost track of which folder it was —
  after clearing site data, a fresh install, or moving to a new computer
  — you choose a folder again. To stop you grabbing the wrong one, the
  chooser **previews the contents** of each `Fellows*` folder it finds
  (groups · members · notes · last changed · which device created it) and
  recommends the newest. **Pick by content, not by filename.**

See the [folder troubleshooting page](folder_troubleshooting.md#reconnecting-vs-re-picking)
for more.

### Where is my data file?

`showDirectoryPicker` deliberately hides absolute system paths
from web apps, so the badge can only show a relative location
(e.g. *Documents / Fellows*). To find the live file on disk:

- **macOS** — open Spotlight (⌘-Space), type `relationships.db`,
  and the file you just created shows up. Or navigate to the
  parent folder you picked in Finder; the `Fellows/` subfolder
  is right there.
- **Windows** — open File Explorer, paste `relationships.db` into
  the search box at the top, and pick the result.
- **Linux** — `find ~ -name relationships.db` from a terminal.

### Badge states

The badge at the top of *Private data* always tells you the current
state:

- **Saved** (green) — private data is on, your data is in the folder, and
  the last save succeeded.
- **Folder selected — no save yet** (blue) — you've picked a folder but
  the first save hasn't completed yet (rare; usually flips to *Saved*
  within a second).
- **Browse-only — no folder attached yet** (yellow) — default on a fresh
  Chromium-desktop install. Private data is off until you attach a folder;
  nothing private is stored yet. Click **Choose folder…** to turn it on
  (see *[Turning on saved groups](#turning-on-saved-groups-private-data)*).
- **Reconnect your folder to use groups** (yellow) — the OS revoked
  permission to your folder (you moved it, denied on session start, or the
  browser idle-revoked). **Your data is safe in the folder**; click
  **Reconnect** to re-grant the same folder in one click. (See
  *[Reconnecting vs. re-picking](#reconnecting-vs-re-picking-your-folder)*.)
- **Last save failed — Reconnect to re-pick** (yellow) — the most recent
  write threw an error (disk full, permissions changed mid-write, *or
  another browser window of this app has the same folder open*). Your data
  is safe; close any other window pointed at the same folder, then make a
  small edit to retry — the next save succeeds automatically. So you don't
  miss this while working away from Settings, a red banner also appears
  across the top of the app — *"Your latest change wasn't saved."* — and
  clears itself the moment the next save succeeds. If verification of a
  newly picked folder fails (e.g. a cloud-only folder), the badge points
  to the [folder troubleshooting page](folder_troubleshooting.md).
- **Browse-only — Enable on Chrome desktop** (yellow) — desktop **Safari**
  and **Firefox** don't ship the File System Access API, so private data
  can't be turned on here. The controls are grayed out; the link routes to
  the [migration steps](#migrating-from-another-browser). Use *Download my
  private data* (below) on the browser that has your data.
- **On phones, private data isn't available here** — on **any phone or
  tablet** the private controls are hidden entirely (Android can only save
  into a Downloads subfolder the system clears; iOS has no picker), so a
  durable folder isn't reachable. Private data lives on a Chromium desktop
  browser; on the phone you browse, search, and contact fellows.

### Backup and restore (works in every browser)

Even when you've picked a private data folder, you can still grab
a portable file copy by hand:

- **Download a backup.** Settings → Private data folder → *⬇ Download my
  private data*. Your browser asks you where to save it
  (Chrome / Edge / Brave on desktop, share sheet on iOS)
  or drops it straight into your Downloads folder
  (Safari / Firefox / Android).
- **Restore from a backup.** Settings → *Restore from backup →
  Restore from a file* → pick the `.db` file you downloaded earlier.
  The current data is captured into the auto-backup list first, so
  a wrong restore is one click away from being undone.
- **Auto-backups happen on their own.** While you work, the app
  periodically snapshots your data. Pick one with Settings →
  *Restore from backup → Recent auto-backups*.

**What clearing does** (see *Clearing app data* below for the full
breakdown): **Clear App Cache** keeps your data and auto-backups.
**Reset Everything** wipes the in-browser data and auto-backups —
that's why it pops up a *Save a backup first?* dialog. **Reset
Everything does NOT delete the private data folder file** — that
file lives on your disk and is yours to keep or remove.

**If you cleared site data and re-installed, but your data folder
is still on disk**, choose the same folder again — the dialog will
offer to *Open existing*, and your groups / notes / tags come back.

**Phones run in browse-only mode** — private data (saved groups, tags,
notes) isn't available on a phone or tablet at all, so there's nothing
private stored there to clear. (*Clear Storage* on Android or *Clear
History and Website Data* on iOS still clears the app's browser state,
but your private data lives on a Chromium desktop browser, not the phone.)

**Switching browsers or devices.** If you set up a private data
folder inside a cloud-sync folder (Dropbox / iCloud Drive /
Syncthing / OneDrive), point the new browser at the same folder
and pick *Open existing* — your groups / notes / tags carry over.
Otherwise, download a backup in the source browser, move the file
across (AirDrop, email-to-yourself, USB, cloud drive), then use
*Restore from a file* in the new browser.

---

## On a phone

Phones (and tablets) run in **browse-only mode** — search the directory,
open a fellow, and email or call them. Saved groups, tags, notes, and the
Claude Desktop integration are **desktop-only** features, because a phone
browser can't reliably keep that private data safe (see *[Where your data
is stored](#where-your-data-is-stored)*). The phone layout reflects that:

- **Getting around.** Tap the **☰ menu** (top-right of the app bar) to
  reach **Directory**, **Settings**, and **About**. There's no Groups
  tab — groups don't exist on a phone.
- **The list scrolls, the search bar doesn't.** The app bar and the
  search box stay pinned at the top while the list of names scrolls under
  them.
- **Tap a name** to open that fellow. Rows are plain links with a ›
  chevron — there's no "add to group" button.
- **Email / Call.** A fellow's profile leads with big **Email** and
  **Call** buttons (when those details exist). Email opens your mail app
  with the address filled in; Call opens your dialer. The copy buttons
  (📋) are still there for pasting elsewhere.
- **Settings** is short on a phone: app version info and a few tools
  (Diagnostics, Report a bug, Clear app cache, Reset everything). The
  email field, data-folder, download, restore, and Claude Desktop
  sections are desktop-only.

Want the full experience — saved groups, notes, Claude Desktop? Open the
app in **Chrome (or Edge/Brave/Arc) on a desktop** and attach a folder
(*[Turning on saved groups](#turning-on-saved-groups-private-data)*).

---

## The directory

![Directory page during a search; the visible-count line tracks how many
fellows match.](images/users_manual/01_directory_search.png)

- **Search** by name, tagline, or any keyword — results update as you
  type.
- **Has email** filter (top) is on by default; turn it off to see fellows
  without an email.
- **Filters** button (next to the search input) opens a panel where you
  can narrow the directory by **cohort**, **fellow type**, **region**,
  and **citizenship**. Selections apply immediately; the button shows
  how many filters are active. **Reset** clears them in one tap. Active
  filters are written into the page URL — copy the URL to share a
  filtered view, or reload to come back to the same filtered list.
  (The Filters button is disabled until the directory has finished
  loading the full fellow data; **Search** and **Has email** keep
  working before then.)
- The visible-count line ("142 of 515 fellows visible") tracks the
  current search + filter.
- **📋** beside any email or phone number copies just that value to your
  clipboard — useful when your default mail app is misconfigured and the
  underlined link does nothing.

---

## Fellow detail

![A fellow's detail page. Personal fields are blurred in this user-guide
screenshot; the app renders them normally.](images/users_manual/04_fellow_detail.png)

Click a name (in the directory or any group) to open the profile. The
**← →** arrows step through the directory alphabetically. The **+**
beside the name drops the fellow into your current selection (see
Groups below); once added it flips to **✕** — tap again to remove.

---

## Groups

Groups let you save a set of fellows for repeat workflows — emailing a
cohort, exporting a sub-directory, tracking who you've reached out to.
They live on your device, never sync to a server, and survive **Clear
App Cache**.

### Composing a group

The directory page is where you build groups.

1. Search or filter.
2. Tap **+** beside a fellow (it flips to **✕** once they're in the draft).
3. Run another search — your selection persists.
4. Name the group and click **Create new group**.

**Selection persists across searches** is the part most people miss.
Browse a few different slices in one sitting (region, topic, name) and
pick from each. Until you type a name, the rail auto-names the group
after your most recent search.

![A first search ("auckland") narrows the directory to two fellows; the
right-side composer rail is empty.](images/users_manual/01_directory_search.png)

![After tapping + on both Auckland fellows and changing the search to
"design", the rail still holds them.](images/users_manual/02_second_search_rail_kept.png)

![After a third search ("climate") the rail has seven fellows from three
different keywords.](images/users_manual/03_third_search_rail_seven.png)

On phones the composer is a bottom-sheet behind a "N SELECTED" floating
button. Drafts in progress survive a tab close (cleared by **Clear App
Cache** — drafts are unsaved by definition).

### Browsing your groups

`#/groups` (or **Groups** in the nav). Newest-touched first, with a
member count beside each.

![Groups index on desktop.](images/users_manual/08_groups_index.png)

### Group detail

`#/groups/<id>` shows the group's title, member list, free-text note,
and an action bar.

![Group detail on desktop.](images/users_manual/05_group_detail.png)

- **Rename** — pencil ✎ next to the title.
- **Note** — auto-saves on edit.
- **view as visual directory** — small text link below the title opens
  the yearbook-style portrait grid for the same group (see below).
- **Delete** — kebab → *Delete*; confirms before removing. Only the
  group is deleted; fellows themselves are untouched.

### Emailing a group

The most common next step after creating a group.

1. Click **✉ Mail to the whole group**.
2. (Optional) Toggle **CC / BCC** — BCC if you'd rather members not see
   each other.
3. Your default mail client opens with every member's email pre-filled.

Long lists may be split across multiple drafts to fit your mail client's
address-line limit. If the mail link does nothing (mis-configured
default client), click **📋 Copy email addresses** for the same
comma-separated list on your clipboard — paste anywhere.

### Exporting a group

Click **⬇ Export a directory**. Two-phase flow:

1. Pick **PDF** or **HTML** and click **Export**. The file lands in your
   Downloads folder.
2. The panel reveals a **View** link and **Email it to me** button.
   Override the recipient if you want it sent elsewhere; the mail
   client opens with a draft to that address. Attach the file from
   Downloads before sending — browsers can't attach files to a `mailto:`
   automatically.

![Export panel before clicking Export.](images/users_manual/06_export_panel.png)
![Export panel after Export — View link and "Email it to me" appear.](images/users_manual/07_export_done.png)

### Editing members

Click **✎ Edit members** on the detail page. A yellow banner across the
top confirms which group; the directory list returns on the left for
picking; the rail flips to **editing group / Done editing** with the
current members pre-filled.

Every add/remove **auto-saves**. Two exits:

- **Done editing** — keep the changes.
- **Cancel edits** — revert to where this edit session started.

![Edit mode.](images/users_manual/10_edit_mode.png)

### Visual directory

`#/groups/<id>/directory` shows the group as a yearbook-style portrait
grid. The bar at the top has the same **Mail to the whole group**
action as the detail page.

![Visual portrait directory.](images/users_manual/09_visual_directory.png)

---

## Settings

`#/settings`.

- **Your email ("me" email)** — used by export "Email it to me" and any
  other place the app addresses something *to you*. Auto-captured from
  your magic link, so most people never need to touch this.
- **Private data** — shows where on disk your `relationships.db`
  is being kept (or *Browse-only* if no folder is attached, *Enable on
  Chrome desktop* on Safari / Firefox, or hidden entirely on phones).
  On a Chromium desktop browser this is where you turn private data on —
  see *[Turning on saved groups](#turning-on-saved-groups-private-data)*
  and *[Where is my data file?](#where-is-my-data-file)*.
- **Private data → ⬇ Download my private data** — saves all
  your groups, notes, tags, and settings to a single `.db` file.
  Your browser opens its native save dialog (Chrome / Edge / Brave
  on desktop) or share sheet (iOS) so **you choose where the file
  goes**; on Safari, Firefox, and Android the file lands in your
  Downloads folder. The app also auto-snapshots the same file before
  every upgrade and keeps the newest 3.
- **Restore from backup → Restore from a file** — replace your current
  saved data with a previously downloaded `.db`. The app shows a
  confirmation summary ("4 groups, 12 notes → 7 groups, 23 notes —
  Continue?") and only swaps once you say yes. Your pre-restore state
  is captured into the auto-backup list, so a wrong restore is one
  click away from undo.
- **Restore from backup → Recent auto-backups** — every snapshot the
  app has on this device. Each row shows when it was taken and what's
  inside (groups · notes · tags). **Restore this** rolls back to that
  snapshot.

Settings survive both app updates and **Clear App Cache**.

![Settings page — "me" email field, download button, restore from a
file or a recent auto-backup.](images/users_manual/11_settings.png)

---

## About

`#/about` shows fellowship statistics (totals, breakdowns by region /
cohort / fellow type) plus a unified identity-and-updates block:

- **App** — the build label running in this tab (app + server SHAs),
  with the install codename right underneath so you can tell copies
  apart on a multi-install device.
- **Directory data** — when `fellows.db` was last fetched.
- **Signing key** — the fingerprint of the key that signed this
  bundle; compare against the value in your magic-link email.

Two independent buttons drive the freshness checks:

- **Check for application updates** — asks the server whether the
  app code (and the MCP server bundles that ship with it) is current.
  Relabels to **New application version available** when stale; click
  **Reload to apply** next to it to update.
- **Check for directory data updates** — asks whether the server's
  `fellows.db` snapshot is newer than yours. Relabels to **New
  directory data update available** when stale; click **Update
  directory data** to swap (see *Updating directory data* below).

If Claude Desktop integration is installed and your local extension
files are older than the app or directory snapshot on the server, a
**Re-install Claude Desktop bundles** button appears next to the
relevant row — one click downloads the current `.mcpb` files so you
can re-install in Claude Desktop.

Other status text you may see in either row:

- *up to date* — nothing to do.
- *Couldn't check (offline?)* — the server didn't respond. Try again
  when you're online.
- *Reload the app to enable update checks* — appears briefly right
  after an app update if the previous service worker was still running
  when the page loaded. A single reload spawns a fresh background
  worker and the check works.

A line below the block shows when fellow data was last fetched (or
the most recent failure), e.g. *"Last update check: 2026-05-04T18:22:07Z
— succeeded."* — useful when a fellow asks "am I seeing the latest
data?".

![About page.](images/users_manual/12_about_page.png)

### Install name

Below the support and help links, the About page shows a line like:

> This install: **giraffe-gorilla-mouse**

That's an auto-generated name unique to this copy of the app. It's
also tacked onto the window title bar, so it's visible without
opening the About page.

**Why it's there.** If you install the app in more than one browser
(or more than one browser profile), each install has its own data
and its own name. The install name is the easiest way to confirm
which copy you have open when something looks off. See
[Multiple installs on the same device](#multiple-installs-on-the-same-device)
above for the rest of the story.

**What changes the name:**

- *Reset Everything* generates a new name (it's a fresh start in
  every other respect, too).
- *Clear App Cache* keeps your name.
- Reloading the page, restarting the browser, app updates — all
  keep your name.
- The name doesn't carry over to a different browser or device —
  each install gets its own.

The name is entirely local. It isn't sent anywhere, doesn't identify
you, and isn't tied to any account. If you ever
[file a bug report](#reporting-a-bug), the install name is
automatically included so the maintainer can join the report to the
right install.

---

## Use with Claude Desktop (optional)

You can plug the directory into **Claude Desktop** so you can ask Claude
things like *"who's in my Climate Action group?"* or *"draft an invite
email to my Climate Action group — don't send, just stage it for me to
review."* Claude reads your local fellows data to answer, and hands
email drafts back to you to review and send.

See [Use with Claude Desktop](use_with_claude_desktop.md) for the
step-by-step setup walkthrough. Optional — the Fellows app itself
doesn't need any of this.

### One-time consent before you connect a cloud AI

The first time you set this up, the app shows a short agreement you have
to read and accept. This is deliberate. The rest of the Fellows app is
**local-only** — it never sends your data to anyone's server. Connecting
Claude Desktop changes that:

- **You're leaving the local-only model.** Claude Desktop is a cloud
  product. When it answers questions about your fellows, your data —
  potentially including your private groups and notes — is sent to a SaaS
  vendor (Anthropic). No one can guarantee what a SaaS vendor will or
  won't do with data you send it. You have to be OK with that to
  continue.
- **MCP and LLMs are new, and can misbehave.** The extensions are written
  to do only benign, read-only things, and the code is auditable — but an
  LLM driving them can still make mistakes or hit bugs. The good news:
  the extensions only touch two files, and both are recoverable. You can
  re-download the shared directory at any time, and you can restore your
  private data (groups, notes) from a backup or export. So the worst case
  is recoverable.

To proceed you scroll the agreement to the end, tick **I understand and
accept these risks**, then click **Continue — start downloads**. The app
records your consent once. On later **Re-download all extensions**, it
shows only a one-line reminder (with a *Review full terms* link) and lets
you continue right away.

Separately, when you open each downloaded extension, **Claude Desktop
shows its own scary, vague warning** that the extension "can access
everything on your computer." That message is Claude Desktop's, not ours,
and it's far broader than what actually happens — the extensions only
read the two fellows files. The accurate description of the real tradeoff
is the agreement above.

### PNA mode and the "not a PNA" banner

Most of the time the Fellows app runs in **PNA mode**. PNA stands for
*personal-network app*: the app lives entirely on your device and never
talks to a SaaS server. That's the normal, safe state.

Accepting the consent agreement and connecting Claude Desktop is a
deliberate choice to **leave PNA mode**. Internally the app calls this
the **EX-CLOUD-LLM exception** — a named exception to the local-only
promise. While it's active, a persistent **red banner** sits at the top
of the app:

> **Going rogue — not a PNA.**

The banner is how the app tells you which mode you're in, so you're never
in cloud-AI mode without knowing it. It has two controls:

- **What this means** opens an in-app explainer page (route
  `#/exception/EX-CLOUD-LLM`; there's also an index at `#/exceptions`).
  The explainer spells out what the exception relaxes — the
  local-only / never-SaaS promise — what data is affected (the shared
  directory, plus your private groups and notes if the private extension
  is installed), confirms that it's reversible, and shows an honest
  per-item breakdown of how strong each protection is (what the app
  *enforces* vs. what is only best-effort or outside its control once
  data reaches the cloud provider).
- **Dismiss** hides the banner. Dismissing is an **acknowledgement, not a
  fix**: it does *not* return the app to PNA mode, and the dismissal
  persists across reloads. You're still connected to the cloud AI — you've
  just told the app you've seen the notice.

### Returning to PNA mode

Leaving PNA mode is reversible. You'll find a **Return to PNA mode**
control in two places, shown only while the exception is active:

- On the **What this means** explainer page, and
- In **Settings → Claude Desktop integration**.

Clicking it returns the app to PNA mode, removes the red banner, and
**re-arms the consent gate** — so the next time you connect Claude
Desktop, the app asks you to read and accept the agreement again.

One honest caveat: returning to PNA mode stops *future* sharing, but it
**cannot recall data already sent** to the cloud provider. It changes
what happens from here on, not what's already left your device.

---

## Updates

The app handles two kinds of updates separately. Both are surfaced on
the **About** page; you can click **Check for application updates** or
**Check for directory data updates** at any time to re-check each one.

### App updates

The app shell (UI, layout, fixes) auto-checks for new versions — at
every launch, and once an hour while open. When one's available a
banner reads *"New version available — Reload."* Click Reload. The
About page shows the same state alongside an inline **Reload to
apply** button.

Reloading replaces only the app. Your saved groups, notes, settings,
and the fellow data on this device are untouched.

### Directory data updates

The fellow data on this device — names, profiles, contact info — is a
snapshot. **By design it does not change automatically.** Once
installed, the directory you see is yours: a fellow's profile won't
shift mid-session, and your saved groups will keep referring to the
same people.

When the server's snapshot differs from yours, the About page's
*Directory data* row shows **Directory Data update available** and an
**Update directory data** button.

Before applying the update, the app checks whether any of your saved
group members would disappear from the new snapshot. If so, a confirm
dialog lists them by name and group, e.g.:

> *This update removes 2 fellows from your saved groups:*
> *• Alice Smith — in 'NZ Mentors', 'Investors'*
> *• Bob Jones   — in 'NZ Mentors'*
>
> *After the update they will no longer appear in those groups.
> Their entries will be flagged as 'Profile no longer available' so
> you can review and remove them.*
>
> *[Cancel] [Update anyway]*

If no members would disappear, the update applies silently and the
status flips to *Directory data updated.*

After an update, members whose profile is no longer in the directory
render in group detail as **Profile no longer available (record_id:
…)** with a per-row **Remove** button. The data isn't lost — it's just
no longer in the active snapshot. You can leave the row in place
(harmless) or click **Remove** to drop it from the group.

The same row also appears with a small *(fellow data unavailable)*
note anywhere else the group surfaces — composer rail when editing,
visual directory grid, and PDF / HTML exports — so you can spot the
gap without opening group detail.

---

## Clearing app data

Two reset paths if the app gets weird. Try the gentle one first.

|  | Clear App Cache | Reset everything |
|---|---|---|
| Wipes the cache, signs you out | ✓ | ✓ |
| Wipes saved groups, notes, tags, settings | — | ✓ |
| Wipes the on-device fellow data snapshot | — | ✓ |
| Lands you at | the install landing | the email gate |

- **Phone / tablet** — top-right **⋮** kebab → either option.
- **Desktop** — bottom-right red **Clear App Cache & Reload** button;
  *…or reset everything* small link just above it.

![Mobile app-bar kebab — both options live in one
sheet.](images/users_manual/m6_mobile_appbar_kebab.png)

A confirm dialog spells out what's lost before it runs. In-progress
group drafts are lost in either reset (drafts are unsaved by
definition).

**Reset Everything offers a backup first.** Because Reset Everything
wipes your saved groups, notes, and settings — including the
auto-backups stored alongside them — clicking it pops up a *Save a
backup first?* dialog with three options:

- **⬇ Download backup & continue** — downloads the same `.db` file
  Settings → *Download my private data* produces, then proceeds to the
  destructive confirm. Safe choice if you might want to restore later.
- **Skip — no data to save** — for clean installs or when you don't
  care about losing the data. Goes straight to the destructive confirm.
- **Cancel** — backs out without resetting anything.

After a reset, install the app again from a fresh magic link, then
Settings → *Restore from backup → Restore from a file* → pick the
`.db` you downloaded.

### When the directory hangs at "Loading…"

Rare, but it can happen — usually a stuck service worker or an
unresponsive local database after a deploy. After about 20 seconds of
no progress the app replaces the loading message with a recovery
panel that names the last completed phase and gives you three options:

- **Reload** — try again with a fresh page load. Fixes most stuck
  service-worker cases on its own.
- **Clear App Cache & Reload** — same as the red button at the
  bottom of the page. Wipes the shell cache and signs you out, but
  keeps your saved groups and the on-device fellow data.
- **Send report to the maintainer** — opens the bug-report dialog
  pre-filled with the boot trace so we can see where it stalled.

Try Reload first; if that doesn't help, Clear App Cache. Send the
report if both fail — that's the case where we want to hear about it.

---

## Reporting a bug

Click **Report a bug** (small button bottom-left on desktop; kebab →
*Report a bug…* on mobile). The dialog pre-fills your browser, OS,
build SHA, [install name](#install-name), and the most recent app
errors. Add a one-line description and submit; it lands in the
maintainer's log.

If you're stuck at the email-gate page (no link arriving, error on
submit), the gate has its own diagnostics block:

- **Copy diagnostics** — to clipboard; paste into chat / email along
  with the time you tried.
- **Send diagnostics** — one-tap to the maintainer's log. Your email
  and IP are **never sent** — only browser / OS, recent requests, build
  SHA, and a non-reversible 12-char hash of your address (so we can
  find which sign-in attempt failed). Sanitization happens server-side
  in
  [`deploy/client_error_sanitizer.py`](https://github.com/richbodo/fellows_local_db/blob/main/deploy/client_error_sanitizer.py).

Prefer GitHub? File an issue at
[github.com/richbodo/fellows_local_db/issues](https://github.com/richbodo/fellows_local_db/issues)
— useful when you want a thread to track the fix in, or when the in-app
report can't reach the server. Ask Rich to add you to the repo if you
don't have access yet.

---

## Offline

The app is local-first by design. Once installed, it runs entirely on
your device — fellow data, your saved groups, your notes, your
settings. No login, no server round-trip on each click. Photos that
finished caching are available; the rest show a placeholder until you
get a chance to fetch them.

If you ever wonder whether the app has reached the server recently,
the **About** page shows the timestamp of the last successful fetch
under the update buttons. Picking up new fellows, fixes, or a
refreshed profile is opt-in — see *Updates → Directory data updates*
above. If your session has expired, visit `/?gate=1` for a new magic
link.

---

## Supported browsers

**Browsing, search, and contacting fellows work on every modern browser**
(desktop and mobile). The minimum versions, for the storage the app runs
on:

- **Chrome / Edge** 102+ (May 2022)
- **Safari** 16.4+ on macOS 13.3+ / iOS 16.4+ (March 2023)
- **Firefox** 111+ (March 2023)

**Saved groups (private data) additionally need a verified folder on
disk**, which today is only possible on a **Chromium desktop browser**
(Chrome, Edge, Brave, Arc, Opera). On Safari / Firefox desktop the private
controls are grayed with an "Enable on Chrome desktop" link; on phones
they're hidden. See *[Where your data is stored](#where-your-data-is-stored)*.

Older browsers can still browse the directory and read profiles. Every
browser on iOS uses Safari's engine, so Chrome / Firefox on iPhone won't
help — update iOS itself (iPhone 8 and newer support 16.4+).

---

## Getting help

- **General questions** — fellows channels, or EHF Communications
  Working Group.
- **Bug reports / feature requests** — file a
  [GitHub issue](https://github.com/richbodo/fellows_local_db/issues)
  (you'll need to be added to the repo first — ask Rich). The same
  GitHub link is on the About page.
- **Lost or expired install link** — request a fresh one from the
  operator.

---

## Your device is now the directory

Because the app is local-first, the full directory — every fellow's
email and phone number — lives on **your** device after you install,
and keeps working with no server. That's the point: it survives even
after the distribution server is shut down. The flip side is that your
device is now where the directory needs protecting. There is **no
remote wipe** — if a device is lost, the copy on it can't be revoked.

A few minutes of basic hygiene covers almost all of the real risk:

- **Turn on full-disk encryption.** FileVault (Mac), BitLocker
  (Windows), or the on-by-default encryption on a modern iPhone /
  Android. This is the single biggest protection: a lost or stolen
  device is then just a brick, not a copy of the directory.
- **Use a screen lock** with a passcode/biometric and a short
  auto-lock timeout.
- **Keep your browser and OS updated.** The app's security depends on
  the browser; updates are how that stays true over time.
- **Retiring or selling a device?** Open the app and use **Settings →
  Reset Everything** (see *Clearing app data* above) to wipe your
  groups, notes, and the cached directory, then do a full factory
  reset of the device.
- **Lending your laptop to someone?** Lock the screen, or use a
  separate OS user account — the installed app is visible to anyone
  who can use your logged-in session.

None of this is unusual — it's the same care any contact list on your
phone deserves. It just matters a little more here, because this list
belongs to the whole fellowship.

---

## Privacy

This app ships fellows' contact info and free-text responses. It is
**not** a public service. Keep screenshots and data inside the
fellowship.
