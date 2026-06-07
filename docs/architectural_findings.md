# Architectural Findings

Discoveries about *this application* that reshaped how we think about the
PNA architecture it conforms to. Where [`ac_decisions_log.md`](ac_decisions_log.md)
records individual decisions made *under* the architecture, this file
records the rarer moments where building and operating the app taught us
something the architecture itself didn't yet account for — findings worth
feeding back into the [PNA Spec / Personal Network Toolkit](https://github.com/richbodo/personal_network_toolkit).

Newest first.

---

## 2026-06-07 — The workspace is the user's actuation surface; test the gate, not the human

### The finding

Planning AI write-proposals ([`../plans/ai_write_proposals_groups.md`](../plans/ai_write_proposals_groups.md))
made explicit a discipline the app had been practising piecemeal: an AI may
*propose* a change, but the user *disposes* of it against a deterministic
before/after diff **in the workspace, not in the AI's interface**. Pulling the
thread showed this is not a rule about AI writes — it is one instance of a
single, previously-unnamed principle:

> **The human is the actuator; the workspace is the locus of ground truth.**
> Every path that mutates the sovereign store or sends data out of it routes
> through a user-legible review in a surface the user controls. The proposer —
> AI, network, or importer — only *stages*; the human *disposes*.

It was already load-bearing in five places before we named it: **AC-19** (payload
visible before send), **AC-16** (user picks the transport), **AC-MCP-B** (MCP
stages, the workspace launches), **AC-10 / AC-PRM-D** (directory re-import
previews orphaned members and is user-initiated), and **AC-PRM-A** ("an LLM call
over user data is a *transport*", so it inherits the same mediation). The
AI-writes plan is the same principle reaching a new mutation source, not a new
principle.

### The hard part is what you must NOT try to test

The obvious reading — "verify a real human is driving the workspace" — is a trap.
That is the bot-detection / liveness arms race, and detection is not, and should
not be assumed to be, ahead of automation in that race. A guarantee built on
"is this a human?" is false confidence.

The escape is that the invariant never required knowing *who* the actor is. The
enforceable property is a property of the **code**, and it is actor-agnostic:

1. **No bypass** — no path mutates `relationships.db` except through the dispose
   gate (a negative-invariant test, same family as
   `test_no_durable_private_write_when_browse_only` and the `mode=ro` proofs).
2. **Separation** — the proposing surface (the MCP inbox; any in-workspace AI)
   carries *no* actuation capability; dispose is a distinct, attributable event
   decoupled from the proposer.
3. **Legibility** — the diff is deterministic, renders human-readable content
   (names, not `record_id`s), and escapes untrusted proposer strings.

This is why we named it "the human is the *actuator*" and not "a human is
*present*": the first is a code property you can test; the second is a detection
problem you cannot win. **The naming choice is the testability decision.**

### The claim is bounded — and that's the honest part

The gate guarantees **separation, legibility, and attribution. It does not
guarantee comprehension.** We cannot probe the user's understanding, and an
automation driving the workspace can click *Approve* as easily as a person can.
That residual is the same shape as `EX-H7` consent-to-human propagation, which
already landed as a *best-effort* notice in the MCP `instructions` handshake
(`CLOUD_LLM_PROPAGATION_NOTICE`) — conformant for the mechanical half, explicitly
unenforceable for the "did the other side actually tell the human" half. At every
boundary the workspace does not own — the user's mind, the AI client's UI — the
posture is identical: make the ask legible, and attest the gap rather than
pretend to close it. (The further idea of *extracting a binding promise from
another AI* runs aground here: a stateless generator has no continuous identity
or liability to bind, so an "AI contract" is closer to a category error than an
unsolved engineering problem. Test that *we* made and recorded the ask; treat the
other agent's compliance as out-of-band.)

### Two consequences worth acting on

- **A gap the principle exposes:** private-data *restore*
  (`importRelationshipsBytes` over `relationships.db`) is a wholesale replace with
  far less "what is changing" legibility than AC-10 gives a *directory* import. It
  is the sibling boundary that does not yet meet its family's bar.
- **A commitment to pin before it's needed:** "review happens in a non-AI
  surface" is true today only *by construction* (vanilla-JS SPA, no embedded
  agent). The `window.ai` search affordance and the plan's deferred in-app local
  model are the pressure points. The honest commitment is not "the workspace MUST
  NOT be an AI interface" but the user-knowledge form: any in-workspace AI is a
  *proposer* subject to the same gate, never an *actuator*. Declare it, with a
  frontier, before local-AI lands — not after.

### What this feeds back into the toolkit

A candidate third general PNA mechanism, dual in spirit to exceptions (the user
raises) and constraints (the platform imposes): a **user-mediation /
informed-actuation invariant** — the proposer stages, the human disposes, and the
claim is *separation + legibility + attribution*, never *comprehension*. Per the
toolkit's reference-driven model it should ride upstream with the working design
that demonstrates it — and that demonstration is **test-first**: the demonstrating
tests (the three properties above) define the enforceable boundary, and the spec
is written to match what proved testable, not the other way round. Tracked in
[#252](https://github.com/richbodo/fellows_local_db/issues/252).

---

## 2026-06-01 — A PWA can't give every platform a writable private store; "constraints" name the ceiling honestly

### The finding

A user's Private Data Ops MCP server stopped connecting to Claude Desktop.
The proximate cause was mundane — the `.mcpb` extension pointed at a
`relationships.db` export that had been relocated out of `~/Downloads` —
but chasing *why the handoff was that fragile in the first place* surfaced
a class-level ceiling we had been routing around without naming:

> For a PNA delivered as a web app, the private-data half's writability and
> external-readability is gated entirely by the browser's **File System
> Access API** — which is Chromium-only. On every non-FSA browser (Safari,
> Firefox, *all* of iOS), the private store can only live in the opaque
> OPFS sandbox (invisible to the user and to companion tools like the app's
> own MCP servers), is subject to silent browser eviction (Safari's
> script-storage cap), and can escape to a real file only as a one-shot,
> immediately-stale download snapshot. So on those browsers the private
> half — the part that is supposed to be the user's sovereign, live,
> manipulable, forever data — degrades to a **read-only snapshot at best**.

This is a different *kind* of finding from the cloud-LLM exception below it.
That one is a **privacy** deviation a user deliberately *raises* and the app
*handles* honestly. This one is a **data-loss** ceiling the *platform*
imposes — nobody raises it; it is a property of the medium. It is arguably
the more serious of the two, because the failure mode is silent and the
casualty is the user's own data.

### Why it's the application class, not this app

The ceiling falls out of the intersection `distribution:web-bundle` ×
`storage:opfs-sqlite-wasm` × a browser-capability fact. Nothing about EHF,
the fellows schema, or this app participates. **Any** PNA that makes those
two axis picks inherits it — and inherits a whole family of sibling ceilings
alongside it (eviction, no built-in sync, the single-owner OPFS architecture,
the sandbox boundary that seals the store off from the user's other tools).
A PNA is meant to be the *hub* the user's other tools (comms clients, LLMs,
scripts, backups) act on; a store those tools cannot read is only half a PNA.
That makes the sandbox boundary, not the FSA gap alone, the deepest edge here.

### The resolution: constraints (the dual of exceptions)

We model the ceiling as a first-class, named **constraint** — the dual of an
[exception](#2026-05-30--users-want-a-cloud-llm-exceptions-let-a-pna-stay-honest-instead-of-forbidding-it).
An exception is a deviation the *user* raises and the *app* catches and
handles; a constraint is a limitation the *platform* imposes and the *app*
must likewise catch and handle — never silently. Same "always know what mode
you're in" philosophy, opposite origin.

> A **constraint (`CST-*`)** is a platform- or substrate-imposed ceiling,
> inherited automatically by one or more **axis picks** (raised by no one —
> it's a property of the medium), that **removes or bounds functionality a
> PNA would otherwise offer**. It obligates a documented **handling** —
> typically honest capability reduction matched to what the platform can
> actually deliver ("enough power to be useful, not enough to be
> dangerous") — and a reference design stays conformant by handling it
> honestly, *not* by overcoming it. Every constraint carries an explicit
> **resolution frontier**: whether a viable workaround is known, or whether
> (as of this version) none has been found.

Each `CST-*` records: **Triggered by** (the axis pick[s]), **Ceiling** (what
it removes/bounds), **Stresses** (the Goal/AC it bounds), **Handling** (the
obligated response), **Frontier** (`Open` / `Mitigated` / `Solved-on-<platform>`
/ `Inherent` — whether anyone has beaten it yet), and **Detectability** (how a
builder knows they're under it on a given platform: clean feature-detect /
empirical probe / **must-UA-sniff**).

The **Frontier** field is the one that keeps a reference design honest. Our
actual product decision — *drop private data on mobile and Safari, for now* —
is the *handling*, and its frontier is **Open**: no viable workaround found as
of Toolkit-Version 0.1, but there might be one (an encrypt-then-email-to-self
portability pattern is a candidate, unproven). A future revision can flip a
constraint from `Open` → worked-around and document *how*. We do not pretend
to have solved what we have only reduced.

### The ceilings we hit (the eight that earn a normative `CST-*`)

| ID | Triggered by | Ceiling | Frontier |
|---|---|---|---|
| `CST-PWA-PRIVATE-SNAPSHOT` | web-bundle × opfs, non-FSA browser | Private store is read-only-snapshot-at-best off Chromium | **Open** (mitigated: drop private writes off Chromium; encrypted-email transport is an unproven candidate) |
| `CST-PWA-SANDBOX-SEALED` | opfs storage | Store invisible to the user *and* unreadable by their other tools (MCP, backups, CLIs); the PWA also can't host native integration to bridge it — **the root of the MCP-handoff fragility** | Solved on Chromium via folder mode; **Open** otherwise |
| `CST-PWA-STORAGE-EVICTABLE` | opfs / IndexedDB | Script storage is evictable; `persist()` is a request, not a guarantee; Safari caps it | **Open** (mitigated: backup ring + export discipline) |
| `CST-PWA-NO-SYNC` | web-bundle × opfs | Origin- and device-local silos; zero built-in portability | **Open** (encrypted-email is the candidate pattern) |
| `CST-PWA-DURABLE-SQL-ARCH` | opfs-sqlite-wasm | Durable SQL forces a worker-owned, cross-origin-isolated, single-connection architecture | **Inherent** (accepted cost; the worker-owned convention is the handling) |
| `CST-PWA-SINGLE-OWNER` | opfs-sqlite-wasm | Multi-tab contention with no OS file lock | **Solved** (Web Locks + ownership-conflict detection) |
| `CST-PWA-NO-BACKGROUND` | web-bundle | No reliable scheduled background execution (esp. iOS) → backups can only be opportunistic | **Open on iOS** (mitigated: per-boot debounced backup; never promise scheduled protection) |
| `CST-PWA-SERVER-FLOOR` | web-bundle | Needs an origin + TLS + secure context; true serverless-local is unreachable | **Inherent** (handled by bounding the server to distribution/update — Never-SaaS) |

Two **meta-principles** sit above the table and are more reusable than any
single row:

- **M1 — capability presence ≠ usefulness ≠ permanence.** `showDirectoryPicker
  in window` is true on Android Chrome but only reaches an OS-clearable folder;
  `persist()` returns true but Safari still evicts; `createSyncAccessHandle`
  exists in a worker but not on the page. You must detect *useful, durable*
  capability — often empirically — and distrust the obvious feature-check.
  This is why the entry scheme carries a **Detectability** field at all.
- **M3 — the handling pattern is per-platform capability reduction.** Match each
  platform's *offered* features to the durability it can actually *keep*. Mobile
  loses folder mode (it can't keep the promise; see PR #234 / `8392193`) and is
  left with OPFS + manual backup. "Enough power to be useful, not enough to be
  dangerous." For constraints this is the dual of the exception's "catch and
  handle honestly."

**Footgun companion (non-normative — recorded so builders don't re-derive
them, but they don't carry a ceiling's weight):** service-worker staleness /
"what code is actually running" ambiguity; no atomic factory reset (OPFS has no
per-origin wipe API; the HttpOnly cookie needs a server round-trip); PWA install
+ manifest gotchas (WebAPK `related_applications`, POST `share_target`, iOS's
hidden Add-to-Home-Screen). All navigable; none is a wall.

### A note on "helpful constraints"

Some platform ceilings happen to *serve* a PNA goal — a PWA can't send mail
itself, only hand off a `mailto:` URL, which lands the app in exactly the
"transports cannot read message contents" shape the spec wants (AC-18). These
are real, but they are **not** builder/verifier advice in the way an adverse
ceiling is — a builder will either already know, be pleasantly surprised, or
harmlessly ignore one. They belong in a future *"things that worked well,
proven true and useful"* channel, **not** the constraints registry. We park
that channel deliberately; the registry is for ceilings that take capability
away.

### What this feeds back into the toolkit

The plan to contribute this upstream — introducing **constraints** as a
general PNA mechanism (dual to exceptions, applicable to any substrate, with
the PWA ceilings above as the first populated set), via a new normative
`spec/constraints.md` registry, a `lint-spec-ids.py` extension that traces
`CST-*` / `Triggered-by:` / `Frontier:` the way it already traces `AC-*` and
`EX-*`, axis-pick cross-references on Storage and Distribution, and
fellows_local_db as the demonstrating reference design — will be staged in
[`../plans/pna_toolkit_constraints_contribution.md`](../plans/pna_toolkit_constraints_contribution.md),
mirroring the exceptions contribution. The decisions locked before drafting: the concept is a
**general mechanism** (not a PWA-only catalog); **hard ceilings are normative,
footguns are preserved as non-normative notes**; and the registry is
**adverse-only** (no valence field — helpful ceilings are the separate
channel above). Per the toolkit's reference-driven model, the spec change
rides along with the working design that demonstrates it; this app is that
design.

The factual substrate matrix this finding generalizes already lives in
[`browser_support.md`](browser_support.md) (capability floors; folder mode
*required* for private data — the verified-folder gate, not an additive
tier) and [`persistence_and_upgrades.md`](persistence_and_upgrades.md) (the
per-substrate state-survival table; browse-only mode is localStorage-only
with no durable private store). Both now point here for the *why /
class-level* framing. The realization is the private-data capability gate
([`../plans/private_data_capability_gate.md`](../plans/private_data_capability_gate.md)),
attested in [`Architecture.md` § Constraint attestation](Architecture.md);
the user-facing surfacing (per-platform feature availability, "Download my
private data," browse-only on Safari/Firefox/phones) is documented in
[`users_manual.md`](users_manual.md) and [`feature_platform_matrix.md`](feature_platform_matrix.md);
the platform-tiering decisions are recorded in [`ac_decisions_log.md`](ac_decisions_log.md).

---

## 2026-05-30 — Users want a cloud LLM; "exceptions" let a PNA stay honest instead of forbidding it

### The finding

The PNA architecture's core promise is in its own definition: a personal
network application *"runs local-only, never as SaaS."* Goal 1 is
private-data sovereignty. Taken literally, that forbids wiring the
directory to a cloud LLM — connecting Claude Desktop (a cloud-hosted
model) to the MCP servers sends fellows data, and potentially a user's
private groups and notes, to a SaaS vendor.

But when we shipped the MCP servers and watched our ~500-fellow user base
actually use them, **every test user wanted Claude Desktop**, on the
hosted model. Local AI — a locally-served model behind Ollama or similar
— is the architecturally "green" path, but it is well beyond the hardware
and the patience of essentially all of these users. There is, today, no
realistic local option for them. Cloud LLM integration is simultaneously
**the thing everyone wants** and **a direct violation of the app's
defining constraint**.

That is the finding: for a real PNA with real users, the local-only
guarantee will be deliberately broken, by users, on purpose, because the
SaaS option is the only usable one. A spec that only says "don't" leaves
the app with three bad choices — forbid the feature users need, allow it
silently (dishonest), or quietly stop being a PNA.

### The resolution: exceptions

We model the violation as a first-class, named **exception** — borrowing
the software-exception metaphor. An exception (`EX-*`) is a stable-ID'd
condition under which the app deliberately departs from a baseline
guarantee. Like a software exception it is **raised** (by a specific
user action), must be **caught** (never silent), and is **handled** by a
defined solution. Raising one **exits PNA mode**; the app is "in PNA
mode" when no exceptions are active.

The first (and so far only) exception is **`EX-CLOUD-LLM`**: raised when
the user consents to wiring the directory to a cloud LLM. Its handler, as
implemented here, is:

- A pre-raise **informed-consent gate** (scroll-then-accept) that names
  the exception and links to its explanation.
- A persistent, dismissable **"Going rogue — not a PNA" banner** while
  the exception is active — onerous enough that nobody wants it
  permanently, which is itself a gentle disincentive against casual SaaS
  coupling. Dismissal *acknowledges*; it does not resolve.
- An in-app **explainer** (`#/exception/EX-CLOUD-LLM`) describing the
  currently-active exception set — in-app rather than on GitHub because
  exception *combinations* are installation-specific and can't be
  enumerated statically.
- A **reversible** path back to PNA mode (Settings + the explainer).
  Reversibility is **mode-only**: returning to PNA mode stops future
  sharing but does not recall data already sent to the provider. We say
  so explicitly rather than implying an "undo."

The key reframing: **conformance stops being "never deviates" and becomes
"catches and handles every deviation honestly."** An app stays a
conformant PNA — even while *not in PNA mode* — if and only if every
active exception is handled to contract. A user can take the app out of
PNA mode and put it back; the architecture's job is to make sure they
always *know which mode they're in*.

### A second-order finding: validation, not certification

Working this through surfaced something the toolkit under-states today:
**PNT validates behaviors against Goals; it does not certify.** There is
no pass/fail badge. The right posture for reversibility, for instance, is
not "every exception MUST be reversible" but "an exception *declares*
whether it is reversible, and the validation system *detects and verifies*
that claim against the code/UX." The exceptions work is the natural place
to make the validation-not-certification framing explicit.

### What this feeds back into the toolkit

The plan to contribute this upstream — a new `spec/exceptions.md` (the
normative handler contract + the `EX-CLOUD-LLM` registry entry), a
`lint-spec-ids.py` extension that traces `EX-*` / `Relaxes:` /
`Reversible:` the way it already traces `AC-*` / `Realizes:`, the
validation-not-certification framing, and fellows_local_db as the
demonstrating reference design — lives in
[`../plans/pna_toolkit_exceptions_contribution.md`](../plans/pna_toolkit_exceptions_contribution.md).
Per the toolkit's reference-driven model, the spec change rides along
with the working design that demonstrates it; this app is that design.

The in-app realization (the banner, the explainer route, the
reversibility control, the `EX-CLOUD-LLM` marker) is documented for
users in [`users_manual.md`](users_manual.md) and recorded as a decision
in [`ac_decisions_log.md`](ac_decisions_log.md).
