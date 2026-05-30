# Architectural Findings

Discoveries about *this application* that reshaped how we think about the
PNA architecture it conforms to. Where [`ac_decisions_log.md`](ac_decisions_log.md)
records individual decisions made *under* the architecture, this file
records the rarer moments where building and operating the app taught us
something the architecture itself didn't yet account for — findings worth
feeding back into the [PNA Spec / Personal Network Toolkit](https://github.com/richbodo/personal_network_toolkit).

Newest first.

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
