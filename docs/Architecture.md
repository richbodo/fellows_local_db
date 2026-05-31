# Architecture (fellows_local_db)

This document is fellows_local_db's **specialization-and-conformance layer**: it declares which version of the PNA Spec this repo conforms to, names the axis picks fellows has made, and catalogs the fellows-specific values that the spec leaves to each implementation (HTTP routes, schema, worker constants, debug placeholders, distribution tunables).

Universal PNA architecture — vocabulary, goals, the two-store ownership split, the worker-owned-OPFS rule, the version-handshake contract, the universal ACs — lives in the [PNA Spec](https://github.com/richbodo/personal_network_toolkit/blob/main/PNA_Spec.md) at the [personal_network_toolkit](https://github.com/richbodo/personal_network_toolkit) repo. This file does not restate it.

---

## Spec conformance

**Spec-Version:** [0.1 (draft)](https://github.com/richbodo/personal_network_toolkit/blob/main/CHANGELOG.md)
**Use case:** [Directory Archive](https://github.com/richbodo/personal_network_toolkit/blob/main/use_cases.md#directory-archive)

### Flavor — fellows's six axis picks

| Axis | Pick | Why |
|---|---|---|
| [Distribution](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#distribution) | `web-bundle-with-magic-link` | EHF-allowlisted PWA; multiple fellows install from one origin behind a magic-link gate. |
| [Storage substrate](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#storage-substrate) | `opfs-sqlite-wasm` | Browser-only deployment; sqlite3.wasm in a dedicated worker with OPFS-SAH-Pool VFS. |
| [Ingestion shape](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#ingestion-shape) | `single-source-static-mirror` | One source (Knack JSON dump); no dedup; opt-in user-driven re-import. |
| [Workspace shell](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#workspace-shell) | `vanilla-js-spa` | Single-IIFE `app/static/app.js`; hash routing; no framework, no bundler. |
| [Comms transport set](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#comms-transport-set) | `mailto-only` | `mailto:` (+ `tel:`) today; Signal planned. |
| [MCP-exposure](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md#mcp-exposure) | `shared+private+comms` | `mcp_servers/` ships three stdio MCP servers for Claude Desktop and similar clients. |

This section is fellows's **AC attestation table** — the Security Target role from the toolkit's
[`ARCHITECTURE_TEMPLATE.md`](https://github.com/richbodo/personal_network_toolkit/blob/main/reference_designs/templates/ARCHITECTURE_TEMPLATE.md).
Every applicable AC carries a **Realization** (how the code satisfies it), a **Verification** (the
test, rubric, or human-review note that proves it), and a **Status**. Verification refs are
`file::test_function` where a deterministic test exists; otherwise an LLM rubric or a human-review
note is named (both acceptable per the template). Status is `conformant` / `partial-conformance` /
`not-applicable`. Partial rows state honestly what is and isn't covered.

### Universal ACs

| AC | Realization | Verification | Status |
|---|---|---|---|
| AC-1 (two-store ownership split) | Two SQLite DBs: `fellows.db` (read-only contact data) + `relationships.db` (read-write, user-owned), separate OPFS files. `app/relationships.py:open_db()` ATTACHes fellows as `f` with `?mode=ro`; the worker owns the pair. | `tests/test_relationships.py::test_attach_fellows_readonly_allows_select`, `::test_attach_fellows_readonly_denies_write`; `tests/test_database.py` | conformant |
| AC-4 (versioned cross-boundary handshake) | `WORKER_RPC_VERSION`/`RELATIONSHIPS_SCHEMA_VERSION` in `vendor/sqlite-worker.js`; `EXPECTED_WORKER_RPC_VERSION` in `app.js`; `refuseIfVersionSkew()` gates mutating RPCs on mismatch, reads still pass; build label is not the gate. | `tests/e2e/test_version_handshake.py::test_version_skew_refuses_mutations_but_allows_reads`; `tests/e2e/test_worker_rpc.py` | conformant |
| AC-6 (always-reachable diagnostic escape) | `?gate=1` forces the email gate regardless of stuck state; Reset Everything + Clear App Cache `POST /api/logout` and reload. | `tests/e2e/test_email_gate.py`; `tests/e2e/test_reset_everything.py`; `tests/e2e/test_clear_app_cache.py` | conformant |
| AC-7 (self-service field-debug substrate) | Build label (AC-15), `?diag=1` state-dump, sanitized error capture (`deploy/client_error_sanitizer.py`), bug-report flow, `?gate=1` escape, boot watchdog with named phase marks, slow-boot persistence. | `tests/e2e/test_diagnostics_panel.py`; `test_boot_watchdog.py`; `test_boot_error_panel.py`; `test_bug_report.py`; `test_boot_beacon.py` | conformant |
| AC-9 (auto-backup of private data) | `vendor/sqlite-worker.js:maybeBackupRelationshipsDb()` — per-boot debounced (`BACKUP_DEBOUNCE_MS`), 5-slot rotation ring; folder mode writes the ring into the user folder. | `tests/e2e/test_user_folder_storage.py::test_snapshot_lands_in_folder_when_folder_mode_active`, `::test_opfs_to_folder_backup_migration_on_folder_boot`; restore via `tests/e2e/test_settings.py`. Debounce cadence by code inspection (LLM rubric). | conformant |
| AC-10 (opt-in non-destructive re-imports) | About-page *Update directory data*; `previewFellowsDbSwap()`/`applyFellowsDbSwap()` preview `group_members` orphaned by the swap before commit; one-shot soft scan. | `tests/e2e/test_directory_data_update_flow.py::test_apply_with_group_impact_shows_dialog_and_can_cancel`, `::test_apply_with_group_impact_confirm_completes_swap`; `test_orphan_soft_scan.py`; `test_versioned_fellows_db.py` | conformant |
| AC-11 (concurrent-access detection) | Worker `isOwnershipConflictError()` → `OWNERSHIP_CONFLICT` with a specific "another tab/window of this app is already open" message; Web Lock `fellows-relationships-folder-write` guards folder writes. | `tests/e2e/test_user_folder_storage.py::TestPhase2WriteLock::test_lock_held_during_write_surfaces_failure_then_recovers`; `test_worker_spawn_failure.py` | conformant |
| AC-15 (build label tied to source revision) | `build/build_pwa.py:compute_build_label()` → `<YYYY-MM-DD>-<short-sha>`, stamped into `app.js`/`sw.js`/`vendor/sqlite-worker.js` at build time; `app/server.py` substitutes the same at serve time. | `tests/test_build_pwa.py`; `tests/e2e/test_update_check.py`; `test_bug_report.py` (asserts `app: <YYYY-MM-DD>-<sha>`); `test_boot_beacon.py` | conformant |
| AC-16 (user-driven transport selection) | Group/fellow export surfaces `mailto:` (+ `tel:`); the user picks per outreach; no transport is hardcoded as the sole option. Axis pick is `comms-transport-set: mailto-only` (Signal planned). | `tests/e2e/test_groups_export.py`; `tests/test_comms.py` | partial-conformance (conformant to the `mailto-only` axis pick; richer transports planned) |
| AC-17 (mirrored data is sourced) | `build/restore_from_knack_scrapefile.py` maps every column to a Knack `field_*` (raw_dump fallback); no contact data introduced beyond the configured Knack source. | `tests/test_database.py`; `build/diff_fellows_db.py` (bytewise vs `fellows.db.backup.2026-04-08`, via `just db-verify`); [`./data_provenance.md`](./data_provenance.md) (human review) | conformant |
| AC-18 (transports cannot read message contents) | Only `mailto:` / `tel:` offered — no centralized SaaS message broker (Slack/Discord). `mailto:` hands to the user's client; MCP comms only stages a `mailto:` URL. | Architectural / human-review; `tests/test_comms.py` (stage-only, returns `mailto:` URL); `tests/test_private_data_ops.py` (`mode=ro`) | conformant |
| AC-19 (user-visible payload before send) | Group export panel shows recipients + subject + body + merged data before launch, editable/cancelable; bulk shows recipient count + warning. | `tests/e2e/test_groups_export.py`; `tests/e2e/test_groups_compose.py` | conformant |
| AC-PRM-A (LLM calls over user data are transports) | Cloud-LLM use is opt-in via the `EX-CLOUD-LLM` exception (consent gate → non-PNA mode); a local model is the default green path. Per-call prompt + merged-data visibility lives in the cloud client's own UI (the user drives Claude Desktop). | `tests/e2e/test_pna_exception_mode.py`; `test_mcpb_settings.py`; see Exception attestation below | partial-conformance (cloud opt-in via per-install consent; per-call prompt visibility is the cloud client's UI, not the workspace's) |
| AC-PRM-D (re-ingestion is user-initiated) | Directory-data refresh is an explicit About-page button only; boot is install-only and never background-polls. | `tests/e2e/test_directory_data_update_flow.py`; `test_versioned_fellows_db.py::test_install_only_does_not_refetch_on_sha_mismatch` | conformant |
| AC-MCP-A (cloud AI clients require consent for Private DB) | Realized as the `EX-CLOUD-LLM` exception: a workspace consent gate before the user wires up a cloud client + a persistent non-PNA-mode signal; `mcp_servers/private_data_ops.py` opens both DBs `mode=ro`. The stdio servers are not per-call gated by design (out-of-band from the workspace — see [`../plans/pna_toolkit_exceptions_contribution.md`](../plans/pna_toolkit_exceptions_contribution.md) open question). | `tests/e2e/test_pna_exception_mode.py`; `tests/test_private_data_ops.py` (`mode=ro`) | partial-conformance (per-session/per-install opt-in via `EX-CLOUD-LLM`; not per-call server-side gating) |
| AC-MCP-B (MCP Communications stages; workspace launches) | `mcp_servers/comms.py:stage_email()` returns a `mailto:` URL + payload preview and never fires a transport; the user's mail client launches it. | `tests/test_comms.py::test_stage_email_basic_to`, `::test_stage_email_bcc_group_send` | conformant |

### Flavor-derived ACs triggered by fellows's picks

Cross-referenced to the toolkit's [axes.md](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md):

| AC | Triggered by | Realization | Verification | Status |
|---|---|---|---|---|
| AC-2 (no SaaS surface) | `dist:web-bundle-with-magic-link` | `deploy/server.py` ships no per-user RW endpoints; the dev server's retired `/api/groups` and `/api/settings` were the only ones that ever existed (Phase 1 cutover). | `tests/test_deploy_auth_round_trip.py::test_directory_api_is_403_without_session`; `test_deploy_sqlite_api.py`; `test_deploy_mcpb_routes.py` | conformant |
| AC-3 (single OPFS owner) | `storage:opfs-sqlite-wasm` | `app/static/vendor/sqlite-worker.js` is the sole context that calls `navigator.storage.getDirectory` or opens a `FileSystemSyncAccessHandle`. | `tests/e2e/test_worker_rpc.py`; `test_worker_cold_start.py`; `test_local_first_boot.py` | conformant |
| AC-5 (stale session never locks users out of cache) | `dist:web-bundle-with-magic-link` (auth-gated) | Three-tier `window.__dataProvider` hot-swaps `worker` → `api+idb` on 401/403 mid-boot; the cached directory stays readable. | `tests/e2e/test_offline_only_mode.py::test_returning_visit_renders_from_local_opfs_when_network_down`; `test_search_offline_fallback.py`; `test_local_first_boot.py` | conformant |
| AC-8 (anti-enumeration + abuse-bounded analytics) | `dist:web-bundle-with-magic-link` + `debug:has-error-sink` | `deploy/server.py` auth endpoints return neutral payloads with per-IP rate limits (`deploy/magic_link_auth.py:check_rate_limit`); the `/api/client-errors` sink is sanitized (`deploy/client_error_sanitizer.py`). See [`./email_gate.md`](./email_gate.md). | `tests/test_magic_link_auth.py`; `test_deploy_auth_round_trip.py`; `test_deploy_client_errors.py`; `test_client_error_sanitizer.py` | conformant |
| AC-12 (capability detection inside worker) | `storage:opfs-sqlite-wasm` | Worker `init` reports `opfsCapable`; the main thread reads the field and renders the unsupported-browser panel rather than UA-sniffing. | `tests/e2e/test_unsupported_browser.py::test_no_sah_falls_back_to_api_idb_provider`; `test_worker_cold_start.py` | conformant |
| AC-13 (COOP/COEP required) | `storage:opfs-sqlite-wasm` + `dist:web-served` | Both dev (`app/server.py:Handler.end_headers`) and prod (`deploy/server.py`) send `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp` and a strict CSP. Caddy preserves them at the edge. | `tests/test_api.py::TestSecurityHeaders::test_coop_coep_present`, `::test_strict_csp_present`, `::test_other_hardening_headers_present` | conformant |
| AC-14 (SW never owns SQLite) | `dist:web-bundle-with-magic-link` (PWA) | `app/static/sw.js` is app-shell + update/signature only; `/fellows.db` is explicitly bypassed in the fetch handler. | `tests/e2e/test_sw_post_caching.py`; `test_image_cache_no_bust.py` | conformant |

### ACs that are not applicable in fellows's flavor

| AC | Reason |
|---|---|
| AC-PRM-B | Applies to `ingestion:multi-source-merge-with-dedup`; fellows is single-source (`single-source-static-mirror`). |
| AC-PRM-C | Applies to `storage:native-sqlite-via-filesystem`; fellows uses `opfs-sqlite-wasm`. |

Picks fellows did not take on other axes carry their own flavor-derived ACs in [axes.md](https://github.com/richbodo/personal_network_toolkit/blob/main/axes.md); none fire here.

### Exception attestation (non-PNA mode)

fellows raises one PNA **Exception** — `EX-CLOUD-LLM` — when the user wires the directory to a
cloud LLM (Claude Desktop MCP). See [`./architectural_findings.md`](./architectural_findings.md) for
the discovery and [`../plans/pna_toolkit_exceptions_contribution.md`](../plans/pna_toolkit_exceptions_contribution.md)
for the upstream-contribution plan (the handler contract `EX-H1..EX-H8`).

| EX | Relaxes | Handled? | Realization | Verification | Status |
|---|---|---|---|---|---|
| EX-CLOUD-LLM | PNA-DEFINITION (local-only / never-SaaS), AC-MCP-A; stresses Goal 1 | yes; reversible (mode only) | Workspace-side handler: consent gate in Settings before the user wires up the cloud client (`recordMcpbConsent()`); persistent dismissable "Going rogue — not a PNA" banner naming the exception (`syncNotAPnaBanner()`, `index.html`); in-app explainer `#/exception/EX-CLOUD-LLM` rendering the **per-dimension strength profile** (`PNA_EXCEPTION_STRENGTH` → `renderExceptionPage()`, EX-H8); "Return to PNA mode" control (`returnToPnaMode()`); `<body data-pna-mode/data-pna-exceptions>` machine-readable marker. **EX-H7** consent-to-human propagation is surfaced best-effort via the MCP `instructions` handshake on the data-returning servers (`CLOUD_LLM_PROPAGATION_NOTICE` in `mcp_servers/private_data_ops.py` + `mcp_servers/shared_data_ops.py`); servers stay `mode=ro`, not per-call gated. Code: `app/static/app.js`, `app/static/index.html`, `mcp_servers/`. | `tests/e2e/test_pna_exception_mode.py` (raise/dismiss/persist, banner→explainer, return-to-PNA from explainer + Settings, explainer active/inactive/unknown, `test_explainer_shows_per_dimension_strength_profile`); `tests/e2e/test_mcpb_settings.py`; `tests/test_private_data_ops.py::test_instructions_carry_cloud_llm_propagation_notice`; `tests/test_shared_data_ops.py::test_instructions_carry_cloud_llm_propagation_notice` | conformant for EX-H1–H6 and EX-H8; EX-H7 (consent-to-human) surfaced best-effort via MCP `instructions` |

---

## HTTP API

Read-only fellow data (served from `app/fellows.db`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/fellows` | Minimal list (`record_id`, `slug`, `name`, `has_contact_email`) for instant directory render. |
| GET | `/api/fellows?full=1` | Full fellow rows (phase 2 of the two-phase load). |
| GET | `/api/fellows/<slug>` | One fellow by `slug` or `record_id`. |
| GET | `/api/search?q=…` | FTS5 search across name / bio / cohort / fellow_type / search_tags / key_links. |
| GET | `/api/stats` | Aggregates for the About page: total, breakdowns by fellow_type / cohort / region, field completeness. |
| GET | `/fellows.db` | Raw SQLite snapshot for the PWA's OPFS bootstrap. |
| GET | `/images/<slug>.{jpg,png}` | Profile image; alphanumeric-fuzzy filename fallback. |
| GET | `/` and other static paths | App shell from `app/static/`. |

Production-only routes (added by `deploy/server.py`; conform to the Distribution slot's auth contract [`distribution-auth.openapi.yaml`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/distribution-auth.openapi.yaml)):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/status` | Never gated; returns `{authEnabled, authenticated, hasSessionCookie, installRecentlyAllowed, build, buildGitSha}`. |
| POST | `/api/send-unlock` | Anti-enum, always 200; rate-limited per email-hash. |
| POST | `/api/verify-token` | 200 + Set-Cookie on success; 401 with distinct `expired`/`invalid` strings otherwise. |
| POST | `/api/logout` | Idempotent, always 200. |
| POST | `/api/client-errors` | Unauthenticated client-error sink. Always 204. Sanitized + rate-limited; logs `event=client_error` to journald. Dev stub mirrors prod for round-trip. Schema: [`client-errors-payload.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/client-errors-payload.schema.json); privacy boundary detailed in [`./email_gate.md` § Client error reporting](./email_gate.md#client-error-reporting). |
| GET | `/healthz` | Liveness probe. |
| GET | `/build-meta.json` | Build label + git SHA + `fellows_db_sha` for SW drift-check. |
| GET | `/api/debug/diagnostics` | Operator diagnostics blob. |

The server opens a new SQLite connection per request (no pool; unnecessary at local scale). `/api/stats` is heavier than a simple row fetch (region split + field-completeness pass over `extra_json` via `json_extract`); still fine at local scale.

The Two-Phase Load pattern (`/api/fellows` then `/api/fellows?full=1` in the background, falling back to `/api/fellows/<slug>` if the user clicks before phase 2 completes) is a Workspace concern; the route names are fellows specifics.

---

## Cross-origin and CSP headers

Both servers send (must be preserved by Caddy at the edge):

- `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp` — AC-13 prerequisite for OPFS-SAH-Pool.
- `Cross-Origin-Resource-Policy: same-origin`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff`.
- A strict Content-Security-Policy: `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none';`
- A locked-down `Permissions-Policy` (geolocation / camera / microphone / payment / sensors / USB / etc. all `=()`).

HSTS is added by Caddy (`ansible/roles/caddy/templates/Caddyfile.j2`), not the Python server.

**Subresource Integrity (SRI):** `index.html` carries SHA-384 `integrity=` attributes on both `<script src>` tags. `build/build_pwa.py:stamp_sri_attributes` computes the hashes at build time over the post-build-label-stamped bytes; the dev server (`app/server.py`) performs the same substitution at request time so dev and prod produce byte-identical integrity values. The service worker itself isn't covered — that gap is the motivation for the signed-bundle work tracked separately.

---

## Shared DB schema (`fellows.db`)

Specializes the [Shared schema](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/shared-db.schema.sql) — record_id / slug / name / extra_json plus app-defined display columns. fellows renames the spec's `records` table to `fellows` (spec-allowed; see the contract's naming note).

```sql
CREATE TABLE fellows (
    record_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT,
    bio_tagline TEXT,
    fellow_type TEXT,
    cohort TEXT,
    contact_email TEXT,
    key_links TEXT,
    key_links_urls TEXT,       -- JSON array of URLs (stored as TEXT)
    image_url TEXT,
    currently_based_in TEXT,
    search_tags TEXT,
    fellow_status TEXT,
    gender_pronouns TEXT,
    ethnicity TEXT,
    primary_citizenship TEXT,
    global_regions_currently_based_in TEXT,
    extra_json TEXT            -- JSON object of all other source fields
);

CREATE UNIQUE INDEX idx_fellows_slug ON fellows(slug);

CREATE VIRTUAL TABLE fellows_fts USING fts5(
    name,
    bio_tagline,
    cohort,
    fellow_type,
    search_tags,
    key_links,
    content='fellows',
    content_rowid='rowid'
);
```

> **Drift from spec form:** the spec contract enforces `slug` uniqueness with a table constraint (`UNIQUE (slug)`); fellows uses a separate `CREATE UNIQUE INDEX`. Functionally equivalent — both enforce the same contract at the SQLite level.

The 17 explicit columns are the fellows-specific app-defined display columns. Source-specific fields not in this list are serialized into `extra_json`, which `row_to_fellow()` in `app/fellows_queries.py` merges back into the API response. FTS5 also creates internal shadow tables (`fellows_fts_data`, `fellows_fts_idx`, etc.); those are SQLite-managed and not altered by hand.

**Per-record asset URL convention:** `/images/<slug>.{jpg,png}` — alphanumeric-only fuzzy fallback in the server handler covers slug-vs-filename drift. Asset URLs are slug-keyed, immutable, and cacheable; they're separate from the database. See SH-3 in the [Shared schema contract](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/shared-db.schema.sql).

**Build pipeline:** `build/restore_from_knack_scrapefile.py` reads the Knack API detail dump (with a fallback read of the list-view `raw_dump` for a few fields), deduplicates slugs, detects grey-diamond placeholder avatars by MD5, and writes both tables. See [`./data_provenance.md`](./data_provenance.md) for the full data pipeline.

---

## Private DB schema (`relationships.db`)

Specializes the [Private schema](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/private-db.schema.sql). Created on first access by `app.relationships.open_db()`; the same DDL is mirrored in the PWA via `RELATIONSHIPS_SCHEMA_SQL` in `app/static/app.js` so the OPFS-backed sqlite3.wasm path matches the dev server.

```sql
CREATE TABLE groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    fellow_record_id TEXT NOT NULL,
    PRIMARY KEY (group_id, fellow_record_id)
);

CREATE INDEX idx_group_members_group ON group_members(group_id);

CREATE TABLE fellow_tags (
    fellow_record_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (fellow_record_id, tag)
);

CREATE INDEX idx_fellow_tags_tag ON fellow_tags(tag);

CREATE TABLE fellow_notes (
    fellow_record_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

`PRAGMA user_version = 1` at bootstrap; `PRAGMA foreign_keys = ON` per connection (without it the `ON DELETE CASCADE` is silently inert).

> **Drift notes vs the spec contract:**
>
> - **Column rename.** Spec calls the Private-DB FK column `record_id`; fellows uses `fellow_record_id` for in-app ergonomics. Spec-allowed specialization; same shape and same PK semantics.
> - **Table renames.** Spec uses `record_tags` and `record_notes`; fellows uses `fellow_tags` and `fellow_notes` (same reason).
> - **Settings PK.** Spec uses composite `(workspace_id, key)`; fellows is single-workspace and uses a simpler `key TEXT PRIMARY KEY`. A future schema migration can add `workspace_id` with default `''` to converge on the spec shape without losing rows.
> - **`record_comms_history` absent.** Spec attests this as an opt-in PR-2 table (disabled by default). Fellows doesn't ship it yet; when comms-history capture is added, it will conform to PR-2.

**Durability (per PR-4):** `relationships.db` is gitignored, per-user, never replaced on app update, survives Clear App Cache, and is wiped only by Reset Everything (the workspace's explicit-user-choice nuclear path). Auto-backup, restore, and the OPFS-vs-IndexedDB-vs-cookie state-survival matrix live in [`./persistence_and_upgrades.md`](./persistence_and_upgrades.md).

**Substrate (two modes, single source of truth per session).** Folder mode (Chromium desktop with a user-picked `FileSystemDirectoryHandle`) treats the user's folder file as canonical: the OPFS slot is a transient mem-VFS buffer hydrated from folder bytes on boot, serialized back atomically on every committed mutation, and guarded across agents by a Web Lock on `'fellows-relationships-folder-write'`. OPFS-only mode (Safari / Firefox / mobile, or Chromium users who declined the picker) treats the OPFS-resident slot as canonical. No hybrid — boot resolves to exactly one mode per session. Full architecture (mode resolution, pivot migration, per-commit write path, backup ring location, Web Lock semantics) in [`../plans/user_folder_storage.md`](../plans/user_folder_storage.md). The state-survival matrix in `persistence_and_upgrades.md` enumerates the per-substrate storage layers.

---

## Worker constants (fellows's version-handshake values)

The spec's [AC-4 versioned cross-boundary handshake](https://github.com/richbodo/personal_network_toolkit/blob/main/PNA_Spec.md#universal-architectural-commitments) is parameterized; fellows pins:

- `WORKER_RPC_VERSION = 2` (bumped only when the request/response shape of any RPC changes; gates mutating ops on mismatch)
- `RELATIONSHIPS_SCHEMA_VERSION = 1` (mirrors `PRAGMA user_version`; bumped only on schema migrations)
- Worker file path: `app/static/vendor/sqlite-worker.js`

The page reads both during the worker `init` handshake (the handshake shape itself is specified in [`worker-init-handshake.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/worker-init-handshake.schema.json) and the RPC envelope in [`worker-rpc-protocol.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/worker-rpc-protocol.schema.json)) and refuses mutating RPCs on mismatch. Reads still work, so the user can browse cached data while the SW's "New version available — Reload" banner does its job. Build label is **not** consulted for this gate.

---

## Data provider abstraction

The Workspace slot's data provider has three tiers per AC-5; in fellows the active provider is exposed at `window.__dataProvider` for tests and diagnostics:

1. `worker` — happy path. RPC into the OPFS-owning worker.
2. `api+idb` — auth-failure / OPFS-incapable fallback. Directory reads come from `/api/fellows` when the session is valid, or from the IndexedDB cache populated by a prior successful boot when it isn't.
3. `api` — deepest fallback. Same as `api+idb` without IDB; used in environments without IndexedDB.

`bootDirectoryAsApp` starts with the worker provider; if the worker's `ensureFellowsDb` returns 401/403 (stale session), the boot path swaps to `api+idb` mid-flight. The worker process stays alive (it still owns OPFS; `clearEverything` reaches it through `warmWorker.rpc` for the wipe). The build badge flips to `server: offline · using cache`.

---

## Boot orchestration

Specializes AC-7's self-service field-debug substrate. Fellows pins:

- **Phase marks** (eight, in order): `script_start`, `pick_provider_start`, `worker_init_done`, `provider_ready`, `get_list_done`, `get_full_done`, `image_prewarm_done`, `summary`.
- **Watchdog timeout:** 20 seconds. If `get_list_done` doesn't arrive in time, the recovery panel (`#boot-stuck-panel`) renders naming the last completed mark.
- **Slow-boot persistence:** total >3000 ms or any single phase >2000 ms writes a record to `localStorage['fellows_last_slow_boot']`. Survives Clear App Cache. Surfaced under "Last slow boot recorded" in the `?diag=1` panel on the next session.
- **E2E test seams:** `window.__bootMarks` (read-only) and `window.__bootDebugLines` (chronological trace).

---

## Frontend routing

Hash-based SPA routing with no history API and no router library, defined in `route()` in `app/static/app.js`. Specializes the Workspace slot's routing sub-contract.

| Route | Purpose |
|---|---|
| `#/` (default; empty or unmatched hash) | Directory. Two-phase load: minimal list, then full rows in the background. Filter state persists in a query suffix on the hash (`#/?cohort=2020`), read on every `route()` call by `applyFiltersToHash` / `readFiltersFromHash`. |
| `#/about` | About page. Loads fellowship statistics via `GET /api/stats`; links out to the user guide. |
| `#/fellow/<slug>` | Fellow detail. Resolves from the in-memory cache or `GET /api/fellows/<slug>`. |
| `#/groups` | Groups index — saved groups with member counts. |
| `#/groups/<id>` | Group detail. Action bar (Contact / Export / Edit), member list, inline note editor. |
| `#/groups/<id>/directory` | Visual portrait directory for the group; click a portrait → `#/fellow/<slug>`. |
| `#/edit/<id>` | Edit-mode entry. Re-uses the right-rail composer against an existing group; auto-saves on toggle, "Cancel edits" reverts to the entry snapshot. |
| `#/settings` | Settings page. The user's "me" email used for export `mailto:?to=…`; auto-captured from the magic-link gate, persisted to `relationships.settings` and mirrored to localStorage on boot. |

User-facing screen behavior, navigation, and UX flows live in [`./users_manual.md`](./users_manual.md). Treat the user guide as the source of truth for UI/UX from a user's perspective and keep it in sync when the UI changes.

A `window.ai` natural-language search affordance is behind a capability gate; when present, it's wired into the directory route's filter pipeline.

---

## Debug substitutions and addresses

Specializes the Debug contract. fellows pins:

- **Build-label format:** `<YYYY-MM-DD>-<short-sha>`.
- **Placeholders substituted at build + serve time:** `__FELLOWS_UI_DIAG__`, `__CACHE_VERSION__` (in `app.js`, `sw.js`, `vendor/sqlite-worker.js`).
- **Sanitized error sink:** `POST /api/client-errors` (16 KB body cap; per-IP rate limit; always 204; `kind=` enum allowlist).
- **Bug-report `mailto:` target:** `richbodo@gmail.com`.
- **Force-gate URL:** `/?gate=1` (AC-6's realization for SPA shells; doesn't bypass auth — only the UI decision tree).
- **In-app diagnostics URL:** `/?diag=1`.

---

## Distribution flavor specifics (magic-link PWA)

Specializes the Distribution slot. Auth-endpoint shapes are in [`distribution-auth.openapi.yaml`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/distribution-auth.openapi.yaml); the behavioral decision tree and the operator runbook live in the annexes.

Fellows pins:

- `TOKEN_TTL = 30 min`, `INSTALL_WINDOW = 30 min`, `SESSION_MAX_AGE = 7 days`.
- Session cookie: HttpOnly, HMAC-signed, **v2 format** (v1 rejected on sight post-deploy).
- Token re-consume grace window: ~60 s — defends against bfcache, iOS back-button, email-side link scanners.
- Allowlist built in memory at startup by HMAC-ing each `contact_email` row in `fellows.db` with `FELLOWS_ALLOWLIST_HMAC_KEY`. No `allowed_emails.json` artifact ships in `dist/`.
- Six-step browser-mode decision tree (see [`./email_gate.md`](./email_gate.md) for the full table).
- Persistence marker (per WS persistence-marker contract): `localStorage['fellows_authenticated_once']` is the one localStorage key preserved across the workspace's Clear App Cache affordance.

### PWA manifest gotchas

`app/static/manifest.webmanifest` is intentionally minimal: `id`, `start_url`, `scope` all `=/`; three icons (`any`, `any`, `maskable`). Two specific things to keep out, per the Distribution slot's PWA contract:

- **`related_applications`** — a stale or wrong app ID here triggers Android's WebAPK pipeline to verify against the Play Store and fail with a cryptic "Older Version of Android" install error.
- **`share_target` with `method: "POST"`** — some Samsung/Chromium WebAPK servers reject POST share targets and the install silently fails. If a future feature needs a share target, use `method: "GET"`.

---

## MCP servers

Fellows attests `mcp-exposure:shared+private+comms`. Three stdio MCP servers ship today, all read-only or stage-only (no writes, no transports fired from inside the MCP process); their typed tool surfaces live in `https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/`.

| Server | Source | Contract | Tools |
|---|---|---|---|
| Shared Data Ops | `mcp_servers/shared_data_ops.py` | [`mcp-shared-data-ops.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/mcp-shared-data-ops.schema.json) | `search_fellows`, `get_fellow`, `list_fellows`, `get_directory_stats` |
| Private Data Ops | `mcp_servers/private_data_ops.py` | [`mcp-private-data-ops.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/mcp-private-data-ops.schema.json) | `list_groups`, `find_group`, `get_group_members` |
| Communications | `mcp_servers/comms.py` | [`mcp-comms.schema.json`](https://github.com/richbodo/personal_network_toolkit/blob/main/spec/contracts/mcp-comms.schema.json) | `stage_email`, `get_staged` |

Per AC-MCP-B, `stage_email` returns a `mailto:` URL with a staging ID; the user's mail client launches the transport when the user clicks. The server never invokes a transport. Per AC-MCP-A, the Private Data Ops server returns Private DB rows and so requires per-call consent when wired to a cloud AI client; see [`../mcp_servers/README.md`](../mcp_servers/README.md) § Cloud LLM caveat.

Ingestion and Diagnostics MCP servers are not yet built; their spec contracts are placeholders pending first reference implementations.

The `mcp_servers/` directory is the project's one exception to the stdlib-only constraint — it depends on the official `mcp` SDK, isolated in `mcp_servers/.venv`. It imports from `app/` only via pure-logic helpers (e.g. `app/fellows_queries.py`).

---

## Operator concerns

Production-side, fellows-specific operator concerns (out of spec scope):

- **Deployment, systemd hardening, droplet topology** — [`./DevOps.md`](./DevOps.md).
- **Magic-link operator runbook (Postmark, env file, journald schema)** — [`./email_system_management.md`](./email_system_management.md).
- **Data pipeline + recovery paths** — [`./data_provenance.md`](./data_provenance.md).
- **Ansible specifics (tags, galaxy install, troubleshooting)** — [`../ansible/README.md`](../ansible/README.md).

---

## Annexes

Architecture-adjacent docs that specialize one part of the spec or operator surface in depth:

| Annex | Specializes |
|---|---|
| [`./email_gate.md`](./email_gate.md) | Distribution slot — magic-link auth flow, decision tree, client-error sanitization. |
| [`./persistence_and_upgrades.md`](./persistence_and_upgrades.md) | Storage slot — state-survival matrix across Clear App Cache / Reset Everything / app update; auto-backup; restore. |
| [`./browser_support.md`](./browser_support.md) | Storage slot — capability detection inside the worker, required versions, unsupported-browser surfacing (AC-12). |
| [`./data_provenance.md`](./data_provenance.md) | Ingestion slot — column-by-column source mapping; backup/restore workflow; recovery paths. |
| [`./architectural_findings.md`](./architectural_findings.md) | Findings that feed back into the spec — e.g. the cloud-LLM "exception" / non-PNA-mode concept (`EX-CLOUD-LLM`). |

---

## Roadmap

See [`../ROADMAP.md`](../ROADMAP.md).
