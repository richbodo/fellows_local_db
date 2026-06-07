"""E2E for the fellows.db install + opt-in refresh primitives.

Originally Phase 3 of plans/local_first_worker_architecture.md ("SHA-keyed
refresh"). plans/opt_in_directory_data_updates.md narrowed the policy:
the boot path is install-only (never auto-refreshes a returning
visitor), and the user-driven "Update directory data" button on the
About page is the only way an installed fellows.db ever gets replaced.
The worker primitive (`ensureFellowsDb({mode: 'refresh'})`) still exists
and is what `applyFellowsDbSwap` builds on; this file pins that
primitive's behavior. The boot-path policy is covered by
`test_directory_data_update_flow.py`.

This file covers four runtime-falsifiable acceptance criteria:

  1. Two consecutive returning boots produce zero GET /fellows.db
     requests on the second boot — install-only is the default.
  2. ensureFellowsDb({mode: 'refresh'}) triggers exactly one GET
     /fellows.db; meta.sha rotates to the freshly-computed digest.
     This is the primitive applyFellowsDbSwap leans on — preserving
     it keeps the user-driven swap path testable.
  3. A failed refresh (network error or non-2xx) leaves the previously
     live fellows.db intact and writes meta.last_failure_* — the
     directory keeps rendering against the cached bytes.
  4. Restoring a relationships.db backup does not trigger a fellows.db
     re-fetch on next boot — proves the freshness sidecar
     (`fellows.db.meta.json`) lives outside the SAH-pool dir and is not
     touched by the relationships.db swap (invariant L8).

These run against the dev server (no auth gate) using the standalone-mode
fixture so the directory boot path is exercised end-to-end. The SW's
runtime-cache pass-through for /fellows.db (P3) is implicitly tested:
if it ever started caching again, the second-boot zero-fetch assertion
would fail.
"""
from __future__ import annotations

import json
import re

import pytest


def _wait_for_first_ensure(page, timeout_ms: int = 10000) -> dict:
    """Wait for the boot path's ensureFellowsDb to settle and return the meta.

    The worker's onmessage dispatcher does not serialize handlers, so a
    probe call with a different serverSha than the boot call would race
    on cold start (both could enter the fetch+import path). Instead, the
    helper fetches /build-meta.json itself and passes the real
    fellows_db_sha — that way the probe is idempotent with whatever boot
    is doing. Once fellowsDb is open and meta.sha matches the server's
    sha, the worker returns the no-op branch with `meta` populated.
    """
    return page.evaluate(
        """
        async (timeoutMs) => {
          // Get the canonical server SHA up-front so probe + boot agree.
          let serverSha = null;
          try {
            const r = await fetch('/build-meta.json', { cache: 'no-store' });
            if (r.ok) {
              const meta = await r.json();
              serverSha = (typeof meta.fellows_db_sha === 'string') ? meta.fellows_db_sha : null;
            }
          } catch (e) {}
          const deadline = Date.now() + timeoutMs;
          while (Date.now() < deadline) {
            if (window.__dataProvider && window.__dataProvider.kind === 'worker') {
              try {
                const res = await window.__dataProvider._ensureFellowsDb({ serverSha: serverSha });
                if (res && res.hasFellowsDb && res.meta && res.meta.sha) {
                  return res.meta;
                }
              } catch (e) {}
            }
            await new Promise((r) => setTimeout(r, 100));
          }
          throw new Error('Worker never settled with meta.sha within ' + timeoutMs + 'ms');
        }
        """,
        timeout_ms,
    )


def test_matching_sha_makes_no_second_fetch(standalone_page, base_url_fixture):
    """First boot fetches once; reload with same SHA fetches zero times.

    Proves the SHA-keyed gate works: returning visitors with up-to-date
    bytes do not re-download the directory on every page load.
    """
    page = standalone_page
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )

    # First boot — fresh profile, no OPFS state. Cold-start fetch is expected.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    meta1 = _wait_for_first_ensure(page)
    assert meta1 is not None and meta1.get("sha"), (
        f"first boot should populate meta.sha with the digest of fetched bytes; got {meta1}"
    )
    assert any(r.endswith("/fellows.db") for r in requests), (
        f"first boot should issue at least one GET /fellows.db; got {requests}"
    )
    first_sha = meta1["sha"]
    first_boot_count = sum(1 for r in requests if r.endswith("/fellows.db"))

    # Reload — same context, OPFS persists, /build-meta.json reports the
    # same fellows_db_sha. The SHA-keyed gate should suppress the fetch.
    page.reload(wait_until="domcontentloaded")
    meta2 = _wait_for_first_ensure(page)
    assert meta2 and meta2.get("sha") == first_sha, (
        f"meta.sha must be stable across reloads when server SHA didn't change: "
        f"first={first_sha} second={meta2 and meta2.get('sha')}"
    )
    second_boot_count = sum(1 for r in requests if r.endswith("/fellows.db"))
    assert second_boot_count == first_boot_count, (
        f"second boot should issue zero additional GET /fellows.db; "
        f"first_boot_count={first_boot_count} after_reload={second_boot_count} "
        f"all_requests={requests}"
    )


def test_explicit_refresh_triggers_one_refetch(standalone_page, base_url_fixture):
    """ensureFellowsDb({mode: 'refresh'}) rotates meta.sha to the actual
    fetched digest and produces exactly one GET /fellows.db.

    This is the worker primitive applyFellowsDbSwap builds on — it must
    keep working under direct invocation even though boot-path callers
    now always use mode='install-only'. plans/opt_in_directory_data_updates.md.
    """
    page = standalone_page

    # Boot once normally so OPFS has a fellows.db + meta installed.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    meta_before = _wait_for_first_ensure(page)
    assert meta_before and meta_before.get("sha"), (
        f"first boot should populate meta.sha; got {meta_before}"
    )
    real_sha = meta_before["sha"]

    # Drive an explicit refresh — install-only would no-op even with a
    # different serverSha, so we have to opt in via mode='refresh'.
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )
    fake_server_sha = "f" * 64  # syntactically a SHA-256 hex but not a real digest
    result = page.evaluate(
        "(sha) => window.__dataProvider._ensureFellowsDb({ serverSha: sha, mode: 'refresh' })",
        fake_server_sha,
    )

    assert result.get("refreshed") is True, (
        f"explicit refresh should re-import; got result={result}"
    )
    fetched = [r for r in requests if r.endswith("/fellows.db")]
    assert len(fetched) == 1, (
        f"explicit refresh must produce exactly one GET /fellows.db; got {fetched}"
    )
    # meta.sha is the digest the worker computed over the fetched bytes —
    # not the serverSha the page passed in. The dev server returns the
    # same DB bytes, so the digest should round-trip to the original sha.
    assert result["meta"]["sha"] == real_sha, (
        f"meta.sha must reflect the digest of fetched bytes (server-returned sha "
        f"{real_sha}), not the serverSha the page passed in ({fake_server_sha}); "
        f"got {result['meta']['sha']}"
    )


def test_install_only_does_not_refetch_on_sha_mismatch(standalone_page, base_url_fixture):
    """Install-only is a hard policy: even if the page hands the worker a
    different serverSha, no fetch happens when fellowsDb is already open.

    This is the boot-path contract — without it, every reload after a
    deploy would silently re-import fellows.db and the user could see
    profile data change underneath them. plans/opt_in_directory_data_updates.md.
    """
    page = standalone_page

    # Cold-start boot.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    meta_before = _wait_for_first_ensure(page)
    assert meta_before and meta_before.get("sha")
    sha_before = meta_before["sha"]

    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )
    fake_server_sha = "f" * 64
    # Default mode (no `mode` arg) coerces to 'install-only'; explicit
    # mode='install-only' is the same. Either way: no fetch, no refresh.
    for mode_arg in (None, "install-only"):
        if mode_arg is None:
            result = page.evaluate(
                "(sha) => window.__dataProvider._ensureFellowsDb({ serverSha: sha })",
                fake_server_sha,
            )
        else:
            result = page.evaluate(
                "(args) => window.__dataProvider._ensureFellowsDb(args)",
                {"serverSha": fake_server_sha, "mode": mode_arg},
            )
        assert result.get("refreshed") is False, (
            f"install-only with SHA mismatch must NOT refresh "
            f"(mode={mode_arg!r}); got result={result}"
        )
        assert result["meta"]["sha"] == sha_before, (
            f"install-only no-op must leave meta.sha unchanged; "
            f"before={sha_before} after={result['meta']['sha']}"
        )
    fetched = [r for r in requests if r.endswith("/fellows.db")]
    assert len(fetched) == 0, (
        f"install-only must produce zero GET /fellows.db requests "
        f"regardless of SHA; got {fetched}"
    )


def test_failed_refresh_preserves_previous_db_and_records_failure(
    standalone_page, base_url_fixture
):
    """When a refresh fails, the previously live fellows.db stays open and
    `meta.last_failure_*` records what went wrong. Directory keeps working."""
    page = standalone_page

    # Cold-start boot to populate fellows.db.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    meta_before = _wait_for_first_ensure(page)
    assert meta_before and meta_before.get("sha")
    sha_before = meta_before["sha"]

    # Make /fellows.db return 503 for the next refresh attempt. page.route
    # intercepts the worker's fetch (same browser context) and lets us
    # simulate a server-side outage.
    def fail_fellows_db(route):
        route.fulfill(status=503, body=b"Service Unavailable")

    page.route(re.compile(r".*/fellows\.db$"), fail_fellows_db)
    try:
        # Drive a refresh attempt. SHA differs → worker tries to fetch →
        # 503 → throws fellows_db_fetch_http. We catch on the JS side so
        # the test sees the error shape, not Playwright's generic
        # "evaluate threw" wrapping.
        outcome = page.evaluate(
            """
            async () => {
              try {
                const res = await window.__dataProvider._ensureFellowsDb({
                  serverSha: 'f'.repeat(64),
                  mode: 'refresh'
                });
                return { ok: true, res };
              } catch (e) {
                return {
                  ok: false,
                  message: String(e && e.message || e),
                  code: e && e.code || null,
                  httpStatus: e && e.httpStatus || null,
                  meta: e && e.meta || null
                };
              }
            }
            """
        )
    finally:
        page.unroute(re.compile(r".*/fellows\.db$"))

    assert outcome["ok"] is False, f"503 response should reject; got {outcome}"
    assert outcome["httpStatus"] == 503
    assert outcome["code"] == "fellows_db_fetch_http"
    failed_meta = outcome["meta"]
    assert failed_meta and failed_meta.get("last_failure_at"), (
        f"failure must be recorded in meta; got {failed_meta}"
    )
    assert "503" in (failed_meta.get("last_failure_reason") or ""), (
        f"failure reason should mention HTTP 503; got {failed_meta.get('last_failure_reason')!r}"
    )
    # Crucially: the previously live SHA is still recorded (not wiped).
    # The previous bytes are still readable — directory still works.
    assert failed_meta.get("sha") == sha_before, (
        f"meta.sha must remain the previous value on failure; "
        f"before={sha_before} after_failure={failed_meta.get('sha')}"
    )
    # Sanity: getList still returns rows from the cached fellows.db.
    rows = page.evaluate("() => window.__dataProvider.getList()")
    assert isinstance(rows, list) and len(rows) > 0, (
        f"directory must still render after a failed refresh; got {len(rows) if isinstance(rows, list) else rows}"
    )


def test_relationships_restore_does_not_refetch_fellows_db(
    folder_attached_page, base_url_fixture
):
    """Restoring a relationships.db backup must not desync fellows.db
    freshness — invariant L8 in the local-first worker plan.

    Boots with a verified folder attached (``folder_attached_page``): under the
    capability gate, createGroup + importRelationshipsBytes are durable-write
    ops, refused off-folder at both the page and the worker (#244/#252), so the
    restore round-trip this test needs requires a folder. fellows.db freshness
    (the thing under test) is independent of the relationships folder.

    The whole reason `fellows.db.meta.json` lives at the OPFS root
    (sibling of the SAH-pool dir, not inside relationships.settings) is
    so a relationships.db swap can't accidentally wipe or invalidate
    the fellows.db freshness signal. This pins that decoupling: after
    a real importRelationshipsBytes round-trip, a reload must produce
    zero GET /fellows.db requests because meta.sha still matches.
    """
    page = folder_attached_page

    # Cold-start boot to populate fellows.db + record its sha in meta.
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    meta_before = _wait_for_first_ensure(page)
    assert meta_before and meta_before.get("sha"), (
        f"first boot should populate meta.sha; got {meta_before}"
    )
    sha_before = meta_before["sha"]

    # Capture pristine relationships.db bytes, mutate, then restore — all
    # inside one page.evaluate so the Uint8Array stays in the same JS
    # context. Mutation is what proves the import actually swapped the
    # DB; if importRelationshipsBytes silently no-op'd, the test would
    # still see groupsAfter > 0 and fail loudly.
    restore_outcome = page.evaluate(
        """
        async () => {
          const dp = window.__dataProvider;
          // Drain reconcileHasEmailFilterOnBoot before exporting so the
          // captured bytes reflect a settled relationships.db. Same
          // reasoning as conftest.py's wipe_relationships helper.
          for (let i = 0; i < 20; i++) {
            const probe = await dp.getSetting('has_email_only');
            if (probe === '0' || probe === '1') break;
            await new Promise((r) => setTimeout(r, 50));
          }
          const originalBytes = await dp.exportRelationshipsBytes();
          await dp.createGroup({
            name: 'phase3-decouple-canary',
            note: '',
            fellow_record_ids: []
          });
          const groupsBefore = await dp.listGroups();
          const importResult = await dp.importRelationshipsBytes(originalBytes);
          const groupsAfter = await dp.listGroups();
          return {
            groupsBefore: (groupsBefore || []).length,
            groupsAfter: (groupsAfter || []).length,
            preRestoreSnapshot: importResult && importResult.preRestoreSnapshot
              ? true
              : false
          };
        }
        """
    )
    assert restore_outcome["groupsBefore"] >= 1, (
        f"createGroup mutation should be visible before the restore; "
        f"got {restore_outcome}"
    )
    assert restore_outcome["groupsAfter"] == 0, (
        f"importRelationshipsBytes must replace the live DB with the "
        f"pristine bytes (canary group should be gone); got {restore_outcome}"
    )
    assert restore_outcome["preRestoreSnapshot"], (
        f"import path should snapshot the pre-restore DB; got {restore_outcome}"
    )

    # Now reload. The relationships.db restore is committed to OPFS; on
    # next boot the worker re-reads fellows.db.meta.json untouched and
    # the SHA-keyed gate must skip the fetch.
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if req.url.endswith("/fellows.db") else None,
    )
    page.reload(wait_until="domcontentloaded")
    meta_after = _wait_for_first_ensure(page)

    assert meta_after and meta_after.get("sha") == sha_before, (
        f"meta.sha must survive a relationships.db restore unchanged: "
        f"before={sha_before} after_restore_reload={meta_after and meta_after.get('sha')}"
    )
    fetched = [r for r in requests if r.endswith("/fellows.db")]
    assert len(fetched) == 0, (
        f"a relationships.db restore must not trigger /fellows.db re-fetch "
        f"on next boot; got {fetched}"
    )
