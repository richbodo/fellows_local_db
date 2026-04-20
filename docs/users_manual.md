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

**Heads-up:** clearing the cache logs you out of the app on that device.
You'll need the original install link (or a fresh one) to re-enter. The
app preserves a small "you've been here before" marker so a future
server outage won't strand you at the loud error panel — that marker is
also cleared.

---

## Offline behaviour

- Once installed and first-loaded, the directory works fully offline.
- Photos that finished caching are available offline; photos that never
  downloaded show a placeholder until you're back online and the prewarm
  catches up.
- If the server is temporarily unreachable (flaky connection, deploy
  blip), the build badge at the top of the app flips to **"server:
  unreachable."** This is informational — the app keeps working.

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
