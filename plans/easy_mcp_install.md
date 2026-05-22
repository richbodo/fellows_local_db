# Easy MCP install for non-technical Mac users

> **Status: ACTIVE.** Decisions locked 2026-05-21; folder-anchor
> revision 2026-05-22 after user_folder_storage Phase 2 shipped.
> Architectural commitments in
> [`docs/ac_decisions_log.md`](../docs/ac_decisions_log.md)
> (see the 2026-05-22 entries).
>
> **What the revision changes**: § 5 was *"PWA exports to Downloads,
> .mcpb's user_config defaults to ~/Downloads/relationships.db"* —
> a workaround for Phase-1 OPFS-only storage. Now that the user's
> data lives at a stable path (`<picked folder>/Fellows/relationships.db`)
> after Phase 2 shipped (#190–#192), the handoff collapses to *"the
> .mcpb's user_config file picker points at the user's data folder."*
> § 2 Pareto slice tightens to **Chromium desktop** (Chrome / Edge /
> Brave / Arc) — Safari/Firefox don't ship `showDirectoryPicker` and
> can't host the stable-folder anchor; they're a documented
> secondary path. New § 5b covers the browser compatibility matrix
> and the cross-browser-on-one-device data silo.

## 1. Why

We just shipped `docs/use_with_claude_desktop.md` — a walkthrough
that takes a fellow from "PWA installed" to "Claude Desktop can read
my fellows data" in six steps. Every one of the following is a
non-tech-killer:

- **Step 1**: Download project ZIP from GitHub (requires repo access).
- **Step 3**: Open Terminal, paste `python3 -m venv … && pip install
  …`, possibly install Xcode Command Line Developer Tools first.
- **Step 4**: Hand-edit `claude_desktop_config.json` — find the
  outermost `}`, add a comma, paste a JSON block, substitute a
  username string in 8 places.

There is no realistic universe in which a non-technical EHF fellow
completes this without help. The flagship value proposition —
*"draft an invite email to my Climate Action group, don't send"* —
sits behind a fifteen-minute power-user dance for the few who push
through.

This plan replaces that walkthrough's intended audience with a
**non-technical Mac desktop user** whose ceiling is "I can click a
button, open a downloaded file, and click Install in dialogs," and
gives them a path to the same flagship demo.

## 2. Pareto slice (v1 scope)

- **Chromium desktop only** (Chrome, Edge, Brave, Arc, Opera) on
  macOS / Windows / Linux. The "easy" experience hinges on a stable
  filesystem path for `relationships.db`, which requires
  `showDirectoryPicker`. Only Chromium ships it as of 2026. See § 5b
  for the full browser compatibility matrix.
- **Claude Desktop only.** No Cursor, Continue.dev, Ollama, or other
  MCP clients in v1.
- **Single user, single Mac/PC.** No multi-device sync, no shared
  MCP install across users on one machine.
- **Apple Silicon + Intel both** — incidental; the chosen mechanism
  doesn't ship CPU-specific binaries.

**Safari / Firefox desktop users** get a documented *secondary path*
(see § 5b) — they can install the `.mcpb`s but the MCP's view of
their private data is whatever they last manually exported. Not a
"set it up once and forget" experience. Easy MCP for them is gated
on WebKit / Gecko shipping `showDirectoryPicker`; tracked but not
something we can engineer around. Architectural rationale in
[`docs/ac_decisions_log.md` § 2026-05-22 — MCP easy install is Chromium-desktop-first](../docs/ac_decisions_log.md).

Out of scope: rewriting the privacy boundary, supporting users
without the PWA installed, Apple Developer Program enrollment as a
prerequisite (see § 3 — `.mcpb` install bypasses Gatekeeper),
cross-browser sync of the same user's data on the same device (no
browser API supports it; see § 5b).

## 3. Research finding: Anthropic's `.mcpb` (Desktop Extensions)

Anthropic shipped [Desktop Extensions](https://www.anthropic.com/engineering/desktop-extensions)
(`.dxt`, recently renamed `.mcpb` — MCP Bundle) in current Claude
Desktop. Material facts:

- A `.mcpb` is a ZIP archive containing a `manifest.json` + the MCP
  server code. Claude Desktop accepts it via drag-and-drop into
  **Settings → Extensions** or double-click-to-open.
- The install dialog reads `manifest.json` (name, description,
  permissions) and prompts for `user_config` values (e.g. file
  paths) before enabling.
- **`.mcpb` install bypasses macOS Gatekeeper.** The bundle is
  unpacked by Claude Desktop, not exec'd by Finder. No
  "unidentified-developer" warning, no quarantine-bit dance.
- Claude Desktop **does not** require `.mcpb` signing today.
- The install writes Claude Desktop's internal config; no
  `claude_desktop_config.json` hand-editing.
- **However, Claude Desktop has its own install-time warning** for
  any extension that isn't Anthropic-verified — a prominent red
  banner reading *"Installing will grant this extension access to
  everything on your computer. Any developer information shown has
  not been verified by Anthropic."* This is a separate trust layer
  from Gatekeeper (Apple Developer ID signing doesn't address it).
  Tracking the disclosure UX in [issue #186](https://github.com/richbodo/fellows_local_db/issues/186);
  the PWA preamble (§ 7) previews the warning so users aren't
  surprised. Discovered during smoke test of #185.

Two gotchas for Python servers (see
[Issue #84](https://github.com/modelcontextprotocol/mcpb/issues/84),
[Issue #89](https://github.com/modelcontextprotocol/mcpb/issues/89)):

- Claude Desktop bundles a **Node.js runtime** but not a **Python
  runtime**.
- For `server.type: "python"` (or `"uv"`), Claude Desktop's
  compatibility check refuses to install if no system Python is
  detected — even if `uv` is available.

The non-tech-friendly path is therefore **Node-based `.mcpb`** —
Claude Desktop's bundled Node runs the server with zero user
prerequisites. We accept the cost of porting the three servers
from Python to TypeScript to unlock that.

## 4. The plan

### Stage 1 — Three Node-based `.mcpb` files

Port `shared_data_ops`, `private_data_ops`, and `comms` from Python
(`mcp_servers/`) to TypeScript (`mcpb/node/`). Build each as its
own `.mcpb`. Serve all three from prod under the magic-link gate.
PWA Settings → "Set up Claude Desktop integration" sequences the
three downloads + the install preamble (see § 7).

**Why three bundles, not one** — see
[`docs/ac_decisions_log.md` § 2026-05-21](../docs/ac_decisions_log.md).
The short version: the `mcp-exposure:shared+private+comms` axis
pick and AC-MCP-A's exception clause require the three servers to
be independently enableable, and Claude Desktop's Extensions UI
toggles whole bundles, so each server gets its own `.mcpb`.

**Engineering scope.**

- `mcpb/` directory at repo root. Sibling to `mcp_servers/`, not a
  replacement.
- `mcpb/node/` — TypeScript source.
  - `mcpb/node/src/shared_data_ops/` — port of `mcp_servers/shared_data_ops.py`.
  - `mcpb/node/src/private_data_ops/` — port of `mcp_servers/private_data_ops.py`.
  - `mcpb/node/src/comms/` — port of `mcp_servers/comms.py`.
  - Shared utilities for SQLite access (`better-sqlite3`) and
    response shaping live in `mcpb/node/src/_shared/`.
  - `mcpb/node/package.json` — pins `@modelcontextprotocol/sdk` and
    `better-sqlite3`. Devved into each `.mcpb` via `mcpb pack`.
  - `mcpb/node/tsconfig.json`.
  - `mcpb/node/manifests/{shared,private,comms}.json` — three
    Anthropic MCP Bundle manifests. Each declares
    `server.type: "node"`, its tool surface, and a `user_config`
    block where appropriate (only `private` needs the
    `relationships_db_path` prompt; `shared` bundles `fellows.db`;
    `comms` has no DB).
- `mcpb/node/data/fellows.db` — bundled at build time into the
  `shared-data-ops.mcpb` only. ~2.5 MB. Per the Shared-vs-Private
  boundary in [`docs/Architecture.md`](../docs/Architecture.md)
  § Two-DB architecture, fellows.db is the read-only shared
  snapshot — fine to bundle. `relationships.db` is per-user OPFS
  and **never** bundled.
- `build/build_mcpb.py` — installs the `mcpb` CLI (`npm install -g
  @anthropic-ai/mcpb`) if missing, runs `mcpb pack` against each
  manifest, writes `deploy/dist/mcpb/{shared,private,comms}.mcpb`.
- `deploy/server.py` — adds `GET /mcpb/<name>.mcpb` routes,
  auth-gated (same posture as `/fellows.db`). Magic-link session
  required.
- `just build-mcpb` recipe + `just test-mcpb-parity` recipe
  (see § 6).
- `app/static/app.js` — new Settings section *"Claude Desktop
  integration (beta)"*:
  - Single button: *"Set up Claude Desktop integration"*.
  - On click, shows the **preamble dialog** described in § 7.
  - On confirm, exports `relationships.db` via existing
    `dataProvider.exportRelationshipsBytes()` (already wired —
    `app.js:1420` worker provider, `app.js:3667` worker RPC,
    `app.js:2128` `downloadRelationshipsBackup`) as a standard
    `a.click()` download to the user's Downloads, then triggers
    sequential downloads of the three `.mcpb` files.
  - Shows post-download instructions inline.
  - Refresh-relationships flow: clicking the button again
    re-exports `relationships.db` without redownloading the bundles
    (status row shows *"relationships data refreshed"*).
  - Refresh-fellows-directory flow: when the PWA detects a
    directory data update via `/build-meta.json`'s
    `fellows_db_sha`, the integration status row says *"new
    directory data available — re-install shared-data-ops"* and
    offers a button to re-download only the shared bundle.
- `app/static/index.html` — Settings-page markup for the
  integration row + status indicator.
- `docs/use_with_claude_desktop.md` — rewritten from a 6-step
  Terminal walkthrough into a 3-step *click button → open three
  downloaded files → restart Claude Desktop* walkthrough, with
  screenshots.
- `tests/e2e/test_mcpb_setup.py` — exercises the Settings button,
  verifies three `.mcpb` files + `relationships.db` are downloaded,
  parses each `.mcpb` and validates the manifest.
- `tests/test_mcpb_parity.py` — see § 6.

**Acceptance criteria — Stage 1.**

1. On a fresh Mac with **no Python anywhere**, a fellow goes from
   PWA Settings → fully-working Claude Desktop install in **under 5
   minutes**, running *"How many fellows are in the directory?"*
   successfully at the end.
2. Zero Terminal, zero JSON editing, zero file copying inside the
   project tree, zero `<your username>` substitutions.
3. The PWA's preamble dialog (see § 7) is the user's single
   informed-consent point, satisfying AC-MCP-A at the install
   moment.
4. The flagship demo — *"Draft an invite email to my [group] group
   inviting them to meet Thursday at 1pm NZ time. Don't send —
   stage it for me to review."* — works on the first try after
   install.
5. Refresh-relationships flow: clicking the Settings button a
   second time refreshes only `relationships.db`. User sees a
   *"relationships data refreshed"* indicator. No need to re-install
   any `.mcpb`.
6. Refresh-fellows-directory flow: when fellows.db changes on prod,
   the user sees a *"directory data update — re-install
   shared-data-ops"* row and can re-download just that one bundle.
7. Tool-surface parity (see § 6): every tool the Python servers in
   `mcp_servers/` expose returns structurally-equal output to its
   Node counterpart for a fixed test corpus, CI-enforced.

### Stage 2 — Polish (optional, driven by user feedback)

Stage 1 delivers the non-tech goal. Stage 2 is incremental:

- **Code-sign the `.mcpb`** if Anthropic adds signature
  verification to Claude Desktop in a future release. Today this is
  not required; if Rich's Apple Developer ID is in hand by then,
  signing is a small step.
- **Auto-update inside the `.mcpb`** — Claude Desktop's extension
  manager may grow this. If so, manifests declare an update
  endpoint pointed at prod.
- **First-install bundle** — magic-link install landing offers a
  *"Set up Claude Desktop too?"* checkbox alongside *Install app*.
  Adds the integration in one shot rather than two visits. Reuses
  the same preamble + download sequence as the Settings button.
- **Submission to Anthropic's curated MCP directory** —
  probably not, because our bundles include a private fellows.db
  snapshot. Distribution from our prod stays the right call.

## 5. The data-handoff resolution (folder anchor)

The single biggest technical question the plan answers is *"how
does the user's private data get to a process Claude Desktop
spawns?"* — because the current
`docs/use_with_claude_desktop.md` walkthrough handwaves it (it
assumes the user has a developer copy of `fellows.db` on disk,
which no end user does).

**Resolution (post-user_folder_storage-Phase-2).**

- **`fellows.db` is bundled inside `shared-data-ops.mcpb` at build
  time.** It's the public shared snapshot per the Two-DB boundary;
  safe to ship in every release. Bundle size ~2.5 MB. Refreshing
  the directory = re-downloading the shared bundle (PWA prompts
  when its existing `/build-meta.json` `fellows_db_sha` check
  detects a new snapshot).
- **`relationships.db` lives at `<picked folder>/Fellows/relationships.db`**
  on the user's filesystem. The PWA writes there atomically on
  every committed mutation (per user-folder-storage Phase 2, shipped
  in PR #190). The `private-data-ops.mcpb`'s `user_config` exposes
  a `relationships_db_path` file-picker; the user navigates to
  their data folder once during install and points it at
  `Fellows/relationships.db`. From that moment on, the MCP server
  reads the same file the PWA writes — always current, no
  re-export rituals.
- **The MCP install flow no longer needs to export anything.** The
  file the MCP picker points at IS the user's data. This collapses
  the original plan's `dataProvider.exportRelationshipsBytes →
  blob URL → ~/Downloads → user picks the timestamped file → manual
  re-export when stale` dance into a single user_config navigation
  during install.

**For Chromium desktop users with a data folder** (the Pareto
slice in § 2): this is the green path. The PWA prompts via the
folder-push banner (shipped in PR #192) on first launch; user
picks a folder; subsequent MCP install points at that stable
location. The MCP "set it up once and forget" promise holds.

**For Safari / Firefox users**: see § 5b. They get a documented
secondary path that uses the existing `Download my user data`
button + a periodic-re-export discipline.

## 5b. Browser compatibility matrix + cross-browser data silos

| Browser (desktop) | `showDirectoryPicker` | Folder-mode in the app | MCP install path | MCP view stays current? |
|---|---|---|---|---|
| **Chrome / Edge / Brave / Arc / Opera** | ✓ | ✓ | Set up data folder once → `.mcpb` install file-picker points at `<folder>/Fellows/relationships.db`. | ✓ Every PWA commit auto-writes; MCP reads live state. |
| **Safari (macOS)** | ✗ | ✗ — OPFS-only | Click *Download my user data* → file lands in `~/Downloads/relationships-<ISO>.db` → `.mcpb` install file-picker points at that file. | ✗ Stale immediately after any further mutation. User must re-export + re-point. |
| **Firefox (any desktop OS)** | ✗ | ✗ — OPFS-only | Same as Safari. | ✗ Same staleness. |
| **iOS / Android browsers** | n/a | n/a | Claude Desktop doesn't run on these platforms. | n/a |

### Why Safari and Firefox can't host the easy path

The File System Access API the green path depends on
(`showDirectoryPicker` plus the persistent IDB-stored handle
plumbing in `vendor/sqlite-worker.js`'s user-folder-storage
section) only ships in Chromium-based browsers. Safari has
shipped the single-file half of the spec
(`showOpenFilePicker` / `showSaveFilePicker`, Safari 15.2+) but
**not** the directory half. Firefox has shipped none of it.
There is no shipped JS API in either browser that gives a PWA
ongoing read/write access to a user-picked folder. WebKit lists
the directory API as ["in development"](https://webkit.org/status)
but with no announced shipping target as of 2026.

The PWA cannot work around this. The only ways to get
`relationships.db` onto a Safari/Firefox user's filesystem are
(a) the existing `Download my user data` button — a one-shot
snapshot to `~/Downloads/` — and (b) the user dragging the file
out of the auto-backup ring (which only exists in folder mode,
which Safari/Firefox can't enter — so not actually an option).

For the MCP install, the `.mcpb` install dialog's file-picker
accepts any filesystem path. Safari/Firefox users CAN point it
at a downloaded snapshot. The bundle then works against that
snapshot. The catch: the snapshot is frozen at the moment it was
downloaded. Any further PWA mutation diverges the snapshot from
the user's live data. The MCP returns stale results until the
user manually exports again and re-points the install.

### Cross-browser-on-one-device data silos

A separate, related constraint surfaced during the conversation
that produced this revision: **browser storage is per-origin
per-browser on the same device.** A fellow who installs the PWA
in Safari, uses it for a month, then opens the same URL in
Chrome will see a fresh-install empty state — Chrome's OPFS
namespace for `fellows.globaldonut.com` is independent of
Safari's, and the `fellows_authenticated_once` localStorage
marker is also per-browser.

There is no JS API to detect "this user has data for this
origin in another browser on this device." Storage isolation is
the point of per-browser sandboxes. So the PWA cannot
automatically notice cross-browser state — and cannot
automatically migrate it.

What this looks like in practice for a Mac user who installs in
multiple browsers:

| Install order | What they see |
|---|---|
| Safari → Chrome | Chrome appears empty. Safari groups are invisible there. To migrate: Safari → Settings → *Download my user data* → save the file → Chrome → Settings → *Restore from a file* → pick that file. From then on, the two browsers diverge again. |
| Chrome (with folder mode) → Safari | Safari appears empty. Safari can't read Chrome's folder file (no API). To migrate: same export-from-A → import-into-B recipe. Safari then has a frozen copy of Chrome's state at export time. |
| Two Chromium browsers (Chrome + Brave) on the same folder | Both browsers' OPFS buffers diverge from the folder file; both write atomically; last-write-wins. **Single-writer assumption per [`plans/user_folder_storage.md` § Non-goals](./user_folder_storage.md). Real data loss possible.** Don't share folders across browsers in one session. |
| Two Chromium browsers on DIFFERENT folders | Each browser has its own folder + its own data. No conflict, but also no sync. Same export-from-A → import-into-B recipe to consolidate. |

### What we DO (and don't) build to mitigate this

**Build** (Phase 2-follow-up scope — separate small PR after this
plan revision):

- A *"Migrate from another browser"* affordance in Settings →
  Restore from backup, linking to a docs recipe (export from
  source browser, restore in this browser).
- Updated `docs/users_manual.md` "Where your data is stored"
  section explicitly warning about per-browser silos +
  recommending Chromium for fellows who want MCP.
- The folder-push banner already covers the "you haven't picked
  a folder yet" case for Chromium users; no change needed there.

**Don't build** (architectural commitment per the AC log entry):

- No auto-detection of cross-browser state (no API).
- No server-side mirror (violates AC-2).
- No periodic-re-export-prompt for Safari (worse UX than the
  current stale-after-export reality).
- No cross-browser file-sync hack (every approach we sketched
  produces dueling writes; Web Locks can't coordinate
  cross-browser).

### Recommended browser for fellows who want MCP

Chrome, Edge, Brave, or Arc on desktop. The install walkthrough
(written in `docs/use_with_claude_desktop.md`, rewritten in a
follow-up PR) leads with this recommendation. Fellows on Safari
who want MCP face a clear choice: switch to a Chromium browser
for the fellows app (and accept that their data lives in that
browser's storage going forward), or stay on Safari and accept
the manual-re-export grind.

## 6. Dual-codebase governance (Python + Node)

After Stage 1 ships, we maintain **two implementations** of the same
MCP surface:

- `mcp_servers/` (Python) — used by Rich, by Claude Code/Cursor +
  uv setups, by AI clients that want programmatic access, by audit
  and test workflows. **Permanent surface; not deprecated.**
- `mcpb/node/` (TypeScript) — the Claude Desktop install path for
  end users. The `.mcpb` bundles are this surface's release
  artifact.

Both target the same PNA spec contracts
([`mcp-shared-data-ops.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/),
`mcp-private-data-ops.schema.json`,
`mcp-comms.schema.json`). The contracts are the conformance anchor.

**The risk that makes dual-codebase dangerous:** silent behavioral
drift — a bug fix lands in Python but not Node, or a privacy
boundary tightens in one but not the other. Without a structural
backstop, the boundary depends on humans staying in sync.

**The governance mitigation:** a parity test in CI that runs the
same input corpus against both implementations and asserts
structurally-equal output.

- `tests/test_mcpb_parity.py` — for each tool defined in the spec
  contracts, runs a fixed input corpus against (a) the Python
  server via the existing `mcp_servers/.venv` and (b) the Node
  server via the built `.mcpb`'s entry point.
- Outputs compared structurally (modulo intentionally-variable
  fields like staging IDs in `comms.stage_email`).
- Differences fail CI.
- Required to pass before any change in either `mcp_servers/` or
  `mcpb/node/` merges.

This converts dual-codebase from a *risk* into a *cost*. The cost
is real (parity tests are slower than unit tests; some divergences
will require thought to reconcile) but bounded.

**If the parity test ever becomes load-bearing for a privacy
constraint** (e.g., catches a case where Python redacts an email
that Node doesn't), that's the signal to either fix the divergence
or deprecate one implementation. Don't disable the test to ship
faster.

## 7. The three-bundle UX: the preamble dialog

Three `.mcpb` files means three install dialogs from Claude
Desktop. To keep this from feeling like spam, the PWA Settings
button runs a **preamble dialog first** — the user sees the
boundary, gives one informed consent, then the three install
dialogs become a sequence they already understand.

**Preamble copy (draft, refine in implementation):**

> ### Set up Claude Desktop integration
>
> **Before you start:** make sure you've set up a data folder
> (Settings → Data folder → Choose data folder…) and you're on
> Chrome, Edge, Brave, or Arc. If you're on Safari or Firefox, the
> MCP integration works differently — see the *Manual setup* link
> at the bottom of this dialog.
>
> This will install three extensions into Claude Desktop so it can
> read your fellows data and help you compose group emails. Each
> extension covers a different boundary; you can install just the
> ones you want.
>
> 1. **Fellows directory (Shared).** Lets Claude read the public
>    fellows directory: names, bios, contact info, search.
>    Recommended.
>
> 2. **Your saved groups (Private).** Lets Claude read your saved
>    groups, group members, and any notes you've added. This data
>    is private to you and never leaves your device through the
>    Fellows app — but when Claude reads it, it goes to Claude's
>    servers (Anthropic). If that's not OK for you, skip this
>    extension and Claude will only have access to the directory.
>
> 3. **Email staging (Communications).** Lets Claude prepare draft
>    emails to your groups and hand them back to you for review.
>    Claude never sends mail itself — drafts open in your mail app
>    with To, Subject, and Body filled in, and you click Send.
>
> **One thing to expect during install:** Claude Desktop will show a
> red warning banner for each of these extensions saying *"Installing
> will grant this extension access to everything on your computer..."*
> That warning fires for any extension that isn't Anthropic-verified —
> it's not specific to ours and doesn't mean anything is wrong. The
> extensions only read the fellows data files they were configured
> with; they don't have wider access than you grant them. Click
> **Install** to proceed.
>
> **What happens next:** three `.mcpb` installer files will download.
> Claude Desktop will pop up an Install dialog for each in turn —
> approve the ones you want, skip the ones you don't. For the
> **Your saved groups** extension, the install dialog will ask you
> to pick a file: navigate to your data folder → **Fellows** →
> **relationships.db**. When all three install dialogs are done,
> quit Claude Desktop (⌘Q) and reopen it.
>
> [Continue] [Cancel] [Manual setup (Safari / Firefox)]

This dialog is the AC-MCP-A informed-consent moment translated
into plain language. It's also where we honestly disclose that the
Private-data extension means *"Claude's servers see your group
data when Claude uses this."* The disclosure mirrors the existing
*A note on privacy* section in `docs/use_with_claude_desktop.md`
and the *Cloud LLM caveat* in `mcp_servers/README.md`.

Copy will be reviewed in implementation; the structure (the
three-bundle boundary + the consent moment + the per-bundle
opt-in + the install-warning preview) is the load-bearing part.
The install-warning preview specifically is tracked in
[issue #186](https://github.com/richbodo/fellows_local_db/issues/186) —
the wording above is a first draft to be refined with a real
screenshot once the Settings UI is in implementation.

## 8. Interactions with in-flight plans

| Plan | Interaction |
|---|---|
| [`user_folder_storage.md`](./user_folder_storage.md) | **Load-bearing prerequisite** (post-2026-05-22 revision). Phase 2 shipped (#190 per-commit folder writes, #191 backup ring move, #192 settings UI push). The MCP install plan now anchors `relationships.db` discoverability on the user's data folder — see § 5 and § 5b. For Chromium-desktop users the `.mcpb` install file-picker just navigates to `<folder>/Fellows/relationships.db`; for Safari/Firefox users (no folder mode available) the secondary path uses the existing *Download my user data* button. |
| [`opt_in_directory_data_updates.md`](./opt_in_directory_data_updates.md) | Tight coupling on the refresh signal. When the PWA detects a new `fellows.db` on the server, the Settings-page integration row mirrors the *"Directory Data update available"* affordance, with a button that re-downloads only `shared-data-ops.mcpb` (which carries the new snapshot). Both flows read `/build-meta.json`'s `fellows_db_sha`. |
| [`local_first_worker_architecture.md`](./local_first_worker_architecture.md) | Already-shipped Phase 1 cutover means `exportRelationshipsBytes` lives in the worker, not the page. Stage 1 reuses the existing worker RPC — no new surface required. |
| [`multi_tab_ownership_takeover.md`](./multi_tab_ownership_takeover.md) | Independent. `.mcpb` servers run as Claude Desktop subprocesses, fully outside the browser-tab worker-ownership model. |
| [`auth_debug_improvements.md`](./auth_debug_improvements.md) | The `/mcpb/<name>.mcpb` routes are auth-gated the same way `/fellows.db` is. Reuses existing magic-link / session-cookie gate. |

## 9. Risks

- **Claude Desktop changes the `.mcpb` format.** Anthropic already
  renamed `.dxt` to `.mcpb`; another rename is plausible.
  Mitigation: treat `.mcpb` spec as load-bearing-but-not-frozen;
  the build pipeline is a thin wrapper around `mcpb pack` so
  changes are localized to one file.
- **Claude Desktop version skew.** Older Claude Desktop versions
  may not support `.mcpb` at all. Mitigation: surface the
  version-incompatibility error from Claude Desktop's install
  dialog back to the PWA's status row (so the user sees *"please
  update Claude Desktop and try again"* rather than a silent
  failure).
- **Parity-test maintenance becomes a chore.** Some divergences
  will require reconciliation work. Mitigation: keep the input
  corpus small and contract-aligned; resist growing it
  speculatively. The test exists to catch privacy-boundary drift,
  not to enumerate every behavior.
- **Node port introduces a Node toolchain to the repo.** Today the
  project is Python + vanilla JS; `mcpb/node/` adds npm, `tsc`,
  and a JS test runner. Mitigation: confined to `mcpb/node/` (a
  sibling of `mcp_servers/`, both off the app's main stdlib path).
  The CLAUDE.md exception already exists for `mcp_servers/`; the
  `mcpb/` directory extends the same carved-out boundary.
- **`relationships.db` schema drift across PWA versions.**
  `RELATIONSHIPS_SCHEMA_VERSION = 1` today. If we bump it without
  a migration in the `.mcpb`, the Node server reads stale data.
  Mitigation: bake the expected schema version into
  `private-data-ops.mcpb`; refuse to start with a clear error
  message and a *"re-install the integration"* nudge.
- **Three install dialogs may still feel like spam to some users.**
  Mitigation: the preamble dialog (§ 7) frames it as expected and
  per-extension-optional. If post-launch feedback says it's too
  much, the fallback is one combined bundle accepting the
  architectural cost — and documenting that flip in
  `docs/ac_decisions_log.md` as a follow-up entry.
- **Privacy: an installed `.mcpb` still leaks fellows data to
  Anthropic's cloud when used.** Already covered in current
  users-manual privacy section; carry the same disclosure into the
  preamble (§ 7) verbatim.

## 10. Non-goals

- iOS / Android — Claude Desktop is not there.
- Windows / Linux — out of v1 Pareto slice.
- Other MCP clients (Cursor, Continue.dev, Ollama, mcp-cli).
- A locally-hosted-model setup wizard — solving the AC-MCP-A cloud
  caveat is a separate plan.
- Auto-update from inside the `.mcpb` (Stage 2 polish, optional).
- A *full* native macOS `.app` or `.pkg` wrapper — `.mcpb` makes
  this unnecessary.
- Apple Developer Program enrollment as a prerequisite — `.mcpb`
  install bypasses Gatekeeper. Rich's ongoing Dev ID work remains
  useful for the broader app's distribution posture but doesn't
  gate this plan.
- Deprecating `mcp_servers/` — explicitly kept as a permanent
  surface for power users and AI audit workflows.

## 11. Decisions made during planning

Captured in the architectural decisions log:

- [2026-05-21 — MCP servers ship as three separate `.mcpb` files,
  not one consolidated bundle](../docs/ac_decisions_log.md#2026-05-21--mcp-servers-ship-as-three-separate-mcpb-files-not-one-consolidated-bundle)
- [2026-05-22 — MCP easy install is Chromium-desktop-first; Safari / Firefox get a documented secondary path; cross-browser-on-one-device data silos are accepted, not engineered around](../docs/ac_decisions_log.md#2026-05-22--mcp-easy-install-is-chromium-desktop-first-safari--firefox-get-a-documented-secondary-path-cross-browser-on-one-device-data-silos-are-accepted-not-engineered-around)

Decisions internal to this plan (don't rise to architectural-log
level):

- **Skip the Python-`.mcpb` intermediate stage.** Original plan had
  it as Stage 1 to ship fast. Cut because (a) Claude Desktop's
  Python compat check refuses install without system Python ([Issue #84](https://github.com/modelcontextprotocol/mcpb/issues/84)),
  defeating the "non-tech" goal; (b) Anthropic's direction is Node-first
  Python-second-class, so investment in a Python bundle would age
  poorly; (c) keeping `mcp_servers/` as a Python surface (below)
  already serves the audience that benefits from Python.
- **Keep `mcp_servers/` Python source permanently.** Used by Rich,
  by Cursor + uv power users, by future programmatic AI clients,
  by audit/test workflows. Pairs with the parity-test governance
  in § 6 to make dual-codebase safe.
- **Distribution is auth-gated from prod.** Public hosting would
  let a fellow forward the `.mcpb` (with bundled `fellows.db`) to
  a non-fellow who could install it and read the data without
  ever authenticating. The data must not leak.
- **PWA discovery is Settings-only** (not About page, not magic-link
  landing in v1). Settings is where the existing "Download a
  backup" affordance lives — the natural home. First-install
  bundling is Stage-2 polish.

## 12. Phasing summary

| Stage | Ship signal | Audience reached | Engineering days |
|---|---|---|---|
| **Stage 1 — Three Node `.mcpb` files + PWA Settings UI** | Three `.mcpb` files install cleanly in Claude Desktop on a fresh Mac with no Python; PWA Settings button triggers downloads + preamble; parity test green in CI. | ~95% of Mac Claude Desktop fellows. The non-tech goal. | ~5-8 |
| **Stage 2 — polish** | Optional; driven by feedback. Code signing if Anthropic adds signature verification; first-install bundle on magic-link landing; etc. | Long-tail. | ad-hoc |

### Suggested PR sequence for Stage 1

1. **This plan + decision log.** Branch `plan/easy-mcp-install`.
   Review and merge before implementation.
2. **`mcpb/node/` scaffolding + first server port.** Branch
   `feat/mcpb-comms-port`. Port `comms.py` first — no DB, smallest
   surface, exercises the build pipeline end-to-end. Includes
   `build/build_mcpb.py`, `just build-mcpb`, and the first parity
   test case.
3. **`shared-data-ops` port + `fellows.db` bundling.** Branch
   `feat/mcpb-shared-data-ops`. Extends parity test.
4. **`private-data-ops` port.** Branch `feat/mcpb-private-data-ops`.
   Extends parity test.
5. **`deploy/server.py` `/mcpb/<name>.mcpb` routes.** Branch
   `feat/mcpb-prod-routes`. Auth-gated.
6. **PWA Settings UI + preamble dialog.** Branch
   `feat/mcpb-settings-ui`. Includes the user-facing wiring and the
   refresh-flow indicators. Per the 2026-05-22 revision: the
   preamble checks for a configured data folder + a Chromium
   browser before offering the easy path; Safari/Firefox users get
   the secondary-path link instead. The `user_config.relationships_db`
   default uses the path the PWA knows about (`<folder>/Fellows/relationships.db`)
   for the Chromium user. Addresses [#186](https://github.com/richbodo/fellows_local_db/issues/186)
   install-warning preview in the same PR.
7. **`docs/use_with_claude_desktop.md` rewrite.** Branch
   `docs/mcpb-walkthrough-rewrite`. Replaces the current
   Terminal-heavy walkthrough with the three-click flow. Per the
   2026-05-22 revision: leads with the Chromium-only recommendation,
   documents the Safari/Firefox secondary path with re-export
   discipline, references the *"migrate from another browser"*
   recipe.
8. **"Migrate from another browser" affordance** (small, separable).
   Branch `feat/migrate-from-another-browser`. Adds the inline link
   in Settings → Restore from backup pointing to the
   `docs/users_manual.md` recipe. No detection logic — just
   discoverability for users who installed in multiple browsers.
9. **E2E test.** Branch `test/e2e-mcpb-setup`. Final gate.

Each PR is independently reviewable + revertable. The parity test
grows incrementally across PRs 2-4.

## 13. End-of-Stage-1 polish checklist

Working scratchpad for found-in-implementation realities and small
documentation items that should land before Stage 1 ships. Items
accumulate as work proceeds — when the list stabilizes, it becomes
the work-plan for the final-polish PR (somewhere around § 12 step
8). Each item should link a GH issue if it warrants tracking
beyond this file.

- **[#186](https://github.com/richbodo/fellows_local_db/issues/186) — install-warning disclosure UX.** Claude Desktop shows a red *"access to everything / not Anthropic-verified"* banner during `.mcpb` install. Apple Developer ID code signing does not address it (different trust layer). The realistic resolution is the PWA preamble previewing the warning so users aren't surprised; copy lives in § 7 above. Address in the `feat/mcpb-settings-ui` and `docs/mcpb-walkthrough-rewrite` PRs.

- ✅ **Parity test exercises the staged bundle layout.** Resolved in the private-data-ops PR. `tests/test_mcpb_parity.py` now includes `test_staged_shared_bundle_default_resolution` and `test_staged_private_bundle_default_resolution` which spawn `mcpb/node/.staging/<name>/server/index.js` with no env-var overrides and assert default path resolution Just Works. Both bugs from #187 would have been caught here.

- **"Migrate from another browser" affordance.** Browser storage is per-origin-per-browser; a user who installs the PWA in Safari then opens it in Chrome sees an empty state. § 5b documents the workaround (export-from-source-browser → import-into-this-browser via existing Settings → Restore from a file). The affordance: a small inline link in Settings → Restore from backup labeled *"Migrating from another browser? See the recipe"* that points at the docs section. No detection (no API for it), just discoverability. Address as a small standalone PR before the MCP install walkthrough rewrite.

- **`docs/use_with_claude_desktop.md` rewrite** — the existing 6-step Terminal walkthrough becomes a 3-step click-button-and-open-files flow. Must reflect the Chromium-only easy path + the Safari/Firefox secondary path explicitly. Tracked as PR step 7 in § 12 above.

(More items will land here as they emerge.)

---

## Sources (DXT/MCPB research)

- [Anthropic — One-click MCP server installation (Desktop Extensions announcement)](https://www.anthropic.com/engineering/desktop-extensions)
- [`anthropics/dxt` repo (renamed to MCPB)](https://github.com/anthropics/dxt)
- [Issue #89 — Python runtime policy clarification request](https://github.com/modelcontextprotocol/mcpb/issues/89)
- [Issue #84 — Python compatibility check blocks install without system Python](https://github.com/modelcontextprotocol/mcpb/issues/84)
- [Claude Help Center — Getting Started with Local MCP Servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
