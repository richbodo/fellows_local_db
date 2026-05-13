# PNA Spec

> **Spec-Version:** 0.1 (draft)
> **Status:** Skeleton — substantive content to be migrated from `../_pna_triage.md` per the triage doc's Next Steps.
>
> This document is the universal specification for personal network applications. Reference designs (e.g. `fellows_local_db`) declare conformance to a specific spec version and to a specific flavor (constellation of axis picks).
>
> When the `personal_network_toolkit` repo is created, this file moves there. fellows-specific content lives in `../Architecture.md`.

---

## Vocabulary

<!-- TODO (step 2): migrate from _pna_triage.md § Vocabulary, dropping fellows-specific examples. -->

---

## Goals

<!-- TODO (step 2): migrate Preamble + Goals 1-5 from _pna_triage.md § Goals. -->

---

## Use cases

A use case names a coherent class of PNA from the user's perspective. A use case typically suggests default axis picks but does not determine them.

See [`use_cases.md`](use_cases.md) for the attested use case catalog.

---

## Axes

A PNA's *flavor* is the full constellation of axis picks the builder makes. v0.1 names seven Axes: composition model, distribution, storage substrate, ingestion shape, workspace shell, comms transport set, MCP-exposure.

See [`axes.md`](axes.md) for the attested picks per Axis and the flavor-derived ACs each pick triggers.

---

## Composition

<!-- TODO (step 2): migrate from _pna_triage.md § Composition. Three attested compositional models: build-time-bundle, runtime-shell-pipeline, runtime-MCP-RPC. -->

---

## Universal architectural commitments

<!-- TODO (step 2): migrate the Universal ACs table from _pna_triage.md § Architectural commitments § Universal ACs. Flavor-derived ACs live in axes.md, grouped under the axis-pick that triggers them. -->

---

## Slot map

<!-- TODO (step 2): migrate from _pna_triage.md § Slot map. -->

---

## Scope and versioning

<!-- TODO (step 2): migrate from _pna_triage.md § Scope and versioning. -->

See [`CHANGELOG.md`](CHANGELOG.md) for the version history.
