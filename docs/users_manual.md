# EHF Fellows Directory — User Guide

A fast local-only directory for EHF fellows.

It's a private, installable web app. Once installed it runs entirely on your
device — fellow data lives in your browser's local storage, so it works
offline. You can group fellows, email a whole group in one click, and
export sub-directories.

The app is distributed only by emailed magic link. Keep the data and any
screenshots inside the fellowship.

---

## Installing the app

You'll get a magic link in email. Click it.

1. On the install landing, click **Install app**.
2. Confirm your browser's prompt:
   - **Desktop Chrome / Edge** — small prompt near the address bar; the
     app opens in its own window.
   - **Android Chrome** — *Add to Home screen*; appears in your launcher.
   - **iOS Safari** — *Share → Add to Home Screen*. (iOS has no one-click
     prompt.)
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

## Can't install at all?

Likely a device-side quirk. Two third-party tools that triage before you
ask for help:

- **[PWAHero](https://pwahero.com/)** — paste the URL; walks you through
  install steps for your specific browser/OS.
- **[Progressier's PWA diagnostic](https://progressier.com/pwa-testing-tool)**
  — green/red checklist of what's missing.

Both are free and don't require sign-in. Send the report to the EHF
Communications Working Group along with what you tried.

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

## The directory

![Directory page during a search; the visible-count line tracks how many
fellows match.](images/users_manual/01_directory_search.png)

- **Search** by name, tagline, or any keyword — results update as you
  type.
- **Has email** filter (top) is on by default; turn it off to see fellows
  without an email.
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
- **Your saved data → Download my user data** — saves all your groups,
  notes, tags, and settings to a single `.db` file. The app also
  auto-snapshots the same file before every upgrade and keeps the
  newest 3.
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
cohort / fellow type) plus a two-line update status block:

- **App** — the build label running in this tab.
- **Directory data** — when fellows.db was last fetched.

Click **Check for updates** to ask the server about both. Each row
updates independently:

- *up to date* — nothing to do.
- *App update available* — a newer app version is on the server. A
  **Reload to apply** button appears next to the row; clicking it is
  the same as clicking the *New version available* banner.
- *Directory Data update available* — the bundled fellow data on the
  server differs from the snapshot on this device. An **Update
  directory data** button appears. See *Updating directory data*
  below.
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

---

## Updates

The app handles two kinds of updates separately. Both are surfaced on
the **About** page; you can click **Check for updates** at any time to
re-check.

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

---

## Reporting a bug

Click **Report a bug** (small button bottom-left on desktop; kebab →
*Report a bug…* on mobile). The dialog pre-fills your browser, OS,
build SHA, and the most recent app errors. Add a one-line description
and submit; it lands in the maintainer's log.

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

---

## Offline

The app is local-first by design. Once installed, it runs entirely on
your device — fellow data, your saved groups, your notes, your
settings. No login, no server round-trip on each click. Photos that
finished caching are available; the rest show a placeholder until you
get a chance to fetch them.

If you ever wonder whether the app has reached the server recently,
the **About** page shows the timestamp of the last successful fetch
under **Check for updates**. Picking up new fellows, fixes, or a
refreshed profile is opt-in — see *Updates → Directory data updates*
above. If your session has expired, visit `/?gate=1` for a new magic
link.

---

## Supported browsers

Saved groups and settings need OPFS (a recent browser storage API).

- **Chrome / Edge** 102+ (May 2022)
- **Safari** 16.4+ on macOS 13.3+ / iOS 16.4+ (March 2023)
- **Firefox** 111+ (March 2023)

Older browsers can still browse the directory and read profiles;
creating groups will show a panel explaining what to do. Every browser
on iOS uses Safari's engine, so Chrome / Firefox on iPhone won't help —
update iOS itself (iPhone 8 and newer support 16.4+).

---

## Getting help

- **General questions** — fellows channels, or EHF Communications
  Working Group.
- **Bug reports / feature requests** — GitHub issue (link on About
  page; you'll need to be added — ask Rich).
- **Lost or expired install link** — request a fresh one from the
  operator.

---

## Privacy

This app ships fellows' contact info and free-text responses. It is
**not** a public service. Keep screenshots and data inside the
fellowship.
