# Plan — AI write proposals for the Private DB (propose/dispose machinery, groups first)

**Status:** ⏸️ **DEFERRED — richer demonstrator, NOT on the critical path.** **Created:** 2026-06-03.

> **This is one satellite of the User-Mediation Arc; the spine is
> [`pna_toolkit_user_mediation_contribution.md`](pna_toolkit_user_mediation_contribution.md).** Decision
> recorded 2026-06-08: the user-mediation invariant is demonstrated **now** via the MVD path (already-green
> fellows proofs) + PRM's built propose→apply loop — *without* building this feature. This feature would
> add a *third* mediated boundary (AI-proposed group writes, the cleanest single-design propose→diff→dispose
> loop) and is worth building **only if it earns product value on its own**. The design below stands; just
> don't treat it as a prerequisite for the upstream mechanism. See arc §4 (PRM) and §5 (this feature's role).

Extends fellows's MCP Private surface from **read-only** (today:
`mcp_servers/private_data_ops.py`, `mode=ro`, groups only) to **write-via-proposal**:
an AI client may *propose* changes to `groups` / `group_members`, but it can never
write `relationships.db`. The user reviews a deterministic diff **in the workspace**
(not the AI interface) and an explicit workspace action applies it. This is the
**review-required** tier of the PRM safe-write model
([`../../prm/docs/prm-feature-spec.md` § Safe AI writes to private data](../../prm/docs/prm-feature-spec.md))
realized under fellows's `opfs-sqlite-wasm` storage substrate, and a direct
generalization of fellows's already-conformant **AC-MCP-B** (MCP *stages*; the
workspace *launches*) from comms to data writes.

---

## 1. The one architectural fact that shapes everything

PRM lets its MCP server write the private store because PRM picks
`native-sqlite-via-filesystem` with a local daemon mediating one on-disk file.
**Fellows picked `opfs-sqlite-wasm`, so it has no second writer to give:**

- `relationships.db` is owned **exclusively** by the worker (AC-3). An external
  MCP process cannot reach it off-folder at all (CST-PWA-SANDBOX-SEALED).
- Even in folder mode, the worker treats the folder file as canonical by
  hydrating OPFS from it on boot and **serializing the whole DB back atomically
  on every commit** under the `fellows-relationships-folder-write` Web Lock. That
  lock is a *browser* lock; it cannot coordinate with an OS process. A direct
  external write to the file is silently clobbered by the worker's next commit.

Therefore **direct MCP writes to `relationships.db` are rejected on concurrency
grounds, independent of the integrity argument.** The MCP server writes a
**proposal file** to a folder-resident inbox; the **worker is the sole applier**.
There is still exactly one writer of `relationships.db` (the worker) and exactly
one writer of the inbox (the MCP server). No shared lock required — ownership is
split per file.

### Why the inbox is a folder file (and not anything else)

The MCP process and the browser have **no IPC channel** (stdio MCP is
client↔server; the browser is not the client), CSP `connect-src 'self'` forbids
the PWA from fetching a localhost MCP listener, and proposals-as-DB-rows hit the
clobber above. The user's chosen folder is the **only** medium both processes can
touch. The MCP server is already configured with the path to the folder's
`relationships.db`; the inbox is a sibling directory next to it.

### Scope: this feature is Chromium-folder-mode-only (correctly)

- **Mobile (Safari/Firefox/OPFS-only):** no desktop MCP client + OPFS is
  unreachable → feature does not exist. Honest, gated.
- **Desktop Chromium off-folder:** no folder-resident inbox → propose path
  refuses; workspace has nothing to review.
- **Desktop Chromium folder mode:** full feature.

This is the private-data capability gate again, and a deliberate incentive to
connect a folder (→ Chromium).

### No cloud-vs-local tier distinction in v1

Groups are **review-required**, so a human gates every change in the workspace
diff regardless of which model authored the proposal. The cloud/local split only
matters for *auto-applied* tiers (append-only / free-write), which v1 does not
build. Reads remain the cloud-LLM privacy concern (EX-CLOUD-LLM warnings,
unchanged). Writes add an **integrity/manipulation** concern, defended by the
review gate for everyone.

---

## 2. Components

### A. MCP server (`mcp_servers/private_data_ops.py`) — propose-only, never writes the DB

- **Keep `mode=ro` on `relationships.db` forever.** Proposals are *validated* by
  reading (resolve member `record_id`s against `f.fellows`, confirm a target
  group exists) and *written to a different file*. The read-only connection stays
  the structural proof that no direct DB mutation can occur.
- **New write-intent tools** (no DB write — they author a changeset file):
  - `propose_create_group(name, note?, member_record_ids?)`
  - `propose_update_group(group_id, name?, note?)`
  - `propose_add_members(group_id, member_record_ids)`
  - `propose_remove_members(group_id, member_record_ids)`
  - `propose_delete_group(group_id)`
  - (Optionally one general `propose_group_changeset(ops[])`; the typed wrappers
    are friendlier for the model and easier to validate.)
- **New read tools** so the AI can close the loop with the user:
  - `list_pending_proposals()` → ids + summaries + status
  - `get_proposal(id)` → full changeset + status (`pending`/`applied`/`rejected`/`superseded`)
- **Inbox location:** `<dir(relationships.db)>/proposals/`. Configurable via
  `FELLOWS_PROPOSAL_INBOX`; defaults to the sibling dir. If the inbox dir does
  not exist / is not writable (off-folder, or read-only export), the propose
  tools **refuse** with a message pointing at folder setup — they never silently
  no-op.
- **Atomic file write:** write `proposals/<id>.json.tmp` then rename to
  `proposals/<id>.json` so the worker never reads a half-written file.
- **Changeset schema (JSON):**
  ```jsonc
  {
    "schema": "fellows.proposal/1",
    "id": "<uuid>",
    "created_at": "<iso8601>",
    "author": { "client": "claude-desktop", "model": "<if known>" },
    "base": { "workspace_uuid": "<from settings>", "write_generation": <int> },
    "summary": "Human-readable one-liner the workspace shows first.",
    "ops": [ { "op": "create_group", "name": "...", "note": "...", "members": ["rec_..."] } ],
    "status": "pending"
  }
  ```
  `base.write_generation` is read from the `settings` table at propose time. The
  worker uses it for **conflict detection at apply time** (PRM's apply-time
  conflict check): if the DB has advanced past `base`, the proposal is flagged
  `stale` and must be re-reviewed against current state.

### B. Worker (`app/static/vendor/sqlite-worker.js`) — sole applier

- **Discover:** new RPC `listPendingProposals()` enumerates
  `folderRecord.parentHandle.getDirectoryHandle(subfolderName)` → `proposals/`,
  parses each `*.json` with `status == "pending"`. Run on boot **and on a periodic
  re-scan** while the workspace is open (decision: a proposal authored mid-session
  appears without a reload), plus on demand. Off-folder it returns `[]` (no
  handle, nothing to scan).
- **Apply:** new RPC `applyProposal(id)`:
  1. Re-read the changeset from the folder (source of truth, not a page copy).
  2. **Re-validate** ops against the *current* DB; check `base.write_generation`
     vs current. On mismatch → return `STALE_PROPOSAL` (do not apply).
  3. **Snapshot first** — reuse the existing backup ring
     (`maybeBackupRelationshipsDb` path / `listRelationshipsBackups`) to force a
     pre-apply snapshot (realizes AC-9 / PRM "snapshot before any apply").
  4. Apply ops in one transaction inside the existing folder-write path under the
     `FOLDER_WRITE_LOCK_NAME` Web Lock; bump `write_generation`.
  5. **Audit:** append one line to `proposals/applied.jsonl` (append-only audit
     log: proposal id, ops, applied_at, resulting write_generation).
  6. Move the changeset to `proposals/applied/<id>.json` with `status: "applied"`,
     so `list_pending_proposals` (MCP) and the badge clear. **Retention: keep
     applied history forever** (decision — the volume is trivial for this app and
     it's the user-readable audit trail; no ring pruning).
- **Reject:** new RPC `rejectProposal(id, reason)` → mark `status: "rejected"`,
  audit line, no DB change.
- **Structural rule:** the worker is the only code that mutates `relationships.db`
  from a proposal. The MCP surface exposes **no** apply path — "absent tool +
  `mode=ro`" are the two independent locks (mirrors PRM's "foreign key + absent
  tool", and fellows's own existing discipline).

### C. Page / dataProvider (`app/static/app.js`) — the deterministic review UI

- **New route `#/proposals`** (and a badge on the nav when
  `listPendingProposals()` is non-empty, refreshed by the periodic worker
  re-scan): list pending proposals, each rendering a
  **deterministic before/after diff** — group name/note changes; member adds /
  removes with fellow names resolved from `fellows.db` (so the user reads "Add
  Jane Doe, Remove John Smith", never raw `record_id`s). `escapeHtml()` on every
  AI-authored string (the changeset is untrusted input).
- **Controls:** Approve all / approve some (per-op checkboxes) / edit / reject.
  Approve → `worker.applyProposal(id)`; show the `STALE_PROPOSAL` re-review state
  if the DB moved underneath it.
- **Defense-in-depth:** the `dataProvider` exposes the apply path only through the
  worker RPC; no page-side direct write. Apply is refused off-folder
  (`refuseIfBrowseOnly`, already shipped in PR #244) — belt and suspenders.

### D. Substrate (reuse what exists)

- **Snapshot-before-apply:** the 5-slot backup ring already in the worker.
- **Append-only audit log:** `proposals/applied.jsonl` in the folder.
- **Changesets as JSON files:** the diff renders from them directly.
- No VCS — same reasoning PRM records (canonical store is binary SQLite; git
  diffs are useless; review is one-at-a-time against current state).

---

## 3. Implementation sequence (each PR shippable; keep `just test-fast` green)

### PR A — changeset format + MCP propose/read tools (no worker, no UI yet)
- Implement the propose/list/get tools in `private_data_ops.py`, inbox
  resolution, atomic file write, validation, refusal off-inbox.
- **Tests (`tests/test_private_data_ops.py`):**
  - `propose_*` writes a well-formed changeset file; `mode=ro` connection never
    mutates `relationships.db` (assert DB bytes unchanged).
  - inbox-absent → propose **refuses** (negative test).
  - `list_pending_proposals` / `get_proposal` round-trip.
  - changeset validates against `fellows.proposal/1` (member `record_id`s must
    resolve; unknown group_id rejected).

### PR B — worker apply/reject/list + audit + snapshot (the load-bearing half)
- `listPendingProposals` / `applyProposal` / `rejectProposal` RPCs; conflict
  detection via `write_generation`; pre-apply snapshot; `applied.jsonl`.
- **Tests (`tests/e2e/test_ai_write_proposals.py`):**
  - apply: pending changeset → group mutation lands; `write_generation` bumps;
    audit line written; status flips to `applied`.
  - **negative:** `applyProposal` with a stale `base.write_generation` returns
    `STALE_PROPOSAL` and does **not** mutate (the core integrity guard).
  - **negative:** off-folder, `listPendingProposals` → `[]` and `applyProposal`
    refuses (no folder handle).
  - reject leaves the DB untouched and audits.
  - malformed / oversized changeset is refused, not partially applied.

### PR C — workspace review UI (`#/proposals` + badge)
- Diff rendering, approve/some/edit/reject, stale re-review state, `escapeHtml`.
- **Tests:** e2e drives the worker via `window.__dataProvider`; render diff,
  approve → DB changes; reject → no change; stale → re-review prompt.
- **Docs:** `docs/users_manual.md` (new review flow — required by the UI/UX
  convention), `docs/use_with_claude_desktop.md` (new tools + the folder
  requirement), `mcp_servers/README.md`.

### PR D — attestation + upstream
- `docs/Architecture.md`: new MCP-table tools; **realize PRM's proposed
  `AC-PRM-E` / `AC-PRM-F` directly** (decision) — fellows becomes the second
  design demonstrating the tiered safe-write model, which strengthens the case to
  land those ACs in PNT. Cite the per-tier realization (`review-required` for
  groups in v1) and tighten `AC-MCP-A` accordingly. Honest status + resolvable
  test refs (enforced by `tests/test_attestation_has_evidence.py`).
- Feed the demonstrated design back to PNT alongside PRM's contribution. **Note:**
  until `AC-PRM-E/F` are accepted upstream, these rows carry a provisional marker
  (the AC numbers are PRM-proposed, not yet in the spec) — same pattern fellows
  already uses for `EX-*` / `CST-*` that ride upstream with their demonstrating
  design. v1 just needs enough usability to make the upstream case real.

> Batching: A→B→C are sequential (the guarantee isn't user-visible until C, but
> B is where it becomes *true*). D lands with or just after C.

---

## 4. Out of scope / deferred
- **Append-only and free-write tiers** (`fellow_notes` / `fellow_tags`
  enrichment, the autonomous gatherer). v1 is review-required for `groups` only.
  When added: `fellow_notes` is the natural free-write field; auto-applied tiers
  should require a **local** model while EX-CLOUD-LLM is active.
- **Local-AI capability** in-app — separate, larger effort; would change the
  cloud/local calculus for higher tiers.
- **Mobile / OPFS-only / off-folder** — feature absent by construction; no work
  beyond the honest refusal + a folder-setup pointer.
- Direct MCP DB writes / a coordination protocol with the worker — **rejected**
  (§1); do not revisit without a daemon-style single writer.

---

## 5. Decisions (resolved 2026-06-03)
1. **Proposal granularity** — **typed per-op tools** (`propose_create_group`,
   `propose_add_members`, …). No general `ops[]` tool in v1.
2. **Discovery UX** — **boot scan + periodic re-scan** while the workspace is
   open, driving the nav badge; mid-session proposals appear without a reload.
3. **Applied-changeset retention** — **keep forever** in `proposals/applied/`;
   volume is trivial for this app and it's the audit trail. No ring pruning.
4. **Attestation home** — **realize `AC-PRM-E/F` directly** (provisional/PRM-
   proposed markers until accepted upstream); fellows v1 is the second demonstrator
   and the usability lever to get those ACs recognized in PNT soon.
