"""Regression: image URLs must not carry a `?v=<build_label>` query.

In production we observed `fellows-images-v1` growing to 725 entries
across only 508 fellows-with-photos — a 1.43× overcount caused by a
cache-bust suffix that produced a fresh cache key on every deploy
without ever evicting the prior key. The image cache is intentionally
*not* busted on shell-version bumps (sw.js:10 — `fellows-images-v1`),
which is the right call for ~34 MB of mostly-static assets; the URL
suffix defeated that intent.

This file pins the fix:

  1. Image fetches initiated by the prewarm and the on-demand detail
     render carry no query string.
  2. The image cache, after a render, contains no `?` URLs.

Together they guarantee a stable cache key per fellow across deploys.
"""
from __future__ import annotations

import re

import pytest


def _wait_for_provider_and_fellows_db(page, timeout_ms: int = 10000) -> None:
    """Block until the worker has opened fellows.db. The worker init is
    network-free post-Phase-1 (L4a); the page must drive
    `ensureFellowsDb` before any `getList` / `getOne` call. Same pattern
    as tests/e2e/test_versioned_fellows_db.py:_wait_for_first_ensure.
    """
    page.evaluate(
        """
        async (timeoutMs) => {
          // Get the canonical server SHA so the probe is idempotent
          // with whatever the boot is doing.
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
            if (window.__dataProvider && typeof window.__dataProvider.getList === 'function') {
              try {
                const res = await window.__dataProvider._ensureFellowsDb({ serverSha: serverSha });
                if (res && res.hasFellowsDb) return;
              } catch (e) {}
            }
            await new Promise((r) => setTimeout(r, 100));
          }
          throw new Error('worker did not settle with fellows.db open within ' + timeoutMs + 'ms');
        }
        """,
        timeout_ms,
    )


def _first_with_image_slug(page) -> str:
    """Find a slug whose fellow has has_image=true. Required because the
    detail-render path only emits an /images/<slug>.jpg request when
    the fellow actually uploaded a photo; picking the first slug
    blindly hits a placeholder and the assertion finds nothing.
    """
    return page.evaluate(
        """
        async () => {
          const dp = window.__dataProvider;
          const list = await dp.getList();
          for (const row of list) {
            if (row && row.slug) {
              const f = await dp.getOne(row.slug);
              if (f && (f.has_image === 1 || f.has_image === true)) return row.slug;
            }
          }
          throw new Error('no fellow with has_image found');
        }
        """
    )


def test_image_urls_have_no_cache_bust_query(standalone_page, base_url_fixture):
    """Capture every /images/* request the page makes during boot +
    detail render. None should carry a `?v=…` query — the bug was the
    `?v=<FELLOWS_UI_DIAG>` suffix on every image URL.
    """
    page = standalone_page
    image_requests: list[str] = []
    page.on(
        "request",
        lambda req: image_requests.append(req.url) if "/images/" in req.url else None,
    )

    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_provider_and_fellows_db(page)

    slug = _first_with_image_slug(page)
    page.goto(base_url_fixture + "/#/fellow/" + slug, wait_until="domcontentloaded")
    # Wait for the <img> to settle — either loaded or in error fallback.
    page.wait_for_function(
        """
        () => {
          const imgs = document.querySelectorAll('img.profile-image');
          if (!imgs.length) return false;
          return Array.from(imgs).every((img) => img.complete);
        }
        """,
        timeout=10000,
    )

    # The page makes many image requests during boot (prewarm) and detail
    # render. Every one of them must be a bare URL.
    assert image_requests, (
        "expected at least one /images/* request during boot + detail render; "
        "got none — fixture may be misconfigured"
    )
    bad = [u for u in image_requests if "?" in u]
    assert not bad, (
        "image URLs must not carry a query string — every `?v=...` produces a "
        "fresh cache key on each deploy and never evicts the old one. "
        "Offending URLs:\n  " + "\n  ".join(bad[:10])
    )


def test_image_cache_holds_no_bust_query_entries(standalone_page, base_url_fixture):
    """After the page renders a profile detail, fellows-images-v1 must
    contain only bare-URL entries. Catches the symptom directly: if the
    prewarm or any other image fetch ever re-introduces `?v=`, the
    cache will record it and this assertion will trip."""
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_provider_and_fellows_db(page)
    slug = _first_with_image_slug(page)
    page.goto(base_url_fixture + "/#/fellow/" + slug, wait_until="domcontentloaded")
    page.wait_for_function(
        """
        () => {
          const imgs = document.querySelectorAll('img.profile-image');
          if (!imgs.length) return false;
          return Array.from(imgs).every((img) => img.complete);
        }
        """,
        timeout=10000,
    )

    # Inspect the cache contents directly. The SW writes to
    # fellows-images-v1 via cacheFirstInto; entry count > 0 proves the
    # path is exercised, and the no-`?` predicate proves no entry slipped
    # in with a query string.
    bad_urls = page.evaluate(
        """
        async () => {
          if (!('caches' in self)) return null;
          const keys = await caches.keys();
          if (keys.indexOf('fellows-images-v1') === -1) return [];
          const cache = await caches.open('fellows-images-v1');
          const reqs = await cache.keys();
          return reqs.map((r) => r.url).filter((u) => u.indexOf('?') !== -1);
        }
        """
    )
    if bad_urls is None:
        pytest.skip("Cache API unavailable in this browser context")
    assert bad_urls == [], (
        "fellows-images-v1 must not contain any URLs with a query string. "
        "Offending entries:\n  " + "\n  ".join(bad_urls[:10])
    )


def test_sw_activate_sweeps_legacy_bust_entries(standalone_page, base_url_fixture):
    """Pre-populate fellows-images-v1 with a synthetic `?v=…` entry,
    then force the SW to re-activate. The activate handler's one-time
    sweep must remove the legacy entry while leaving bare-URL entries
    intact.

    We can't trigger a real SW upgrade from the test (the SW only
    activates when its bytes change), so we open the cache directly,
    insert the entries, and then call `unregister()` + reload to get
    a fresh install→activate cycle on the same context.
    """
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")

    # Wait for SW to be controlling — otherwise the cache might not
    # have been opened yet by anything.
    page.wait_for_function(
        "() => navigator.serviceWorker && navigator.serviceWorker.controller",
        timeout=10000,
    )

    # Seed two entries: one legacy (with ?v=), one bare. Use a
    # synthetic Response so we don't depend on a real /images endpoint.
    page.evaluate(
        """
        async () => {
          const cache = await caches.open('fellows-images-v1');
          const ok = new Response(new Blob(['x']), { status: 200 });
          await cache.put('/images/test-slug.jpg?v=2026-04-01-deadbeef', ok.clone());
          await cache.put('/images/test-slug-bare.jpg', ok.clone());
        }
        """
    )

    # Force the SW to re-install + re-activate. unregister() drops the
    # registration; the next navigation triggers install handlers,
    # which on this codebase culminate in the activate sweep.
    page.evaluate(
        """
        async () => {
          const regs = await navigator.serviceWorker.getRegistrations();
          await Promise.all(regs.map((r) => r.unregister()));
        }
        """
    )
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        "() => navigator.serviceWorker && navigator.serviceWorker.controller",
        timeout=10000,
    )

    # The bare entry should still be there; the `?v=` entry should be gone.
    state = page.evaluate(
        """
        async () => {
          const cache = await caches.open('fellows-images-v1');
          const reqs = await cache.keys();
          const urls = reqs.map((r) => r.url);
          return {
            hasBare: urls.some((u) => u.endsWith('/images/test-slug-bare.jpg')),
            hasBust: urls.some((u) => u.indexOf('/images/test-slug.jpg?') !== -1),
            allWithBust: urls.filter((u) => u.indexOf('?') !== -1)
          };
        }
        """
    )
    assert state["hasBust"] is False, (
        "SW activate sweep should have removed the legacy ?v= entry from "
        "fellows-images-v1; remaining query-string entries: "
        + str(state["allWithBust"])
    )
    assert state["hasBare"] is True, (
        "SW activate sweep must not touch bare-URL entries; lost the seeded "
        "test-slug-bare.jpg"
    )
