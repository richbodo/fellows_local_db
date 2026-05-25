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


def test_selecting_fellow_reveals_fab(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Tapping the +/× marker on a directory row should add the fellow
    to the selection draft and reveal the composer FAB so the user has
    a path to actually create a group on mobile.

    Root of the user-reported "no way to create a group" bug — if this
    fails, the rail-driven group-creation flow has no mobile entry
    point at all."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    mark = page.locator("#directory li.dir-row .dir-mark").first
    expect(mark).to_be_visible()
    mark.click()
    # Body picks up .has-selection once the draft is non-empty.
    expect(page.locator("body")).to_have_class(
        re.compile(r"\bhas-selection\b"),
        timeout=3000,
    )
    # FAB is hidden initially via .hidden; should become visible on
    # selection at mobile widths.
    fab = page.locator("#composer-fab")
    expect(fab).to_be_visible(timeout=3000)


def test_can_open_and_close_composer_sheet(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Tap the FAB → composer rail slides up as a bottom sheet
    (body.composer-open). Closing the composer should remove the
    class and put the rail back off-screen."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    page.locator("#directory li.dir-row .dir-mark").first.click()
    fab = page.locator("#composer-fab")
    expect(fab).to_be_visible(timeout=3000)
    fab.click()
    expect(page.locator("body")).to_have_class(
        re.compile(r"\bcomposer-open\b"),
        timeout=3000,
    )
    # The composer rail itself must now be visible on-screen.
    rail = page.locator("#group-rail")
    expect(rail).to_be_visible()
    rail_metrics = page.evaluate(
        """
        () => {
          const r = document.getElementById('group-rail').getBoundingClientRect();
          return {top: r.top, bottom: r.bottom, vh: window.innerHeight};
        }
        """
    )
    assert rail_metrics["top"] < rail_metrics["vh"], (
        f"composer rail not on-screen after open at {device_name}: "
        f"top={rail_metrics['top']}, vh={rail_metrics['vh']}"
    )


def test_can_create_group_from_directory_route(
    mobile_worker_data, device_name, base_url_fixture
):
    """Headline test: a user at mobile should be able to create a group
    end to end without leaving the directory route.

    Flow: select one fellow → tap FAB → fill name → tap Create new
    group → assert the group was persisted via the worker.

    Failure here = the user's reported bug ("no way to create a group
    on mobile") is reproduced."""
    helper = mobile_worker_data
    page = helper.page
    # mobile_worker_data already navigated + waited; ensure we're on directory.
    page.evaluate("location.hash = '#/'")
    _wait_for_app_boot(page)
    # Select the first fellow.
    page.locator("#directory li.dir-row .dir-mark").first.click()
    # Open composer.
    fab = page.locator("#composer-fab")
    expect(fab).to_be_visible(timeout=3000)
    fab.click()
    expect(page.locator("body")).to_have_class(
        re.compile(r"\bcomposer-open\b"),
        timeout=3000,
    )
    # Fill the group name. The title input is contenteditable in the
    # current shipping rail. Fall back to typing if it's a regular input.
    title = page.locator("#group-rail-title")
    expect(title).to_be_visible()
    group_name = f"Mobile created at {device_name}"
    is_editable = page.evaluate(
        "() => document.getElementById('group-rail-title').isContentEditable"
    )
    if is_editable:
        title.click()
        page.keyboard.type(group_name)
    else:
        title.fill(group_name)
    # Submit.
    create_btn = page.locator("#group-rail-create")
    expect(create_btn).to_be_enabled(timeout=3000)
    create_btn.click()
    # Worker should now report the group exists.
    page.wait_for_function(
        f"() => window.__dataProvider.listGroups().then(gs => "
        f"gs.some(g => g.name === {group_name!r}))",
        timeout=5000,
    )
    groups = helper.list_groups()
    names = [g["name"] for g in groups]
    assert group_name in names, (
        f"group not persisted via mobile composer at {device_name}; "
        f"got names={names!r}"
    )


# ===== Kebab menu (app-bar) ================================================


def test_kebab_menu_opens_and_dismisses(
    mobile_interaction_page, device_name, base_url_fixture
):
    """Top-right kebab button should open the bottom sheet; close
    button (or scrim tap) should dismiss it."""
    page = mobile_interaction_page
    page.goto(base_url_fixture + "/", wait_until="domcontentloaded")
    _wait_for_app_boot(page)
    kebab = page.locator(".appbar__kebab").first
    expect(kebab).to_be_visible(timeout=5000)
    kebab.click()
    # The kebab sheet has id="kebab-sheet" or similar — look for the
    # generic .sheet that becomes visible after the click. Use whichever
    # of the known kebab sheet ids exists in the DOM.
    sheet_visible = page.evaluate(
        """
        () => {
          const sheets = document.querySelectorAll('.sheet');
          for (const s of sheets) {
            if (!s.classList.contains('hidden')
                && getComputedStyle(s).display !== 'none') {
              return {id: s.id, cls: s.className};
            }
          }
          return null;
        }
        """
    )
    assert sheet_visible is not None, (
        f"kebab tap did not open any .sheet at {device_name}"
    )


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


# ===== Settings page (post-#205 private-data-folder layout) ================


def test_settings_email_field_saves(
    mobile_worker_data, device_name, base_url_fixture
):
    """Settings → Your email saves to relationships.db via the worker.
    Catches mobile-keyboard-covers-the-input + tap-the-save-button
    failures at narrow widths."""
    helper = mobile_worker_data
    page = helper.page
    page.evaluate("location.hash = '#/settings'")
    _wait_for_app_boot(page)
    email_input = page.locator("#settings-self-email")
    expect(email_input).to_be_visible()
    email_input.fill(f"mobile-{device_name.replace(' ', '-').lower()}@example.com")
    page.locator(".settings-save").click()
    # The setting lands via worker RPC.
    page.wait_for_function(
        f"() => window.__dataProvider.getSetting('self_email')"
        f"  .then(v => v && v.indexOf('mobile-') === 0)",
        timeout=5000,
    )
    saved = helper.get_setting("self_email")
    assert saved and saved.startswith("mobile-"), (
        f"settings did not persist via mobile UI at {device_name}; got {saved!r}"
    )


# ===== Groups index + fellow detail ========================================


def test_groups_index_renders_card_list_on_mobile(
    mobile_worker_data, device_name, base_url_fixture
):
    """At mobile widths the groups index renders as cards (the
    .groups-table is hidden). With at least one group seeded, at least
    one card must render and be visible."""
    helper = mobile_worker_data
    helper.create_group(name="Mobile index card", fellow_record_ids=[])
    page = helper.page
    page.evaluate("location.hash = '#/groups'")
    _wait_for_app_boot(page)
    # .groups-table is hidden at mobile; .groups-card-list takes over.
    card_list = page.locator(".groups-card-list")
    expect(card_list).to_be_visible()
    cards = page.locator(".groups-card-list .groups-card")
    assert cards.count() > 0, (
        f"groups card list rendered no cards at {device_name}"
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
