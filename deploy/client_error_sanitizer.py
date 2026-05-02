"""Sanitizer for `POST /api/client-errors` payloads.

The `/api/client-errors` endpoint is unauthenticated by design — its job is
to capture diagnostics from users who couldn't get past the auth gate. That
makes the privacy boundary load-bearing: anything in this file is what the
maintainer is willing to see in journald, and nothing else may pass.

Pure functions, no I/O, no globals. Importable from both `deploy/server.py`
(prod) and `app/server.py` (dev stub) without setting up a server. The
public surface is `sanitize_payload(body) -> dict` (raises ValueError on
unrecoverable shape errors); the lower-level helpers are exposed only so
tests can pin each rule.

Rules, in priority order — match what's documented in
`docs/email_gate.md` (§ Client error reporting). If you change one, keep
that doc in lockstep.

1. Top-level keys are an accept-list. Unknown keys are silently dropped.
2. `events` is required, must be a list, and is capped at MAX_EVENTS.
3. Each event has its own accept-list of keys; `kind` is restricted to a
   small enum so a malicious caller can't tag an entry with an
   exfiltration label.
4. Free-text fields (`msg`, `extra`, `route`, `ua`) are sanitized:
     - email-shaped substrings → ``<email>``
     - within hash routes, ``/fellow/<slug>`` and ``/unlock/<token>`` are
       redacted (slugs identify which fellow profile a user was viewing;
       tokens are obviously sensitive). Group IDs (``/groups/<id>``) are
       integers and not redacted — group membership is shared among
       fellows and the route is high-signal for triage.
     - query strings (``?...``) and URL fragments past the route are
       dropped (they can carry tokens, search terms, or referrers).
     - hard length caps stop a malicious caller from filling journald.
5. `lastSubmitHashPrefix` must be exactly 12 hex chars (matches what the
   client computes via `sha256HexBrowser(email).slice(0,12)` — see
   `app/static/app.js`). Anything else is dropped.

The output is a dict ready to be merged into the structured journald
event in `deploy/server.py:_handle_client_errors`.
"""

from __future__ import annotations

import re

# Caps are small enough to keep journald lines short and large enough to
# not clip useful context. If you raise these, also raise the
# Content-Length cap in `deploy/server.py:do_POST` so the bytes can land.
MAX_EVENTS = 20
MAX_MSG_LEN = 500
MAX_EXTRA_LEN = 200  # matches BUG_REPORT_RING_MAX entry cap in app.js
MAX_UA_LEN = 240     # matches deploy/server.py auth_status user-agent slice
MAX_ROUTE_LEN = 240
MAX_BUILD_LEN = 64

# Restricted set so a caller can't smuggle e.g. `kind=admin_command`.
# `install` carries install-funnel telemetry from the install landing
# page (beforeinstallprompt fired / never arrived, button clicked,
# accept/dismiss outcome, app installed, "use in tab" escape hatch,
# iOS Safari advisory). The privacy boundary is the same — same
# free-text sanitization on `msg` and `extra` — so adding the kind
# doesn't widen what a caller can put in the journald log.
ALLOWED_EVENT_KINDS = frozenset({
    "http",
    "sw",
    "window.error",
    "unhandledrejection",
    "console.error",
    "install",
})

ALLOWED_DISPLAY_MODES = frozenset({"standalone", "browser-tab"})

# Email regex tuned to be greedy enough to catch obfuscations like
# `me+tag@example.co.uk` but not so greedy it eats unrelated `@` mentions
# in stack traces. Word boundary on each side keeps false positives low.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Hash-route segments to redact. The regex is anchored on the segment
# label (`fellow` or `unlock`) so `groups/<id>` stays intact.
_SLUG_RE = re.compile(r"(#/(?:fellow|unlock)/)[^/?#]+")

_HEX12_RE = re.compile(r"^[0-9a-f]{12}$")


def redact_email(s: str) -> str:
    """Replace email-shaped substrings with ``<email>``."""
    if not isinstance(s, str):
        return ""
    return _EMAIL_RE.sub("<email>", s)


def redact_route(s: str) -> str:
    """Drop query/fragment-after-route, redact slug-bearing segments.

    Idempotent. Handles both absolute paths (``/foo?bar``) and hash
    routes (``#/fellow/jane-doe``) that may appear in URL strings or
    error messages. The order matters: trim query first so the regex
    only sees clean route segments.
    """
    if not isinstance(s, str):
        return ""
    # Drop query string everywhere it appears.
    s = re.sub(r"\?[^\s#]*", "", s)
    # Redact sensitive slugs / tokens inside hash routes.
    s = _SLUG_RE.sub(r"\1<redacted>", s)
    return s


def _truncate(s: str, cap: int) -> str:
    if not isinstance(s, str):
        return ""
    if len(s) <= cap:
        return s
    return s[:cap] + "…"


def sanitize_text_field(s, cap: int) -> str:
    """Sanitize a free-text field intended for log emission.

    Order: redact slugs (also drops query strings), redact emails,
    truncate. Email redaction runs after route redaction because a route
    may contain an email-like slug we'd rather see as ``<redacted>`` than
    as ``<email>``.
    """
    if not isinstance(s, str):
        return ""
    s = redact_route(s)
    s = redact_email(s)
    return _truncate(s, cap)


def _sanitize_event(raw) -> dict | None:
    """Sanitize one event dict. Returns None if shape is unrecoverable."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if kind not in ALLOWED_EVENT_KINDS:
        return None
    out = {"kind": kind}
    ts = raw.get("ts")
    if isinstance(ts, str) and len(ts) <= 32:
        # ISO-8601 strings only; we don't parse, just clip length.
        out["ts"] = ts
    msg = raw.get("msg")
    if msg is not None:
        out["msg"] = sanitize_text_field(msg, MAX_MSG_LEN)
    extra = raw.get("extra")
    if extra is not None:
        out["extra"] = sanitize_text_field(extra, MAX_EXTRA_LEN)
    return out


def sanitize_payload(body) -> dict:
    """Validate + sanitize a `POST /api/client-errors` body.

    Returns a dict with only allowed keys. Raises ValueError if the body
    is unrecoverable (not a dict, missing/invalid `events` array). The
    caller logs the returned dict as a structured journald event.
    """
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    raw_events = body.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("events must be a list")

    events = []
    for raw in raw_events[:MAX_EVENTS]:
        e = _sanitize_event(raw)
        if e is not None:
            events.append(e)

    out: dict = {"events": events}

    ua = body.get("ua")
    if isinstance(ua, str):
        # UA is just length-capped; we deliberately don't sanitize it
        # because it's the most useful triage field and rarely contains
        # PII (some browsers do encode device names — accepted tradeoff).
        out["ua"] = _truncate(ua, MAX_UA_LEN)
    route = body.get("route")
    if isinstance(route, str):
        out["route"] = sanitize_text_field(route, MAX_ROUTE_LEN)
    build = body.get("build")
    if isinstance(build, str):
        out["build"] = _truncate(build, MAX_BUILD_LEN)
    display_mode = body.get("displayMode")
    if display_mode in ALLOWED_DISPLAY_MODES:
        out["displayMode"] = display_mode
    online = body.get("online")
    if isinstance(online, bool):
        out["online"] = online

    last_hash = body.get("lastSubmitHashPrefix")
    if isinstance(last_hash, str) and _HEX12_RE.match(last_hash):
        out["lastSubmitHashPrefix"] = last_hash

    return out
