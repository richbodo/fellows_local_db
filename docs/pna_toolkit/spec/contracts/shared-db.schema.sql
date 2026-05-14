-- Shared schema interface — canonical SQL DDL for a conforming Shared DB.
--
-- Sub-contracts SH-1 through SH-6 from PNA_Spec.md § Slot map. The Shared
-- DB holds mirrored contact data — read-only inside the PNA, written only
-- by the Ingestion slot. AC-17 (mirrored data is sourced) and AC-10
-- (opt-in non-destructive re-imports with orphan preview) apply.
--
-- This DDL is the spec-generic shape — implementations supply app-specific
-- display columns and decide whether to ship the optional FTS5 index.
-- The contract pins three things:
--   (1) the primary record table's core column set (SH-1)
--   (2) the read-only enforcement mechanism (SH-4) — at JOIN time, not DDL
--   (3) the asset-URL convention when one is used (SH-3)
--
-- Naming note: the spec uses the table name `records`; specializations may
-- rename. fellows_local_db's specialization calls it `fellows`. The
-- column names below (record_id, slug, name, extra_json) are normative
-- across all Shared DBs.

-- SH-1: Primary record table.
--
-- Required columns:
--   record_id   TEXT  PRIMARY KEY     — opaque, STABLE across re-mirrors.
--                                      This is the join key from the
--                                      Private DB; AC-10's orphan-preview
--                                      depends on stability for the set
--                                      difference to be meaningful.
--   slug        TEXT  NOT NULL UNIQUE — display URL key; deterministic
--                                      from `name`. SH-3's optional asset
--                                      URL convention keys on this.
--   name        TEXT  NOT NULL        — display label; what orphan-preview
--                                      surfaces to the user.
--   extra_json  TEXT                  — JSON-encoded overflow for any
--                                      source-specific keys not in the
--                                      app-defined explicit columns. The
--                                      workspace merges these into per-
--                                      record API responses without per-
--                                      field schema knowledge.
--
-- Plus zero or more app-defined display columns. fellows_local_db ships
-- 17 explicit display columns (name, bio_tagline, fellow_type, cohort,
-- contact_email, …); see fellows_local_db's Architecture.md § Database
-- Schema for the full list. Other PNAs will have wildly different display
-- columns; that's expected and not constrained by the spec.
CREATE TABLE IF NOT EXISTS records (
    record_id   TEXT PRIMARY KEY,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    extra_json  TEXT,
    -- app-defined display columns go here (workspace-rendered fields)
    --   e.g. bio_tagline TEXT,
    --        contact_email TEXT,
    --        image_url TEXT,
    --        ...
    -- SH-6: Multi-source PNAs add a provenance column. Single-source PNAs
    -- (Directory Archive flavors) may omit it. fellows_local_db is
    -- single-source today; AC-PRM-B's draft multi-source contract will
    -- formalize the per-field provenance shape for PRM-flavor PNAs.
    --   source TEXT,
    -- SH-3 optional asset URL convention is OUT of the SQL — see comment
    -- below.
    UNIQUE (slug)
);

-- SH-2: Optional FTS5 virtual table.
--
-- When a PNA wants full-text search across the Shared DB, the spec
-- recommends FTS5 with external content (`content='records'`,
-- `content_rowid='rowid'`) so the index stays in sync with the primary
-- table without per-row triggers being a hand-maintained burden. Which
-- columns to index is app-specific; fellows_local_db indexes name,
-- bio_tagline, cohort, fellow_type, search_tags, key_links.
--
-- CLI / native PNAs may use a different search engine (Tantivy, ripgrep
-- shelling out, …); the contract names the FTS5 path as the recommended
-- default for SQLite-substrate PNAs, not a mandate.
--
--   CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
--       name,
--       /* app-defined searchable columns */,
--       content='records',
--       content_rowid='rowid'
--   );

-- SH-3: Optional per-record asset URL convention.
--
-- When a PNA serves per-record binary assets (profile photos, attachment
-- previews, etc.), the convention is to make them slug-keyed and content-
-- addressable so they're cacheable, immutable, and never include the
-- record_id (which may be opaque). The path lives on the workspace /
-- distribution side, not in the Shared DB — but the SLUG is what binds
-- them, so it goes here as documentation.
--
-- fellows_local_db convention: `/images/<slug>.{jpg,png}`. Alphanumeric-
-- fuzzy fallback in the server handler covers slug-vs-filename drift.

-- SH-4: Read-only enforcement.
--
-- The Shared DB is read-only at runtime. Implementations MUST enforce
-- this at the storage substrate level when joining from the Private DB:
--
--   ATTACH DATABASE 'file:.../shared.db?mode=ro' AS shared;
--
-- For browser PNAs using OPFS, the dedicated worker (Storage slot) opens
-- the file with the equivalent read-only flag at SAH-pool import. Any
-- stray write into the attached namespace raises `OperationalError` —
-- the read-only-ness is not just an app-layer convention.
--
-- The only writer is the Ingestion slot's atomic-swap pipeline (SH-5).

-- SH-5: Atomic re-import semantics with orphan preview (AC-10).
--
-- Implemented by ST-8 (worker-rpc-protocol.schema.json:op_previewSharedDbSwap
-- → op_applySharedDbSwap). The DDL above is what an ingested fresh DB
-- must conform to; the orchestration (stage, validate via PRAGMA
-- quick_check, compute affected Private DB references, surface them to
-- the user before commit, atomic swap) is in the Storage slot.
