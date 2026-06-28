# Where Does Your Data Live? Data Safety in a Progressive Web App

*A talk companion. Plain language, minimal jargon. The few technical terms you
need are defined the first time they appear.*

> **The one-sentence version.** We built an app you can install on any device
> from a single web link — and discovered that "save the user's data somewhere
> it will reliably still be there tomorrow" is a problem the web platform
> mostly refuses to solve. Only one family of browsers gives us a real answer.
> So the app has to *figure out which platform it's running on* and honestly
> turn features on or off to match. This document is about why that is, and how
> we handled it without ever pretending the data is safer than it is.

---

## 1. What we built, and why it makes data hard

This is a **Progressive Web App (PWA)** — think of it as a website you can
*install*. You open one link, the browser offers "Add to Home Screen" or
"Install," and from then on it behaves like a normal app with its own icon. No
app store, no separate download for Mac vs. Windows vs. phone. One link, every
platform.

That single property — *one app that runs everywhere* — is the whole reason
data safety got hard.

A normal desktop program written for macOS knows it's on macOS. It can save a
file to your Documents folder and trust it'll be there next week. A PWA can't
assume any of that. The exact same code might be running:

- in Chrome on a Mac laptop,
- in Safari on an iPhone,
- in Firefox on a Linux desktop,
- as an installed app on an Android phone.

Each of those gives a web app **a different, and mostly very limited, ability to
store data**. The app can't know in advance which one it's in. It has to *ask
the browser at runtime* what it's allowed to do, and then behave accordingly.

That's the headline. The rest of this document is the detail.

---

## 2. The first hard truth: browsers don't trust web pages with your files

When you visit a web page, the browser treats it as **untrusted** by default —
which is correct, because most web pages are strangers. A stranger should not be
able to rummage through your hard drive. So browsers historically gave web pages
*no* access to the file system at all. A web page could keep small scraps of
data (a few megabytes in something called *local storage*, roughly a notepad),
but nothing like "here is a real database file, keep it safe."

For an app whose entire job is to hold the user's contacts, notes, and saved
groups, "a notepad" is not enough. We need a real, durable, reasonably large
place to keep a database.

The web platform's answer to this is a feature called **OPFS**.

---

## 3. OPFS and "the worker": the app's private vault

**OPFS** stands for *Origin Private File System*. Ignore the name; here's what it
actually is:

> OPFS is a **private storage vault** that the browser hands to one specific web
> app and no one else. Our app can read and write real files in it — including a
> full database — at real speed. But it is invisible: the user can't open it in
> Finder, other apps can't see it, and other websites can't touch it.

So OPFS solves the "we need a real database" problem. Good. But it comes with two
strings attached, and both shaped the whole architecture.

### String 1: only *one* part of the app may touch the vault at a time

A database file is fragile if two things write to it at once — like two people
editing the same paper document simultaneously, crossing out each other's words.
Normal apps avoid this with an operating-system "file lock." The browser doesn't
offer one for OPFS.

Our solution is to appoint a single gatekeeper. In a browser, you can run code in
the background, off the main screen-drawing thread; that background context is
called a **worker**. We put *all* database access inside one dedicated worker,
and nothing else is allowed to open the vault. The visible part of the app (the
buttons, the lists) never touches the database directly — it sends requests to
the worker and waits for answers, the way a bank teller is the only one who
reaches into the vault while customers stay at the counter.

The project's architecture notes put it bluntly:

> *"Durable SQL in a browser forces this worker-owned, single-connection
> architecture — a property of the medium accepted as the substrate's cost, not
> a defect."*

In other words: this isn't a design we chose because it's elegant. It's the
shape the platform forces on anyone who wants a reliable database in a browser.
We accepted it and built around it.

### String 2: the vault only works under special "isolation" headers

To allow the fast, safe database access OPFS needs, the browser requires the page
to run in a locked-down mode called **cross-origin isolation** — essentially the
app promising "I will not load anything from other websites." We set a couple of
technical headers to opt into that. The practical upshot for a presentation: this
high-security mode is a *prerequisite*, and if a server or network in front of
the app strips those headers, the vault silently fails to open. It's one more way
the same code can behave differently depending on where it's running.

---

## 4. The catch nobody tells you: that vault can be erased without warning

Here's the part that turns "we have storage" into "we have a data-safety
problem."

OPFS — and the smaller storage layers next to it — are officially **evictable**.
That means the browser reserves the right to **delete the app's data on its own**,
without asking, if:

- the device gets low on disk space,
- the user hasn't opened the app in a long time,
- (on Safari) the data crosses a size cap, or
- the user taps an innocent-looking "Clear browsing data" / "Clear storage"
  button.

There is a function a web app can call — `navigator.storage.persist()` — that
*requests* the browser not to do this. But it is a polite request, not a
guarantee. The browser can say no, or say yes and change its mind.

So the honest summary is:

> The only storage the web platform reliably gives a PWA on *every* device is
> storage the platform can also **erase out from under you**. It is fine for a
> cache. It is not, by itself, a safe home for data the user would be upset to
> lose.

This is the crux of the entire problem. Browsing the public directory is fine on
evictable storage — if it's wiped, we just re-download it. But the user's *own*
work — their saved groups, their private notes — must never live *only* in a
place the browser might delete. We needed a way to put that on **real disk**.

---

## 5. The real fix exists on exactly one family of browsers

There *is* a web feature that lets an app save to a real folder on your actual
disk — a folder you choose, that you can see in Finder, that survives "clear
browsing data" because it isn't browser storage at all. It's called the **File
System Access API**, and the user-facing piece is a **folder picker**: the app
asks, a normal "choose a folder" dialog appears, you pick one, and from then on
the app can keep its database there as a real file.

This is exactly the reliable home we wanted.

**The problem: only Chromium browsers have it.**

"Chromium" is the shared engine under Chrome, Edge, Brave, and Arc. The folder
picker works there. It does **not** work in Safari (so: no iPhones, no iPads, and
Safari on Mac), and it does **not** work in Firefox. On Android, even Chrome only
offers a crippled version that routes into a folder the system can wipe — so it
can't keep the promise either.

So the single most important data-safety feature in the app is available to
*some* of our users and not others, and **the app has no way to know which group
a given user is in except to check, live, in the browser they happen to be
using.** This is the precise point the user feels most: *"you have to know what
platform you're on to enable certain features."* The app is doing that check on
every boot.

---

## 6. Two modes, decided fresh every time the app starts

Because the reliable folder only exists sometimes, the app runs in one of **two
modes**, and it decides which one the moment it starts up:

### Folder mode (the good case — Chromium desktop, folder attached)

The user has picked a real folder. The database lives there, on disk, as a normal
file. The OPFS vault is demoted to a temporary scratchpad. Your saved groups and
notes are on your actual disk, visible in Finder, and survive a browser-data
wipe. This is the experience we want everyone to have, and can only give to some.

### Browse-only mode (everywhere else — Safari, Firefox, all phones, or "no folder yet")

There is no reliable folder, so the app **does not pretend to durably store your
private work at all**. You can still browse the whole directory, search it, open
a person, and email or call them. But "create a saved group" and "write a private
note" are switched off, because the only place to put them would be storage the
browser can erase — and quietly losing someone's data is worse than honestly not
offering the feature.

A deliberately strict rule sits underneath this: **the app commits to exactly one
mode per session, with no halfway "hybrid."** An earlier design tried to keep a
copy in the fast vault *and* sync it to the folder. It was abandoned because it
created a silent way to lose data: if the folder copy was out of date at startup,
it could overwrite newer work without any error. Picking one source of truth and
sticking to it for the session removes that whole class of bug.

### "Attached" isn't enough — the folder has to be *verified*

It's not sufficient for the user to merely click a folder. Cloud-synced or
virtual folders can *look* writable and silently fail. So before the app trusts a
folder with your data, it runs a quick five-step handshake and **all five must
pass**:

1. you **pick** a folder;
2. the app **creates** its own sub-folder inside it;
3. the app **writes** a tiny test file;
4. the app **reads that test file back** and the contents match exactly; and
5. the browser **remembers the permission** so it still works after a restart.

Only a folder that clears all five is treated as a real home. Anything less, and
the app stays in browse-only mode. The point is worth stating plainly: we don't
ask the browser "can you do this?" and take its word — *we make it actually do it
and check the result.* Capability claims lie; a successful read-back doesn't.

---

## 7. So the app constantly asks "what can this platform actually keep?"

Put the last few sections together and you get the core engineering stance of the
whole project:

> **Detect what the platform can *durably* deliver, then turn features on or off
> to match — and never promise durability the platform can't keep.**

Two things make this trustworthy rather than just cosmetic:

- **We test the capability, we don't guess from the browser's name.** It would be
  easy (and wrong) to say "if the name contains *Safari*, hide the button." Names
  lie and change. Instead the app tries the actual operation and watches whether
  it really works.

- **The "off switch" lives at the data layer, not just the screen.** Hiding a
  "Create group" button is the easy, cosmetic half. The real protection is that
  the part of the app that *writes to the database* refuses to do so when there's
  no verified folder — so even a power user poking at the app through developer
  tools can't sneak a durable write into storage that will be erased. As the
  internal rule states it: *"A gated capability whose write still succeeds from
  the developer console is not reduced."* The promise has to be enforced where
  the data actually moves.

---

## 8. The "platform exceptions" we had to declare

Once you accept that the platform imposes hard ceilings, the honest thing to do
is **write them down** rather than paper over them. The project keeps a formal
list of these platform-imposed limits. (Internally they carry codes like
`CST-PWA-…`; you don't need the codes — here they are in plain language.) Each one
is a thing the web platform *won't* give us, paired with how we handle it without
lying to the user.

| The platform won't give us… | What that means for you | How the app handles it honestly |
|---|---|---|
| **A real file for private data on most browsers.** The folder picker is Chromium-only. | On Safari/Firefox/phones, there's no durable home for *your* groups and notes. | Full private features on Chromium-with-a-folder; **browse-only everywhere else** — never a fake durable store. A manual database export is the bridge between devices. |
| **Storage it won't erase.** OPFS and its neighbors are evictable. | The browser may wipe app storage to reclaim space. | Settings/prefs are kept in the most durable small-storage available; private work goes to the *real folder*, not the erasable vault. If old data is ever stranded in the vault, the app **shows a banner** nudging you to save it to disk before it's lost. |
| **A way to sync between your devices.** Web storage is walled off per-browser, per-device. | Your phone and your laptop can't see each other's data automatically. | The app stamps each database copy with an identity + a version counter so it can tell you *which copy is newer* when you reconnect a folder. Cross-device moves are a deliberate manual export — no silent magic sync. |
| **A file lock to coordinate two open tabs.** | Two tabs could fight over the same database. | One dedicated worker owns the database; a browser "lock" guards folder writes; if a second tab grabs ownership, the app says so clearly instead of corrupting anything. |
| **Reliable background tasks (especially on iOS).** | The app can't promise to back up your data on a schedule while it's closed. | Backups happen **opportunistically when you open the app**, never as a promise of scheduled protection. (More below.) |
| **A truly server-free install.** A web app needs a web address and a secure connection to exist. | There has to be *a* server somewhere. | That server's job is strictly limited to *handing you the app and updates* — it holds none of your personal data. (This app's "never-SaaS" stance.) |

The thing to take from this slide isn't the individual rows — it's the posture:
**every limit is named, and every limit has a stated handling, and where we
haven't truly solved something we say so.** A limit we merely *reduced* is never
described as *solved*. Over-claiming safety would itself be a kind of safety bug.

---

## 9. Backups: the safety net, and the promise we refuse to make

Because the good storage can vanish and the good folder isn't available
everywhere, the app keeps a small **rolling set of backups** of the user's
private database — a handful of recent snapshots (currently the five most recent),
each tiny (tens of kilobytes). In folder mode these snapshots sit right next to
the main file in your chosen folder, visible in Finder, surviving a browser wipe.
Restoring is two clicks, and the app shows you what's about to change before you
commit.

But notice *when* the backups happen: **when you open the app**, not on a timer.
That's a direct consequence of the platform ceiling about background tasks. A web
app — especially on an iPhone — cannot reliably wake itself up to do a backup
while it's closed. We could *pretend* to ("automatic hourly backups!"), but it
would be a promise the platform breaks for us. So we make the smaller, true
promise instead: *every time you come back, we quietly check and snapshot.* Honest
and modest beats impressive and false.

---

## 10. The takeaway

A PWA's superpower — *install once, run on every platform* — is exactly what makes
data safety hard, because every platform offers a different, mostly stingy deal on
where data can live and whether it survives. The web gives every app a fast
private vault that the browser can erase, and gives a *real, durable folder* to
only one family of browsers.

So the app does three things, over and over:

1. **Ask the platform what it can actually keep** — by testing, not guessing.
2. **Match the features to the answer** — full power where there's a real folder,
   honest browse-only where there isn't — and enforce that *where the data moves*,
   not just on screen.
3. **Name every limit out loud** and never describe a worked-around ceiling as a
   solved one.

The unglamorous, accurate headline for the whole effort: *we worked very hard to
make sure the app never tells you your data is safe when the platform it's running
on can't make that true.*

---

## Appendix: where this lives (for the curious)

- **The single database-owning worker:** `app/static/vendor/sqlite-worker.js`
- **The two storage modes and the folder write-path:** `plans/user_folder_storage.md`
- **The capability gate (folder-verified before private data turns on):**
  `plans/private_data_capability_gate.md`, `plans/private_data_enforcement.md`
- **Which features work on which platforms (the matrix):**
  `docs/feature_platform_matrix.md`
- **Capability detection vs. browser-name sniffing:** `docs/browser_support.md`
- **Backups, restore, and what survives a wipe:** `docs/persistence_and_upgrades.md`
- **The formal list of platform ceilings (the "constraints"):** the *Constraint
  attestation* table in `docs/Architecture.md`, with the discovery story in
  `docs/architectural_findings.md`
