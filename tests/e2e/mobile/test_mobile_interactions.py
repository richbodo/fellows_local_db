"""Mobile interaction tests.

Drives real user flows at mobile viewports — taps, form submits,
sheet open/close, navigation. Catches the class of bug that
screenshot-only smoke tests miss ("button doesn't actually do
anything when tapped on a phone"). Parametrized across the device
matrix (Pixel 5 / iPhone 13 / narrow-360) via the existing
device_name fixture in conftest.

The headline test for the discovery PR is
``test_can_create_group_from_directory_route`` — it exercises the
mobile group-creation flow end to end and fails when the reported
bug (no path to the composer on mobile) is present.

Tests use the ``mobile_interaction_page`` fixture (full shim) or
``mobile_worker_data`` (when worker-RPC setup or assertion is
needed). Both live in ``conftest.py``.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect


def _wait_for_app_boot(page, timeout: int = 10000) -> None:
    page.locator("#loading").wait_for(state="hidden", timeout=timeout)
    page.wait_for_timeout(400)


# ===== Directory route =====================================================


def test_directory_loads_and_shows_fellow_names(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Directory at mobile should render a list of fellow names. Sanity
    check that the route boots cleanly at mobile viewports."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    rows = page.locator("#directory li.dir-row")
    assert rows.count() > 0, (
        f"no directory rows rendered at {device_name}"
    )
    first_link = rows.first.locator(".dir-link")
    expect(first_link).to_be_visible()
    name = first_link.text_content()
    assert name and name.strip(), (
        f"first directory row has no name text at {device_name}"
    )


def test_tap_fellow_name_navigates_to_detail(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Tapping a fellow's name should navigate to their detail page.
    The detail route must then render visible content."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    first_link = page.locator("#directory li.dir-row .dir-link").first
    expect(first_link).to_be_visible()
    first_link.click()
    page.wait_for_function(
        "() => window.location.hash.indexOf('#/fellow/') === 0",
        timeout=5000,
    )
    # The body picks up route-fellow once the route() handler runs.
    expect(page.locator("body")).to_have_class(
        re.compile(r"\broute-fellow\b"),
        timeout=3000,
    )
    # #detail is the main pane where the fellow's content renders.
    expect(page.locator("#detail")).to_be_visible()


# ===== Browse-only on phones (PR6 step 3) ==================================
#
# Groups, selection, and the composer have NO UI on a phone — private data
# is gated off (it lives in plans/private_data_capability_gate.md). These
# tests replace the former mobile group-creation flow tests (the rail-driven
# composer, FAB, and +/× markers) which guarded a path that PR6 removes.


def test_directory_rows_have_no_group_marker_on_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Phone directory rows are plain links — no +/× group marker (it's
    JS-skipped, not just CSS-hidden, so there's no dead tap target)."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    rows = page.locator("#directory li.dir-row")
    assert rows.count() > 0, f"no directory rows at {device_name}"
    assert page.locator("#directory li.dir-row .dir-mark").count() == 0, (
        f"group +/− marker still present on phone rows at {device_name}"
    )


def test_directory_row_links_to_fellow_with_chevron(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Each phone row links straight to the fellow and shows a trailing
    chevron affordance; tapping navigates to the detail route."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    first = page.locator("#directory li.dir-row").first
    link = first.locator(".dir-link")
    expect(link).to_be_visible()
    assert (link.get_attribute("href") or "").startswith("#/fellow/"), (
        f"row link does not target a fellow at {device_name}"
    )
    expect(first.locator(".dir-row__go")).to_have_count(1)
    link.click()
    page.wait_for_function(
        "() => location.hash.indexOf('#/fellow/') === 0", timeout=3000
    )


def test_no_composer_fab_or_rail_on_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """The selection FAB and composer rail never surface on a phone."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    expect(page.locator("#composer-fab")).to_be_hidden()
    expect(page.locator("#group-rail")).to_be_hidden()
    expect(page.locator("#bulk-select-bar")).to_be_hidden()


@pytest.mark.parametrize(
    "group_hash",
    ["#/groups", "#/groups/1", "#/groups/1/directory", "#/edit/1"],
)
def test_group_route_redirects_to_directory_on_phone(
    mobile_interaction_page, device_name, base_url_fixture, group_hash
):
    """Any group/edit route on a phone lands on the directory — there's no
    group UI to show, and no unlock (that's desktop-only)."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/" + group_hash, wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    page.wait_for_function("() => location.hash === '#/'", timeout=3000)
    expect(page.locator("#directory")).to_be_visible()


# ===== App-bar kebab retired on phones (PR6 step 5) ========================


def test_appbar_kebab_hidden_on_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """The tools kebab is retired on phones — its actions moved into
    Settings → Tools. The hamburger is the only appbar menu control."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    expect(page.locator("#appbar-kebab")).to_be_hidden()
    expect(page.locator("#appbar-hamburger")).to_be_visible()


# ===== Hamburger nav drawer (PR6 step 2) ===================================


def test_nav_drawer_opens_and_navigates(
    mobile_interaction_page, device_name, base_url_fixture
):
    """The appbar hamburger opens the nav drawer; tapping a destination
    navigates and closes it. On phones the tab strip is gone, so the
    drawer is the only nav."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)

    # The tab strip is retired on phones.
    expect(page.locator("#tabs")).to_be_hidden()

    hamburger = page.locator("#appbar-hamburger")
    expect(hamburger).to_be_visible(timeout=5000)
    drawer = page.locator("#nav-drawer")
    expect(drawer).to_be_hidden()

    hamburger.click()
    expect(drawer).to_be_visible(timeout=2000)
    assert hamburger.get_attribute("aria-expanded") == "true"
    # Build tag populated from the same source the About page uses.
    expect(page.locator("#nav-drawer-build")).to_contain_text("server")

    # Navigate to Settings via the drawer.
    page.locator('#nav-drawer .drawer-link[data-nav="settings"]').click()
    expect(drawer).to_be_hidden(timeout=2000)
    page.wait_for_function("() => location.hash.indexOf('#/settings') === 0", timeout=3000)
    assert hamburger.get_attribute("aria-expanded") == "false"


def test_nav_drawer_dismisses_via_scrim_and_close(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Scrim tap and the close (✕) button both dismiss the drawer."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    hamburger = page.locator("#appbar-hamburger")
    drawer = page.locator("#nav-drawer")

    # Close button.
    hamburger.click()
    expect(drawer).to_be_visible(timeout=2000)
    page.locator("#nav-drawer-close").click()
    expect(drawer).to_be_hidden(timeout=2000)

    # Scrim tap. The drawer covers the right ~80% of the full-screen
    # scrim, so click the exposed left strip rather than the center.
    hamburger.click()
    expect(drawer).to_be_visible(timeout=2000)
    page.locator("#nav-scrim").click(position={"x": 8, "y": 200})
    expect(drawer).to_be_hidden(timeout=2000)


# ===== About page (post-#205 two-button layout) ============================


def test_about_page_two_check_buttons_present(
    mobile_interaction_page, device_name, base_url_fixture
):
    """After #205, About has two explicit check buttons. Both must be
    visible and tappable on mobile."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    app_btn = page.locator("#about-check-app-update")
    data_btn = page.locator("#about-check-data-update")
    expect(app_btn).to_be_visible()
    expect(app_btn).to_have_text("Check for application updates")
    expect(data_btn).to_be_visible()
    expect(data_btn).to_have_text("Check for directory data updates")
    # The install codename moved inside the App row in #205; confirm
    # the inline element renders on mobile too.
    codename = page.locator(".about-install-name-inline")
    expect(codename).to_be_visible()


def test_about_check_application_updates_button_taps(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Tapping Check for application updates should run the check and
    populate the app-row status. We don't assert the specific result
    (depends on server build label) — only that the button is
    interactive at mobile widths and produces a status update."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/#/about", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    app_status = page.locator("#about-app-status")
    initial = app_status.text_content() or ""
    page.locator("#about-check-app-update").click()
    # Either the status text changes (most likely) or the button gets
    # relabeled. Wait for either.
    page.wait_for_function(
        f"() => document.getElementById('about-app-status').textContent !== {initial!r}"
        f" || document.getElementById('about-check-app-update').textContent !== 'Check for application updates'",
        timeout=5000,
    )


# ===== Reduced mobile Settings (PR6 step 5) ================================


def test_mobile_settings_reduced_to_app_info_and_tools(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Phone Settings shows App info + Tools only. The private-data
    surfaces — email field, folder section, download, restore, and the
    Claude-Desktop/MCPB section — are all gated off (browse-only)."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    _wait_for_app_boot(page)

    # Present: app-info stat lines + the four tool buttons.
    expect(page.locator(".settings-statlines")).to_have_count(1)
    for tool_id in (
        "#settings-phone-diagnostics",
        "#settings-phone-bug-report",
        "#settings-phone-clear-cache",
        "#settings-phone-reset",
    ):
        expect(page.locator(tool_id)).to_be_visible()

    # Absent: every private-data settings surface.
    for gone in (
        "#settings-self-email",
        "#settings-folder-section",
        "#settings-download-userdata",
        "#settings-restore-section",
        "#settings-mcpb-section",
    ):
        assert page.locator(gone).count() == 0, (
            f"{gone} should not render in phone Settings at {device_name}"
        )


def test_mobile_settings_diagnostics_tool_opens_panel(
    mobile_interaction_page, device_name, base_url_fixture
):
    """A Tools button proxies to the existing handler: tapping
    Diagnostics opens the diagnostics panel (the same as the retired
    kebab action did)."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/#/settings", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    expect(page.locator("#diag-panel")).to_be_hidden()
    page.locator("#settings-phone-diagnostics").click()
    expect(page.locator("#diag-panel")).to_be_visible(timeout=3000)


# ===== Fellow detail =======================================================


def test_groups_index_redirects_even_with_seeded_groups_on_phone(
    mobile_worker_data, device_name, base_url_fixture
):
    """Even when groups exist in the worker store, #/groups on a phone
    redirects to the directory — the groups index has no phone UI.

    (Replaces the former card-list test: groups are browse-only-gated
    off on phones, so there's no card list to render.)"""
    helper = mobile_worker_data
    helper.create_group(name="Mobile index card", fellow_record_ids=[])
    page = helper.page
    page.evaluate("location.hash = '#/groups'")
    _wait_for_app_boot(page)
    page.wait_for_function("() => location.hash === '#/'", timeout=3000)
    expect(page.locator("#directory")).to_be_visible()
    assert page.locator(".groups-card-list").count() == 0, (
        f"groups card list rendered on a phone at {device_name}"
    )


def test_fellow_detail_renders_useful_content(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Fellow detail route at mobile must render the fellow's name in
    the central pane. Sanity check for the route the user described as
    'looked okay' — guards the working state."""
    page = mobile_interaction_page
    page.goto(
        base_url_fixture + "/#/fellow/aaron_bird",
        wait_until="domcontentloaded",
    )
    _wait_for_app_boot(page)
    expect(page.locator("body")).to_have_class(
        re.compile(r"\broute-fellow\b"),
        timeout=3000,
    )
    detail = page.locator("#detail")
    expect(detail).to_be_visible()
    # The fellow's name should be in the detail pane.
    text = detail.text_content() or ""
    assert text.strip(), (
        f"#detail is empty on fellow-detail route at {device_name}"
    )


# ===== Fellow-detail Email/Call CTAs (PR6 step 4) ==========================


def test_fellow_detail_email_and_call_ctas_on_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """A fellow with both email and phone shows an Email (mailto, primary)
    CTA and a Call (tel, ghost) CTA near the top of the detail."""
    page = mobile_interaction_page
    # aaron_bird has both a contact email and a mobile number.
    page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    cta = page.locator("#detail .contact-cta")
    expect(cta).to_have_count(1)

    email_btn = page.locator("#detail .contact-cta__btn--primary")
    expect(email_btn).to_have_count(1)
    assert (email_btn.get_attribute("href") or "").startswith("mailto:"), (
        f"Email CTA is not a mailto link at {device_name}"
    )
    assert "Email" in (email_btn.inner_text() or ""), "Email CTA mislabeled"

    call_btn = page.locator("#detail .contact-cta__btn--ghost")
    expect(call_btn).to_have_count(1)
    assert (call_btn.get_attribute("href") or "").startswith("tel:"), (
        f"Call CTA is not a tel link at {device_name}"
    )


def test_fellow_detail_call_cta_absent_without_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """A fellow with email but no phone shows the Email CTA and no Call
    CTA (each button is guarded on its field)."""
    page = mobile_interaction_page
    # aaron_mcdonald has a contact email but no mobile number.
    page.goto(
        base_url_fixture + "/#/fellow/aaron_mcdonald", wait_until="domcontentloaded"
    )
    _wait_for_app_boot(page)
    expect(page.locator("#detail .contact-cta")).to_have_count(1)
    expect(page.locator("#detail .contact-cta__btn--primary")).to_have_count(1)
    expect(page.locator("#detail .contact-cta__btn--ghost")).to_have_count(0)


def test_fellow_detail_has_no_add_to_group_on_phone(
    mobile_interaction_page, device_name, base_url_fixture
):
    """The +/− add-to-group affordance in the detail name is skipped on
    phones (groups have no phone UI)."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/#/fellow/aaron_bird", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    expect(page.locator("#detail .detail-add-to-group")).to_have_count(0)
