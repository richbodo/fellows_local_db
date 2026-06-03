"""Negative e2e for CST-PWA-SANDBOX-SEALED (Tier-2 security invariant).

The constraint: OPFS is an origin-scoped sandbox, so the private store is
invisible to the user's file manager and unreadable by their other tools
(MCP servers, backups, CLIs). A verified data folder dissolves the boundary —
`relationships.db` becomes a real file the private MCP server reads directly.

The honest handling fellows ships (see docs/Architecture.md § Constraint
attestation, and the maintainer decision recorded 2026-06-03):

  - **Off-folder there is no folder-resident private store** for an external
    tool to read. The durable-write guard (PR #244) means no canonical
    `relationships.db` exists off-folder; the OPFS slot stays sealed and
    invisible. The *private* MCP bundle therefore has nothing live to point
    at — only a user-driven `.db` export bridges it.
  - The Claude Desktop setup flow does **not** hide MCP off-folder
    (`shared_data_ops` legitimately reads the on-device `fellows.db`), but it
    **honestly warns** that the private bundle needs a connected folder.
  - With a folder attached the boundary dissolves and the warning is gone.

This file pins those facts. It is the negative-test half the attestation row
was missing (it previously cited only a positive "folder-mode MCP e2e").

Companion: tests/e2e/test_private_data_enforcement.py (no durable private write
off-folder — the data-layer fact this UI surface reflects).
"""
from __future__ import annotations

from playwright.sync_api import expect


def _boot_off_folder_to_settings(page, base_url: str) -> None:
    """Boot browse-only (no folder), wait for the two-phase load to settle,
    then open Settings. Mirrors test_mcpb_settings._boot_to_settings but
    asserts the browse-only tier so a regression that silently enabled
    private data here would fail loudly rather than pass vacuously."""
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    page.wait_for_function(
        "() => window.__bootMarks && window.__bootMarks.get_full_done != null",
        timeout=15000,
    )
    # Confirm the gate is genuinely browse-only — the precondition that makes
    # this a real SANDBOX-SEALED test rather than a vacuous one.
    page.wait_for_function(
        "() => window.__privateDataTier "
        "&& window.__privateDataTier.indexOf('browse-only') === 0",
        timeout=10000,
    )
    page.evaluate("location.hash = '#/settings'")
    page.wait_for_selector("#settings-mcpb-section", timeout=10000)


def test_no_folder_resident_private_store_off_folder(standalone_page, base_url_fixture):
    """The data-layer fact the constraint rests on: off-folder the folder
    controller reports no live handle, so there is NO real file an external
    tool (the private MCP server) could read. The store stays inside the OPFS
    sandbox — sealed and invisible."""
    page = standalone_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.__dataProvider && window.__dataProvider.kind === 'worker'",
        timeout=15000,
    )
    state = page.evaluate(
        "async () => { try { return await window.__folderController.getState(); }"
        " catch (e) { return { error: String(e) }; } }"
    )
    assert state.get("hasHandle") is False, (
        "off-folder must expose no folder-resident private store for an "
        f"external/MCP reader; getState()={state}"
    )
    # And the gate agrees: browse-only, no durable private store.
    tier = page.evaluate("() => window.__privateDataTier")
    assert tier and tier.startswith("browse-only"), tier


def test_mcp_setup_warns_no_folder_off_folder(standalone_page, base_url_fixture):
    """Honest signal (not a silent gap): opening the Claude Desktop setup
    preamble off-folder surfaces the folder warning, telling the user the
    private bundle needs a connected folder. We do NOT assert the section is
    hidden — `shared_data_ops` reads `fellows.db` and stays useful off-folder
    by design; what's bounded off-folder is the *private* store's external
    readability, which the warning names."""
    page = standalone_page
    _boot_off_folder_to_settings(page, base_url_fixture)
    page.click("#settings-mcpb-setup")
    expect(page.locator("#settings-mcpb-preamble-dialog")).to_be_visible()
    warning = page.locator("#settings-mcpb-preamble-folder-warning")
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("private data folder")


def test_mcp_folder_warning_hidden_when_folder_attached(folder_attached_page, base_url_fixture):
    """Positive control / the Solved-on-chromium half: with a verified folder
    attached the sandbox boundary dissolves — `relationships.db` is a real
    file the private MCP server reads — so the folder warning is gone."""
    page = folder_attached_page
    page.evaluate("location.hash = '#/settings'")
    page.wait_for_selector("#settings-mcpb-section", timeout=10000)
    # Sanity: the gate really did flip open (folder verified).
    assert page.evaluate(
        "() => !document.body.classList.contains('no-private-data')"
    ), "folder_attached_page should have flipped privateDataEnabled() true"
    page.click("#settings-mcpb-setup")
    expect(page.locator("#settings-mcpb-preamble-dialog")).to_be_visible()
    expect(page.locator("#settings-mcpb-preamble-folder-warning")).to_be_hidden()
