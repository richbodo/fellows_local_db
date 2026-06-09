# docs/conformance/

Generated conformance artifacts for `fellows_local_db`. The **source of truth**
for every claim is the attestation table in [`../Architecture.md`](../Architecture.md)
(the Security Target); everything here is a deterministic serialization of it.
Nothing in this directory is hand-edited.

## Two artifacts, two audiences

| File | Format | Audience | Emitted by |
|---|---|---|---|
| `report.json` / `report.md` | **fellows-format** | this repo's ship gate + a human reading "are we honest?" | `scripts/conformance_report.py` |
| `evaluate-report.json` | **PNT toolkit schema** | the upstream Personal Network Toolkit (PNT) — its keystone `[verify].entrypoint` | `scripts/evaluate_report.py` |

Both are derived from the same attestation rows via the shared
`scripts/conformance_lib.py`, so they cannot disagree about what a row cites or
whether a cited test is a live, non-deferred assertion.

### `report.{json,md}` — the deterministic gate readout

Verifies that every `conformant` row in `Architecture.md` is backed by **live,
executable evidence** (a resolvable, non-`xfail`/`skip` test ref or a declared
verification kind), counts strict-xfail deferrals against the cap, and flags
abandoned deferrals. This is the *fellows* readout; it does **not** validate
against the toolkit's render schema. See
[`../../plans/conformance_report_and_gate.md`](../../plans/conformance_report_and_gate.md).

### `evaluate-report.json` — the toolkit render-contract artifact

The machine-comparable form the PNT evaluate flow produces, conforming to
`personal_network_toolkit/tools/evaluate-report.schema.json`. The toolkit
consumes this as the keystone's `[verify].entrypoint` output: a schema-valid
report is what lets the toolkit's `design.toml` flip `archival` to `archived`.

**This is the deterministic emitter, not an LLM audit.** It is reproducible and
CI-able: same `candidate.commit` + same attestation → byte-identical output (no
wall-clock timestamp is stamped).

The toolkit schema is **AC-keyed** — `findings[].ac_id` must match
`^AC-[A-Z0-9-]+$`, and the schema's own `$comment` places `EX-*`/`CST-*` "as
references inside the AC findings they bear on." So the emitter:

- emits **one finding per AC row** (Universal ACs, Flavor-derived ACs, and the
  not-applicable table);
- **folds each `EX-*`/`CST-*` row into the `evidence` of the AC(s) it bears on**,
  via `EXTENSION_AC_HOME` in `scripts/evaluate_report.py`. A declared
  exception/constraint with no AC home makes the emitter **raise** — it cannot
  be silently dropped (same fail-loudly discipline as the rest of the gate);
- maps status: `conformant` → `conformant`; `not-applicable` →
  `not-applicable` (+ the row's Reason as `rationale`); `partial-conformance` →
  `conformant` + `needs_human_review: true` (the schema has no `partial`
  status, so the residual is recorded honestly as a review flag with the
  original Status text preserved in the evidence prose).

The fellows-local `UM-*` user-mediation rows and the mediated-boundary registry
sit *beneath* the AC families and are out of scope for the AC-keyed toolkit
model; they remain in `report.{json,md}`.

## Regenerate / validate

```bash
just evaluate-report
```

Emits `evaluate-report.json` and validates it against PNT's render contract. It
runs the authoritative toolkit lint when the PNT checkout is present
(`$HOME/src/personal_network_toolkit`, or `PNT_REPO=<path>` to override) and
falls back to the emitter's built-in render-contract check otherwise. The raw
form the toolkit documents as the success criterion:

```bash
python3 ~/src/personal_network_toolkit/tools/report-fixtures-lint.py \
    docs/conformance/evaluate-report.json
# -> "satisfies the render contract"
```

> **Don't lint the whole directory.** `report-fixtures-lint.py docs/conformance/`
> would also try to lint `report.json` (fellows-format, not toolkit-schema) and
> fail. Always point the lint at the **file** `evaluate-report.json`.

## How it stays current (the gate wiring)

- `scripts/conformance_report.py`'s write path also re-emits
  `evaluate-report.json`, so `just conformance`, `just conformance-refresh`, and
  the staleness refresh inside `just test` all keep it in sync with `report.json`.
- `deploy-preflight` runs `scripts/evaluate_report.py --check` (hermetic, no
  toolkit needed) so every deploy route gates on its render-contract validity.
- `tests/test_evaluate_report.py` validates the render contract under `just test`
  and runs the real toolkit lint when the checkout is present.
