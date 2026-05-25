"""E2E: per-install codename + browser/OS/install-date identity.

The codename is generated on first launch, persisted in localStorage
under `fellows_install_identity`, and surfaced in `document.title`,
the About page, and the diagnostics block (and therefore the bug
report). The goal is to let a user with multiple installs on the
same device (Safari + Chrome on macOS, multiple Chrome profiles,
etc.) tell instances apart.

These tests pin the visible contract:

  - First launch persists an identity object with `codename`,
    `browser`, `os`, `installedAt`.
  - `document.title` includes ` · <codename>` so window/tab chrome
    shows it.
  - About page renders "This install: <codename>" with a
    "(What's this?)" link to the users-manual section.
  - About page user-guide link is relabeled "Help from the user
    manual".
  - Diagnostics include codename + browser/OS + install timestamp
    (so the in-app *Report a bug* dialog picks them up).
  - Reload keeps the same codename — it does not regenerate per
    session.
"""
from __future__ import annotations

import re

from playwright.sync_api import expect


CODENAME_PATTERN = re.compile(r"^[a-z]+-[a-z]+-[a-z]+$")
ISO_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def _boot_to_directory(page, base_url: str) -> None:
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )


def _read_identity(page) -> dict:
    return page.evaluate(
        """
        () => {
          const raw = localStorage.getItem('fellows_install_identity');
          return raw ? JSON.parse(raw) : null;
        }
        """
    )


def test_codename_generated_and_persisted_on_first_launch(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_to_directory(page, base_url_fixture)

    identity = _read_identity(page)
    assert identity is not None, "first launch should persist an install identity"
    assert CODENAME_PATTERN.match(identity["codename"]), (
        f"codename {identity['codename']!r} should match {CODENAME_PATTERN.pattern}"
    )
    # Browser/OS detection is best-effort — accept the values the helper can
    # produce, including Unknown for headless/exotic UAs.
    assert identity["browser"] in {
        "Chrome", "Edge", "Firefox", "Safari", "Opera", "Unknown",
    }
    assert identity["os"] in {
        "macOS", "Windows", "Linux", "Android", "iOS", "Unknown",
    }
    assert ISO_PREFIX.match(identity["installedAt"]), (
        f"installedAt {identity['installedAt']!r} should be an ISO timestamp"
    )


def test_codename_persists_across_reload(standalone_page, base_url_fixture):
    """Codename lives in localStorage so it survives reload. The reload
    intentionally does NOT wait for the worker — chromium's OPFS lock
    handoff between the old worker and the new one is racy enough that
    we'd flake on the wait. The identity read only needs localStorage,
    which is available as soon as the new page document loads.
    """
    page = standalone_page
    _boot_to_directory(page, base_url_fixture)
    first = _read_identity(page)["codename"]

    page.reload(wait_until="domcontentloaded")
    # Wait for app.js to have set document.title — that's the cheapest
    # post-load signal that the install-identity init has run.
    page.wait_for_function(
        f"() => document.title.indexOf(' · {first}') !== -1",
        timeout=10000,
    )
    second = _read_identity(page)["codename"]
    assert first == second, "codename must not regenerate on reload"


def test_codename_appears_in_document_title(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_to_directory(page, base_url_fixture)
    codename = _read_identity(page)["codename"]
    title = page.title()
    assert codename in title, f"title {title!r} should include codename"
    assert " · " in title, f"title {title!r} should include separator"
    assert title.startswith("EHF Fellows Directory"), (
        f"title {title!r} should preserve the base app name"
    )


def test_codename_appears_on_about_page(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_to_directory(page, base_url_fixture)
    codename = _read_identity(page)["codename"]

    page.evaluate("location.hash = '#/about'")
    page.wait_for_selector(".about-install-name-inline", timeout=10000)
    install_p = page.locator(".about-install-name-inline")
    expect(install_p).to_contain_text("This install:")
    expect(install_p).to_contain_text(codename)
    # "(What's this?)" links to the users-manual install-name anchor.
    expect(install_p.locator("a")).to_have_attribute(
        "href",
        re.compile(r"users_manual\.md#install-name$"),
    )


def test_about_page_help_link_relabeled(standalone_page, base_url_fixture):
    page = standalone_page
    _boot_to_directory(page, base_url_fixture)
    page.evaluate("location.hash = '#/about'")
    page.wait_for_selector(".about-users-manual", timeout=10000)
    link = page.locator(".about-users-manual a")
    expect(link).to_have_text("Help from the user manual")


def test_codename_in_diagnostics_output(standalone_page, base_url_fixture):
    """Diagnostics output is what `Report a bug` ships — codename should
    flow in automatically so the maintainer can join the report to a
    specific install.
    """
    page = standalone_page
    page.goto(base_url_fixture + "/?diag=1", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )

    text = page.evaluate(
        """
        async () => {
          const deadline = Date.now() + 10000;
          while (Date.now() < deadline) {
            const pre = document.getElementById('diag-pre');
            const t = pre ? (pre.textContent || '') : '';
            if (t.length > 1000) return t;
            await new Promise((r) => setTimeout(r, 100));
          }
          throw new Error('diag did not populate within 10s');
        }
        """
    )
    codename = _read_identity(page)["codename"]
    assert f"install codename: {codename}" in text
    assert "install detected browser/OS:" in text
    assert "install first launched (ISO):" in text
