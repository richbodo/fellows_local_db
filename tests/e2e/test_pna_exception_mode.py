"""E2E for the PNA "exception" / non-PNA-mode handler.

Wiring the directory to a cloud LLM (Claude Desktop) is modeled as a
named, stable-ID'd *exception* (``EX-CLOUD-LLM``) that takes the app out
of PNA (local-only) mode. Accepting the consent gate RAISES the
exception; the handler is the persistent "Going rogue — not a PNA"
banner, the in-app ``#/exception/<id>`` explainer, and a reversible
"Return to PNA mode" control.

Runtime state is mirrored onto ``<body>`` as ``data-pna-mode`` /
``data-pna-exceptions`` (the machine-readable marker a conformance check
can catch) and persisted on ``localStorage[fellows_mcpb_setup]``.

See plans/pna_toolkit_exceptions_contribution.md.
"""
from __future__ import annotations

from playwright.sync_api import expect


def _boot_to_settings(page, base_url: str) -> None:
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=15000,
    )
    page.evaluate("location.hash = '#/settings'")
    page.wait_for_selector("#settings-mcpb-section", timeout=10000)


_MCPB_CLICK_INTERCEPT = """
window.__capturedMcpbClicks = [];
(function () {
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const href = this.getAttribute('href') || '';
    if (href.indexOf('/mcpb/') !== -1) {
      window.__capturedMcpbClicks.push(href);
      return;
    }
    return origClick.call(this);
  };
})();
"""


def _enter_non_pna_mode(page, base_url: str) -> None:
    """Boot to Settings, run the integration setup, scroll+accept the
    consent gate, and Continue — which records consent and raises the
    EX-CLOUD-LLM exception. Downloads are swallowed by the anchor
    intercept; we only care about the resulting mode state.
    """
    page.add_init_script(_MCPB_CLICK_INTERCEPT)
    _boot_to_settings(page, base_url)
    page.click("#settings-mcpb-setup")
    page.evaluate(
        """() => {
          const a = document.getElementById('settings-mcpb-agreement');
          if (a) { a.scrollTop = a.scrollHeight; a.dispatchEvent(new Event('scroll')); }
        }"""
    )
    page.check("#settings-mcpb-consent-checkbox")
    page.click("#settings-mcpb-preamble-continue")
    page.wait_for_function(
        "() => document.body.getAttribute('data-pna-mode') === 'non-pna'",
        timeout=5000,
    )


class TestPnaExceptionMode:
    def test_accepting_consent_enters_non_pna_mode_and_shows_banner(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        _enter_non_pna_mode(page, base_url_fixture)
        # Body carries the machine-readable markers.
        assert page.evaluate("document.body.getAttribute('data-pna-mode')") == "non-pna"
        assert "EX-CLOUD-LLM" in (
            page.evaluate("document.body.getAttribute('data-pna-exceptions')") or ""
        )
        # The banner is visible and names/links the exception.
        expect(page.locator("#not-a-pna-banner")).to_be_visible()
        expect(page.locator("#not-a-pna-banner")).to_contain_text("not a PNA")
        assert (
            page.get_attribute("#not-a-pna-banner-link", "href")
            == "#/exception/EX-CLOUD-LLM"
        )

    def test_dismiss_hides_banner_but_stays_non_pna(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        _enter_non_pna_mode(page, base_url_fixture)
        page.click("#not-a-pna-dismiss")
        expect(page.locator("#not-a-pna-banner")).to_be_hidden()
        # Dismissal acknowledges; it MUST NOT clear the exception.
        assert page.evaluate("document.body.getAttribute('data-pna-mode')") == "non-pna"
        import json as _json

        raw = page.evaluate("localStorage.getItem('fellows_mcpb_setup')")
        assert _json.loads(raw).get("consentAt"), "exception still active"
        # Banner stays hidden across a reload (dismissal persists).
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#not-a-pna-banner", state="attached", timeout=10000)
        expect(page.locator("#not-a-pna-banner")).to_be_hidden()

    def test_banner_links_to_active_explainer(self, standalone_page, base_url_fixture):
        page = standalone_page
        _enter_non_pna_mode(page, base_url_fixture)
        page.click("#not-a-pna-banner-link")
        page.wait_for_function(
            "() => location.hash === '#/exception/EX-CLOUD-LLM'", timeout=5000
        )
        explainer = page.locator(".exception-page")
        expect(explainer).to_be_visible()
        expect(explainer).to_contain_text("Active now")
        expect(explainer).to_contain_text("reversible")
        # The honesty guard: returning to PNA mode does not recall sent data.
        expect(explainer).to_contain_text("does not recall data already sent")

    def test_return_to_pna_mode_from_explainer_clears_exception(
        self, standalone_page, base_url_fixture
    ):
        page = standalone_page
        _enter_non_pna_mode(page, base_url_fixture)
        page.evaluate("location.hash = '#/exception/EX-CLOUD-LLM'")
        page.wait_for_selector("#exception-return-pna", timeout=5000)
        page.click("#exception-return-pna")
        page.wait_for_function(
            "() => document.body.getAttribute('data-pna-mode') === 'pna'", timeout=5000
        )
        # Banner gone, exception cleared from storage.
        expect(page.locator("#not-a-pna-banner")).to_be_hidden()
        assert not page.evaluate("document.body.getAttribute('data-pna-exceptions')")
        import json as _json

        raw = page.evaluate("localStorage.getItem('fellows_mcpb_setup')")
        assert _json.loads(raw).get("consentAt") is None, "consent cleared"
        # The page re-renders to the inactive state.
        expect(page.locator(".exception-page")).to_contain_text("Not currently active")

    def test_return_to_pna_mode_from_settings(self, standalone_page, base_url_fixture):
        page = standalone_page
        _enter_non_pna_mode(page, base_url_fixture)
        # The Settings non-PNA row is visible while the exception is active.
        expect(page.locator("#settings-mcpb-pna-mode")).to_be_visible()
        page.click("#settings-mcpb-return-pna")
        page.wait_for_function(
            "() => document.body.getAttribute('data-pna-mode') === 'pna'", timeout=5000
        )
        expect(page.locator("#settings-mcpb-pna-mode")).to_be_hidden()
        expect(page.locator("#not-a-pna-banner")).to_be_hidden()

    def test_explainer_route_when_inactive(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
            timeout=15000,
        )
        page.evaluate("location.hash = '#/exception/EX-CLOUD-LLM'")
        page.wait_for_selector(".exception-page", timeout=5000)
        expect(page.locator(".exception-page")).to_contain_text("Not currently active")
        # No exception active → no banner, body in PNA mode.
        assert page.evaluate("document.body.getAttribute('data-pna-mode')") == "pna"
        expect(page.locator("#not-a-pna-banner")).to_be_hidden()

    def test_unknown_exception_route(self, standalone_page, base_url_fixture):
        page = standalone_page
        page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
            timeout=15000,
        )
        page.evaluate("location.hash = '#/exception/EX-BOGUS'")
        page.wait_for_selector(".exception-page", timeout=5000)
        expect(page.locator(".exception-page")).to_contain_text("Unknown exception")
