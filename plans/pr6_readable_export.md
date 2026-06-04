# Plan — PR-6 human-readable Private-DB export (schema-embedded JSON)

**Status:** SCOPED, not started. **Created:** 2026-06-03.
**Why:** PNT added a Private-schema sub-contract, **PR-6** (human-readable export),
landed upstream in [personal_network_toolkit#17](https://github.com/richbodo/personal_network_toolkit/pull/17).
It SHOULD-requires a flat, tool-free export of the Private DB *in addition to* the
canonical SQLite file — readable with a generic JSON/CSV reader and **no app
tooling**. fellows_local_db is the demonstrating reference design: this plan
implements the export, its test, and the `docs/Architecture.md` attestation row
that closes the reference-driven rule for the PR-6 spec change. Originating
discussion: `richbodo/fellows_local_db#216` (now closed).

The "Long Now" gap this closes: today the only Private-DB export is a binary
`.db`, openable only with a SQLite tool. For ~500 non-developer fellows, owning
the bytes is not the same as being able to read them. PR-6 gives them a copy
they can open.

**Format decision:** schema-embedded JSON only for v1 — one self-contained file,
complete, longevity-friendly, trivially tool-free. CSV-per-table (for
spreadsheet users) is a noted fast-follow, not v1.

---

## 1. What exists (the rails this slots onto)

The app already exports the Private DB as binary `.db` via a clean
worker-RPC → app → Settings-button chain. PR-6 adds a readable sibling on the
same rails.

- **Worker RPC:** `app/static/vendor/sqlite-worker.js`
  - `handlers.exportRelationshipsBytes()` (line 1047) — returns raw SQLite bytes.
  - `handlers.countRelationships()` (line 1056) — already SELECT-counts across the
    Private tables; the **template** for a multi-table read.
  - `dbSelectAll()` helper — `(relDb, sql, params)` row reader.
- **App download fn:** `app/static/app.js` `downloadRelationships()` (line 2437)
  — calls the RPC, names the file `ehf-fellows-private-data-<YYYY-MM-DD>.db`,
  triggers a browser download.
- **Settings UI:** `app/static/app.js` `renderSettingsPage()` "Private data folder"
  section (~line 9401), button `settings-download-userdata`, gated on
  `dataProvider.kind === 'worker'`.
- **Private tables actually shipped:** `groups`, `group_members`, `fellow_tags`,
  `fellow_notes`, `settings`. (`record_comms_history` / spec PR-2 is not shipped —
  absent from the export, by design.)
- **Test pattern:** `tests/e2e/test_user_folder_storage.py` drives
  `window.__dataProvider` via `page.evaluate()`; `tests/test_attestation_has_evidence.py`
  enforces that every `conformant` Architecture row cites resolvable evidence.

## 2. Changes

### 2.1 Worker — new read-only handler
`app/static/vendor/sqlite-worker.js`, beside `exportRelationshipsBytes` (line 1047):

- `handlers.exportPrivateDbReadable()` → returns a plain object:
  ```
  { schema: { <table>: [<col>, ...], ... },
    exported_at: "<YYYY-MM-DD>",
    record_counts: { <table>: <n>, ... },
    records: { <table>: [ {col: val, ...}, ... ], ... } }
  ```
- One `dbSelectAll('SELECT * FROM <t>')` per shipped table; build `schema` from the
  column names. Model the table list on `countRelationships()`. Stdlib-JSON-serializable
  only (no Blobs/typed arrays).

### 2.2 App — download function
`app/static/app.js`, mirroring `downloadRelationships()` (line 2437):

- `downloadReadablePrivateData()` → `await dataProvider.exportPrivateDbReadable()`,
  `JSON.stringify(obj, null, 2)`, download as
  `ehf-fellows-private-data-<YYYY-MM-DD>.json`.

### 2.3 UI — one button
`app/static/app.js` Settings "Private data folder" section (~line 9401):

- Add "⬇ Download readable copy (JSON)" next to the existing binary-download button,
  under the same `dataProvider.kind === 'worker'` gate. Wire its click to
  `downloadReadablePrivateData()`.

### 2.4 Test — new e2e
`tests/e2e/test_export_readable_private_db.py` (mirror `test_user_folder_storage.py`
fixtures):

- `test_readable_export_parses_with_stdlib_only` — capture the export payload via
  `page.evaluate("() => window.__dataProvider.exportPrivateDbReadable()")`, write to
  a temp file, and assert it loads with **`json.load`** and no app code. (Same
  property PNT's `tools/export-readable-lint.py` checks; kept self-contained so
  fellows takes no PNT runtime dependency.)
- `test_readable_export_row_counts_match_db` — the load-bearing integrity invariant:
  per-table `len(records[t])` and `record_counts[t]` **equal** `countRelationships()`
  against the live DB. Guards against silently dropping rows (over-claiming the
  export's completeness is the dangerous failure).
- (Optional) `test_readable_export_schema_lists_all_columns` — `schema[t]` matches the
  table's real columns.

### 2.5 Attestation — one Architecture row
`docs/Architecture.md`, in the sub-contract attestation table:

```
| PR-6 (human-readable export) | `vendor/sqlite-worker.js:exportPrivateDbReadable()` builds a schema-embedded JSON of the five Private tables; `app.js:downloadReadablePrivateData()` + the Settings "Download readable copy" button deliver it. One-way *by construction*: there is no import handler for this format — restore accepts only `.db` (PR-5 path). | `tests/e2e/test_export_readable_private_db.py::test_readable_export_parses_with_stdlib_only`, `::test_readable_export_row_counts_match_db` | conformant |
```

`tests/test_attestation_has_evidence.py` then enforces this row automatically.

## 3. Conformance nuances (get these right or the attestation lies)

1. **A local download is NOT a transport.** It is a file save to the user's own
   device, not egress to a third party — so **AC-18 / AC-19 do not apply** and MUST
   NOT be cited on the PR-6 row.
2. **The "one-way" MUST NOT** (PR-6 forbids treating the readable export as a
   re-import surface) is attested **`by construction`**: no import handler exists for
   the JSON format; restore accepts only `.db`. State this in the Realization cell so
   the negative is honest rather than silently assumed.
3. **Status is `conformant` only once the tests land.** Until then the row is `Open`.

## 4. Out of scope (noted, not built)

- **CSV-per-table** (spreadsheet-friendly, the highest-value follow-up for non-dev
  fellows) — a zip of CSVs is ~20 lines of JS later.
- **Broader availability.** The export is just SELECTs and could work on the
  `api+idb` fallback provider too; v1 mirrors the binary download's worker-only gate.
- **`record_comms_history`** export — lands if/when PR-2's opt-in table ships.

## 5. Effort

Small, ~1 focused session. Worker handler ~40 lines, app fn ~25, UI ~10, e2e test
~80, attestation row + plan update trivial. No new dependencies (stdlib only,
including the test). No bundler involved (vanilla JS).

## 6. Checklist

- [ ] `exportPrivateDbReadable()` worker handler
- [ ] `downloadReadablePrivateData()` app fn
- [ ] Settings "Download readable copy" button + wiring
- [ ] `tests/e2e/test_export_readable_private_db.py` (parse + row-count-match)
- [ ] `docs/Architecture.md` PR-6 row (`conformant`, cites the tests)
- [ ] `just test tests/test_attestation_has_evidence.py` green
- [ ] `just test-e2e -k export_readable` green
- [ ] Update this plan's Status to DONE; note the commit
