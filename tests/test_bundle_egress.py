"""Static egress canary: first-party JS must not reach any external origin.

The runtime backstop is the CSP `connect-src 'self'` (asserted in
tests/test_api.py::TestSecurityHeaders), which blocks exfiltration at the
browser. This file is defense-in-depth at the *source*: a deterministic,
dependency-free scan that fires the moment someone adds a fetch/importScripts
to an absolute external URL, or introduces a new network primitive
(WebSocket/EventSource/sendBeacon/XHR) the egress story hasn't accounted for.

Why this matters here specifically: the private-data capability gate is a
DURABILITY control, not a confidentiality boundary
(plans/private_data_capability_gate.md) — a DevTools session by the data's
owner reaching their own data is in-design, not a breach. The real on-device
confidentiality boundary is the egress wall (CSP + no external network calls),
so it earns a regression net at two layers.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# First-party scripts only. Third-party vendored files (sqlite3.js, jspdf) are
# covered by SRI + the signed bundle (tests/test_build_pwa.py, test_sign_bundle.py);
# scanning their minified bodies here would only add false positives.
FIRST_PARTY_JS = [
    "app/static/app.js",
    "app/static/sw.js",
    "app/static/vendor/sqlite-worker.js",
]

# fetch(...) / importScripts(...) with a STRING-LITERAL target. The negative
# lookbehind excludes `prefetch(` (and any identifier-suffixed name) while
# still matching bare `fetch(` and `window.fetch(`. Calls with a variable
# target (e.g. fetch(url, opts)) aren't matched — those are fed same-origin
# paths internally and the CSP is their runtime backstop.
_CALL_LITERAL = re.compile(r"(?<![A-Za-z])(?:fetch|importScripts)\(\s*(['\"`])([^'\"`]+)\1")

# Anything that looks like a URI scheme (http:, https:, ws:, wss:, data:, ...).
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:")

# Network primitives the app deliberately does not use today. If one appears,
# the egress audit must be revisited on purpose — route it same-origin and
# update this list with a rationale.
_FORBIDDEN_PRIMITIVES = (
    "new WebSocket(",
    "new EventSource(",
    "navigator.sendBeacon(",
    "new XMLHttpRequest(",
)


def _read(rel):
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_fetch_and_import_targets_are_same_origin():
    offenders = []
    for rel in FIRST_PARTY_JS:
        for m in _CALL_LITERAL.finditer(_read(rel)):
            target = m.group(2)
            # Same-origin = root-relative ("/x") or relative ("./x", "../x").
            # Reject any scheme (http:/https:/ws:/data:) or protocol-relative
            # "//host".
            if target.startswith("//") or _SCHEME.match(target):
                offenders.append((rel, target))
    assert not offenders, (
        "fetch()/importScripts() targets an external origin — this breaches "
        f"the connect-src 'self' egress wall. Offenders: {offenders}"
    )


def test_no_unaccounted_network_primitives():
    offenders = []
    for rel in FIRST_PARTY_JS:
        src = _read(rel)
        for prim in _FORBIDDEN_PRIMITIVES:
            if prim in src:
                offenders.append((rel, prim))
    assert not offenders, (
        "A network primitive outside the egress audit appeared. If intentional, "
        "keep it same-origin and update _FORBIDDEN_PRIMITIVES with rationale. "
        f"Offenders: {offenders}"
    )
