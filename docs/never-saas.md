# Never-SaaS

> **Working definition.** This page is the working draft of a useful
> shorthand for an architectural posture this app embodies. Refine as
> the term gets used in more contexts.

## Definition

A **Never-SaaS** application is one whose runtime contract with the
user contains **no ongoing server dependency for user-authored
data**. The server, if any, is a *delivery channel* — not a
*service*.

A Never-SaaS app MAY contact a server for:

- Initial download / installation of the application
- Application-code updates (a newer version of the app itself)
- Refreshable shared-data updates (new snapshots of public reference
  data the app *reads*, such as a directory the user browses but
  doesn't author)
- Authentication for distribution (a gate that authorizes the user
  to *receive* the bundle — e.g., a magic link)

A Never-SaaS app MUST NOT:

- Store user-authored data on a server
- Sync user state to a server
- Require server connectivity to function after install
- Become unusable when the server is unreachable or taken offline
- Expose per-user read/write endpoints on the server

The server's existence is bounded to bootstrap + occasional update
delivery. Pull the server's plug forever, and an installed
Never-SaaS app keeps working — the user's data is on their device.

Mirroring upstream sources is fine (and common — `fellows_local_db`
mirrors data from a contact database). Mirroring is one-way refresh,
not sync. The user's edits do not flow back upstream.

## The Never-SaaS test

A four-question gut check:

1. After install, can the user disconnect from the internet and use
   the app productively?
2. If the server is taken offline forever, does the app keep working
   (for everyone who already has it installed)?
3. Is the user's authored data on their device only?
4. Does the app ever upload user-authored data anywhere?

If the answers are **yes / yes / yes / no**, it's Never-SaaS.

## Why the term is useful

It collapses a category that would otherwise need a paragraph each
time: *"single-user, local-first, no per-user cloud state,
distributed via a server but not dependent on it."* That's tedious.
*Never-SaaS* is two syllables and reasonably self-explanatory once
defined.

It also flags a specific *architectural commitment* — the choice to
not be a service. The PNA Spec captures this as AC-2 *(no SaaS
surface)*; `fellows_local_db` is built around it. Other apps in the
Personal Network space share the posture, and *Never-SaaS* is the
shorthand that ties them together.

## Platform fitness

Runtime platforms vary in how well they support Never-SaaS apps
with **user-authored data** (groups, notes, tags, edits — the stuff
that can't be regenerated if lost). The matrix isn't uniform.

### Strong fit

- **Native desktop apps** (macOS `.app`, Windows installer or
  `.exe`, Linux native packages or AppImage). Full filesystem
  access, OS-managed app identity that survives across launches,
  no browser-storage quirks, predictable uninstall semantics.
  The user can `cp` their data file, point another tool at it,
  back it up to wherever. Best-of-class.

- **CLI / TUI tools** distributed as single binaries (`curl |
  bash` install, Homebrew, package manager). Filesystem access
  is unrestricted; data is plain files; scripting / piping /
  sync-via-Dropbox all Just Work. Lowest distribution friction.
  The trade-off is the lack of a graphical UI for users who
  want one.

- **Electron / Tauri** (desktop apps built with web technology).
  OS-managed app identity *and* filesystem access *and* a
  browser-derived UI. Bundle weight is the cost; the Never-SaaS
  guarantees are otherwise as strong as native.

### Stretched fit

- **Progressive Web Apps (PWAs).** Workable for Never-SaaS apps
  whose data is **read-only / refreshable / archival** — e.g.,
  a directory the user browses, a manual the user reads, a
  mirror of external information. The browser as runtime is
  fine for these: data comes down with the bundle, the user
  reads it offline, the server-as-delivery-channel posture
  holds.

  PWAs **stretch** when user-authored data enters the picture.
  The practical risks (catalogued in detail in
  [`./ac_decisions_log.md`](./ac_decisions_log.md)'s 2026-05-22
  entries and in
  [`../plans/user_folder_storage.md`](../plans/user_folder_storage.md)):
  - **Browser-isolated storage.** Installing the PWA in two
    browsers on the same device gives the user two independent
    data stores. No cross-browser sync API exists.
  - **PWA install lifecycle is per-browser, not OS-level.**
    Uninstalling a browser destroys that browser's PWA data.
    Multiple installs in macOS Spotlight share the same icon +
    name and can't be visually distinguished without renaming
    the bundles by hand.
  - **`window.showDirectoryPicker` is Chromium-only.**
    Safari/Firefox can't host the "stable file at a known
    path" model that external tools (MCP servers, scripts,
    sync services) need to read the user's data.
  - **PWA install support is patchy by vendor.** Firefox
    dropped desktop PWA install in 2021. Apple's *Add to Dock*
    (macOS 14+) is the only Safari path and is less
    discoverable than Chromium's install affordance.

  `fellows_local_db` is a Never-SaaS PWA with user-authored
  data *and* has pushed the model as hard as a PWA reasonably
  can — user-picked folder for stable storage, per-commit
  folder writes, folder-resident auto-backup ring, in-app push
  to encourage folder mode, documented cross-browser-silo
  behavior. It works for the test group. It is also more
  engineering effort than the same app would have taken in
  any of the *Strong fit* categories.

  **Forward-looking advice.** A new Never-SaaS project with
  user-authored data should default to native desktop or
  Electron/Tauri unless there's a strong reason to be in the
  browser. The PWA path is viable; it's a *stretch* in the
  literal sense — pushing a model toward its edges.

- **Browser extensions.** Ambient access to web pages is the
  killer feature, but storage quotas, no filesystem access,
  and highly browser-specific APIs limit how much real data
  they can own. Workable as an *adjunct* to a Never-SaaS app
  (e.g., a Chrome extension that talks to a desktop daemon
  over local HTTP), less so as the whole app.

### Doesn't apply

- **Pure SaaS web apps.** By definition.
- **Cloud-mandatory mobile apps.** Many App Store apps assume
  sign-in + cloud sync as table stakes. A Never-SaaS posture is
  technically possible but architecturally swimming upstream.

## See also

- [PNA Spec](https://github.com/richbodo/personal_network_toolkit) — the universal architectural commitments AC-2 (*no SaaS surface*) formalizes what *Never-SaaS* names colloquially.
- [`docs/Architecture.md`](./Architecture.md) — `fellows_local_db`'s own AC-2 realization (PWA-with-user-folder).
- [`docs/ac_decisions_log.md`](./ac_decisions_log.md) — concrete decisions where the Never-SaaS posture shaped the architecture.
- [`plans/user_folder_storage.md`](../plans/user_folder_storage.md) — the architecture that closes most of the PWA-as-Never-SaaS gap.
