# The Risk of Decentralising a Directory: Local-First vs. SaaS

**Audience:** the fellows, and anyone who was part of — or wants to understand —
the decision to turn a shared, centrally-hosted directory into a local-first
app that every member carries a full copy of. The decision is already made
(the central directory is being retired). This document exists so the reasoning
is on the record for posterity, and so the next community facing the same choice
has an honest analysis to start from rather than a slogan.

It is **not** a backlog of things to fix — that's
[`docs/securityaudit.md`](./securityaudit.md). This is an analysis of a risk we
**chose to take**, why it's defensible, and where it would *not* be.

---

## The question

When a central directory is wound down, the data doesn't have to die with it.
You can hand every member a full local copy and let the directory live on their
devices — offline, indefinitely, owned by no one. That's what this app does.

But "decentralise it so it survives" is a trade, not a free win. The honest
question is: **what risk do you take on when you replace one well-defended
central copy with N≈500 copies spread across members' laptops and phones, and
turn off the central infrastructure that used to mediate access?**

The intuitive answer — "SaaS is one big target; spreading it across 500 devices
is safer" — is misleading here. In *both* models, any authenticated member can
see the entire directory. Per-account blast radius is the full N in both. The
real differences live elsewhere: in *who* can be compromised, in *how long* a
leak persists, and in *what happens when the lights go out*.

---

## The two models, side by side

| Dimension | Centralised SaaS (e.g. the retired directory) | Local-first (this app) |
|---|---|---|
| Server-side full-DB exfil | Provider's security sets the floor | Smaller surface: no per-user state, just an allowlist + a mail token + a session secret |
| Per-account / per-device takeover | Full N exposed during the session window | Full N exposed (whatever is on disk) |
| Persistence of a leak | Session-bound; revocable by resetting the account | **Indefinite**; the copy on a stolen device can't be revoked |
| Ex-member retention | Revoke the account → their future access ends | Past data lives forever on departed members' devices |
| Provider insider / subpoena / breach | A real, central risk | None — there is no provider |
| Provider shutdown | **Catastrophic** — the directory disappears for everyone | None — the directory survives on every device |
| Update / supply chain | The provider's deploy pipeline | **One maintainer + one VPS** is the entire supply chain |
| Audit / detection | Central logs; mass exfil is at least *detectable* | None — a leak is invisible to the maintainer |
| Patching cadence | One server, patched fast | N devices, long-tailed; old copies never patch |

Read the table as a *reshaping* of risk, not a reduction of it. Decentralisation
**removes the peak risks** (no provider to breach, no insider, no subpoena, no
single shutdown that ends the directory) and **adds tail risks** (copies that
can't be revoked, a one-person supply chain, no central detection).

---

## Rough quantification

Order-of-magnitude, 5-year horizon, ~500 members. The point isn't the exact
numbers — it's that the two models land in the same ballpark, and *where* they
differ.

- **p(server full-DB compromise / year):** ≈ 2% for a well-run SaaS; ≈ 1–3% for
  a single hardened droplet. Comparable. (And for the local-first model this
  term **goes to zero** once distribution shuts down — there's no longer a
  server to compromise.)
- **p(per-member device/account compromise / year):** ≈ 3% baseline (phishing +
  malware), independent across members. So **E[compromise events/year] ≈ 0.03 ×
  500 ≈ 15** — and this dominates the breach count, *in both models roughly
  equally.* Most breaches are a member's own device or inbox, not the server.

The interesting term is the **conditional cost** of each event:

- **SaaS account takeover:** attacker has a bounded window; ~1× full-N exposure,
  then the account can be reset.
- **Local device compromise:** attacker reads the on-disk copy at leisure —
  including the highest-value fields (mobile numbers, citizenship, free-text) —
  and **the data persists** even after the session, the device owner's
  awareness, or the maintainer are gone.

With ~5%/year membership turnover, over a decade **~250 ex-members hold full,
unrevocable copies**. SaaS revokes departed members; local-first cannot. That
cumulative, unrevocable retention is the **structural risk premium** of going
local-first. It is the price of the thing that makes local-first worth doing.

**Net:** comparable expected exposure in any single year; **lower peak risk**
(no provider/insider/subpoena/shutdown event is even possible) bought with
**higher tail risk over time** (retention compounds; the update channel is a
single point of failure). Local-first here is *defensible* — not *unambiguously
safer.*

---

## What decentralisation buys

1. **It survives the shutdown.** The whole reason this exists. When the central
   directory is retired, a SaaS directory would simply be *gone*. The local-first
   directory keeps working on every device that installed it — offline, forever,
   even after the maintainer, the org, or the server are no longer around. Its
   single most useful function (composing email to a saved group) works with no
   server at all.
2. **No provider to breach, subpoena, or sell.** There is no central honeypot,
   no insider with standing access, no third party whose terms can change. The
   peak-severity events of the SaaS world are removed from the board.
3. **The data lives at the level it was always shared.** For *this* directory,
   the fields involved (email, mobile) were already shared among all members by
   the directory's social contract. Persisting them on each member's device is
   the deal members accepted — not a new exposure.

## What it costs

1. **Unrevocable retention.** You cannot un-give the data. A departed member, or
   a stolen device, keeps the directory indefinitely. There is no "disable
   account."
2. **A one-person supply chain.** One maintainer and one VPS sign and serve the
   bundle. A compromise there is the worst plausible event *by impact* — a
   poisoned update could reach every device. (This app mitigates it with
   out-of-band **signed bundles** the service worker verifies, and a public-key
   fingerprint delivered through a separate channel — see `SECURITY.md` — but the
   maintainer's keys remain the crown jewels.)
3. **No central detection.** In the SaaS model a mass exfil at least leaves a log.
   Here, a leak from a member's device is simply invisible. You trade
   detectability for the absence of a thing to detect.

---

## "But could we just keep the SaaS alive on donations?"

A fair counter-question, and worth answering honestly rather than dismissing.
Keeping an unmaintained (or barely-maintained) central directory alive — funded
by member donations or goodwill — carries its *own* risks, and they are not
obviously smaller:

- **An unmaintained app is a decaying app.** A live server running
  rarely-patched application code is a *growing* attack surface over time. The
  local-first bundle, by contrast, exposes no server-side application logic once
  distribution ends.
- **The funding cliff is a shutdown waiting to happen.** Donation-funded infra
  survives only as long as the donations and a willing operator do. The day
  either lapses, you get the *catastrophic* SaaS-shutdown event anyway — except
  now with no decentralised copies to fall back on. You'd have paid the running
  cost *and* still lost the directory.
- **It re-centralises the high-severity risks** decentralisation removed:
  provider insider access, subpoena exposure, one breach = everyone, and a
  single operator whose account compromise is total.
- **It doesn't actually lower the dominant risk.** Recall the math: ~15 of the
  ~15 expected yearly breaches come from *members' own* devices and inboxes.
  Keeping the server alive doesn't touch that term. It mostly buys back
  *revocability* and *central detection* — real but secondary — at the cost of
  re-introducing every peak risk plus an ongoing maintenance burden.

The defensible reading: a donation-funded SaaS makes sense **only** if the
community both (a) genuinely needs revocability/detection enough to pay for it,
and (b) can guarantee a *maintained* — not merely *alive* — application
indefinitely. Absent (b), "keep it alive on donations" tends to be the worst of
both worlds: SaaS-level peak risk, plus the eventual shutdown, plus a steady
maintenance bill. For this directory, with the central option already retired
and a trusted-ish membership, decentralising and stepping back was the better
trade.

---

## When this pattern fits — and when it doesn't

**This recurs whenever an organisation wants to decentralise an archival
directory before winding down its central infrastructure.** If you're applying
the same playbook to another community, the decision turns on a few questions:

- **Is the data "public among the members" already?** If the fields are what
  every member shares *with every other member* by the group's own social
  contract (names, emails, "what I'm working on"), local-first persistence is
  just formalising the existing deal. ✅ Good fit.
- **Is some of the data sensitive *between* members?** Health records, current
  physical location, employer disputes — data members would *not* hand each
  other freely. Then unrevocable, full-copy-on-every-device is the wrong shape.
  ✗ Wrong fit; that data wants an app with different contracts (server-mediated,
  per-record reads, revocable access) — a *different* app, not a tweak to this
  one.
- **Is the central option actually surviving?** If a maintained central service
  is genuinely on the table and funded, the revocability + detection it buys may
  be worth keeping. If it's being retired regardless (as here), local-first is
  about *survival*, and the comparison is moot.
- **Can you make the supply chain trustworthy?** A one-maintainer local-first
  channel is only as safe as its update path. Signed bundles + an out-of-band
  key are the minimum bar; without them, the supply-chain tail risk dominates.

---

## Conclusion

For a moderate-sensitivity directory, with a trusted-ish membership, and no
surviving central option, **local-first is defensible — it trades concentration
risk for tail risk, not "more secure" in the simple sense.** It removes the
peak-severity events (provider breach, insider, subpoena, catastrophic
shutdown) at the cost of unrevocable retention and a single-maintainer supply
chain. The mitigations that matter most are therefore the ones aimed at the tail:
hardening the maintainer's keys and update channel (see
[`docs/securityaudit.md`](./securityaudit.md) B2), signing every bundle, and
raising members' own device hygiene — because in both models, the member's own
device is where most breaches actually begin.
