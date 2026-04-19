#!/usr/bin/env python3
"""Debug email delivery for fellows-pwa.

SSHes to the production droplet, pulls recent ``event=send_unlock_email``
entries and rate-limit lines out of ``journalctl -u fellows-pwa``, and
optionally resolves Postmark ``MessageID``s to their downstream delivery
events via the Postmark Messages API.

Read-only. Python stdlib only. Hashed email prefixes only — plaintext
addresses never leave this machine and never hit the filter query on the
server.

Usage:

  # Last 24h, all results:
  scripts/debug_email_delivery.py

  # Narrow to one email over the last 2 hours:
  scripts/debug_email_delivery.py --since '2 hours ago' --email me@example.com

  # Also resolve Postmark delivery events (needs FELLOWS_POSTMARK_TOKEN):
  FELLOWS_POSTMARK_TOKEN=... scripts/debug_email_delivery.py --postmark

  # JSON out for piping:
  scripts/debug_email_delivery.py --json

See docs/email_gate.md for the surrounding algorithm; this script debugs
the send half of that flow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_HOST = "fellows.globaldonut.com"
DEFAULT_PORT = "52221"
DEFAULT_USER = "rsb"
UNIT = "fellows-pwa"
POSTMARK_BASE = "https://api.postmarkapp.com"

# Ring of results we understand. Anything else we keep and print as-is.
KNOWN_RESULTS = {"sent", "http_error", "error", "rate_limit"}


def hash_email(email: str) -> str:
    """SHA-256 hex of the normalized email — same recipe as the server."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def ssh_journal(host: str, port: str, user: str, since: str, unit: str = UNIT) -> str:
    """Fetch journalctl JSON lines via SSH. Returns raw stdout."""
    cmd = [
        "ssh",
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        f"{user}@{host}",
        "journalctl",
        "-u",
        unit,
        "--since",
        since,
        "-o",
        "json",
        "--no-pager",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError:
        sys.stderr.write("ssh binary not found on PATH\n")
        sys.exit(2)
    except subprocess.TimeoutExpired:
        sys.stderr.write("ssh/journalctl timed out after 60s\n")
        sys.exit(2)
    if r.returncode != 0:
        sys.stderr.write(f"ssh/journalctl failed (exit {r.returncode}):\n")
        sys.stderr.write(r.stderr)
        sys.stderr.write(
            "\nHints: is your SSH key loaded? Does "
            f"`ssh -p {port} {user}@{host} true` succeed interactively?\n"
        )
        sys.exit(1)
    return r.stdout


_RATE_LIMIT_RE = re.compile(r"Rate limit: send-unlock for hash prefix ([a-f0-9]+)")


def parse_events(raw_lines: str) -> list[dict]:
    """Extract send-attempt events from raw journalctl ``-o json`` stdout.

    journalctl emits one JSON envelope per log line. The server's log lines are
    either (a) structured ``event=send_unlock_email`` JSON strings in the
    ``MESSAGE`` field, or (b) plain-text rate-limit lines. We surface both.
    """
    events: list[dict] = []
    for line in raw_lines.splitlines():
        if not line.startswith("{"):
            continue
        try:
            outer = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = outer.get("MESSAGE") or ""
        if isinstance(msg, list):
            # journalctl can emit MESSAGE as a byte array when it contains
            # non-UTF8; we don't emit those, so just skip.
            continue
        ts_iso = _ts_from_outer(outer)
        if msg.startswith("{"):
            try:
                obj = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if obj.get("event") != "send_unlock_email":
                continue
            obj["_ts"] = ts_iso
            events.append(obj)
            continue
        m = _RATE_LIMIT_RE.search(msg)
        if m:
            events.append(
                {
                    "event": "rate_limit",
                    "result": "rate_limit",
                    "email_hash_prefix": m.group(1),
                    "_ts": ts_iso,
                    "_raw": msg.strip(),
                }
            )
    return events


def _ts_from_outer(outer: dict) -> str | None:
    raw = outer.get("__REALTIME_TIMESTAMP")
    if not raw:
        return None
    try:
        seconds = int(raw) / 1_000_000
        return (
            datetime.fromtimestamp(seconds, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (ValueError, OSError):
        return None


def filter_events(
    events: list[dict],
    email_hash_prefix: str | None = None,
    result: str | None = None,
) -> list[dict]:
    """Apply optional filters. Prefix match is exact-prefix on hex (12 char default)."""
    out = events
    if email_hash_prefix:
        p = email_hash_prefix.lower()
        out = [e for e in out if (e.get("email_hash_prefix") or "").lower().startswith(p)]
    if result:
        out = [e for e in out if (e.get("result") or "").lower() == result.lower()]
    return out


def fetch_postmark_message(message_id: str, token: str) -> dict:
    """Resolve a Postmark outbound ``MessageID`` to its full record + events.

    Returns the parsed JSON on success, or a dict with an ``_error`` key on
    failure so callers can report without bailing the whole run.
    """
    url = f"{POSTMARK_BASE}/messages/outbound/{message_id}"
    req = urllib.request.Request(
        url,
        headers={
            "X-Postmark-Server-Token": token,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except OSError:
            body = ""
        return {"_error": f"HTTP {e.code}", "_body": body[:400]}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def format_report(
    events: list[dict],
    postmark_lookups: dict[str, dict],
    header_meta: dict,
) -> str:
    """Human-readable report. Newest-first events + summary."""
    lines: list[str] = []
    lines.append(f"Email delivery report · {header_meta['host']}")
    lines.append(f"Window: since {header_meta['since']!r}  (unit={UNIT})")
    if header_meta.get("filter_desc"):
        lines.append(f"Filter: {header_meta['filter_desc']}")
    lines.append("")
    if not events:
        lines.append("No events in window.")
        return "\n".join(lines) + "\n"

    lines.append(f"Events ({len(events)}, newest first):")
    lines.append("")
    for e in reversed(events):
        lines.extend(_format_event(e))
        lines.append("")

    counts: dict[str, int] = {}
    for e in events:
        r = (e.get("result") or "unknown").lower()
        counts[r] = counts.get(r, 0) + 1
    summary = "  ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    lines.append("Summary:")
    lines.append(f"  {summary}")

    if postmark_lookups:
        lines.append("")
        lines.append(f"Postmark resolution ({len(postmark_lookups)} MessageID(s)):")
        for mid, resp in postmark_lookups.items():
            lines.extend(_format_postmark(mid, resp))

    return "\n".join(lines) + "\n"


def _format_event(e: dict) -> list[str]:
    ts = e.get("_ts") or "(no timestamp)"
    result = e.get("result") or "unknown"
    head = f"  {ts}  result={result}"
    out = [head]
    if e.get("token_prefix"):
        out.append(f"    token:  {e['token_prefix']}")
    if e.get("email_hash_prefix"):
        out.append(f"    email:  {e['email_hash_prefix']}")
    pm = e.get("postmark") or {}
    if pm:
        mid = pm.get("message_id") or pm.get("MessageID")
        err = pm.get("error_code") or pm.get("ErrorCode")
        msg = pm.get("message") or pm.get("Message")
        to = pm.get("to") or pm.get("To")
        sub = pm.get("submitted_at") or pm.get("SubmittedAt")
        if mid:
            out.append(f"    Postmark MessageID: {mid}")
        if sub:
            out.append(f"    SubmittedAt:        {sub}")
        if err not in (None, 0):
            out.append(f"    ErrorCode:          {err}")
        if msg and msg != "OK":
            out.append(f"    Message:            {msg}")
        if to:
            # This is what Postmark returns in the API response; server already
            # logged it. We don't hide it here — it's not *new* information.
            out.append(f"    To:                 {to}")
    if result == "http_error":
        status = e.get("status")
        reason = e.get("reason")
        body = e.get("body") or ""
        if status is not None:
            out.append(f"    HTTP status:  {status}")
        if reason:
            out.append(f"    reason:       {reason}")
        if body:
            out.append(f"    body:         {body[:400]}")
    if result == "error":
        err = e.get("error")
        if err:
            out.append(f"    exception:    {err[:400]}")
    if result == "rate_limit":
        out.append("    (server refused the send; 3-per-hour window)")
    return out


def _format_postmark(mid: str, resp: dict) -> list[str]:
    out = [f"  {mid}"]
    if resp.get("_error"):
        out.append(f"    lookup error: {resp['_error']}")
        if resp.get("_body"):
            out.append(f"    body:         {resp['_body']}")
        return out
    status = resp.get("Status") or "(unknown)"
    recipients = resp.get("Recipients") or []
    out.append(f"    Status:     {status}")
    if recipients:
        out.append(f"    Recipients: {', '.join(recipients)}")
    events = resp.get("MessageEvents") or []
    if events:
        for ev in events:
            kind = ev.get("Type") or "?"
            at = ev.get("ReceivedAt") or ""
            details = ev.get("Details") or {}
            extra = ""
            if details:
                # Pick a couple of common fields if present
                for k in ("DeliveryMessage", "BounceType", "Summary"):
                    if details.get(k):
                        extra = f"  ({k}={details[k]})"
                        break
            out.append(f"    {at}  {kind}{extra}")
    else:
        out.append("    MessageEvents: (none yet — Postmark accepted but hasn't attempted delivery)")
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="debug_email_delivery.py",
        description="Debug fellows-pwa email delivery by reading journalctl over SSH.",
    )
    ap.add_argument("--host", default=os.environ.get("FELLOWS_HOST", DEFAULT_HOST))
    ap.add_argument("--port", default=os.environ.get("FELLOWS_SSH_PORT", DEFAULT_PORT))
    ap.add_argument("--user", default=os.environ.get("FELLOWS_SSH_USER", DEFAULT_USER))
    ap.add_argument(
        "--since",
        default="24 hours ago",
        help='journalctl --since value (default "24 hours ago")',
    )
    ap.add_argument(
        "--email",
        help="Filter to this email (hashed on your machine; only the 12-char prefix leaves).",
    )
    ap.add_argument(
        "--email-hash-prefix",
        help="Filter by pre-computed SHA-256 hex prefix (use this when you don't want to type the address).",
    )
    ap.add_argument(
        "--result",
        choices=sorted(KNOWN_RESULTS),
        help="Filter to a specific result type.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Keep only the most recent N events after filtering (default 50).",
    )
    ap.add_argument(
        "--postmark",
        action="store_true",
        help="Resolve Postmark MessageIDs via the Messages API. Requires FELLOWS_POSTMARK_TOKEN.",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON (for piping / jq). Suppresses the formatted report.",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    if args.email and args.email_hash_prefix:
        ap.error("pass one of --email or --email-hash-prefix, not both")

    prefix = None
    email_desc = None
    if args.email:
        full = hash_email(args.email)
        prefix = full[:12]
        email_desc = f"{prefix}… ({args.email})"
    elif args.email_hash_prefix:
        prefix = args.email_hash_prefix.lower().strip()
        email_desc = f"{prefix}…"

    raw = ssh_journal(args.host, args.port, args.user, args.since)
    events = parse_events(raw)
    events = filter_events(events, email_hash_prefix=prefix, result=args.result)
    if args.limit > 0:
        events = events[-args.limit :]

    postmark_lookups: dict[str, dict] = {}
    if args.postmark:
        token = os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip()
        if not token:
            sys.stderr.write("--postmark requires FELLOWS_POSTMARK_TOKEN in env.\n")
            return 2
        seen: set[str] = set()
        for e in events:
            mid = ((e.get("postmark") or {}).get("message_id")
                   or (e.get("postmark") or {}).get("MessageID"))
            if mid and mid not in seen:
                seen.add(mid)
                postmark_lookups[mid] = fetch_postmark_message(mid, token)

    filter_desc_parts = []
    if email_desc:
        filter_desc_parts.append(f"email hash {email_desc}")
    if args.result:
        filter_desc_parts.append(f"result={args.result}")
    filter_desc = "; ".join(filter_desc_parts) if filter_desc_parts else None

    if args.json:
        out = {
            "host": args.host,
            "since": args.since,
            "filter": {
                "email_hash_prefix": prefix,
                "result": args.result,
            },
            "events": events,
            "postmark": postmark_lookups,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        report = format_report(
            events,
            postmark_lookups,
            {
                "host": args.host,
                "since": args.since,
                "filter_desc": filter_desc,
            },
        )
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
