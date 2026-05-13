# Axes

> **Spec-Version:** 0.1 (draft)

This document catalogs the six Axes a PNA picks along, the attested picks on each Axis, and the flavor-derived ACs each pick triggers.

The Axis concept is defined in [`PNA_Spec.md` § Vocabulary](PNA_Spec.md#vocabulary). The Axes overview in `PNA_Spec.md` lists picks at a glance; this file is the authoritative catalog with full descriptions and AC triggers.

For each Axis below: a description of what the Axis decides, the attested picks (each with a short note on what it implies, where it's attested, and which other axis-picks it commonly correlates with), and a `Triggered flavor-derived ACs` subsection when any picks on that axis fire flavor-derived ACs.

---

## Distribution

How the PNA reaches a user's device. The distribution pick shapes whether the PNA has a server at all, whether that server gates installs, and whether the bundle ships as a PWA — choices that ripple into several flavor-derived ACs.

### Picks

- **`web-bundle-with-magic-link`** *(server-backed, auth-gated, PWA)* — An HTTP origin serves the bundle behind email-allowlist auth. The user receives an unlock link, exchanges it for a session, and installs the PWA. Multiple users install from the same source. Attested in [fellows_local_db](../Architecture.md). Triggers AC-2, AC-5, AC-8, AC-14; combines with `storage:opfs-sqlite-wasm` to trigger AC-13.
- **`never-distributed-single-user`** — The PNA is built or installed by the user themselves; no per-user delivery story. No server, no auth, no service worker. PRT-inspired. Triggers no flavor-derived ACs on this axis.
- **`web-bundle-open`** *(server-backed, no auth, PWA)* — Same delivery shape as magic-link but with no auth gate; anyone with the URL can install. Triggers AC-2 and AC-14; combines with `storage:opfs-sqlite-wasm` to trigger AC-13.
- **`app-store-native`** — Packaged native app distributed via a platform store (Mac App Store, Google Play, etc.). The store is the install path; no PNA-operated server. None of this axis's flavor-derived ACs fire.
- **`sideloaded-native`** — Packaged native app distributed directly (download a binary, install). Same: no PNA-operated server; none of this axis's flavor-derived ACs fire.

### Triggered flavor-derived ACs

| AC | Triggered by | Commitment |
|---|---|---|
| AC-2 | `[dist:server-backed]` (any `web-bundle-*` pick) | **No SaaS surface.** Server (when present) is a delivery channel, not a service. No per-user RW endpoints, no server-side persistence of private data, no admin console, no cross-device sync. |
| AC-5 | `[dist:auth-gated]` (`web-bundle-with-magic-link`) | **Stale session never locks users out of cached data.** A 401/403 from any shared-side fetch falls through to the local cache. Fresh data requires explicit user action. |
| AC-8 | `[dist:auth-server]` + `[debug:has-error-sink]` | **Anti-enumeration on auth + abuse-bounded analytics.** Distribution-channel auth endpoints always return neutral payloads; per-IP rate limits; sanitized error sink doubles as analytics pipe (`kind=install`, `kind=worker`, …) with no widening of the privacy boundary. |
| AC-14 | `[dist:pwa]` (any `web-bundle-*` PWA pick) | **Service worker never owns SQLite.** SW lifecycle (idle eviction, multi-instance, restart on push) is hostile to data ownership. SW is app-shell + update detection only. The Shared store URL is explicitly bypassed in the SW fetch handler. |

---

## Storage substrate

What backs the data layer — the bytes on disk or in OPFS that hold the Shared and Private DBs. The storage substrate pick shapes ownership of file handles, concurrent-access detection, and what cross-origin headers (if any) the distribution must serve.

### Picks

- **`opfs-sqlite-wasm`** — sqlite-wasm running in a dedicated worker, with OPFS-SAH-Pool VFS as the underlying storage. Browser-only. Attested in [fellows_local_db](../Architecture.md). Triggers AC-3, AC-12; combines with `dist:web-served` to trigger AC-13.
- **`native-sqlite-via-filesystem`** — Native SQLite library (libsqlite3) opens database files directly via OS filesystem APIs. WAL mode + advisory file locks recommended. CLI / native PNAs only. PRT-inspired (not yet against this spec). Triggers AC-PRM-C **[draft]**.
- **`idb-only-browser`** — IndexedDB without SQLite. Less expressive (no SQL); mostly hypothetical for PNA. No flavor-derived ACs in v0.1 (the relevant ACs assume sqlite); a future spec version may add IDB-specific ACs if a reference design picks this.
- **`native-sqlcipher`** — Encrypted-at-rest variant of `native-sqlite-via-filesystem`. Inherits AC-PRM-C **[draft]** plus additional commitments about key storage and rotation that v0.1 doesn't yet name. Deferred ACs land when a SQLCipher-flavored reference design is built.

### Triggered flavor-derived ACs

| AC | Triggered by | Commitment |
|---|---|---|
| AC-3 | `[storage:opfs-sqlite-wasm]` | **Single OPFS owner.** All OPFS handles and SQLite-WASM instances live in one dedicated worker. The workspace is an RPC client. No parallel main-thread OPFS. *Realizes AC-1 + AC-11 for this substrate.* |
| AC-12 | `[storage:opfs-sqlite-wasm]` | **Capability detection inside the worker, UA-parsing for messaging only.** Browsers lie about main-thread OPFS support; the worker is the only context where the answer is reliable. UA strings inform error messages, never gating. |
| AC-13 | `[storage:opfs-sqlite-wasm]` + `[dist:web-served]` | **COOP/COEP required.** OPFS-SAH-Pool needs `crossOriginIsolated`; both dev server and prod reverse proxy must send `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. Without this, the storage substrate silently fails to install. |
| AC-PRM-C **[draft]** | `[storage:native-sqlite-via-filesystem]` | **Single-instance file-lock.** Native SQLite demands one writer; a second process refuses cleanly with a specific message naming the holding process. *Realizes AC-11 for this substrate.* **[draft — no reference design yet]** |

---

## Ingestion shape

How the Shared DB is filled and refreshed — whether from a single export, a single live source, multiple merged sources, or federated reads from peers. The ingestion pick determines whether dedup is a concern at all and what re-import semantics look like.

### Picks

- **`single-source-static-mirror`** — One external source produces a complete Shared DB on each refresh; ingestion stages → validates → atomically swaps. No dedup needed. Re-imports are opt-in per AC-10. Attested in [fellows_local_db](../Architecture.md) (Knack-JSON ETL). Triggers no axis-specific ACs.
- **`single-source-live-pull`** — One external source queried live (REST API, OAuth, etc.). Same single-source dedup story (none needed). Triggers no axis-specific ACs in v0.1; a future spec version may add live-pull contracts (rate limiting, partial-failure handling, etc.).
- **`multi-source-merge-with-dedup`** — Multiple external sources (Google + Apple + Facebook + organizational directories) merged into one Shared DB. Dedup wizard surfaces conflicts; per-field provenance preserved. PRT-inspired (not yet against this spec). Triggers AC-PRM-B **[draft]**.
- **`federated-read`** *(deferred)* — Reading from peer PNAs. Out of scope for v0.1.

### Triggered flavor-derived ACs

| AC | Triggered by | Commitment |
|---|---|---|
| AC-PRM-B **[draft]** | `[ingestion:multi-source-merge-with-dedup]` | **Multi-source dedup contract.** Stable `record_id` survives merge across sources; dedup wizard surfaces conflicts; per-source provenance is recorded *per field*, not just per record. Lifts the deferred "multi-source dedup contract" from § Scope into v0.1 for PRM-flavor PNAs. **[draft — no reference design yet]** |

---

## Workspace shell

<!-- TODO (step 3): attested picks — vanilla-js-spa, framework-spa, tui-textual, cli-subcommands, native-shell-tauri, native-shell-native. -->

---

## Comms transport set

<!-- TODO (step 3): attested picks — mailto-only, mailto-plus-signal, mailto-plus-matrix, shell-out-to-cli-clients. -->

---

## MCP-exposure

<!-- TODO (step 3): attested picks — none, data-ops-only, data-ops+comms, full. Triggers AC-MCP-A and AC-MCP-B when non-none. -->
