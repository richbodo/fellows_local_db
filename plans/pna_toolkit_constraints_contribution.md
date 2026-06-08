# Plan — Contributing the **Constraints** concept to the Personal Network Toolkit (PNT)

> **Status: MERGED — [PNT PR #18](https://github.com/richbodo/personal_network_toolkit/pull/18) merged 2026-06-03.** This document staged the contribution; it was
> executed on the PNT branch `spec/constraints-concept`, opened as PR #18, and **merged**. The as-built set
> matches §3a–3f: `spec/constraints.md` (new), the `tools/lint-spec-ids.py` CST checks, the
> `PNA_Spec.md`/`axes.md` pointers, the SKILL build + evaluate steps, and the `fellows_local_db`
> reference-design record + § Constraint attestation. No `VERSION` bump (0.1 still draft-in-progress;
> `constraints.md` carries `Toolkit-Version: 0.1`). The open questions in § 5 were surfaced in the PR
> body for maintainer review.
>
> **Post-merge note (2026-06-08):** PR #260 *strengthened* two fellows-side rows
> (`CST-PWA-PRIVATE-SNAPSHOT`, `CST-PWA-STORAGE-EVICTABLE`) to cite the data-layer no-bypass guards
> (`test_browse_only_refuses_import_relationships_bytes`, `test_worker_is_load_bearing_off_folder_via_raw_rpc`).
> That evidence is newer than PR #18, so the PNT copy of fellows' § Constraint attestation may want a
> refresh at the next convenient sync (additive evidence only — no semantic change to any constraint).
> Tracked in [`upstream_contributions_staging.md`](upstream_contributions_staging.md). PR #18
> introduced the shared `PNA-DEFINITION` sentinel + validation-not-certification framing + lint
> header-tracing that the Exceptions and User-mediation contributions must now build on (land order
> inverted from this plan's §4 step 1 assumption). This file lives in the `fellows_local_db` repo
> (`plans/`) as the design record.
>
> Local paths referenced below (confirmed against the current checkout):
> - PNT repo: `/Users/richbodo/src/personal_network_toolkit` (spec files under `spec/`; `VERSION` = `0.1.0-draft`)
> - Demonstrating design (this repo): `/Users/richbodo/src/fellows_local_db`
>
> **Companion to** [`pna_toolkit_exceptions_contribution.md`](pna_toolkit_exceptions_contribution.md).
> Constraints are the **dual** of Exceptions; this plan deliberately mirrors that one's shape so the
> two land as a matched pair. The canonical lesson-learned that motivates it is
> [`../docs/architectural_findings.md` § 2026-06-01](../docs/architectural_findings.md).

---

## 1. Summary + motivation

### The discovery

A fellow's Private Data Ops MCP server stopped connecting to Claude Desktop. The proximate cause was
mundane — the `.mcpb` extension pointed at a `relationships.db` export that had been relocated out of
`~/Downloads`. But chasing *why the handoff was that fragile in the first place* surfaced a
class-level ceiling the app had been routing around without naming:

> For a PNA delivered as a web app, the private-data half's writability and external-readability is
> gated entirely by the browser's **File System Access API** — which is Chromium-only. On every
> non-FSA browser (Safari, Firefox, all of iOS), the private store can only live in the opaque OPFS
> sandbox (invisible to the user and to companion tools like the app's own MCP servers), is subject
> to silent browser eviction, and can escape to a real file only as a one-shot, immediately-stale
> download snapshot. So on those browsers the private half degrades to a **read-only snapshot at
> best**.

This is a different *kind* of finding from `EX-CLOUD-LLM`. That one is a **privacy** deviation a
user deliberately *raises* and the app *handles*. This is a **data-loss** ceiling the *platform*
imposes — nobody raises it; it is a property of the medium. The app's honest response was to
**reduce capability per platform**: folder mode (a real, user-visible, MCP-readable file) on
Chromium desktop; on Safari/Firefox/mobile, drop the durable private store and offer only
OPFS + manual backup — *for now*. The fellows decision log already reached for the word "constraint"
informally (`docs/ac_decisions_log.md` § 2026-05-22: *"This constraint is **fundamental to the
browser platform**, not something our code [can fix]"*); this contribution formalizes it.

### The tension is structural, not a fellows wart

The PNA Spec commits to private-data sovereignty (Goal 1) and to portable, durable, recoverable user
data (Goal 4; `spec/PNA_Spec.md`), and AC-1 commits to a read-write, locally-owned Private store. But
there is no first-class way for a PNA to say *"the platform I'm running on **cannot** deliver this
capability, here is the ceiling, here is how I reduced scope to stay honest, and here is whether
anyone has found a way around it yet."* The spec models conformance as *honoring every AC*; real
deployments need a way to declare **what the substrate forbids** and to be judged on *handling the
ceiling honestly* rather than on impossibly clearing it.

Any PNA that picks `distribution:web-bundle` × `storage:opfs-sqlite-wasm` inherits this ceiling and a
family of siblings (eviction, no built-in sync, the single-owner OPFS architecture, the sandbox
boundary that seals the store off from the user's other tools). It is a property of the application
*class*, which is exactly what the toolkit exists to capture.

### The resolution

Introduce a new first-class PNT concept — **Constraints** — the dual of Exceptions. A Constraint is a
stable-ID'd (`CST-*`) **platform- or substrate-imposed ceiling**, inherited automatically by one or
more **axis picks**, that *removes or bounds functionality a PNA would otherwise offer*. Unlike an
Exception, **no one raises it** — it is a property of the medium. It obligates a documented
**handling** (typically per-platform capability reduction — "enough power to be useful, not enough to
be dangerous") and carries an explicit **resolution frontier**: whether a viable workaround is known,
or whether (as of this version) none has been found.

**Crucial difference from Exceptions:** handling a Constraint **does not exit PNA mode.** A
capability-reduced PNA that honestly handles its inherited ceilings is *fully a PNA* — just a smaller
one on that platform. The dishonest failure mode is *pretending the ceiling isn't there* — promising
durability the platform can't keep (the Android-folder-mode "false durability" bug fellows fixed in
PR #234). That is a conformance failure, but it is not a "mode."

### Why this belongs upstream, not just in fellows

Per `pna-build-eval-contrib/SKILL.md` § Contribute → Preflight, the most valuable submission pattern
is a **new architectural concept the spec doesn't yet name**, with a demonstrating reference design.
Constraints are exactly that, and fellows already *ships* the handling (folder mode, per-platform
capability reduction, the mobile gate, manual-backup durability path) — so the reference-design half
is in far better shape here than it was for the not-yet-built `EX-CLOUD-LLM` handler. The spec change
rides along with working code, as `CONTRIBUTING.md` requires.

---

## 2. The Constraints concept

### Compile-time-error metaphor (the dual of the Exception's runtime-error metaphor)

Exceptions borrow the *runtime* exception metaphor (raise / catch / handle). Constraints borrow the
*compile-time* one: the platform's type system won't admit the program you wanted, so you restructure
to a smaller program that *does* type-check.

| Software | PNA Constraint |
|---|---|
| A compile-time / type error: the platform won't admit the program you intended | A capability the PNA **cannot express** on a given platform, given its axis picks |
| Not caught at runtime — you restructure the program to fit | Handled by **reducing the feature set** to what the platform can actually keep |
| The error names exactly what's unsupported | Every constraint has a stable `CST-*` ID naming the ceiling |
| `#ifdef PLATFORM` / capability shims | **Per-platform capability reduction** ("enough power to be useful, not dangerous") |
| A `// TODO: unsupported on X` with an issue link | The **Frontier** field: `Open` (no known workaround) vs `Solved`/`Mitigated` (here's how) |

### Inherited / detected / handled

- **Inherited** — a Constraint attaches automatically to one or more axis picks. Picking
  `storage:opfs-sqlite-wasm` *is* taking on `CST-PWA-SANDBOX-SEALED`; no action raises it.
- **Detected** — the app must determine, per platform/session, whether the ceiling is active, and do
  so **honestly** (see the Detectability field — capability presence ≠ usefulness ≠ permanence).
- **Handled** — the app reduces capability to match what the platform can deliver, and **declares the
  frontier honestly** (does not claim to solve what it only mitigated). A reference design stays
  conformant by handling, not by overcoming.

### Constraints do not change PNA mode

> **Exceptions exit PNA mode; Constraints do not.** A PNA that honestly handles an inherited
> Constraint remains in PNA mode — it is simply capability-reduced on that platform. The conformance
> question for a Constraint is not "is it active?" (it always is, on the triggering platform) but
> "is it **handled honestly** — capability matched to deliverable durability, frontier declared
> truthfully, no false promises?"

### The adverse-only registry decision (recorded for the PR)

Some platform ceilings happen to *serve* a PNA goal (a PWA can't send mail itself, only hand off a
`mailto:` URL — landing the app in exactly the "transports cannot read message contents" shape AC-18
wants). These are real but are **not** builder/verifier advice the way an adverse ceiling is. The
constraints registry is therefore **adverse-only**: it catalogs ceilings that *take capability away*.
"Helpful constraints" belong in a separate, future *"things that worked well, proven true and
useful"* channel — explicitly **out of scope** for this contribution. (No `valence` field; the
concept was considered and deferred — see § 5.)

### Validation, not certification (same framing the exceptions work promotes)

This contribution reinforces the framing the Exceptions plan makes load-bearing:

> **PNT validates behaviors against the Goals; it does not certify.** For Constraints, the evaluate
> flow detects each inherited ceiling and verifies that the candidate *handles it honestly* —
> capability reduced to match the platform, frontier declared truthfully — reporting by `CST-*` ID.
> "This design inherits `CST-PWA-PRIVATE-SNAPSHOT` and handles it by dropping private writes
> off-Chromium (frontier: Open)" is a finding, not a grade.

The backstop, dual to the Exceptions backstop: where the Exceptions evaluate pass catches *undeclared
deviations* (the app violates an AC without raising an exception), the Constraints evaluate pass
catches *undeclared over-reach* — the app promises a capability the platform cannot keep without
acknowledging the ceiling (**false durability**). Both are silent dishonesty; both are conformance
failures.

### Terminology note (recorded for the PR)

The concept was considered as *limitation*, *ceiling*, and *constraint*. **Constraint** is preferred:
it pairs cleanly with Exception (the runtime/compile-time dual), the fellows decision log already used
the word, and "limitation" reads as an apology where "constraint" reads as a design boundary. See § 5
for residual terminology questions.

---

## 3. Proposed PNT artifacts

Each sub-plan is concrete enough to be mechanical to execute, with DRAFT text where it helps. None of
it is to be applied to PNT yet.

### 3a. NEW file: `spec/constraints.md`

A new spec file (sibling to `spec/axes.md`, `spec/use_cases.md`, `spec/exceptions.md`). It carries
four things: the concept, the header conventions (`Triggered-by:` / `Bounds:` / `Frontier:` /
`Detectability:`), the constraint registry (eight `CST-PWA-*` entries), and a non-normative
implementation-notes appendix (the "footguns").

#### DRAFT — front matter + concept

```markdown
# PNA Constraints

> **Spec-Version:** tracks the PNA Spec version in spec/PNA_Spec.md.
>
> This file defines **Constraints**: stable-ID'd ceilings (`CST-*`) that a platform or storage
> substrate imposes on a PNA, inherited automatically by one or more axis picks (spec/axes.md).
> Constraints are the dual of Exceptions (spec/exceptions.md): an Exception is a deviation the USER
> raises and the app handles; a Constraint is a limitation the PLATFORM imposes and the app must
> likewise handle — never silently.

## Concept

A Constraint is **inherited** (by an axis pick — raised by no one), must be **detected** honestly per
platform, and must be **handled** by reducing capability to what the platform can actually deliver
("enough power to be useful, not enough to be dangerous").

**Handling a Constraint does NOT exit PNA mode.** A capability-reduced PNA that handles its inherited
ceilings honestly is fully a PNA. The failure mode is over-reach: promising a capability the platform
cannot keep (false durability) without acknowledging the ceiling.

PNT validates behaviors against the Goals; it does not certify. The evaluate flow detects each
inherited Constraint and verifies that the candidate handles it honestly, reporting by `CST-*` ID.

The registry is **adverse-only**: it catalogs ceilings that remove or bound capability. Ceilings that
happen to serve a PNA goal are out of scope here.
```

#### DRAFT — header conventions (mirroring exceptions' `Relaxes:`/`Reversible:`)

```markdown
## Header conventions

These mirror the `Realizes: AC-...` header in `contracts/` and the `Relaxes:`/`Reversible:` headers
in `exceptions.md`. They appear in a constraint's registry entry and in any reference design's
constraint-attestation declaration.

- **`Triggered-by:`** — names the axis pick(s) that inherit this constraint. Each token is an
  axis-pick identifier of the form `<axis>:<pick>` as defined in axes.md (e.g.
  `storage:opfs-sqlite-wasm`, `distribution:web-bundle`). Multiple tokens are comma-separated and
  mean "any of these picks inherits it" unless the entry says the combination is required.
  Example: `Triggered-by: distribution:web-bundle, storage:opfs-sqlite-wasm`
- **`Bounds:`** — names the Goal(s)/AC(s) whose full achievement the ceiling limits. The PNA still
  TRIES to honor them; the constraint bounds how completely it can on the triggering platform. Tokens
  are `AC-*`, `Goal-N`, or the literal `PNA-DEFINITION`. Example: `Bounds: AC-1, Goal-4`
- **`Frontier:`** — the resolution status. One of `Open` (no viable workaround found this version),
  `Mitigated` (partial handling exists; ceiling not removed), `Solved-on-<platform>` (removed on the
  named platform — e.g. `Solved-on-chromium`), or `Inherent` (cannot be removed; it is the medium).
  If `Mitigated` or `Solved-*`, a `Workaround:` field MUST follow naming the mechanism (a control,
  route, or code reference the validation flow can confirm).
  Example: `Frontier: Solved-on-chromium` / `Workaround: File System Access folder mode writes a
  real, user-visible file; see <design>'s Architecture.md.`
- **`Detectability:`** *(builder-actionable)* — how a builder determines whether the ceiling is active
  on a given platform. One of `feature-detect` (a clean capability check suffices), `empirical-probe`
  (the feature check lies; you must actually exercise it), or `ua-sniff` (no reliable capability
  signal; user-agent inference is the only handle). Example: `Detectability: ua-sniff`
```

> **`PNA-DEFINITION` token.** Reused from the Exceptions plan (§ 3a there) — the PNA definition lives
> in prose (`vocab-pna`), not in the AC table, so `Bounds:` references it via the same literal
> sentinel the lint already resolves for `Relaxes:`. No new special-case if the Exceptions
> contribution lands first.

#### DRAFT — constraint registry (all eight entries; the two headliners in full)

```markdown
## Constraint registry

| CST | Name | Triggered-by | Bounds | Frontier | Detectability |
|---|---|---|---|---|---|
| CST-PWA-PRIVATE-SNAPSHOT | Private store read-only off FSA browsers | distribution:web-bundle, storage:opfs-sqlite-wasm | AC-1, Goal-4 | Open | feature-detect (page-side `showDirectoryPicker`) |
| CST-PWA-SANDBOX-SEALED | OPFS store invisible + non-interoperable | storage:opfs-sqlite-wasm | AC-1, Goal-4, AC-MCP-A | Solved-on-chromium | feature-detect |
| CST-PWA-STORAGE-EVICTABLE | Script storage is evictable | storage:opfs-sqlite-wasm | Goal-4 | Mitigated | empirical-probe (`persist()` is advisory) |
| CST-PWA-NO-SYNC | Origin/device-local silos; no built-in portability | distribution:web-bundle, storage:opfs-sqlite-wasm | Goal-4 | Open | feature-detect |
| CST-PWA-DURABLE-SQL-ARCH | Durable SQL forces worker-owned single-connection arch | storage:opfs-sqlite-wasm | (none — bounds the build space, not a user AC) | Inherent | feature-detect (in-worker) |
| CST-PWA-SINGLE-OWNER | Multi-tab contention, no OS file lock | storage:opfs-sqlite-wasm | AC-11 | Solved-on-chromium | empirical-probe |
| CST-PWA-NO-BACKGROUND | No reliable scheduled background execution | distribution:web-bundle | Goal-4 | Mitigated | feature-detect (Periodic Sync absent on iOS) |
| CST-PWA-SERVER-FLOOR | Origin + TLS + secure context required | distribution:web-bundle | PNA-DEFINITION | Inherent | feature-detect (`isSecureContext`) |

### CST-PWA-PRIVATE-SNAPSHOT — Private store is read-only off File-System-Access browsers

**Triggered-by:** distribution:web-bundle, storage:opfs-sqlite-wasm
**Bounds:** AC-1, Goal-4
**Frontier:** Open — no viable workaround found as of Spec-Version 0.x for keeping a LIVE, writable,
externally-readable private store off Chromium. An encrypt-then-email-to-self portability pattern is
a candidate (snapshot transport, not live), unproven.
**Detectability:** feature-detect — page-side `'showDirectoryPicker' in window`. (Necessary but not
sufficient; see CST-PWA-STORAGE-EVICTABLE and the Android caveat in CST-PWA-NO-BACKGROUND for why a
positive check still doesn't guarantee a *durable* store.)

**Ceiling:** The File System Access API (the only browser API granting a web app a persistent
writable handle to a user-chosen, user-visible file) is Chromium-only. On Safari, Firefox, and all
iOS browsers the private store can live only in the opaque OPFS sandbox or escape as a frozen
download snapshot. The "private half" of the PNA — meant to be the user's sovereign, live,
manipulable data — degrades to read-only-snapshot-at-best.

**Recommended handling:** per-platform capability reduction. On FSA-capable platforms, offer folder
mode (a real file). On non-FSA platforms, do not promise a durable live private store; offer
OPFS + an explicit manual backup/export path and SAY SO. Demonstrated by `fellows_local_db`
(reference_designs/fellows_local_db/).

### CST-PWA-SANDBOX-SEALED — OPFS store is invisible to the user and to their other tools

**Triggered-by:** storage:opfs-sqlite-wasm
**Bounds:** AC-1, Goal-4, AC-MCP-A
**Frontier:** Solved-on-chromium
**Workaround:** File System Access folder mode relocates the store to a real, user-visible file that
companion tools (MCP servers, backups, CLIs) can read directly; the sandbox boundary dissolves. Off
Chromium the boundary stands and only snapshot export bridges it.
**Detectability:** feature-detect.

**Ceiling:** OPFS is an origin-scoped sandbox. The store is invisible in the user's file manager and
unreadable by any other program on the machine, and a PWA cannot host native integration (no stdio,
no sockets, no local server) to bridge it — so the app's own MCP servers must ship as separate native
processes that can only read an EXPORTED copy. **This is the root cause of the MCP-handoff fragility
that surfaced this whole finding.** A PNA is meant to be the hub the user's other tools act on; a
store those tools cannot read is half a PNA.

**Recommended handling:** folder mode where available (dissolves the boundary); elsewhere, an explicit
export/import bridge with honest messaging that companion tools see a snapshot, not the live store.
Demonstrated by `fellows_local_db`.
```

> **Remaining six entries** (CST-PWA-STORAGE-EVICTABLE, -NO-SYNC, -DURABLE-SQL-ARCH, -SINGLE-OWNER,
> -NO-BACKGROUND, -SERVER-FLOOR) follow the identical block shape; full prose is drafted from the
> 8-row analysis in `../docs/architectural_findings.md` § 2026-06-01 when this plan is executed. Each
> already has its Triggered-by / Bounds / Frontier / Detectability fixed in the table above.

#### DRAFT — non-normative implementation notes (the "footguns")

```markdown
## Implementation notes (non-normative)

These are navigable PWA footguns — recorded so builders don't re-derive them, but they are NOT
ceilings and carry no `CST-*` ID. (Per the contribution's "ceilings normative, footguns noted"
decision.)

- **Service-worker staleness.** A cached app shell can pin users to old code; "what code is running"
  is ambiguous. Handle with source-tied build labels + an explicit update banner.
- **No atomic factory reset.** OPFS has no per-origin wipe API; an HttpOnly session cookie needs a
  server round-trip. A full reset must reach each layer deliberately.
- **PWA install + manifest gotchas.** WebAPK `related_applications` can trigger Play-Store
  verification failures; POST `share_target` silently fails on some WebAPK servers; iOS hides install
  behind Share → Add to Home Screen. Keep the manifest minimal; document per-platform install flows.
```

#### Meta-principles (promoted alongside the registry)

```markdown
## Meta-principles

- **M1 — capability presence ≠ usefulness ≠ permanence.** `showDirectoryPicker in window` is true on
  Android Chrome but only reaches an OS-clearable folder; `persist()` returns true but Safari still
  evicts; `createSyncAccessHandle` exists in a worker but not on the page. Detect USEFUL, DURABLE
  capability — often empirically. This is why every entry carries a `Detectability:` field.
- **M3 — the handling pattern is per-platform capability reduction.** Match each platform's offered
  features to the durability it can actually keep: "enough power to be useful, not enough to be
  dangerous."
```

### 3b. ONE-LINE pointers from `spec/PNA_Spec.md` and `spec/axes.md`

The lightest touch that keeps the AC-ID lint green (the lint reads `PNA_Spec.md` + `axes.md` for AC
rows and does not parse free text; prose pointers add no `| AC-X |` rows).

- **`spec/PNA_Spec.md`** — a one-line pointer in § Vocabulary or near the Goal-4 (durability)
  statement, since Constraints are precisely where Goal-4 meets platform reality. DRAFT:

  ```markdown
  > A platform or storage substrate may impose a ceiling that bounds how fully a PNA can honor a Goal
  > or AC on a given platform — a **Constraint** (see [`constraints.md`](constraints.md)). A PNA stays
  > conformant by handling each inherited Constraint honestly (capability reduced to what the platform
  > can keep, frontier declared truthfully); handling a Constraint does not exit PNA mode.
  ```

- **`spec/axes.md`** — one cross-reference note on each triggering pick (the `storage:opfs-sqlite-wasm`
  pick and the `distribution:web-bundle*` picks), pointing at the constraints they inherit. DRAFT
  (storage pick): `Inherits CST-PWA-SANDBOX-SEALED, CST-PWA-STORAGE-EVICTABLE,
  CST-PWA-DURABLE-SQL-ARCH, CST-PWA-SINGLE-OWNER (see constraints.md).` This is the **generative**
  half — a builder reading the axis sees what they're taking on.

**Lint-safety check (when executing):** after editing, run `python tools/lint-spec-ids.py` from the
PNT root; confirm `OK` and the same AC count. Pointer text must not contain a line starting with
`| AC-`.

### 3c. Extend `tools/lint-spec-ids.py`

Mirror the AC machinery (and the EX machinery, if the Exceptions contribution lands first) for
constraints. **Design-level, not final code:**

**New regexes (mirror `AC_RE` / `REALIZES_RE` / `REVERSIBLE_RE`):**

```python
# Mirrors AC_RE. Collects CST-* IDs from registry rows in spec/constraints.md.
CST_RE = re.compile(r"^\| (CST-[A-Z0-9-]+?)(?=\s|\*|\|)", re.MULTILINE)

# Mirrors REALIZES_RE. Triggered-by tokens are axis-pick identifiers (<axis>:<pick>).
TRIGGERED_RE = re.compile(r"Triggered-by:\s*((?:[a-z0-9-]+:[a-z0-9-]+(?:\s*,\s*)?)+)", re.IGNORECASE)

# Bounds tokens may be AC-*, Goal-N, or PNA-DEFINITION.
BOUNDS_RE = re.compile(
    r"Bounds:\s*((?:(?:AC-[A-Z0-9-]+|Goal-[0-9]+|PNA-DEFINITION)(?:\s*,\s*)?)+)",
    re.IGNORECASE,
)

# Frontier: Open | Mitigated | Solved-on-<platform> | Inherent. Solved/Mitigated require Workaround:.
FRONTIER_RE = re.compile(r"Frontier:\s*(Open|Mitigated|Solved-on-[a-z0-9-]+|Inherent)\b", re.IGNORECASE)

# Detectability: feature-detect | empirical-probe | ua-sniff.
DETECT_RE = re.compile(r"Detectability:\s*(feature-detect|empirical-probe|ua-sniff)\b", re.IGNORECASE)
```

**New collection + checks in `main()` (mirror the existing AC loop):**

1. `collect_constraint_ids()` — read `spec/constraints.md`, `CST_RE.findall`, return the `CST-*` set.
   Absent file → empty set (lint stays green on repos that haven't adopted constraints).
2. For every `Triggered-by:` token: it MUST resolve to a known axis pick in `axes.md`. (Requires
   collecting `<axis>:<pick>` identifiers from axes.md — a small new collector; if axes.md doesn't yet
   expose pick IDs in a machine-readable form, the first cut MAY validate only the `<axis>:` prefix
   against the known axis list. Flag in § 5.) Failure: `f"{src}: Triggered-by names {tok}, not a known
   axis pick."`
3. For every `Bounds:` token: MUST resolve to a known `AC-*`, a `Goal-N`, or `PNA-DEFINITION`. Exact
   inverse of the existing "claims to realize {ac}" check.
4. For every entry: `Frontier:` MUST match `FRONTIER_RE`; if `Mitigated`/`Solved-*`, a `Workaround:`
   field MUST be present. `Detectability:` MUST match `DETECT_RE`. Failures name the malformed field.

**What the lint deliberately does NOT do:** it does not assert the ceiling is genuinely detected or
handled at runtime, nor that the workaround works — that is the LLM evaluate layer (§ 3e). It
validates declaration shape (presence + traceability), exactly as the tool does for `Realizes:`.

**Output + docstring:** extend the success summary with `spec defines N constraint IDs` /
`M Triggered-by header(s) resolved`; add the CST/Triggered-by/Bounds/Frontier checks to the module
docstring.

### 3d. Strengthen the "validation, not certification" framing (constraints angle)

If the Exceptions contribution already added the framing callout to `spec/PNA_Spec.md` § Building a
PNA, extend it with one clause; otherwise add it. DRAFT addition:

```markdown
> For Constraints, the evaluate flow detects each ceiling a design's axis picks inherit and verifies
> it is handled honestly — capability reduced to what the platform can keep, frontier declared
> truthfully — reporting by `CST-*` ID. Over-reach (promising a capability the platform cannot keep)
> is a silent conformance failure, the dual of an undeclared Exception.
```

### 3e. Add a constraint pass to the SKILL flows (`pna-build-eval-contrib/SKILL.md`)

Constraints are most generative in the **Build** flow and most checkable in the **Evaluate** flow.

**Build flow — new step (after axis selection):**

```markdown
N. **Enumerate inherited Constraints.** From the chosen axis picks, list every Constraint they
   inherit (spec/constraints.md `Triggered-by:`). For each, state the handling you will implement
   (per-platform capability reduction) and its frontier. A web-bundle × opfs-sqlite-wasm PNA inherits
   the full CST-PWA-* family; plan the folder-mode-vs-OPFS-only split and the honest non-Chromium
   messaging up front, not as an afterthought.
```

**Evaluate flow — new step (after the exceptions pass, mirroring it):**

```markdown
3c. **Detect and verify Constraints.** For each Constraint the candidate's axis picks inherit:
    - **Detected honestly?** Confirm the app determines whether the ceiling is active using a sound
      signal for that constraint's Detectability class (feature-detect / empirical-probe / ua-sniff).
      Flag capability checks trusted where presence ≠ usefulness (M1).
    - **Handled by capability reduction?** Confirm the app offers only what the platform can keep, and
      that any durability promise (badges, "saved" affordances) matches reality. Cite code/UX.
    - **Frontier honest?** Read the `Frontier:` declaration; confirm the design does not claim to
      Solve what it only Mitigated, and that a `Workaround:` (where claimed) actually exists in
      code/UX.
    - **Over-reach (the backstop).** If the candidate promises a capability the platform cannot keep
      WITHOUT acknowledging the ceiling — false durability — that is a silent conformance failure.
      Flag it and name the `CST-*` it should have handled.
    Report each finding by `CST-*` ID.
```

The three-layer split matches the Exceptions contribution:
- **Lint (mechanical):** `CST-*` defined; `Triggered-by:` resolves to axis picks; `Bounds:`
  traceable; `Frontier:`/`Detectability:` well-formed (§ 3c).
- **Evaluate (LLM):** detection sound, handling real, frontier honest, over-reach caught (this step).
- **Human:** final judgment at PR time (`CONTRIBUTING.md` § Acceptance — unchanged).

### 3f. `fellows_local_db` as the demonstrating reference design

Unlike the Exceptions contribution (whose `EX-CLOUD-LLM` handler was unbuilt at plan time), fellows
**already ships** the constraint handling — folder mode on Chromium, per-platform capability reduction
off it, the mobile data-folder gate (PR #234), the "Download my private data" backup path, the
browser-only badge. So the reference-design half is largely a *documentation* task, not new feature
work.

**(i) Design record — `reference_designs/fellows_local_db/README.md`** — add a *Contributions to the
spec* bullet for this PR (Constraints concept + CST-PWA-* registry, demonstrated by fellows' folder
mode + capability reduction).

**(ii) Architecture.md copy — `reference_designs/fellows_local_db/Architecture.md`** — PNT keeps its
own copy at acceptance; copy fellows' `docs/Architecture.md` *with* the new Constraints section.

**(iii) Constraint attestation in fellows' `docs/Architecture.md`** — a new section mirroring the
existing *Exception attestation* table, copied into the PNT Architecture.md. DRAFT:

```markdown
## Constraint attestation

| CST | Inherited by | Handling (capability reduction) | Frontier | Verification | Status |
|---|---|---|---|---|---|
| CST-PWA-PRIVATE-SNAPSHOT | web-bundle × opfs | Folder mode (real file) on Chromium desktop; off-Chromium drop durable private store, offer OPFS + manual "Download my private data". Code: `app/static/vendor/sqlite-worker.js` (folder write path), `app/static/app.js` (`folderStorageOffered()`, badges, download button). | Open | e2e `test_user_folder_storage.py`, `test_unsupported_browser.py`; `docs/browser_support.md`; LLM rubric: "off-Chromium, confirm no durable-private-store promise and a visible manual-backup path." | handled (frontier Open) |
| CST-PWA-SANDBOX-SEALED | opfs | Folder mode dissolves the boundary (MCP reads the live file); off-Chromium the `.mcpb` reads an exported snapshot, disclosed in the setup flow. Code: folder write path; `mcp_servers/private_data_ops.py` reads an external file. | Solved-on-chromium | `tests/test_private_data_ops.py`; `docs/architectural_findings.md` § 2026-06-01. | handled |
| CST-PWA-STORAGE-EVICTABLE | opfs | `navigator.storage.persist()` best-effort once per install; 5-slot backup ring; manual export. Code: `app.js` persist path (`~4171`), `sqlite-worker.js` backup ring. | Mitigated | e2e backup/restore tests; AC-9 row. | handled |
| CST-PWA-SINGLE-OWNER | opfs | Web Lock `fellows-relationships-folder-write` + `OWNERSHIP_CONFLICT` panel. Code: `sqlite-worker.js` (`isOwnershipConflictError`, locks). | Solved-on-chromium | `test_user_folder_storage.py::TestPhase2WriteLock`; AC-11 row. | handled |
| CST-PWA-NO-BACKGROUND | web-bundle | Per-boot debounced auto-backup; no scheduled-protection promise. Code: `maybeBackupRelationshipsDb`. | Mitigated | AC-9 row; code inspection. | handled |
| CST-PWA-SERVER-FLOOR | web-bundle | Server bounded to distribution/update only (Never-SaaS); no per-user RW endpoints. Code: `deploy/server.py`. | Inherent | `test_deploy_auth_round_trip.py`; AC-2 row. | handled |
```

> The two entries with no user-facing handling — `CST-PWA-NO-SYNC` (frontier Open; the
> encrypted-email pattern is a candidate, unbuilt) and `CST-PWA-DURABLE-SQL-ARCH` (Inherent; realized
> as the worker-owned architecture, AC-3) — are attested as `Open` / `Inherent` respectively. Honest
> frontiers, not hidden gaps.

#### Gap analysis — fellows' current `docs/Architecture.md`

Much lighter than the Exceptions plan's gap analysis, because the AC attestation table **already
exists** with Realization / Verification / Status columns (`docs/Architecture.md` § Universal ACs +
§ Flavor-derived ACs) and an *Exception attestation* section is already present. The remaining work:

1. **Add a § Constraint attestation** (the table above) — the only substantive doc addition.
2. **Add a short "Constraints triggered by fellows's picks" note** alongside the existing
   "Flavor-derived ACs triggered by fellows's picks" section, cross-referencing the CST IDs.
3. **No new feature code required** — the handling is already shipped (folder mode, capability
   reduction, mobile gate, backup path). This is the key difference from the Exceptions contribution
   and makes the reference-design half low-risk.

---

## 4. Sequencing + how this is driven through the SKILL Contribute flow

Stays a **PLAN in the fellows repo** until the maintainer approves. When approved:

1. **Decide ordering relative to the Exceptions contribution.** Constraints reuse the
   `PNA-DEFINITION` sentinel and the validation-not-certification callout the Exceptions plan
   introduces. **Recommend landing Exceptions first**, then Constraints as the matched dual (smaller
   lint delta, shared framing already in place). They can also land together as one "Exceptions +
   Constraints" pair if the maintainer prefers a single version bump.
2. **Add the § Constraint attestation to fellows' `docs/Architecture.md`** (§ 3f gap #1–#2). No
   feature code — the handling already ships.
3. **Run the SKILL preflight** against fellows: validate the Architecture doc's constraint rows
   against the code/tests; iterate until clean.
4. **Author the PNT changes on a branch in a PNT checkout** (still no PR): `spec/constraints.md`
   (§ 3a), the `PNA_Spec.md` + `axes.md` pointers (§ 3b), the `lint-spec-ids.py` extension (§ 3c), the
   framing clause (§ 3d), the SKILL build + evaluate steps (§ 3e), and the reference-design record +
   Architecture.md copy + constraint attestation (§ 3f). Run `python tools/lint-spec-ids.py`; confirm
   green.
5. **Only on the maintainer's explicit go-ahead:** open the PNT PR per `SKILL.md` § PR authoring /
   `CONTRIBUTING.md` § PR contents. Version bump is **Minor** per `CONTRIBUTING.md` § Versioning
   (additive: a new spec file, a new concept, new header conventions, a new lint check — no existing
   AC altered, no pick removed).
6. **Post-merge** (maintainer): Software Heritage archival at the accepted commit; record the SWHID in
   the design record.

**Explicit decision recorded here:** no issues or PRs are filed into PNT from this plan. This document
is the artifact the maintainer reviews; everything downstream waits on approval.

---

## 5. Open questions / terminology notes

1. **Land order vs Exceptions.** Recommend Exceptions first (Constraints reuse its `PNA-DEFINITION`
   sentinel + framing callout), or ship them as one paired bump. Maintainer's call.
2. **Naming.** "Constraint" over "limitation"/"ceiling" (pairs with Exception; the decision log
   already used it). Confirm the compile-time/runtime dual is the framing the PR leads with.
3. **Are machine-readable axis-pick IDs available for the lint (§ 3c check 2)?** `Triggered-by:`
   resolution needs `<axis>:<pick>` identifiers collectable from `axes.md`. If axes.md doesn't expose
   them in a stable form, either (a) add pick IDs to axes.md (a small, independently-useful change),
   or (b) have the first cut validate only the `<axis>:` prefix against the known axis list. Recommend
   (a) if cheap, else (b) with a TODO.
4. **`Bounds:` vs a non-normative `Stresses:`.** `Bounds:` says the constraint *limits how fully* an
   AC/Goal can be met (the app still tries). Is that the right verb, or should some entries use a
   softer `Stresses:` (pressure without strict bounding), as exceptions do? Recommend `Bounds:` as
   primary with `Stresses:` available for Goal-level pressure that doesn't bound a specific AC.
5. **Valence / "helpful constraints" — deferred, confirm.** The registry is adverse-only; ceilings
   that serve a goal (mailto-only → AC-18) are parked for a future "what worked well, proven true and
   useful" channel. Confirm this stays out of the constraints registry for v1.
6. **`CST-PWA-*` namespace vs a flatter `CST-*`.** The general mechanism is substrate-agnostic, but
   the first eight entries are all PWA/web ceilings, so they're namespaced `CST-PWA-*`, leaving room
   for `CST-NATIVEFS-*`, `CST-MOBILE-NATIVE-*`, etc. Confirm the per-substrate namespace (vs flat
   `CST-1..`); recommend keeping it — it makes "which substrate forbids this" legible at a glance.
7. **Does the lint collect `Triggered-by:`/`Frontier:` from reference-design Architecture docs too, or
   only from `spec/constraints.md`?** Mirror the Exceptions § 5.6 answer: lint the spec registry
   first; extend to design-doc attestations if/when a second substrate's constraints land.
8. **Should `CST-PWA-DURABLE-SQL-ARCH` be in the registry at all?** It bounds the *build space* (you
   must use a worker-owned single-connection architecture), not a user-facing AC — its `Bounds:` is
   empty. It's a real inherited ceiling a builder must know, but it's a different flavor from the
   functionality-dropping ones. Recommend keeping it (the registry's job is "what you inherit by
   picking this axis," which includes architecture-forcing ceilings) but flag it in the PR as the
   one builder-facing-rather-than-user-facing entry.
```
