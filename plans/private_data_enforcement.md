# Plan — Private-Data Enforcement (make "browse-only stores nothing durable" actually true)

**Status:** ✅ DONE. **Created:** 2026-06-03. **Landed:** 2026-06-03.
- **PR A + PR B** (durable-write guard + prefs-dormant-off-folder) shipped in
  **PR #244** (`d2706a9`). The worker-side load-bearing guard + page-side
  defense-in-depth both refuse mutating `relationships.db` RPCs off-folder; the
  boot reconciles no longer call `setSetting` in browse-only mode.
- The strict-xfail placeholder in `tests/e2e/test_browse_only_durability.py`
  was promoted to hard guards in the new
  `tests/e2e/test_private_data_enforcement.py` and the now-superseded xfail was
  dropped (`d1e7edf`).
- **PR C** (the prevention substrate) landed via the conformance-discipline
  work in **PR #243** (`1871b30`): `tests/test_attestation_has_evidence.py` is
  the evidence checker, and the CLAUDE.md stanza from §5 below is now in the
  *Conformance discipline* section of `CLAUDE.md`.
- `docs/Architecture.md` CST rows reconciled to `conformant` citing
  `tests/e2e/test_private_data_enforcement.py` (this PR).

**Closes the gap found** while writing the Tier-1 security tests: the
private-data capability gate
([`private_data_capability_gate.md`](private_data_capability_gate.md))
shipped its **visible** half (UI surface gating, route redirects, unlock/probe,
reconnect/identity) but **never** shipped its **enforcement** half. The plan
put enforcement in PR1 ("Shared mode = localStorage-only; do not open
`relationships.db` for durable data when locked"); the as-built PR1 deferred it
in a code comment, and PR3 ("browse-only feature *reduction*") implemented only
the UI reduction. There is no `privateDataEnabled()` check at any write site.

---

## 1. The gap in one paragraph

Today, off-folder, the app still durably persists private data to evictable
OPFS. Concretely: (a) the worker-provider mutating methods (`createGroup`,
`updateGroup`, `deleteGroup`, `setSetting`) are gated **only** on version skew
(`refuseIfVersionSkew`, `app.js:3915`) — not on the gate — so any caller
(`window.__dataProvider.createGroup(...)` from DevTools, or a stray code path)
writes `relationships.db` to OPFS in browse-only mode; (b) worse, the two boot
reconciles (`reconcileHasEmailFilterOnBoot` `app.js:~5275`,
`reconcileSelfEmailOnBoot` `app.js:~10480`, fired at `app.js:~11531/11536`) are
**ungated** and call `dataProvider.setSetting(...)` on *every* boot — so every
browse-only user gets a settings-bearing `relationships.db` in OPFS with no
folder and no user action. This makes three claims in
[`../docs/Architecture.md`](../docs/Architecture.md) **over-claim**:
`CST-PWA-STORAGE-EVICTABLE` ("Avoided… browse-only is localStorage-only"),
`CST-PWA-PRIVATE-SNAPSHOT` ("absent a folder there is **no** private store"),
and plan §3 ("`relationships.db` stays dormant"). The fix restores truth to the
attestation.

---

## 2. The enforcement has two halves + a layer

| Half | Where | What |
|---|---|---|
| **A. No durable private write off-folder** | worker (load-bearing) + page (defense-in-depth) | Refuse mutating `relationships.db` RPCs unless a verified folder is attached. Reads + the legacy peek still pass. |
| **B. Prefs are localStorage-only off-folder** | page (`app.js`) | `has_email_only` / `self_email` read+write localStorage only when `!privateDataEnabled()`; migrate them *into* `settings` only on unlock, never on a browse-only boot. |
| **C. Make it un-regress** | tests + docs + CLAUDE.md | Promote the strict-xfail to a hard guard, reconcile the attestation, encode the conventions that would have caught this. |

### Why both worker and page for Half A

The existing version-skew guard is **page-side** (`refuseIfVersionSkew`), and
that's an accepted realization for AC-4. We mirror it page-side for the same
reasons (fast feedback, a clean error the UI can surface, closes the
DevTools-calls-`__dataProvider` path). **But the page-side gate is itself
flippable in DevTools** — which is exactly the original concern that started
this work. So the **load-bearing** guard is **worker-side**: the worker owns
OPFS and independently knows its own folder-handle state (hydrated at
`sqlite-worker.js:~1872-1906`; permission at `~2028/2444`). A worker that
refuses `relationships.db` mutations unless it holds a *granted folder handle*
cannot be talked out of it from the page console — a DevTools session can call
the RPC but cannot conjure a real, permission-granted `FileSystemDirectoryHandle`.
This abolishes OPFS-only-**canonical** mode *for `relationships.db`* under the
gate (OPFS stays a transient mem-VFS buffer in folder mode; pre-existing OPFS
rows stay **readable** for the migration peek). This is the one change that
moves the guarantee from cosmetic to real.

---

## 3. Implementation sequence (each PR shippable + revertible; keep `just test-fast` green)

### PR A — the durable-write guard (the core)

**Page-side (`app/static/app.js`):**
- Add `refuseIfBrowseOnly(opLabel)` next to `refuseIfVersionSkew` (`~3915`),
  returning a rejected promise with a typed error (`code: 'browse_only'`,
  message: "Saved data needs a connected folder — open Settings to enable it.")
  when `!privateDataEnabled()`.
- Chain it ahead of the version check on every mutating worker-provider method
  (`createGroup` `3971`, `updateGroup` `3975`, `deleteGroup` `3979`,
  `setSetting` `3989`) — and any group-member / notes / tags mutators that route
  through the worker:
  `return refuseIfBrowseOnly('createGroup') || refuseIfVersionSkew('createGroup') || rpc.call(...)`.
- The `api+idb` provider (`~1643`) has no durable private store (prod ships no
  `/api/groups` per AC-2), but guard its mutators too for symmetry + a clean
  error rather than a network 404.

**Worker-side (`app/static/vendor/sqlite-worker.js`) — the bypass-resistant guard:**
- In the RPC dispatch for `createGroup`/`updateGroup`/`deleteGroup`/`setSetting`
  (and member/notes/tags writes), refuse with an `OWNERSHIP`/`BROWSE_ONLY`-style
  typed error unless the worker currently holds a permission-`granted` folder
  handle for the canonical store. Reads (`listGroups`, `getGroup`, `getSetting`,
  `countRelationships`, `inspectRelationshipsBytes`) and the migration peek stay
  allowed.
- Keep the OPFS slot usable as the folder-mode mem-VFS buffer and as the
  read-only source for the legacy peek; only **mutation persistence** off-folder
  is refused.

**Tests:**
- Promote `tests/e2e/test_browse_only_durability.py::test_no_durable_private_write_when_browse_only`
  from `@pytest.mark.xfail(strict=True)` to a hard guard (drop the marker).
- Add a worker-level analog mirroring
  `tests/e2e/test_version_handshake.py::test_version_skew_refuses_mutations_but_allows_reads`:
  off-folder, mutating RPCs reject while reads + peek succeed.
- Add a page-side unit/e2e: `__dataProvider.createGroup(...)` rejects with
  `code: 'browse_only'` when `!privateDataEnabled()`.

### PR B — prefs go dormant off-folder (complete the "dormant `relationships.db`" claim)

- `reconcileHasEmailFilterOnBoot` / `reconcileSelfEmailOnBoot`: early-return to
  localStorage-only when `!privateDataEnabled()`. Never call `setSetting` on a
  browse-only boot.
- Move the localStorage→`settings` migration of both prefs to fire **on unlock**
  (when the gate flips to `private-folder`), one-shot — so folder users still get
  durable prefs, browse-only users get none.
- Confirm the directory has-email filter + export "email it to me" still work
  from localStorage in browse-only (they already read the localStorage cache).
- **Tests:** after a browse-only boot, the worker reports **no** `relationships.db`
  settings rows (or no `relationships.db` at all); after unlock, the prefs appear
  in `settings`.

### PR C — make this class of gap un-regress (prevention substrate)

- `tests/test_attestation_has_evidence.py` (new, no server): parse the
  Architecture.md AC/CST attestation tables; assert every row marked
  `conformant` names a Verification ref that resolves to a real test
  id/function that exists in `tests/`. Rows marked `Open`/`partial`/`deferred`
  are exempt but must carry the honest status. (Dumb string-resolution check —
  catches "claimed conformant, zero tests" cold, which is precisely this bug.)
- `CLAUDE.md` stanza (see § 5).
- Reconcile `docs/Architecture.md`: once PR A+B land, the three CST rows are
  genuinely test-backed; keep `conformant` and add the new test refs. **Until
  they land, soften those rows to `partial`/`Open` so the doc stops
  over-claiming** — this is the honest interim state.

> Batching: PR A and PR B are a unit (the guarantee isn't true until both land);
> PR C can land alongside or just after. All three are small.

---

## 4. Out of scope / unchanged
- The unlock/probe/reconnect/identity machinery (PR4/PR5) — untouched; this only
  adds the missing write-refusal + pref-routing.
- Folder mode with a verified folder — full app, unchanged.
- The mobile shell (PR6) — orthogonal layout; merges independently.

---

## 5. CLAUDE.md stanza (proposed — the convention that would have caught this)

> **Capability reductions enforce at the data layer, never UI-only.** When a
> feature is gated off (e.g. the private-data capability gate), hiding/greying
> the surface and redirecting the route is *not* the reduction — it's the
> cosmetic half. The reduction is that the **write does not happen**: refuse the
> mutating op at the worker (the OPFS owner) and, defensively, at the
> `dataProvider`. A gated capability whose RPC still succeeds from the DevTools
> console is not reduced.
>
> **Deferred or not-yet-true invariants are `@pytest.mark.xfail(strict=True)`
> tests that name the plan PR which will satisfy them — never a `// TODO` or a
> prose "lands later."** A strict-xfail is a deferral with a tripwire: it can't
> be silently forgotten (it goes red the day someone implements it) and
> `grep xfail(strict` is the live list of claimed-but-unproven invariants.
>
> **No attestation row is `conformant` without an executable Verification ref.**
> The `docs/Architecture.md` AC/CST tables are a Security Target: a claim with
> no test is a finding. Negative invariants ("X must NOT happen off-folder")
> need a negative test; the happy-path test does not cover them.
