#!/usr/bin/env python3
"""Communications MCP server — stage outreach for workspace-mediated launch.

Exposes two tools to AI clients (Claude Desktop, Cursor, mcp-cli, local
Ollama agents):

- stage_email   Build a mailto: URL + a full payload preview from a draft
                composition. Returns a staging_id, the URL, and a warnings
                list (URL-length issues, missing recipients, etc.).
- get_staged    Echo a previously staged composition by id (in-memory).

Architectural posture (AC-MCP-B — see https://github.com/richbodo/personal_network_toolkit/blob/main/PNA_Spec.md § Universal architectural commitments):
**The MCP server proposes; the workspace disposes.** This server never
launches a transport itself. It returns a mailto: URL that the user's
mail client (acting as the workspace for this outreach) opens with the
composition pre-populated. The user reviews and clicks send.

AC-18 (transport eligibility): mailto: passes — the mechanism can't read
message content, and the downstream mail client is the user's choice.
AC-19 (user-visible payload before send): the `preview` field exposes
recipients + subject + body explicitly so the AI client can show the
full composition to the user before they open the link.

State posture: staged compositions live in-memory only. Process exit
clears them. The server intentionally writes nothing to disk — no logs
of who you emailed, no draft persistence. That's the workspace's job
(see PR-2 `record_comms_history` in the spec — opt-in, off by default).
"""

import argparse
import logging
import os
import secrets
import sys
import threading
from pathlib import Path
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

log = logging.getLogger("comms")

mcp = FastMCP("comms")

# Recommended ceiling for mailto: URL length. RFC doesn't set one; practical
# clients vary. macOS Mail.app and Apple Mail on iOS handle ~8 KB; Outlook
# starts dropping characters past ~2 KB; Gmail web "send via mailto" caps near
# ~2 KB. Pick the conservative number and warn above it.
MAILTO_URL_WARN_BYTES = 2000

# In-memory staging table. Cleared at process exit; nothing on disk.
_STAGED: dict[str, dict] = {}
_STAGED_LOCK = threading.Lock()
# Cap to keep memory bounded across a long-running session.
_STAGED_MAX = 100


def _new_staging_id() -> str:
    """16-char URL-safe random id. Opaque to the client."""
    return secrets.token_urlsafe(12)[:16]


def _clean_email(addr: str) -> str:
    """Strip whitespace; pass-through otherwise. Validation is the mail
    client's job — we don't want to reject things the user might fix in their
    composer (e.g., "Jane <jane@x>" address-list syntax).
    """
    return (addr or "").strip()


def _dedupe_emails(addrs):
    """Strip empties, dedupe case-insensitively, preserve order."""
    seen = set()
    out = []
    for a in addrs or ():
        c = _clean_email(a)
        if not c:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _build_mailto(to: list, cc: list, bcc: list, subject: str, body: str) -> str:
    """Compose a mailto: URL per RFC 6068.

    Header values are percent-encoded. Multiple recipients are joined with
    commas. ``to`` is part of the URL path; ``cc``, ``bcc``, ``subject``,
    ``body`` are header parameters.
    """
    path = ",".join(quote(addr, safe="@") for addr in to)
    params = []
    if cc:
        params.append(("cc", ",".join(cc)))
    if bcc:
        params.append(("bcc", ",".join(bcc)))
    if subject:
        params.append(("subject", subject))
    if body:
        params.append(("body", body))
    if not params:
        return f"mailto:{path}"
    qs = "&".join(f"{k}={quote(v, safe='@,')}" for k, v in params)
    return f"mailto:{path}?{qs}"


def _store(record: dict) -> str:
    """Insert into the in-memory staging table, evicting the oldest if full."""
    sid = _new_staging_id()
    with _STAGED_LOCK:
        if len(_STAGED) >= _STAGED_MAX:
            # Drop the oldest insertion (Python dicts preserve insertion order).
            oldest = next(iter(_STAGED))
            _STAGED.pop(oldest, None)
        _STAGED[sid] = record
    return sid


@mcp.tool()
def stage_email(
    subject: str,
    body: str,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict:
    """Stage an email composition for the user to review and send.

    Builds a ``mailto:`` URL that the user's mail client opens with everything
    pre-populated. The MCP server never sends — opening the URL is what the
    user (or the AI client on the user's behalf) does to hand the composition
    off to the mail client.

    For groups, prefer ``bcc`` over ``to`` so individual addresses aren't
    visible in everyone's "To:" header. ``to`` may be empty if the entire
    list is in bcc.

    Recipients are de-duplicated case-insensitively. Empty addresses are
    silently dropped (the AI may pass through fellows with no email).

    Args:
        subject: The email subject. Required (empty string allowed).
        body: The email body. Required (empty string allowed).
        to: Visible primary recipients. Optional; pass an empty list or
            omit for BCC-only group sends.
        cc: Carbon-copied recipients. Optional.
        bcc: Blind-carbon-copied recipients. Optional.

    Returns:
        {
          "staging_id": str,              # opaque id for get_staged
          "mailto_url": str,              # the URL to open
          "preview": {
            "recipients": {
              "to": list[str],
              "cc": list[str],
              "bcc": list[str],
              "total": int,
            },
            "subject": str,
            "body": str,
            "url_byte_length": int,
          },
          "warnings": list[str],          # human-readable issues for the user
        }
    """
    to_clean = _dedupe_emails(to)
    cc_clean = _dedupe_emails(cc)
    bcc_clean = _dedupe_emails(bcc)
    subject = subject or ""
    body = body or ""

    mailto_url = _build_mailto(to_clean, cc_clean, bcc_clean, subject, body)
    url_bytes = len(mailto_url.encode("utf-8"))
    total = len(to_clean) + len(cc_clean) + len(bcc_clean)

    warnings = []
    if total == 0:
        warnings.append(
            "No recipients — the mail client will open but won't have anyone to send to."
        )
    if url_bytes > MAILTO_URL_WARN_BYTES:
        warnings.append(
            f"mailto: URL is {url_bytes} bytes; some mail clients (Outlook, "
            f"Gmail-via-mailto) start truncating around {MAILTO_URL_WARN_BYTES} bytes. "
            "Consider splitting the recipient list, or paste the body into the mail "
            "composer after it opens."
        )
    if to_clean and total > 1 and not bcc_clean:
        # Heuristic: a group send through To: leaks every recipient's address.
        # Worth a nudge for the AI client to surface to the user.
        warnings.append(
            "Multiple recipients in `to`. Consider moving them to `bcc` so addresses "
            "aren't visible to everyone on the thread."
        )

    preview = {
        "recipients": {
            "to": to_clean,
            "cc": cc_clean,
            "bcc": bcc_clean,
            "total": total,
        },
        "subject": subject,
        "body": body,
        "url_byte_length": url_bytes,
    }
    record = {
        "mailto_url": mailto_url,
        "preview": preview,
        "warnings": warnings,
    }
    sid = _store(record)
    log.debug(
        "stage_email -> sid=%s, total=%d recipients, url=%d bytes, warnings=%d",
        sid, total, url_bytes, len(warnings),
    )
    return {"staging_id": sid, **record}


@mcp.tool()
def get_staged(staging_id: str) -> dict | None:
    """Look up a previously staged composition by id.

    Useful when the user asks "what did you draft a minute ago?" Returns null
    when the id isn't known (process restart, eviction, or never staged).
    Staged records live in memory only; nothing persists across restarts.

    Args:
        staging_id: The id returned by stage_email.

    Returns:
        {
          "staging_id": str,
          "mailto_url": str,
          "preview": {...},
          "warnings": list[str],
        }
        or null.
    """
    sid = (staging_id or "").strip()
    if not sid:
        return None
    with _STAGED_LOCK:
        rec = _STAGED.get(sid)
    if rec is None:
        return None
    return {"staging_id": sid, **rec}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Communications MCP server.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Log tool calls and resolved args to stderr.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("comms MCP server starting; stage-only, in-memory")
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
