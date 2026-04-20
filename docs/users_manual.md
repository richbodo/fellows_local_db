# EHF Fellows Directory — User Guide

A short, practical guide for fellows using the installed app. For a deeper
technical tour, see [`Architecture.md`](Architecture.md).

---

## What this app is

A private, installable directory of Edmund Hillary Fellowship fellow
profiles. Once installed, the app runs locally on your device — the fellow
data lives in a local database inside your browser's app storage, so you
can browse the directory even when you're offline.

The app is only distributed to EHF fellows, by emailed magic link. Please
keep the data confidential and do not share the link or screenshots
outside the fellowship.

---

## Installing the app

1. Click the install link in your email. You'll land on a page titled
   **"Install EHF Fellows Directory."**
2. Click **Install app**.
   - On **desktop Chrome / Edge**: a small install prompt appears near the
     address bar — confirm it. The app opens in its own window.
   - On **Android Chrome**: the prompt offers **Add to Home screen**. Accept
     it; the app shows up as an icon in your launcher.
   - On **iOS Safari**: tap the **Share** button, then **Add to Home
     Screen**. (iOS doesn't support the one-click install prompt.)
3. Open the installed app. The first launch downloads fellow data in the
   background — you should see photos filling in over a minute or so on a
   normal connection.

If you see a message saying your browser doesn't support install, try
Chrome or Edge on desktop, or Safari on iOS.

---

## Where does the installed app live?

A PWA install drops an icon on your device so you can launch the app like
any other app — you don't need to type the URL or open a browser to use
it day-to-day.

- **macOS (Chrome / Edge)**: the app appears in your **Applications** folder
  and in Spotlight (Cmd-Space, type "EHF"). Also listed under Chrome's
  **Apps** at [chrome://apps](chrome://apps).
- **Windows (Chrome / Edge)**: look in the **Start menu** under "EHF Fellows
  Directory". Edge also offers to add a taskbar shortcut during install.
- **Linux (Chrome / Edge)**: appears in the application launcher (GNOME
  Activities, KDE Kickoff) and under `~/.local/share/applications/`.
- **Android (Chrome)**: added to the **home screen** (unless you declined)
  and always available in the app drawer.
- **iOS (Safari)**: added to the **home screen**. iOS has no app drawer.

Clicking/tapping the icon opens the app in its own window — no browser
chrome, runs offline from cached data.

---

## Two ways to launch

You have two doors to the same app. Pick whichever is easier:

1. **The installed app icon** (preferred). Opens in its own window, runs
   cleanly offline, and doesn't need a browser to be running. This is the
   "real" app; treat it like any other desktop / mobile app.

2. **The URL — https://fellows.globaldonut.com — in any browser tab**. If
   you've already installed the app on this browser profile, the URL opens
   the directory directly (same data, same UI, inside a regular tab). This
   is handy when:
   - You want to open the app on a device where the icon isn't obvious.
   - You clicked a link from a chat or email.
   - You bookmarked the URL.

The *first* visit from a browser profile always starts at the install
landing. Once you've installed and used the app once, later URL visits
skip the install landing and go straight to the directory.

---

## Using the directory

- **Search** by name, tagline, or any keyword. Results update as you type.
- **Has email** filter (top of the directory) is on by default — it hides
  fellows the app can't reach by email. Turn it off to see everyone.
- **Profile photos** are cached on your device after the first load, so
  scrolling is fast and works offline.
- The visible-count text (e.g. **"142 of 515 fellows visible"**) shows how
  many fellows match your current search + filter.

---

## Updates

The app checks for new versions automatically:

- **On every launch**, the service worker compares against the server.
- **Once an hour** while the app is open, a background check confirms
  you're still on the latest build.
- You can also force a check from the **About** page → **Check for
  updates**.

When an update is available, a banner appears across the top of the app:
**"New version available — Reload."** Click Reload to apply it.

---

## Clearing app data

If the app gets into a weird state (corrupt cache, stuck banner, stale
data), you can reset it:

1. Go to the **About** page.
2. Scroll to **Diagnostics** → **Clear app cache**.
3. Confirm. The app wipes its local storage and reloads.

**Heads-up:** clearing the cache also re-downloads the fellow data and
photos on the next launch. The session cookie is cleared, so if the
server asks for auth again you'll need your install link (or a fresh
one). The app preserves a small "you've been here before" marker so the
URL still opens the directory directly and a future server outage won't
strand you at the error panel.

---

## Offline behaviour

- Once installed and first-loaded, the directory works fully offline.
- Photos that finished caching are available offline; photos that never
  downloaded show a placeholder until you're back online and the prewarm
  catches up.
- If the server is temporarily unreachable (flaky connection, deploy
  blip), the build badge at the top of the app flips to **"server:
  unreachable."** This is informational — the app keeps working.
- If your session has expired (e.g., you haven't opened the app in a
  long time), the app still opens and shows your cached directory from
  the last time you loaded it. The build badge reads **"server: offline
  · using cache."** You can keep browsing normally. To get fresh data
  (new fellows, updated profiles), visit `/?gate=1` and request a new
  magic link.

---

## Getting help

- **General questions**: ask on one of the fellows channels, or contact
  the EHF Communications Working Group.
- **Bug reports / feature requests**: open an issue on the GitHub repo
  (link on the About page). You'll need to be added to the repo first —
  ask Rich.
- **Install link expired or lost**: request a fresh one from the
  operator.

---

## Privacy

The app ships a dump of fellow contact info and free-text responses. It
is explicitly **not** hosted as a public service — distribution is by
individual invitation. Keep screenshots and data within the fellowship.
