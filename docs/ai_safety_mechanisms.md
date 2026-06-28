# AI Safety in a Local-First App: Keeping the Person in Control

*A talk companion. Plain language, with screenshots of every place the app warns,
explains, or asks the user to make a decision. Each screenshot is tied to the
specific rule that produced it.*

> **The one-paragraph version.** This app is built to be *local-only* — your data
> lives on your device and is never sent to a company's servers. Connecting an AI
> like Claude deliberately breaks that promise, because the AI runs in the cloud
> and reads your data there. We didn't want to either forbid AI or wave it
> through. So we did the in-between thing: we treat "turn on cloud AI" as a
> **named, deliberate exception** the user has to knowingly step into, we keep a
> **persistent visible reminder** while it's on, we make it **reversible**, and we
> built the AI's access so that it can only ever **read** and **propose** — the
> human is always the one who actually **acts**. This document walks through every
> screen, warning, and checkbox that implements that, and explains what each one
> is for.

---

## 1. Two ideas that everything else hangs on

Almost every AI-safety screen in this app is an expression of one of two ideas.
It's worth getting them straight before the screenshots, because then each
screenshot just becomes "oh, that's idea 1" or "that's idea 2."

### Idea 1 — *Exceptions*: leaving "local-only" is a door you knowingly walk through

The app's default promise is **local-only / never-SaaS**: it doesn't talk to a
company's servers about your data. When you wire it to a cloud AI, that promise no
longer holds — your data can now leave your device. Rather than hide that, the app
gives the situation a **name and a stable ID: `EX-CLOUD-LLM`** ("the cloud-LLM
exception"). That one ID ties together everything you'll see below: the consent
gate that raises it, the banner that announces it, the explainer page that
describes it, and the control that clears it. Naming the condition is what lets us
be *consistent* about it instead of scattering vague warnings around.

### Idea 2 — *User mediation*: the AI proposes, the human disposes

The second idea governs what the AI is actually *allowed to do*. The rule is:

> **The human is the one who acts. The AI can only suggest.**

Anything that changes your saved data, or sends it anywhere, has to pass through a
moment where **you** review a clear, readable summary and **you** click the
button. The AI — or the network, or an import file — can only *stage* a proposal;
it can never be the thing that pulls the trigger. We call the suggesting side the
*proposer* and the deciding side the *disposer*, and they are deliberately kept
separate.

The rest of this document follows the natural timeline of using an AI with the
app — **before**, **during**, and **after** — and shows how these two ideas show
up at each stage.

---

## 2. BEFORE you turn on AI: the consent gate

You enable cloud AI from the app's **Settings** page, under "Set up Claude Desktop
integration." The very first time, you cannot just breeze through it. The app
opens a gate that you have to *read and accept* before anything happens.

![The cloud-AI consent gate: a platform note, a yellow "set up a folder first"
heads-up, a two-point plain-language agreement, an unchecked "I understand and
accept these risks" box, Claude Desktop's own red warning, and a disabled
"Continue" button.](images/ai_safety/01_consent_gate.png)

There is a lot of intention packed into this one screen. From top to bottom:

- **A platform note.** It states up front that this easy path is for Chromium
  browsers (Chrome, Edge, Brave, Arc); Safari and Firefox users are pointed at a
  manual walkthrough. (This ties back to the data-safety story — the app always
  knows what platform you're on.)

- **A yellow "heads up."** If you haven't set up a durable data folder yet, the
  app warns you here, because without one you'll have to redo this setup every
  time you change a group.

  ![The folder heads-up, shown when no durable data folder is
  attached.](images/ai_safety/03_mcp_folder_warning.png)

- **A two-point agreement, in honest plain English.** Not legalese. The two points
  say, in so many words:

  1. *"You're leaving the local-only model."* Connecting Claude sends your fellows
     data — potentially including your private groups and notes — to a cloud
     vendor (Anthropic), and *"no one can guarantee what a SaaS vendor will or
     won't do with data you send it."*
  2. *"MCP and LLMs are new, and can misbehave."* The extensions are written to do
     only benign, read-only things and the code is auditable — but an AI driving
     them can still make mistakes. The reassuring half is also stated: the
     extensions touch only two files, and *both are recoverable* from a
     re-download or a backup.

- **A pre-emptive de-spin of someone else's scary warning.** The agreement warns
  you that *Claude Desktop will show its own "can access everything on your
  computer" message*, explains that this is Claude Desktop's generic boilerplate
  (the red box you can see in the screenshot), and tells you the *accurate*
  description is the one above. This is unusual and worth dwelling on in a talk:
  we go out of our way to make sure the user isn't either falsely alarmed *or*
  falsely reassured by a warning that isn't ours.

- **A clear statement of what accepting *means*.** Just above the checkbox:
  *"Accepting raises the `EX-CLOUD-LLM` exception and takes this app out of PNA
  (local-only) mode,"* with a link to the full explainer and the reminder that
  *"it is reversible."*

- **A checkbox and a `Continue` button that start out disabled.**

### The deliberate-friction part: you must scroll, then check

The checkbox is **locked until you scroll to the bottom of the agreement.** You
can't accept text you haven't been shown. Only after you've scrolled does the box
become tickable; only after you tick it does `Continue` light up:

![The agreement scrolled to the end, with the "I understand and accept these
risks" box now checked.](images/ai_safety/02_consent_accepted.png)

This scroll-then-check-then-continue sequence is the literal mechanism behind the
strongest safety claim the app makes: **consent genuinely precedes turning the
feature on.** It's three small, deliberate actions, and only the last one starts
anything.

> **Why this counts as "before."** The app records your consent *the instant you
> accept* — before the download even begins. So if you accept and then cancel the
> browser's download prompt, you won't be shown the full gate again, but you also
> haven't been quietly opted in to anything you didn't accept. The decision point
> and the consent record are the same moment.

### What "setup" actually involves

The same dialog lays out the concrete steps, so there are no surprises about what
connecting an AI entails:

![The "What happens next" steps: approve a multi-file download, open the three
extension files, install them in Claude Desktop, point the private extension at
your data file, restart Claude, and test.](images/ai_safety/08_mcp_setup_steps.png)

The three extensions map onto three different boundaries, and you can install only
the ones you want:

1. **Fellows directory (Shared)** — lets the AI read the *public* directory.
2. **Your saved groups (Private)** — lets the AI read *your private* groups and
   notes. The app is explicit that *"when Claude reads it, it goes to Claude's
   servers,"* and that you can simply **skip this extension** if that's not okay
   with you.
3. **Email staging (Communications)** — lets the AI *draft* emails to hand back to
   you. It is spelled out that *"Claude never sends mail itself."* (That's Idea 2
   — proposer/disposer — and we'll come back to it.)

---

## 3. The moment of crossing: the exception is raised

When you accept and continue, the app does something it does for no other action:
it **changes its own declared mode** from "PNA (local-only)" to "not a PNA," and
records that the `EX-CLOUD-LLM` exception is now active. From this point on, the
app is honest with *itself* about no longer keeping its core promise — and it says
so to you, on every screen, until you turn it back off.

---

## 4. DURING: the persistent "Going rogue" reminder

While cloud AI is connected, a banner rides along at the top of the app on every
load. It does not nag with detail — it's a calm, constant, unmissable statement of
fact:

![A pink banner reading "Going rogue. You enabled a cloud-AI exception, so this
app has left local-only mode," with a "Find out What this Means" link and a
"Dismiss" button.](images/ai_safety/04_going_rogue_banner.png)

Three deliberate choices here:

- **It's persistent.** The banner shows on *every* load while the exception is
  active. You can't drift into forgetting that you flipped this switch.

- **"Dismiss" acknowledges; it does not undo.** Tapping `Dismiss` hides the banner
  (it would be obnoxious otherwise), but it pointedly **does not turn the
  exception off** — you're still in non-PNA mode. Hiding a reminder and revoking a
  capability are different actions, and the app refuses to conflate them.

- **It links to a full explanation,** rather than trying to cram the whole story
  into a banner.

Underneath the banner, the app also stamps a small machine-readable marker on the
page (`data-pna-mode="non-pna"`). That sounds like an implementation detail, but
it matters for a talk: it means an automated conformance check can *verify* the
app is being honest about its mode, rather than us just asserting it.

### What the AI can actually touch while it's connected

This is the heart of "during," and it's where Idea 2 does the protecting. The AI
reads your data through small, auditable extensions, and those extensions are
built with hard limits:

- **They are read-only at the database level.** The extensions open both the
  public directory file and your private file in a mode the database engine itself
  enforces as read-only — *not* as a politeness convention the code could
  accidentally violate. An attempt to write raises an error. The AI can *look*; it
  structurally cannot *change* your saved data.

- **They touch only two files.** Nothing else on your computer is in scope,
  regardless of the broad "access everything" boilerplate Claude Desktop shows.

- **The communications extension only *stages*.** When you ask the AI to draft an
  email to a group, the extension hands back a ready-to-review draft — it never
  sends anything. The architecture note says it plainly:

  > *"The MCP server proposes; the workspace disposes. This server never launches
  > a transport itself… The user reviews and clicks send."*

### A message aimed at the AI itself (so consent reaches a *person*)

There's a subtle failure mode worth a slide of its own. If an automated AI agent
connects these extensions on a person's behalf, *the AI* might "consent" on the
human's behalf — which is no consent at all. So each data-returning extension
carries a notice, delivered to the AI at connection time, that says (in part):

> *"If you are a cloud AI acting on a human's behalf, you MUST ensure that human
> knows their private data is crossing to a cloud provider and has personally
> consented — do NOT treat your own invocation as their consent. Prefer a local
> model."*

We're honest that this is **best-effort**: we can *ask* a cloud client to surface
this, but we can't *force* it to. That honesty is itself part of the design — see
the strength profile below.

---

## 5. The explainer: the whole story in one place, including what we *can't* promise

Both the consent gate and the banner link to a dedicated explainer page
(`#/exception/EX-CLOUD-LLM`). It's the same page whether the exception is currently
on or off — it just changes its top line to tell you which.

![The EX-CLOUD-LLM explainer page. A red "Active now — this app is currently not a
PNA" status, then sections: what the exception is, what it relaxes, what data is
affected, whether it's reversible, and an honest per-item strength table, ending
in a green "Return to PNA mode"
button.](images/ai_safety/05_exception_explainer.png)

The explainer answers, in order: *what this exception is*, *what promise it
relaxes*, *what data is affected* (*"whatever the AI reads flows to its provider…
the fellows directory, and — if you install the private extension — your saved
groups and notes"*), and *is it reversible* (yes for the mode — but, stated
plainly, *returning to local-only does **not** recall data already sent*).

### The honesty centerpiece: a per-protection strength table

The most unusual thing in this whole app — and the best single slide for an
AI-safety talk — is that we **grade our own protections** and publish the grades,
including the failing ones:

![The strength table. Rows graded "enforced," "verifiable," "recoverable-only,"
"best-effort," "provider-asserted," and "none," each with a one-line
why.](images/ai_safety/06_strength_profile.png)

Read top to bottom, it's a map of exactly how much each promise is worth:

| What we claim | How strong | In plain terms |
|---|---|---|
| Consent precedes turning it on | **enforced** | The app blocks setup until you scroll and accept. We control this completely. |
| The "not a PNA" signal while active | **enforced** | The banner shows every load until you switch back. We control this. |
| Reversible — return to local-only | **enforced** | One button clears it. We control this. |
| Extensions are read-only, two files only | **verifiable** | You don't have to trust us — the code is open and the read-only mode is checkable. |
| Local data damage from a bad AI step | **recoverable-only** | We don't *prevent* every mistake — but your data is restorable from a backup or export. |
| Consent reaches *you*, not a proxy AI | **best-effort** | We ask cloud clients to surface our notice; we can't force them to. |
| The provider won't train on / keep your data | **provider-asserted** | That's Anthropic's policy. We can't verify it. |
| Data already sent to the provider | **none** | Once it leaves your device, it can't be recalled. Full stop. |

The point of this table is the bottom rows as much as the top. A safety story that
only listed the green "enforced" rows would be marketing. By printing the
**best-effort**, **provider-asserted**, and **none** rows right next to the strong
ones, the app tells the user the truth: *we built strong guarantees around the
boundary — consent, signaling, reversibility, auditability — but once your data
crosses to the cloud, we can't make promises about the data itself.* Being clear
about the edge of our control is the safety feature.

---

## 6. AFTER: turning it back off is one honest click

Because the mode is reversible, every screen that announces the exception also
offers the way out. On the explainer it's the green **"Return to PNA mode"**
button; in Settings it's a matching row:

![The Settings reminder: "Not in PNA mode. Cloud-AI integration (EX-CLOUD-LLM) is
active," with a "Return to PNA mode" button.](images/ai_safety/07_return_to_pna.png)

Clicking it returns the app to local-only mode, clears the banner, and **re-arms
the full consent gate** — so re-enabling later is a fresh, deliberate decision, not
a quiet toggle. The app is also careful *not* to over-promise here: returning to
local-only stops *future* sharing, but the explainer says outright that it can't
pull back data already sent. Reversible mode, irreversible disclosure — and we
don't blur the two.

---

## 7. The proposer/disposer rule, made concrete

Idea 2 said the AI can only *propose*; the human *disposes*. Here's what that
actually looks like, because it's the safety mechanism that operates even when no
AI is involved at all — the same gate protects you from a buggy import or a
malicious link.

The clearest example is reaching out to a group. An AI (or you) can *prepare* an
email to a whole group, but the act of sending always lands in a surface **you**
control and review first:

![A group's detail page with its action bar — "Mail to the whole group," CC/BCC,
"Copy email addresses," "Edit members," "Export a directory" — and the export
panel open, showing the format choice, the exact filename, and the full member
list before anything is produced.](images/users_manual/06_export_panel.png)

Notice what this surface does:

- It shows you **who** (the full member list, by name), **what** (subject, body,
  the merged data), and **how** (email vs. a downloadable directory) — *before*
  anything leaves.
- It's **legible by design**: real names, not internal record numbers, and any
  text that came from an outside source (including from an AI) is shown as plain
  text, never executed as code.
- The thing that finally sends or downloads is **a button you press.** The email
  opens in *your* mail app with To/Subject/Body pre-filled; you click Send. The AI
  never had its finger on that button.

The same pattern guards every door where data changes or leaves:

- **Creating or editing a saved group** → the change is applied only by the app's
  single trusted database-owner, only after you save. And — connecting to the
  data-safety story — *off a verified folder the app refuses the write entirely,
  even if something tries to sneak past the screen and drive the database
  directly.*
- **Sending email** → the AI/extension stages a draft; your mail client (a surface
  you control) sends it.
- **Exporting a group** → you see the full preview, then you download.
- **Updating the shared directory** → if new directory data would orphan members
  of your saved groups, the app shows you exactly what would change and waits for
  your **confirm or cancel**.

> **An honest gap we keep visible.** One path — wholesale *restoring* your private
> database from a backup file — currently shows you a row-count change rather than
> a detailed item-by-item preview. The "human disposes" half holds (you still
> confirm, and an AI can't trigger it off-folder), but the "you can clearly see
> what's changing" half is weaker there than for a directory update. We track that
> as an open item rather than quietly rounding it up to "done." Naming our own
> weak spots is the same instinct as the strength table.

### The frontier we've pinned for the future

Today, the "review happens somewhere an AI can't act" guarantee is partly true
*by construction* — the app's own screens have no AI embedded in them. We've
written down the commitment for when that changes: **any future in-app AI is a
proposer subject to the same dispose gate — never an actor.** It's a line drawn
*before* the feature exists, so it can't be quietly crossed later.

---

## 8. Everything on one slide: each notice mapped to the rule it serves

This is the summary table for the talk — every AI-safety surface, what stage it
belongs to, and which of the two ideas it implements.

| Screen / notice | Stage | Idea it serves | What it guarantees |
|---|---|---|---|
| **Consent gate** — scroll, then check, then continue (screenshots 01–02) | Before | Exceptions | Consent genuinely *precedes* enabling cloud AI. **Enforced.** |
| **Folder heads-up** inside the gate (03) | Before | Data-safety + Exceptions | You're told you lack a durable home for private data before you build on it. |
| **"What happens next" steps** (08) | Before | Transparency | No surprises about what connecting an AI involves. |
| **De-spin of Claude Desktop's own warning** (in 01) | Before | Honesty | You're neither falsely alarmed nor falsely reassured by a third party's message. |
| **"Going rogue" banner** (04) | During | Exceptions | A constant, honest signal that local-only no longer holds. **Enforced.** |
| **Dismiss = acknowledge, not undo** (04) | During | Honesty | Hiding a reminder never silently revokes the capability. |
| **Read-only, two-file extensions** | During | User mediation | The AI can read but structurally cannot change your data. **Verifiable.** |
| **Notice aimed at the AI itself** | During | User mediation | Consent must reach a *person*, not be self-granted by an agent. **Best-effort (stated).** |
| **Explainer page** (05) | During | Exceptions | The full story — what's shared, what's affected — in one place. |
| **Strength table** (06) | During | Honesty | Each protection graded, *including* the ones we can't guarantee. |
| **Compose / export preview** (group screenshot) | During/After | User mediation | You see who/what/how and press the button — the AI only proposed. |
| **"Return to PNA mode"** (07) | After | Exceptions | The exception is reversible with one click, and re-enabling is a fresh decision. **Enforced.** |
| **"…does not recall data already sent" notice** (in 05) | After | Honesty | We don't claim reversibility we don't have. **Strength: none — and we say so.** |

---

## 9. The takeaway

We could have done the easy thing in either direction — ban cloud AI outright, or
add it with a one-tap toggle and a tiny disclaimer. Instead we tried to do right by
the user's *understanding*:

- **Turning on cloud AI is a door you knowingly walk through** — read, scroll,
  check, continue — and it's a named, visible, reversible exception, not a hidden
  setting.
- **While it's on, you're never allowed to forget,** and what the AI can do is
  bounded to *reading* and *proposing* — every change or send still passes through
  a surface where a person reviews and acts.
- **We grade our own protections in public,** including the ones that are only
  best-effort or entirely out of our hands, because the most important safety
  feature is an accurate picture of where our control ends.

The honest headline: *we did our very best to make sure that when a user lets an AI
into their personal data, they understood the situation, stayed in control of
every consequential action, and were never told a protection was stronger than it
really is.*

---

## Appendix: where this lives (for the curious)

- **Consent gate, banner, explainer, return-to-PNA control:** `app/static/app.js`
  (search `recordMcpbConsent`, `syncNotAPnaBanner`, `renderExceptionPage`,
  `returnToPnaMode`) and `app/static/index.html` (the `not-a-pna-banner`).
- **The named exception + its handler cascade (EX-H1…EX-H8):** the *Exception
  attestation* table in `docs/Architecture.md`; discovery story in
  `docs/architectural_findings.md`; upstream write-up in
  `plans/pna_toolkit_exceptions_contribution.md`.
- **Read-only / stage-only AI extensions + the notice to the AI:**
  `mcp_servers/private_data_ops.py`, `mcp_servers/shared_data_ops.py`,
  `mcp_servers/comms.py` (search `CLOUD_LLM_PROPAGATION_NOTICE`).
- **Proposer/disposer rule (user mediation):** the *User-mediation attestation*
  section of `docs/Architecture.md`; `plans/pna_toolkit_user_mediation_contribution.md`;
  the not-yet-shipped AI-write design in `plans/ai_write_proposals_groups.md`.
- **The setup walkthrough:** `docs/use_with_claude_desktop.md`.
- **Tests that hold these surfaces honest:** `tests/e2e/test_pna_exception_mode.py`,
  `tests/e2e/test_mcpb_settings.py`, `tests/e2e/test_sandbox_sealed_mcp.py`,
  `tests/e2e/test_groups_export.py`, `tests/e2e/test_groups_compose.py`,
  `tests/test_private_data_ops.py`, `tests/test_comms.py`.
