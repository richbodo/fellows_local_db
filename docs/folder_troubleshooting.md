# Folder troubleshooting

Saved groups, tags, and notes (your **private data**) live in a real
folder on your computer. To turn them on, the app picks a folder and then
**verifies** it can actually keep your data there — it creates a `Fellows/`
subfolder, writes a small test file, reads that file back, and confirms
the browser will remember the folder next time. If any of those steps
fails, the app stays in **browse-only mode** (you can still browse,
search, open a fellow, and email or call them) and shows you a short
reason. This page explains each reason and what to do about it.

If your private data isn't lighting up, find the reason the app showed
you below.

---

<a id="picker_cancelled"></a>
## picker_cancelled — you closed the folder chooser

**What it means.** The app asked you to pick a folder, but the picker was
dismissed before a folder was chosen.

**Likely cause.** You hit *Cancel*, pressed *Escape*, or clicked away from
the picker window.

**What to do.** Try again: tap the grayed control (or **Settings →
Private data → Choose folder…**) and pick a folder this time — your
Documents folder is a good default. Nothing is broken; you just didn't
finish the step.

---

<a id="subfolder_create_failed"></a>
## subfolder_create_failed — the app couldn't create its data folder

**What it means.** The app picked your folder but couldn't create the
`Fellows/` subfolder it stores your data in.

**Likely cause.** The folder you chose is read-only, is managed by the
system, or your account doesn't have permission to add things to it.

**What to do.** Pick a different folder you own and can write to — your
**Documents** folder is the safest choice. Avoid system folders
(Program Files, /Applications, the root of a drive) and folders shared by
an IT-managed account.

---

<a id="write_failed"></a>
## write_failed — the app couldn't write to the folder

**What it means.** The `Fellows/` subfolder was created, but writing the
test file into it failed.

**Likely cause.** The folder (or drive) is read-only, the browser was
denied permission at the moment of writing, or the disk is full.

**What to do.** Check that the drive has free space and isn't a read-only
or locked location (e.g. a mounted disk image, a network share you only
have read access to). Then pick the folder again. If it keeps failing,
choose a plain folder inside your home directory instead.

---

<a id="readback_mismatch"></a>
## readback_mismatch — the folder didn't return what we wrote (most common)

**What it means.** The app wrote a test file and then read it back — and
the bytes that came back weren't what it wrote. That tells us this
location can't reliably keep your data, so the app refuses to use it.

**Likely cause.** You picked a **cloud-only / online-only folder** — for
example a OneDrive *Files On-Demand* folder, a Dropbox *online-only*
folder, an iCloud Drive folder set to "optimize storage," or a virtual /
placeholder mount. These show file *names* without keeping the file
*contents* on your machine, so a read-back doesn't match a write. This is
exactly the failure the verification step exists to catch — better to
catch it now than to lose your groups later.

**What to do.** **Pick a real, local folder** — one whose files are
actually stored on this computer. Your **Documents** folder is the
reliable choice. If you *want* your data in a sync folder, first make sure
that folder is set to **keep files on this device / always available
offline** (right-click the folder in your file manager and look for an
"always keep on this device" option), then pick it again.

---

<a id="permission_not_persisted"></a>
## permission_not_persisted — the browser won't remember this folder

**What it means.** Everything wrote and read back fine, but the browser
wouldn't save permission to the folder for next time — so the app
couldn't guarantee your data would still be reachable after a restart.

**Likely cause.** A privacy/incognito window, a browser configured to
clear site data on close, or a browser extension that blocks persistent
storage.

**What to do.** Use a normal (non-private) browser window, and check that
your browser isn't set to clear site data / cookies on exit for this site.
Then pick the folder again.

---

## Which browsers support this

Private data needs the **File System Access API**, which today is only on
**Chromium desktop browsers**: **Chrome, Edge, Brave, Arc, Opera, Vivaldi**
on a computer.

- **Safari** and **Firefox** on desktop don't have the API, so the private
  controls are grayed out with an **"Enable on Chrome desktop"** link.
- **Phones and tablets** (Android and iOS) can't keep a durable folder, so
  private data is **hidden** there entirely — there's no action you can
  take on the phone to turn it on.

If you're on one of those, you can still bring private data over by
**migrating to Chrome**:

1. **Back up** — in your current browser, **Settings → Private data →
   Download my private data**. Save the `.db` file (its name is
   self-describing: `ehf-fellows-private-data-<date>.db`).
2. **Install Chrome** (or any Chromium desktop browser) and open the app
   there.
3. **Restore** — **Settings → Restore from a file** → pick the `.db` you
   saved, then attach a folder when prompted.

---

## Reconnecting vs. re-picking

These are two different situations — the app handles them differently:

- **Reconnect (the common case).** Your folder is still set up; the
  browser just needs permission again after a restart or an idle timeout.
  The app already remembers *which* folder, so reconnecting is **one
  click** — *"Reconnect your folder to use groups"* — and re-grants the
  **exact same folder**. **Your data is never hidden or deleted** while
  reconnect is pending; the file is still on your disk. You don't pick a
  folder again.
- **Re-pick (rarer).** The app has lost track of which folder it was —
  usually after clearing site data, a fresh install, or moving to a new
  computer. Here you choose a folder again. To avoid grabbing the wrong
  one, the chooser **previews the contents** of each `Fellows*` folder it
  finds (groups · members · notes · last changed · which device created
  it) and recommends the newest. **Pick by content, not by filename** —
  the preview is there so you don't have to guess.

If you set up a folder more than once and now have `Fellows` and
`Fellows 2`, the re-pick chooser shows both with their contents so you can
tell which holds the data you want.
