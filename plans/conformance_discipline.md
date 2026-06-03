# Plan — Conformance Discipline (keep the Security Target honest by construction)

**Status:** ACTIVE. **Created:** 2026-06-03.
**Why:** the private-data capability gate attested `conformant` for properties
its code never enforced (see [`private_data_enforcement.md`](private_data_enforcement.md)).
The claim-vs-code gap was invisible because: (1) the deferral lived in a **code
comment** ("lands later with the fixture"), which evaporated; (2) the invariant
is a **negative** ("nothing durable off-folder"), which the happy-path test
didn't cover; (3) nothing made the **absence fail loudly**. This plan builds the
mechanisms that would have caught it at merge, and pushes the pattern upstream
so every PNA inherits it.

---

## 1. Principles (the rules this plan makes mechanical)

1. **The attestation is a Security Target. A `conformant` claim with no executable
   evidence is a finding.** Every `conformant` AC/CST row must cite either a
   resolvable test ref (`path/to/test.py[::func]`) or an explicitly **declared
   verification kind** (human-review / LLM-rubric / code-inspection / by-architecture
   / by-bounding / by-construction). A bare doc pointer (`*.md`) is **not** evidence
   — a doc that *asserts* a property does not *prove* it.
2. **Deferrals live ONLY in the formal attestation or as a `strict=True` xfail
   test — never in a code comment.** A code comment deferral is ephemeral and
   unowned. A strict-xfail is a deferral with a tripwire: it goes red the day
   someone implements it, and `grep "xfail(strict"` is the live list of
   claimed-but-unproven invariants.
3. **Negative invariants need negative tests.** "X must NOT happen off-folder" is
   not covered by the test that X happens on-folder. Each conformant row's
   negative invariants are enumerated and each pinned by a negative test.
4. **Capability reductions enforce at the data layer, never UI-only.** Hiding a
   surface is the cosmetic half; the reduction is that the *write does not happen*.
5. **Everything fails loudly.** Absence is converted to a red test or a blocking
   hook — never to a silent pass.

---

## 2. The verification-kind vocabulary (what the checker parses)

Each `conformant` row's **Verification** (or **Status**) cell must contain ≥1 of:

| Kind | Recognized by | Checker action |
|---|---|---|
| `test` | a `path…*.py` ref, optionally `::func` | **must resolve** (file exists; if `::func`, `def func` exists) |
| `review` | one of: `human-review`, `LLM rubric`, `code inspection`, `by architecture`, `by bounding`, `by construction`, `architectural` | accepted as declared non-test evidence |
| `doc-only` (anti-pattern) | only `*.md` refs, or nothing | **FAIL** — add a test, declare a kind, or downgrade the status |

`partial` / `partial-conformance` / `Open` / `not-applicable` rows are exempt
from resolution (they're honestly aspirational) but must carry that status.

---

## 3. Deliverables → PRs

| PR | Repo | Deliverable | Status |
|---|---|---|---|
| **PR-1** | fellows | `CLAUDE.md` "Conformance discipline" stanza + `docs/Architecture.md` attestation reconciliation (kind vocabulary preamble; honest statuses on over-claiming CST rows) + `tests/test_attestation_has_evidence.py` checker (green) | **DONE** `1871b30` (branch `chore/conformance-discipline`) |
| **PR-2** | fellows | `.claude/hooks/{stop,subagent_stop}.py` + `utils/conformance_guard.py`: block-once when a diff touches the attestation rows without tests, or adds a deferral phrase to a frontier file without a strict-xfail. Loop-safe via `stop_hook_active`; fails open. Registered in tracked `.claude/settings.json`. Unit-tested. | **DONE** `4342054` |
| **PR-3** | fellows | `.claude/skills/pna-build-eval-contrib/SKILL.md` — *evaluate* flow attestation-evidence audit + negative-invariant enumeration; build-step-7 + preflight blockers reinforced. | **DONE** `d827ba5` |
| **PR-4** | personal_network_toolkit | `pna-build-eval-contrib/SKILL.md` (mirror) + `reference_designs/templates/ARCHITECTURE_TEMPLATE.md` (kind vocabulary, attestation-checker pattern, strict-xfail discipline, negative-invariant requirement). | **DONE, NOT PUSHED** `4106279` (PNT branch `chore/conformance-evidence-discipline`) — needs maintainer sign-off before push/PR. |

PR-1 is the keystone (defines the vocabulary the others reference). PR-2/3/4 can
follow in any order once PR-1's vocabulary is fixed.

---

## 4. PR-1 detail — attestation reconciliation (per row)

Rows in `docs/Architecture.md` that currently claim `conformant` on **doc-only or
prose-only** evidence, with the honest fix:

| Row | Today | Fix |
|---|---|---|
| `CST-PWA-PRIVATE-SNAPSHOT` | conformant; "no false durability… stores nothing private" | **→ partial.** False today (prefs ride OPFS). Point at `private_data_enforcement.md` + the strict-xfail canary. |
| `CST-PWA-STORAGE-EVICTABLE` | conformant; verification = `persistence_and_upgrades.md` (doc-only) | **→ partial.** Same reason; same pointer. |
| `CST-PWA-SANDBOX-SEALED` | conformant; "folder-mode MCP e2e" (prose) | **→ partial.** MCP-unavailable-off-folder is not pinned by an e2e (Tier-2 test pending). |
| `CST-PWA-NO-SYNC` | conformant; "reconnect/chooser e2e; identity-stamp test" (prose) | Cite the concrete test file(s), or add `human-review`. |
| `CST-PWA-SINGLE-OWNER` | conformant; "folder-write lock test (PR #209)" (prose) | Cite the concrete test file. |
| `CST-PWA-NO-BACKGROUND` | conformant; "auto-backup debounce test" (prose) | Cite the concrete test file, or `code inspection`. |
| `CST-PWA-DURABLE-SQL-ARCH` | "conformant by architecture" | already declares kind — OK, no change. |
| `CST-PWA-SERVER-FLOOR` | "conformant by bounding" | already declares kind — OK, no change. |

Add a short **preamble note** above the attestation tables stating the kind
vocabulary + that the `test_attestation_has_evidence.py` checker enforces it.

The checker (`tests/test_attestation_has_evidence.py`, stdlib only):
- Parse the markdown tables under the attestation sections of `docs/Architecture.md`.
- For each row whose Status contains `conformant` and not `partial`:
  - classify Verification+Status per § 2;
  - `test` kind → assert each `*.py` resolves and each `::func` exists;
  - `review` kind → pass;
  - else → FAIL with the row id + "no executable evidence and no declared kind".

---

## 5. PR-2 detail — the attestation/deferral guard hook

Both `stop.py` and `subagent_stop.py` gain a shared check (factored into
`utils/`), loop-safe via the `stop_hook_active` flag they already read.

**Signal — what changed this session:**
```
changed = set(`git diff --name-only HEAD`)           # uncommitted
        ∪ set(`git diff --name-only main...HEAD`)     # committed on this branch
```

**Check A — attestation touched without tests.** If `docs/Architecture.md` is in
`changed` AND no path under `tests/` is in `changed`:
> block once with: "You changed the conformance attestation without touching
> tests/. A `conformant` row needs executable evidence; a softened row needs an
> honest status. Run `pytest tests/test_attestation_has_evidence.py` and
> add/adjust the negative test, or explain why no test change is needed."

**Check B — deferral phrase in a frontier file without a strict-xfail.** For each
frontier file in `changed` (`app/static/app.js`, `app/static/vendor/sqlite-worker.js`,
`deploy/server.py`, `app/server.py`), scan **added** lines (`git diff` `+`) for
high-signal deferral phrases — `lands later`, `lands together`, `deferred`,
`not yet enforced`, `will be enforced`, `inert for now`, `for now` — and, if any
new `xfail(strict` was *not* also added this session, block once with:
> "Added a deferral comment to a frontier file. Deferrals live in the attestation
> or as a strict-xfail test, never as a code comment (CLAUDE.md § Conformance
> discipline). Encode it as `@pytest.mark.xfail(strict=True, reason=…)` naming the
> plan PR, or move it to the attestation."

**Loop safety:** if `stop_hook_active` is true, print the reminder to stderr and
exit 0 (allow stop) — never block twice. Block = exit code 2 with the message on
stderr (fed back to the agent). On any internal error (not a git repo, etc.),
exit 0 — the guard must never wedge a session.

---

## 6. PR-3 / PR-4 detail — skill + template

**SKILL.md evaluate flow** (fellows copy in PR-3; canonical PNT copy in PR-4) gains
a step:
> **Attestation evidence audit.** An attestation is only as good as its executable
> evidence. For each AC/CST attested `conformant`: (a) confirm the named test
> exists and passes; (b) enumerate the row's **negative invariants** ("X must NOT
> happen") and confirm a **negative test** pins each; (c) reject doc-only evidence
> — a doc that asserts a property is not proof. Deferred/partial rows must say so.

**ARCHITECTURE_TEMPLATE.md** (PR-4) gains: the verification-kind vocabulary (§ 2),
a ready-to-copy `test_attestation_has_evidence.py` reference, the strict-xfail
deferral discipline, and the negative-invariant requirement — so every PNA built
from the toolkit inherits "keep your Security Target honest by construction."

---

## 7. Cross-repo note
PR-4 lives in `../personal_network_toolkit` (separate git repo). Implement on a
branch there; **do not push or open the PR without maintainer sign-off** — it
defines the toolkit for every downstream PNA.
