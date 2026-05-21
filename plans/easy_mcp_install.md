# Easy MCP install for non-technical Mac users

> **Status: ACTIVE.** Decisions locked 2026-05-21 after the planning
> conversation that produced this file and
> [`docs/ac_decisions_log.md`](../docs/ac_decisions_log.md). This plan
> supersedes the rough "two-stage installer with scary-warning UX"
> shape sketched earlier in the conversation; research into MCP
> packaging standards reframed the problem (see § 3).

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

- **Mac desktop only.** Aligns with where most EHF fellows live and
  matches the slice Rich called out in planning.
- **Claude Desktop only.** No Cursor, Continue.dev, Ollama, or other
  MCP clients in v1.
- **Single user, single Mac.** No multi-device sync, no shared MCP
  install across users on one Mac.
- **Apple Silicon + Intel both** — incidental; the chosen mechanism
  doesn't ship CPU-specific binaries.

Out of scope: rewriting the privacy boundary, supporting users
without the PWA installed, Apple Developer Program enrollment as a
prerequisite (see § 3 — `.mcpb` install bypasses Gatekeeper).

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

## 5. The OPFS data-handoff resolution

The single biggest technical question the plan answers is *"how
does data in browser-managed OPFS get to a process Claude Desktop
spawns?"* — because the current
`docs/use_with_claude_desktop.md` walkthrough handwaves it (it
assumes the user has a developer copy of `fellows.db` on disk,
which no end user does).

**Resolution.**

- **`fellows.db` is bundled inside `shared-data-ops.mcpb` at build
  time.** It's the public shared snapshot per the Two-DB boundary;
  safe to ship in every release. Bundle size ~2.5 MB. Refreshing
  the directory = re-downloading the shared bundle (PWA prompts
  when its existing `/build-meta.json` `fellows_db_sha` check
  detects a new snapshot).
- **`relationships.db` is exported from OPFS to `~/Downloads/` by
  the PWA** when the user clicks the Settings button. Re-uses the
  existing `dataProvider.exportRelationshipsBytes()` plumbing. The
  `private-data-ops.mcpb`'s `user_config` block defaults
  `relationships_db_path` to `~/Downloads/relationships.db`; most
  users hit Enter. Refreshing = clicking the same Settings button
  again.
- **No File System Access API** (Safari support is patchy).
  Standard blob-URL `a.click()` download works in every supported
  browser.

This is shippable **without** waiting for
[`user_folder_storage` Phase 2](./user_folder_storage.md) — the
PWA's OPFS remains the source of truth for `relationships.db`; we
provide a recurring export-to-Downloads action. When
`user_folder_storage` Phase 2+ lands and `relationships.db` has a
real filesystem home, the `.mcpb`'s `user_config` default switches
from `~/Downloads/relationships.db` to that path. Zero rework on
the `.mcpb` itself.

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
> **What happens next:** four files will download to your
> Downloads folder (your saved groups + three installer files).
> Claude Desktop will pop up an Install dialog for each installer
> in turn — approve the ones you want, skip the ones you don't.
> When all three install dialogs are done, quit Claude Desktop
> (⌘Q) and reopen it.
>
> [Continue] [Cancel]

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
| [`user_folder_storage.md`](./user_folder_storage.md) | Independent. When Phase 2+ moves `relationships.db` to a user-chosen folder, the `private-data-ops.mcpb`'s `user_config` default changes; no other code change. `.mcpb` can ship before, during, or after. |
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
   refresh-flow indicators.
7. **`docs/use_with_claude_desktop.md` rewrite.** Branch
   `docs/mcpb-walkthrough-rewrite`. Replaces the current
   Terminal-heavy walkthrough with the three-click flow.
8. **E2E test.** Branch `test/e2e-mcpb-setup`. Final gate.

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

- **Parity test should exercise the staged bundle layout, not just `dist/`.** Found-while-fixing in #187 (commits `2807bba`, `91525b5`): two bundle-layout bugs (missing `better-sqlite3` native binding, and `_shared/`/`data/` placed inside `server/` instead of as siblings) reached install because `tests/test_mcpb_parity.py` runs against `mcpb/node/dist/<name>/index.js` with `FELLOWS_DB_PATH` explicitly set. Both conditions are unrealistic — they mask path-resolution bugs that only fire in the staged bundle layout. Either (a) extend the parity test to also exercise `mcpb/node/.staging/<name>/server/index.js` with no env var, or (b) add a separate `tests/test_mcpb_bundle_layout.py` smoke that just spawns `node` against the staging dir and asserts a successful `initialize` + `tools/call get_directory_stats` round-trip. Address before Stage 1 ships — current state has known false-green coverage.

(More items will land here as they emerge.)

---

## Sources (DXT/MCPB research)

- [Anthropic — One-click MCP server installation (Desktop Extensions announcement)](https://www.anthropic.com/engineering/desktop-extensions)
- [`anthropics/dxt` repo (renamed to MCPB)](https://github.com/anthropics/dxt)
- [Issue #89 — Python runtime policy clarification request](https://github.com/modelcontextprotocol/mcpb/issues/89)
- [Issue #84 — Python compatibility check blocks install without system Python](https://github.com/modelcontextprotocol/mcpb/issues/84)
- [Claude Help Center — Getting Started with Local MCP Servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
