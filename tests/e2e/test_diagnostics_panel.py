"""E2E for Phase 4 of plans/local_first_worker_architecture.md.

Two things this file pins:

  1. The Diagnostics panel (`?diag=1`) renders every section the plan
     calls for: worker spawn + version handshake, OPFS inventory,
     `fellows.db.meta.json` block, persisted-storage state. All of it
     is RPC-derived — there is no main-thread `getDirectory` call
     during render.
  2. The legacy "You are online." / "You are offline." connection
     banner is gone. Post-cutover the app has only one mode (local),
     so the banner contradicted the desktop-app mental model.

These run against the dev server using the standalone-mode fixture,
so the directory boot path is exercised end-to-end. The diag panel's
`?diag=1` query auto-opens the panel and triggers `refresh()`, which
calls `collectDiagnosticsText()` — same code path the user gets when
they tap the diag toggle button.
"""
from __future__ import annotations

import re

import pytest


def _wait_for_diag_text(page, timeout_ms: int = 10000) -> str:
    """Wait until the diag <pre> has populated content. The panel renders
    asynchronously: `refresh()` does network probes, awaits worker RPCs,
    and only then writes the joined lines into <pre>. Polling against
    the textContent length is the simplest "it's done" signal — the
    final text is several KB, while a still-rendering panel is empty
    or very short.
    """
    return page.evaluate(
        """
        async (timeoutMs) => {
          const deadline = Date.now() + timeoutMs;
          while (Date.now() < deadline) {
            const pre = document.getElementById('diag-pre');
            const text = pre ? (pre.textContent || '') : '';
            // collectDiagnosticsText emits 80+ lines of dense info;
            // 1 KB is a safe floor for "render finished".
            if (text.length > 1000) return text;
            await new Promise((r) => setTimeout(r, 100));
          }
          throw new Error('diag panel did not populate within ' + timeoutMs + 'ms');
        }
        """,
        timeout_ms,
    )


def test_diag_panel_renders_all_phase4_sections(standalone_page, base_url_fixture):
    """Open `?diag=1` and confirm every Phase 4 section is present.

    Each section is identified by a stable substring from
    collectDiagnosticsText so the test fails loudly if a section is
    accidentally deleted in a future refactor.
    """
    page = standalone_page

    # Cold boot — populates fellows.db.meta.json so the meta block has
    # something real to render. Without an ensureFellowsDb call first
    # the meta is null and we'd only verify the cold-start branch.
    page.goto(base_url_fixture + "/?diag=1", wait_until="domcontentloaded")
    page.evaluate(
        """
        async () => {
          const deadline = Date.now() + 10000;
          while (Date.now() < deadline) {
            if (window.__dataProvider && window.__dataProvider.kind === 'worker') {
              try {
                const r = await fetch('/build-meta.json', { cache: 'no-store' });
                const meta = r.ok ? await r.json() : null;
                const sha = meta && typeof meta.fellows_db_sha === 'string'
                  ? meta.fellows_db_sha : null;
                const res = await window.__dataProvider._ensureFellowsDb({ serverSha: sha });
                if (res && res.hasFellowsDb) return;
              } catch (e) {}
            }
            await new Promise((r) => setTimeout(r, 100));
          }
          throw new Error('worker did not resolve ensureFellowsDb within 10s');
        }
        """
    )

    # The `?diag=1` URL flag auto-opens + refreshes the panel on boot.
    # Refresh once more so the panel re-renders against the now-warm
    # meta (the auto-open fires before our ensureFellowsDb above).
    page.evaluate(
        """
        async () => {
          const btn = document.getElementById('diag-refresh');
          if (btn) btn.click();
        }
        """
    )
    text = _wait_for_diag_text(page)

    # 1. Worker spawn + version handshake.
    assert "worker spawn:" in text, f"missing worker spawn line; text head:\n{text[:500]}"
    assert "worker version compatibility:" in text, "missing version compatibility line"
    assert "worker capabilities:" in text, "missing worker capabilities line"

    # 2. OPFS inventory (RPC-derived from the worker, not getDirectory on main).
    assert "OPFS root entries (worker view):" in text, "missing OPFS root inventory"

    # 3. fellows.db.meta.json block — Phase 4's primary new section.
    assert "fellows.db.meta.json (worker view):" in text, "missing fellows.db.meta.json section"
    # After a successful ensureFellowsDb, sha + fetched_at must be populated.
    # The render uses `(unset)` / `(never)` placeholders when fields are missing —
    # we want the populated path here.
    assert re.search(r"sha:\s+[0-9a-f]{64}", text), (
        f"meta.sha should render as a 64-char hex digest after a successful "
        f"ensureFellowsDb; got snippet:\n{text}"
    )
    assert re.search(r"fetched_at:\s+\d{4}-\d{2}-\d{2}T", text), (
        "meta.fetched_at should render an ISO timestamp after a successful "
        "ensureFellowsDb"
    )

    # 4. persisted-storage state. May be null in a Playwright headless context
    # (no user gesture for a quota prompt), but the line must render either way.
    assert "navigator.storage.persist():" in text, "missing persist-storage line"

    # 5. Build label of the worker bundle (informational).
    assert re.search(r"build=\S+", text), "missing worker build label"


def test_no_main_thread_opfs_during_diag_render(standalone_page, base_url_fixture):
    """Phase 4 acceptance: the panel's render must be RPC-derived. The
    main thread must not call `navigator.storage.getDirectory` while
    populating the diag pre — that would re-introduce the dual-OPFS-owner
    bug Phase 1 cut over to fix.

    We instrument `navigator.storage.getDirectory` *before* navigation
    so any call from page-side JS during boot or diag refresh
    increments a counter we can read after the panel finishes rendering.
    The worker's getDirectory call happens in a different realm and is
    not affected.
    """
    page = standalone_page
    page.add_init_script(
        """
        (() => {
          if (!navigator.storage || !navigator.storage.getDirectory) return;
          const orig = navigator.storage.getDirectory.bind(navigator.storage);
          let count = 0;
          navigator.storage.getDirectory = function () {
            count++;
            return orig.apply(this, arguments);
          };
          Object.defineProperty(window, '__getDirectoryCallCount', {
            get: function () { return count; }
          });
        })();
        """
    )
    page.goto(base_url_fixture + "/?diag=1", wait_until="domcontentloaded")
    _wait_for_diag_text(page)

    count = page.evaluate("() => window.__getDirectoryCallCount || 0")
    assert count == 0, (
        f"main-thread navigator.storage.getDirectory was called {count} time(s) "
        f"during boot + diag render — Phase 1 invariant L1 says the worker is "
        f"the only OPFS opener"
    )


def test_connection_banner_is_gone(standalone_page, base_url_fixture):
    """The legacy `#connection-banner` element ("You are online.") was
    leftover vocabulary from before the worker cutover. Phase 4 deletes
    it. Pin its absence so the element doesn't get accidentally
    re-introduced in a future copy/paste.
    """
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")

    # Explicit check: the element must not exist in the DOM.
    locator = page.locator("#connection-banner")
    assert locator.count() == 0, (
        "Phase 4 removed #connection-banner from the main UI; if you need to "
        "re-introduce a server-status indicator, the About page is the right "
        "place (see docs/users_manual.md and the renderLastUpdateCheck IIFE)."
    )

    # Defense in depth: the user-visible strings must not appear anywhere
    # on the page either, in case the element is reborn under a new id.
    body_text = page.evaluate("() => document.body.innerText || ''")
    assert "You are online." not in body_text
    assert "You are offline." not in body_text
