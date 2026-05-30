# Plan — Contributing the **Exceptions** concept to the Personal Network Toolkit (PNT)

> **Status: PLAN ONLY.** This document stages a future contribution to the
> [`personal_network_toolkit`](https://github.com/richbodo/personal_network_toolkit) (PNT) repo.
> It is **not** the contribution itself, and nothing here has been executed. No issues or PRs are
> to be filed into PNT until the maintainer explicitly says so. This file lives in the
> `fellows_local_db` repo (`plans/`) as a design record the maintainer reviews first.
>
> Local paths referenced below:
> - PNT repo: `/Users/richbodo/src/personal_network_toolkit`
> - Demonstrating design (this repo): `/Users/richbodo/src/fellows_local_db-mcp-consent`

---

## 1. Summary + motivation

### The discovery

`fellows_local_db` ships three MCP servers (`mcp_servers/shared_data_ops.py`,
`mcp_servers/private_data_ops.py`, `mcp_servers/comms.py`) so an AI client can drive the directory
and a user's saved relationships. The flagship UX is a Claude Desktop user asking the model to
find a group, look up emails, and stage a `mailto:` — exactly the cooperation pattern the PNA Spec's
§ Vision describes.

The honest operational reality, captured today in `mcp_servers/README.md` § *Cloud LLM caveat*:

> "For v1, none of the three servers detects or gates cloud clients. … Today's position is:
> **document the boundary, trust the user's choice**. Wire the servers up to a local model … for
> the green-path posture."

A roughly **500-user base** (EHF fellows) wants the cloud-LLM integration. For almost all of them,
running a capable local model (the AC-MCP-A "green path") is impractical — wrong hardware, no
appetite to operate Ollama, and the hosted Claude Desktop model is simply what they already have.
So the realistic choice is binary and uncomfortable:

1. **Forbid it** — refuse cloud MCP clients on the Private Data Ops server. Conforms to AC-MCP-A,
   but denies the feature the users actually asked for, and pushes them toward worse, un-audited
   tools.
2. **Allow it silently** — what v1 does today: the data crosses the network to the provider and the
   only safeguard is a caveat buried in a README. This is dishonest about the app's posture at the
   moment a user is actually pointing a cloud model at their Private DB.

Neither is satisfying, and the tension is **structural**, not a fellows-specific wart. The PNA
definition is *"runs local-only, never as SaaS"* (`spec/PNA_Spec.md` § Vocabulary, `vocab-pna`),
and AC-MCP-A makes cloud Private-DB access opt-in. But there is no first-class way for a PNA to say
*"the user knowingly turned this guarantee off, here is how we caught it and how we handle it."*
The spec models conformance as **never deviating**; real deployments need a way to **deviate
honestly**.

### The resolution

Introduce a new first-class PNT concept — **Exceptions** — modeled on software exceptions. An
Exception is a stable-ID'd (`EX-*`) condition under which a PNA *deliberately departs* from a
baseline guarantee (a named AC, or the core PNA definition). Like a software exception, it is
**raised** by a specific user action, must be **caught** (never silent), and must be **handled** by
a defined **solution**. Raising any exception **exits PNA mode**.

The cloud-LLM tension then resolves into a third option:

3. **Allow it as a caught, handled Exception** — `EX-CLOUD-LLM`. Consent gate before raising,
   persistent "not a PNA right now" signal while active, in-app explainer of the active exception
   set, and a declared return-to-PNA-mode path. The app is honest, conformant *in non-PNA mode*,
   and the user gets the feature they asked for with eyes open.

This is the same ship-and-iterate bias the project already runs on: rather than block the feature
until local models are practical for 500 people, ship the honest non-PNA mode and refine the
handler from real use.

### Why this belongs upstream, not just in fellows

Per `pna-build-eval-contrib/SKILL.md` § Contribute → Preflight, three patterns justify a submission.
This is the most valuable one: a **new architectural concept the spec doesn't yet name**, with a
demonstrating reference design (`fellows_local_db`). The spec change rides along with working code,
exactly as `CONTRIBUTING.md` requires ("Spec changes without a demonstrating design are not
accepted").

---

## 2. The Exceptions concept

### Software-exception metaphor

| Software exception | PNA Exception |
|---|---|
| A condition that interrupts normal control flow | A condition under which a PNA departs from a baseline guarantee |
| `raise` / `throw` | **Raised** by a specific user action (e.g. connecting a cloud MCP client) |
| Uncaught exception crashes / leaks | A *silent* deviation is the failure mode — exceptions MUST be **caught** |
| `try/except` handler | A defined **solution** (consent gate + signal + explainer + reversal path) |
| Stack trace identifies the exception | Every exception has a stable `EX-*` ID and a canonical definition |

### Raise / catch / handle

- **Raise** — a specific, named user action turns the exception on. There is no implicit or
  background raise. For `EX-CLOUD-LLM`, the raise event is "user connects a cloud-hosted MCP client
  to a Private-DB-returning server."
- **Catch** — the app detects the raise and surfaces it. A deviation the app fails to catch is a
  conformance failure regardless of intent. "Caught" means consent was obtained *before* the raise
  and a persistent signal is shown *while active*.
- **Handle** — the app runs the exception's **solution**: the consent surface, the persistent
  signal, the active-exception explainer, and the declared reversibility path.

### PNA mode vs non-PNA mode

> **An app is in PNA mode when no exceptions are active.** Raising any exception exits PNA mode.

A PNA stays **spec-conformant in non-PNA mode iff every active exception is handled to contract**
(the normative handler contract in § 3a). This reframes conformance:

- **Old framing:** conformant = *never deviates from any AC or the PNA definition.*
- **New framing:** conformant = *in PNA mode, honors every applicable AC; in non-PNA mode, catches
  and handles every active deviation honestly.*

This makes the spec describe reality. A tool that lets a user point a hosted model at their Private
DB is not "non-conformant garbage" and is not "secretly fine" — it is **a conformant PNA operating
in a declared non-PNA mode**, and the validation surface can say exactly that, by `EX-*` ID.

### Validation, not certification (the framing the maintainer wants surfaced)

PNT already states this in scattered places — `CONTRIBUTING.md` § "Acceptance is not certification"
and `SKILL.md` § Principles ("Conformance is checked, not awarded"). The Exceptions concept makes it
load-bearing and the maintainer wants it **promoted to a first-class framing statement**:

> **PNT validates behaviors against Goals; it does not certify.** There is no pass/fail badge and no
> certifying body. The evaluate flow *detects* exceptions and *verifies how they are handled*,
> reporting by `EX-*` ID. "This app raises `EX-CLOUD-LLM` and handles it to contract" is a finding,
> not a grade.

Exceptions are what make this framing actionable: the evaluate flow now has concrete, ID'd things to
detect and verify the *handling* of, rather than a binary conform/not-conform verdict.

### Terminology note (settled, recorded for the PR)

The concept was considered under the names *extensions*, *deviations*, and *exceptions*. The
maintainer chose **Exceptions** — the software metaphor (raise/catch/handle) carries the contract
intuition for free, and "extension" is already taken (`vocab-plugin` defines "Plugin / extension").
See § 5 for the residual terminology questions.

---

## 3. Proposed PNT artifacts

Each sub-plan below is concrete enough to be mechanical to execute, with DRAFT text where it helps.
None of it is to be applied to PNT yet.

### 3a. NEW file: `spec/exceptions.md`

A new spec file (sibling to `spec/axes.md` and `spec/use_cases.md`). It carries three things: the
normative handler contract, the header conventions (`Relaxes:` / `Reversible:`), and the exception
registry (first entry `EX-CLOUD-LLM`).

#### DRAFT — front matter + concept

```markdown
# PNA Exceptions

> **Spec-Version:** tracks the PNA Spec version in spec/PNA_Spec.md.
>
> This file defines **Exceptions**: stable-ID'd conditions (`EX-*`) under which a PNA deliberately
> departs from a baseline guarantee — a named AC, or the core PNA definition ("runs local-only,
> never as SaaS"; see PNA_Spec.md § Vocabulary, `vocab-pna`).

## Concept

An Exception is modeled on a software exception. It is **raised** by a specific user action, must
be **caught** (never raised silently), and must be **handled** by a defined **solution**.

**An app is in PNA mode when no exceptions are active.** Raising any exception exits PNA mode. A PNA
is spec-conformant in non-PNA mode **iff** every active exception is handled to the contract below.

PNT validates behaviors against the Goals; it does not certify. The evaluate flow detects
exceptions and verifies how each is handled, reporting by `EX-*` ID.
```

#### DRAFT — normative handler contract (RFC 2119; refined from the maintainer's brief)

```markdown
## Handler contract

Normative language uses RFC 2119 / RFC 8174 keywords (MUST, MUST NOT, SHOULD, MAY) only when
capitalized, consistent with PNA_Spec.md § Universal architectural commitments.

For each exception it can raise, a conforming PNA:

- **EX-H1 — Stable identity.** MUST define and reference the exception by its stable `EX-*` ID.
- **EX-H2 — Consent before raise.** MUST obtain explicit informed consent BEFORE raising the
  exception (no silent raise). The consent surface MUST link to an explanation of that specific
  exception.
- **EX-H3 — Persistent non-PNA-mode signal.** While the exception is active, MUST present a
  persistent user-facing signal that the app is not in PNA mode. The signal MUST name the active
  exception and MUST link to an explanation of the active exception set. The signal MAY be
  dismissable, but dismissal MUST NOT clear the exception (dismissal acknowledges; it does not
  resolve).
- **EX-H4 — Active-set explainer.** MUST provide a user-reachable explanation of the
  CURRENTLY-ACTIVE exception set. Because active combinations are installation-specific and cannot
  be enumerated in a static doc, this explainer MUST be generated at runtime from the active set and
  MUST link out to each active exception's canonical definition in this file.
- **EX-H5 — Declared reversibility.** MUST declare whether returning to PNA mode is supported
  (reversible) or not (irreversible). If it declares reversible, it MUST provide a practical,
  user-reachable path back to PNA mode that the validation flow can confirm from code/UX.
  Reversibility refers to **MODE ONLY**: a handler MUST NOT imply that returning to PNA mode undoes
  consequences already incurred (e.g. data already disclosed to a third party).
- **EX-H6 — Recommended solution.** SHOULD name a recommended solution in its registry entry,
  demonstrated by a reference design.
```

> **Sub-contract IDs.** `EX-H1..EX-H6` follow PNT's existing sub-contract convention
> (`<prefix>-<integer>`, monotonic, never renumbered — see `PNA_Spec.md` § Sub-contracts per slot).
> Using `EX-H*` keeps them distinct from the `EX-*` exception-registry IDs while staying in the
> same family namespace. **Open question for the maintainer (§ 5): are sub-contract IDs wanted here,
> or should the handler clauses stay prose-only?** They make the evaluate flow citable
> ("`EX-CLOUD-LLM` fails EX-H3 — no persistent signal") so the plan recommends keeping them.

#### DRAFT — header conventions (the inverse of `Realizes:`)

```markdown
## Header conventions

These mirror the existing `Realizes: AC-...` header that contract files in `contracts/` carry
(see tools/lint-spec-ids.py). They appear in an exception's registry entry and in any reference
design's handler declaration.

- **`Relaxes:`** — names the baseline guarantee(s) the exception departs from. The inverse of
  `Realizes:`. Each token is either an `AC-*` ID or the literal `PNA-DEFINITION` (for departures
  from "local-only, never SaaS"). Multiple tokens are comma-separated.
  Example: `Relaxes: PNA-DEFINITION, AC-MCP-A`
- **`Reversible:`** — declares whether returning to PNA mode is supported. Value is `yes` or `no`.
  If `yes`, a `Reversal:` field MUST follow naming the mechanism (a route, a control, or a code
  reference the validation flow can confirm). See EX-H5.
  Example: `Reversible: yes` / `Reversal: in-app "Return to PNA mode" control disconnects the
  cloud MCP client; see <design>'s Architecture.md.`
- **`Stresses:`** *(optional, non-normative)* — names a Goal the exception puts under pressure
  without strictly relaxing a single AC. Example: `Stresses: Goal 1`.
```

> **`PNA-DEFINITION` as a relaxable token.** The PNA definition lives in prose (`vocab-pna`), not in
> the `| AC-X |` table, so it has no AC ID. The plan introduces the literal sentinel `PNA-DEFINITION`
> so `Relaxes:` can reference it and the lint can resolve it (see § 3c). **Open question (§ 5):
> alternatively, mint an `AC-0`/`AC-PNA` for the definition so the existing `AC_RE` machinery covers
> it with no special case.**

#### DRAFT — exception registry (first entry)

```markdown
## Exception registry

| EX | Name | Relaxes | Stresses | Reversible | Recommended solution |
|---|---|---|---|---|---|
| EX-CLOUD-LLM | Cloud-hosted AI over PNA data | PNA-DEFINITION, AC-MCP-A | Goal 1 | yes (mode only) | pre-raise consent gate + persistent dismissable "not a PNA" banner + in-app active-exception explainer + return-to-PNA-mode — demonstrated by fellows_local_db |

### EX-CLOUD-LLM — Cloud-hosted AI over PNA data

**Relaxes:** PNA-DEFINITION, AC-MCP-A
**Stresses:** Goal 1
**Reversible:** yes
**Reversal:** mode only — the user can disconnect the cloud MCP client and return to PNA mode.
Returning to PNA mode does NOT undo any disclosure already made to the cloud provider (EX-H5).

**Raised when:** the user connects a cloud-hosted MCP client (e.g. Claude Desktop on a hosted
model, ChatGPT desktop) to a PNA's MCP servers that can return Private DB rows. The canonical
trigger is the Private Data Ops server (see PNA_Spec.md § Vocabulary, MCP server).

**Recommended solution:** pre-raise consent gate (EX-H2) + persistent dismissable "not a PNA right
now" banner naming EX-CLOUD-LLM (EX-H3) + in-app active-exception explainer (EX-H4) +
return-to-PNA-mode control (EX-H5). Demonstrated by `fellows_local_db`
(reference_designs/fellows_local_db/).
```

> **Table format and the lint.** Each registry row begins `| EX-... |`, mirroring the `| AC-X |`
> rows the lint already scans. § 3c adds an `EX_RE` that mirrors `AC_RE` exactly.

#### Note on what `EX-CLOUD-LLM` does and does not relax

It relaxes the *delivery* guarantee (data leaves the device to a cloud model) and AC-MCP-A's
per-call-consent posture. It does **not** relax AC-MCP-B (the workspace still launches transports),
AC-1, or any other AC. Keeping the `Relaxes:` set tight is part of honest handling — an exception
should name the *minimum* set of guarantees it actually departs from.

### 3b. ONE-LINE pointer from `spec/PNA_Spec.md`

The lightest possible touch that keeps the AC-ID lint green. The lint (`tools/lint-spec-ids.py`)
only reads `spec/PNA_Spec.md` and `spec/axes.md` for AC IDs and does not parse free text, so a prose
pointer is safe — it adds no `| AC-X |` rows and changes no existing ones.

**Proposed insertion** — one bullet at the end of `PNA_Spec.md` § Scope and versioning's deferred
list is the *wrong* place (it's not deferred — it's a new sibling concept). Two viable spots:

- **Preferred:** a one-line pointer in the § Vocabulary entry for the PNA definition (`vocab-pna`),
  since exceptions are precisely departures from that definition. DRAFT:

  ```markdown
  > A PNA may deliberately and temporarily depart from this definition or from a named AC by
  > **raising an Exception** — see [`exceptions.md`](exceptions.md). Raising any exception exits
  > "PNA mode"; the PNA stays conformant only while every active exception is handled to the
  > exceptions.md handler contract.
  ```

- **Alternative:** a one-line entry in § Axes / a new short § "Exceptions" heading with a single
  sentence + link. Heavier; only do this if the maintainer wants exceptions visible in the spec's
  table of contents rather than tucked into vocabulary.

**Lint-safety check (do this when executing):** after editing, run
`python tools/lint-spec-ids.py` from the PNT repo root and confirm it still prints `OK` and the same
AC count. The pointer text must not contain a line starting with `| AC-` (it won't).

### 3c. Extend `tools/lint-spec-ids.py`

The current linter (95 lines) does three checks (file header docstring): collects AC IDs from the
two spec files, collects `Realizes:` headers from `contracts/`, and verifies each realized AC
resolves. The extension mirrors that machinery for exceptions. **Design-level, not final code:**

**New regexes (mirror `AC_RE` / `REALIZES_RE`):**

```python
# Mirrors AC_RE (line 22). Collects EX-* IDs from registry rows in spec/exceptions.md.
EX_RE = re.compile(r"^\| (EX-[A-Z0-9-]+?)(?=\s|\*|\|)", re.MULTILINE)

# Mirrors REALIZES_RE (line 23). Tokens may be AC-*, EX-*, or the PNA-DEFINITION sentinel.
RELAXES_RE = re.compile(
    r"Relaxes:\s*((?:(?:AC-[A-Z0-9-]+|EX-[A-Z0-9-]+|PNA-DEFINITION)(?:\s*,\s*)?)+)",
    re.IGNORECASE,
)

# Reversible: yes|no. When 'yes', a Reversal: field must be present (checked separately, not by
# this regex).
REVERSIBLE_RE = re.compile(r"Reversible:\s*(yes|no)\b", re.IGNORECASE)
```

**New collection functions (mirror `collect_spec_ac_ids` / `collect_contract_realizes`):**

1. `collect_exception_ids()` — read `spec/exceptions.md`, `EX_RE.findall(text)`, return the set of
   `EX-*` IDs. Same shape as `collect_spec_ac_ids()` (lines 26–35). If the file is absent, this is a
   no-op returning an empty set (so the lint stays green on repos that haven't adopted exceptions).

2. `collect_relaxes()` — scan each registry entry (and, later, each reference-design handler
   declaration if PNT decides to lint those) for a `Relaxes:` header. Return `{source: [tokens]}`,
   same shape as `collect_contract_realizes()` (lines 38–52).

**New checks in `main()` (mirror the loop at lines 69–76):**

- For every token in every `Relaxes:` header: it MUST resolve to a known `AC-*` ID
  (`spec_ids`), a known `EX-*` ID (`exception_ids`), or the literal `PNA-DEFINITION`. Otherwise
  append a failure: `f"{src}: Relaxes names {tok}, which is not a known AC, EX, or PNA-DEFINITION."`
  This is the exact inverse of the existing "claims to realize {ac}, but {ac} is not defined"
  check.
- For every registry entry / handler declaration that carries a `Reversible:` field: the value
  MUST match `REVERSIBLE_RE` (well-formed `yes|no`). If `yes`, a `Reversal:` field MUST be present
  in the same entry. The lint validates the **declaration's well-formedness and presence**, NOT
  whether the reversal path actually works — that's the LLM layer's job (§ 3d / § 3e). Failure:
  `f"{src}: Reversible: declared but malformed, or 'yes' without a Reversal: field."`

**What the lint deliberately does NOT do:** it does not assert that an exception is genuinely
caught/handled at runtime, and it does not verify a reversal path exists in code. It validates the
*shape of the declaration* (presence + traceability), exactly as the existing tool validates that
`Realizes:` headers name real ACs without checking the realization is correct. This keeps the
80/20 "description-and-process over a Python conformance runner" principle (`SKILL.md` § Principles).

**Output additions:** extend the success summary (lines 87–89) with
`spec defines N exception IDs` and `M Relaxes header(s) resolved`.

**Docstring update:** add checks 4–6 to the module docstring (lines 1–12) describing the EX/Relaxes/
Reversible invariants.

### 3d. Strengthen the "validation, not certification" framing

Two surfaces, both small additions:

1. **`spec/PNA_Spec.md`** — there is no single framing sentence today; the closest is § Vision's
   "conformance evaluation" paragraph and § Building a PNA. Add one sentence to § Building a PNA (or
   a short callout near the AC table intro). DRAFT:

   ```markdown
   > **Validation, not certification.** PNT validates behaviors against the Goals; it does not
   > certify. There is no pass/fail badge and no certifying body. Where a PNA deliberately departs
   > from a guarantee, it raises an Exception (exceptions.md); the evaluate flow detects each
   > exception and verifies how it is handled, reporting by `EX-*` ID rather than by a grade.
   ```

   This complements, and should cross-link, the existing `CONTRIBUTING.md` § "Acceptance is not
   certification" and `SKILL.md` § Principles ("Conformance is checked, not awarded").

2. **`pna-build-eval-contrib/SKILL.md` § Evaluate flow** — see § 3e; the reversibility step and the
   "report by EX-* ID, don't grade" framing land together there.

### 3e. Add a reversibility-detection step to the SKILL Evaluate flow

The Evaluate flow today (`SKILL.md` lines 30–49) loops over ACs and produces a report keyed by AC
ID. Add an exceptions pass. **Proposed wording**, inserted as a new step after the current step 3
(typed-contract checks) and before step 4 (structured report):

```markdown
3b. **Detect and verify exceptions.** For each Exception the candidate can raise (declared in its
    Architecture document's exception/handler table, or inferred from the source where undeclared):
    - **Caught & handled?** Confirm consent is obtained before the raise (EX-H2), a persistent
      non-PNA-mode signal is shown while active (EX-H3), and a runtime active-set explainer exists
      (EX-H4). Cite the code/UX for each.
    - **Reversibility claimed?** Read the `Reversible:` declaration. If `yes`, trace the declared
      `Reversal:` mechanism and decide whether the code/UX actually delivers a practical,
      user-reachable path back to PNA mode. Cite the control or route. Reversibility is MODE only —
      do not credit a handler that implies returning to PNA mode undoes prior disclosure.
    - **Undeclared deviations.** You are the backstop: if the candidate departs from an AC or the
      PNA definition WITHOUT declaring an exception, that is a silent (uncaught) deviation — a
      conformance failure. Flag it and propose the `EX-*` it should have raised.
    Report each finding by `EX-*` ID (and "undeclared" for silent deviations).
```

Also update step 4's report-keying note and the § Principles list so the "report by ID, do not
grade" framing is explicit:

```markdown
- **Validation, not certification.** Report findings — conformant/non-conformant/exception-handled
  — by AC or EX ID. There is no overall pass/fail grade and no badge.
```

The three-layer split the maintainer wants is then complete and explicit:
- **Lint (mechanical):** `Reversible:` well-formed + `Relaxes:`/`EX-*` traceability (§ 3c).
- **Evaluate (LLM):** does the reversal path actually work; catch undeclared deviations (this step).
- **Human:** final judgment at PR time (`CONTRIBUTING.md` § Acceptance process — unchanged).

### 3f. `fellows_local_db` as the demonstrating reference design

The contribution must ride along with a reference design that demonstrates `EX-CLOUD-LLM` handling
(`CONTRIBUTING.md`: "spec changes must ride along with a demonstrating reference design"). Three
artifacts, per `SKILL.md` § PR authoring and `CONTRIBUTING.md` § PR contents required:

**(i) Design record — `reference_designs/fellows_local_db/README.md`**
Already exists as a placeholder (read it; First-accepted date and SWHID are `pending`). Add a
*Contributions to the spec* subsection for this PR. DRAFT bullet:

```markdown
### PNA Spec v<next> — Exceptions concept + EX-CLOUD-LLM (PR #<n>)

- Introduces the Exceptions concept (spec/exceptions.md), the Relaxes:/Reversible: header
  conventions, the lint extension, and the EX-CLOUD-LLM registry entry.
- Demonstrated by fellows_local_db's cloud-MCP consent handler: pre-raise consent gate, persistent
  "not a PNA right now" banner, runtime active-exception explainer, and a return-to-PNA-mode
  control. See this design's Architecture.md § Exceptions.
- Reference design version: commit `<sha>` (TBD when the handler ships).
```

**(ii) Architecture.md copy — `reference_designs/fellows_local_db/Architecture.md`**
PNT keeps its own copy at acceptance (`SKILL.md` step 4). This is a copy of fellows'
`docs/Architecture.md` *with* the new Exceptions content (see the gap analysis below — the upstream
doc needs the additions first).

**(iii) AC/Exception attestation row for `EX-CLOUD-LLM`**
A new attestation block in fellows' `docs/Architecture.md`, copied into the PNT Architecture.md.
DRAFT row (Verification column is mandatory — see gap analysis):

```markdown
## Exception attestation

| EX | Handled? | Realization | Reversible | Verification | Status |
|---|---|---|---|---|---|
| EX-CLOUD-LLM | yes | Consent gate before a cloud MCP client can reach Private Data Ops; persistent dismissable "not a PNA right now" banner naming EX-CLOUD-LLM; in-app active-exception explainer route; "Return to PNA mode" control that disconnects the cloud client. Code: `mcp_servers/private_data_ops.py` (consent gate), `app/static/app.js` (banner + explainer route + return control). | yes (mode only) | LLM rubric: "trace the cloud-MCP code path; confirm consent precedes any Private-DB row return (EX-H2), a persistent signal naming EX-CLOUD-LLM is shown while active (EX-H3), the explainer route exists and lists the active set (EX-H4), and the return-to-PNA control disconnects the client (EX-H5)." Plus a deterministic test asserting the consent gate refuses Private-DB tools until consent is recorded. | conformant (once handler ships) / planned |
| | | | | | |
```

> **Honesty flag for the maintainer:** the handler (consent gate + banner + explainer + return
> control) is **not yet implemented** in this repo — today's state is the README caveat only
> (`mcp_servers/README.md` § Cloud LLM caveat: "none of the three servers detects or gates cloud
> clients"). The attestation above is the *target*. The reference-design PR cannot honestly attest
> `EX-CLOUD-LLM` as `conformant` until that handler ships. **Sequencing depends on building the
> handler first** (§ 4). The `-mcp-consent` worktree name suggests this is the active line of work.

#### Gap analysis — what in fellows' current `docs/Architecture.md` would fail the SKILL preflight

The SKILL preflight (`SKILL.md` § Preflight, step 1 + step 3) requires the Architecture document's
**AC attestation table to have a Verification column on every row**, per
`reference_designs/templates/ARCHITECTURE_TEMPLATE.md` ("A row missing the Verification field … is
grounds for PR rejection") and `CONTRIBUTING.md` § What we don't accept.

Reading fellows' `docs/Architecture.md` (the version in this worktree) against that requirement:

1. **No AC attestation table with Realization/Verification/Status columns at all.** § "Universal
   ACs" (lines 25–27) is a *list* of AC IDs ("AC-1, AC-4, AC-6, …") with no per-AC Realization,
   **no Verification column**, and no Status. The § "Flavor-derived ACs" table (lines 33–41) has
   *Realization* ("Fellows's realization") but **no Verification column and no Status column**. The
   MCP-AC bullets (lines 43–46) and the "vacuous ACs" note (lines 48–50) likewise carry no
   Verification.
   **→ This is the single biggest preflight blocker.** Every universal AC and every triggered
   flavor-derived AC needs a row with a concrete Verification reference (a test file, an LLM rubric,
   or a human-review note) before the PR is acceptable. The doc is rich on *Realization* but was
   written as a specialization narrative, not as the template's attestation table.

2. **No Exceptions section.** There is no § Exceptions, no exception attestation table, and no
   mention of PNA-mode vs non-PNA-mode. Expected — the concept doesn't exist yet — but it must be
   added for this contribution.

3. **`EX-CLOUD-LLM` handler not implemented**, so even once an Exceptions section is added, its
   Status is `planned`, not `conformant` (see honesty flag above). Preflight will (correctly) flag
   the Verification side as not-yet-passing until the handler and its test land.

4. **The PNT-side design record placeholder** (`reference_designs/fellows_local_db/README.md`) still
   has `First accepted: PNA Spec v0.1, <YYYY-MM-DD pending>` and a pending SWHID, and its own copy
   of `Architecture.md` is described as "Pending Phase 5 … with the AC attestation table
   backfilled." So the attestation table is *known-missing on both sides* (upstream design record
   and this repo's source doc). This contribution is a natural moment to backfill it.

**Net:** the Exceptions spec work (§ 3a–3e) is mechanically clean, but the *reference-design half*
(§ 3f) has real prerequisite work in fellows' own `docs/Architecture.md`: build the full AC
attestation table with a Verification column, then add the Exceptions section + attestation. Both
must precede the PNT PR. Neither is part of *this* plan's output (this plan only writes itself) —
they are sequenced in § 4.

---

## 4. Sequencing + how this is driven through the SKILL Contribute flow

This stays a **PLAN in the fellows repo** until the maintainer approves. The sequence, when
approved:

1. **Build the `EX-CLOUD-LLM` handler in fellows first** (separate feature work, not in PNT):
   consent gate on the cloud-MCP path, persistent "not a PNA right now" banner, runtime
   active-exception explainer route, return-to-PNA-mode control. This is the demonstrating code the
   spec change rides along with. UI/UX changes also land in `docs/users_manual.md` per this repo's
   CLAUDE.md convention. *Without this, the reference design cannot honestly attest the exception.*
2. **Backfill fellows' `docs/Architecture.md` AC attestation table** with the Verification column on
   every applicable AC (fixes gap #1), then add the § Exceptions + exception attestation
   (fixes gaps #2–#3). This is the preflight-blocking work.
3. **Run the SKILL preflight** (`SKILL.md` § Contribute → Preflight) against fellows: validate the
   Architecture doc against the code, confirm every AC row (and the EX row) has a working
   Verification reference, iterate until the report is clean.
4. **Author the PNT changes on a branch in a PNT checkout** (still no PR): `spec/exceptions.md`
   (§ 3a), the one-line `PNA_Spec.md` pointer (§ 3b), the `tools/lint-spec-ids.py` extension
   (§ 3c), the framing additions (§ 3d), the SKILL Evaluate-flow step (§ 3e), and the reference
   design record + Architecture.md copy + attestation (§ 3f). Run `python tools/lint-spec-ids.py`
   and confirm green.
5. **Only on the maintainer's explicit go-ahead:** open the PNT PR per `SKILL.md` § PR authoring /
   `CONTRIBUTING.md` § PR contents — spec diff, design record, Architecture.md copy, canonical repo
   URL + commit SHA. Version bump is **Minor** per `CONTRIBUTING.md` § Versioning (additive: a new
   spec file, a new concept, new sub-contracts, a new lint check — no existing AC semantically
   altered, no pick removed).
6. **Post-merge** (maintainer): Software Heritage archival of fellows at the accepted commit; record
   the SWHID in the design record; final clean preflight run.

**Explicit decision recorded here:** no issues or PRs are filed into PNT (or anywhere) from this
plan. This document is the artifact the maintainer reviews; everything downstream waits on approval.

---

## 5. Open questions / terminology notes

1. **Naming — settled but worth a sentence in the PR.** "Exceptions" was chosen over "extensions"
   (collides with `vocab-plugin` "Plugin / extension") and "deviations." Confirm the software
   metaphor (raise/catch/handle) is the framing the PR leads with.

2. **MUST vs SHOULD on the reversal-path requirement (EX-H5).** Current draft: *if* an exception
   declares `Reversible: yes`, it **MUST** provide a confirmable path. The conditional MUST is
   right — but should declaring reversibility itself be encouraged (SHOULD prefer reversible where
   feasible) or stay neutral? `EX-CLOUD-LLM` is reversible (mode only); an irreversible exception
   (e.g. a hypothetical one-way data export) would legitimately declare `Reversible: no`. Recommend
   staying neutral: the spec validates the *honesty* of the declaration, not the *choice*.

3. **One-line pointer vs standalone referenced doc (§ 3b).** Is a single vocabulary-section pointer
   into `exceptions.md` acceptable, or does the maintainer want exceptions surfaced as a top-level
   `PNA_Spec.md` section (heavier, more visible)? The plan recommends the light pointer + standalone
   `exceptions.md` (parallels how `axes.md`/`use_cases.md` are standalone and pointed-to), but flags
   it as the maintainer's call.

4. **`PNA-DEFINITION` sentinel vs minting `AC-PNA` (§ 3a/§ 3c).** The PNA definition is prose, not a
   `| AC-X |` row, so `Relaxes:` needs either the `PNA-DEFINITION` literal (lint special-case) or a
   new AC ID for the definition. Minting `AC-PNA` would let the existing `AC_RE` resolve it with
   zero special-casing — cleaner lint, but it puts the foundational definition into the AC table,
   which may be conceptually heavier than wanted. Maintainer's call.

5. **Handler clause IDs `EX-H1..EX-H6` (§ 3a).** Keep them as citable sub-contracts (recommended —
   the evaluate flow can cite "fails EX-H3") or leave the handler contract prose-only? If kept,
   confirm the `EX-H*` namespace doesn't collide with the `EX-*` registry namespace in the lint
   (the regexes in § 3c anchor registry IDs to `| EX-...` table rows, so `EX-H*` clauses in prose
   are not collected as registry exceptions — no collision, but worth a confirming read).

6. **Should the lint also collect `Relaxes:`/`Reversible:` from reference-design Architecture docs,
   or only from `spec/exceptions.md`?** § 3c is written to support both but the first cut can lint
   only the spec registry (PNT holds the canonical copy of accepted designs' Architecture.md, so the
   tokens are local to the repo either way). Recommend: lint the spec registry first; extend to
   design-doc handler declarations if/when a second exception lands.

7. **Where does the active-set explainer (EX-H4) live across an MCP boundary?** For `EX-CLOUD-LLM`
   the *workspace* (the PWA) is the natural home of the persistent signal and explainer, but the
   raise happens at the *MCP server* (a separate process the workspace doesn't directly observe).
   This is a real design wrinkle for fellows' handler (§ 4 step 1) and may surface a general
   sub-question for the spec: how does a persistent non-PNA-mode signal work when the exception is
   raised in a headless server the user isn't looking at? Worth flagging in the PR as a known
   limitation of the first handler even if fellows solves it pragmatically (e.g. the workspace polls
   or the MCP consent is recorded in a place the workspace reads).
```
