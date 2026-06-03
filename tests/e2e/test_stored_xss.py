"""Stored-XSS regression: user-authored text rendered into innerHTML must be
HTML-escaped, so a payload can never inject a live DOM node.

escapeHtml() (app/static/app.js) is the sink defense; the CSP without
'unsafe-inline' (tests/test_api.py) is the backstop. This test isolates the
ESCAPING from the CSP backstop: it asserts that no payload element is injected
into the DOM at all — true regardless of whether CSP would also have neutered
an inline handler. Group name + note are the user-authored fields rendered via
escapeHtml in renderGroupsList(); they're the realistic stored-XSS surface.

Uses worker_data_folder (a verified folder attached) so the group surfaces are
available now AND after the capability gate's PR3 hides them off-folder.
"""

# Distinct markers so we can prove the payload still RENDERED (as inert text)
# while the active <img>/<svg> were never created.
NAME_PAYLOAD = 'PWNZNAME<img src="x" onerror="window.__xssFired=true">'
NOTE_PAYLOAD = 'PWNZNOTE<svg onload="window.__xssFired=true"></svg>'


def test_group_name_and_note_are_escaped_on_index(worker_data_folder, base_url_fixture):
    wd = worker_data_folder
    wd.create_group(NAME_PAYLOAD, note=NOTE_PAYLOAD)

    page = wd.page
    page.goto(base_url_fixture + "/#/groups", wait_until="domcontentloaded")
    page.locator("#groups-list-wrap .groups-name-link").first.wait_for(timeout=10000)

    # Scope the assertions to the payload's OWN signatures (its handler
    # attributes + the img[src=x]), not "any svg/img" — the mobile card list
    # legitimately renders a decorative kebab <svg>. An injected node would
    # carry onerror/onload; an escaped one is inert text with no such element.
    res = page.evaluate(
        """() => {
            const wrap = document.getElementById('groups-list-wrap');
            return {
                fired: window.__xssFired === true,
                payloadImg: wrap ? wrap.querySelectorAll('img[src="x"]').length : -1,
                onerrorEls: wrap ? wrap.querySelectorAll('[onerror]').length : -1,
                onloadEls: wrap ? wrap.querySelectorAll('[onload]').length : -1,
                text: wrap ? wrap.innerText : ''
            };
        }"""
    )
    assert res["fired"] is False, "XSS payload executed — escaping failed"
    assert res["payloadImg"] == 0, "payload injected a live <img> node — name not escaped"
    assert res["onerrorEls"] == 0, "an element carries an onerror handler — name not escaped"
    assert res["onloadEls"] == 0, "an element carries an onload handler — note not escaped"
    # The payload still rendered — just as inert, escaped text.
    assert "PWNZNAME" in res["text"], res["text"]
    assert "PWNZNOTE" in res["text"], res["text"]
