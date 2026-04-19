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
import getpass
import hashlib
import json
import os
import re
import shlex
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


def build_ssh_cmd(
    host: str,
    port: str,
    user: str,
    since: str,
    unit: str = UNIT,
    use_sudo: bool = False,
) -> list[str]:
    """Build the ssh command list.

    SSH concatenates argv with spaces on the wire and the remote shell
    re-parses, so ``--since '2 hours ago'`` passed as separate argv entries
    arrives on the remote as ``--since 2 hours ago`` and journalctl rejects
    it with "Failed to parse timestamp: 2". Quote each remote arg and pass
    the whole remote command as a single SSH argument.

    When ``use_sudo=True``, prepend ``sudo -S -p ''`` on the remote. Caller
    is responsible for supplying the password on the subprocess's stdin.
    ``-S`` reads the password from stdin; ``-p ''`` silences the prompt
    text so nothing contaminates the journalctl JSON stream. No pty
    allocation (no ``-tt``) — that swallowed the prompt into captured
    stdout and caused indefinite hangs.
    """
    remote_argv = ["journalctl", "-u", unit, "--since", since, "-o", "json", "--no-pager"]
    if use_sudo:
        remote_argv = ["sudo", "-S", "-p", ""] + remote_argv
    remote_cmd = " ".join(shlex.quote(a) for a in remote_argv)

    ssh_flags: list[str] = ["-p", str(port)]
    if not use_sudo:
        ssh_flags.extend(["-o", "BatchMode=yes"])

    return ["ssh", *ssh_flags, f"{user}@{host}", remote_cmd]


def ssh_journal(
    host: str,
    port: str,
    user: str,
    since: str,
    unit: str = UNIT,
    use_sudo: bool = False,
    verbose: bool = False,
    sudo_password: str | None = None,
) -> str:
    """Fetch journalctl JSON lines via SSH. Returns raw stdout.

    With ``use_sudo=True``, prompts locally for the sudo password via
    ``getpass`` (unless ``sudo_password`` is supplied, mostly for tests)
    and pipes it to the remote ``sudo -S`` via the subprocess's stdin.
    """
    if use_sudo and sudo_password is None:
        sudo_password = getpass.getpass(f"sudo password for {user}@{host}: ")

    cmd = build_ssh_cmd(host, port, user, since, unit=unit, use_sudo=use_sudo)

    # Always print a one-line breadcrumb so a hang is obviously a hang on a
    # known line, not a silent wedge. --verbose echoes the full quoted cmd.
    sys.stderr.write(f"→ SSH {user}@{host}:{port} journalctl (use_sudo={use_sudo})…\n")
    sys.stderr.flush()
    if verbose:
        sys.stderr.write(
            "[verbose] " + " ".join(shlex.quote(a) for a in cmd) + "\n"
        )
        sys.stderr.flush()

    try:
        r = subprocess.run(
            cmd,
            input=(sudo_password + "\n") if use_sudo else None,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write("ssh binary not found on PATH\n")
        sys.exit(2)
    except subprocess.TimeoutExpired:
        sys.stderr.write("ssh/journalctl timed out after 120s\n")
        sys.exit(2)

    if r.returncode != 0:
        sys.stderr.write(f"ssh/journalctl failed (exit {r.returncode}):\n")
        if r.stderr:
            sys.stderr.write(r.stderr)
            if not r.stderr.endswith("\n"):
                sys.stderr.write("\n")
        sys.stderr.write(
            "\nHints: is your SSH key loaded? Does "
            f"`ssh -p {port} {user}@{host} true` succeed interactively?\n"
        )
        if use_sudo:
            sys.stderr.write(
                "If sudo failed: check the password. Alternatively, add "
                f"{user} to the systemd-journal group on prod to drop the "
                "--sudo requirement entirely.\n"
            )
        else:
            sys.stderr.write(
                "If journalctl returned no rows for fellows-pwa, rerun with "
                "--sudo — non-privileged journalctl silently hides other "
                "users' unit logs.\n"
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


DEFAULT_ENV_FILE = "/etc/fellows/fellows-pwa.env"
DEFAULT_ALLOWLIST_PATH = "/opt/fellows/deploy/dist/allowed_emails.json"


def fetch_allowlist_from_prod(
    host: str,
    port: str,
    user: str,
    allowlist_path: str = DEFAULT_ALLOWLIST_PATH,
) -> set[str]:
    """SSH + plain `cat` the allowlist JSON; no sudo needed.

    ``/opt/fellows/deploy/dist/`` is mode 2775 owned by ``fellows:fellows``,
    and the operator (``rsb``) is in the ``fellows`` group, so we can read it
    directly. Returns a set of hex SHA-256 hashes.
    """
    remote_cmd = f"cat {shlex.quote(allowlist_path)}"
    cmd = ["ssh", "-o", "BatchMode=yes", "-p", str(port), f"{user}@{host}", remote_cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if r.returncode != 0:
        raise RuntimeError(
            f"ssh/cat allowlist failed (exit {r.returncode}): "
            + (r.stderr.strip() or "no stderr")
        )
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"allowlist JSON parse failed: {e}")
    hashes = data.get("hashes") or []
    return {str(h).lower() for h in hashes if h}


def check_allowlist(email: str, allowlist: set[str]) -> dict:
    """Return {email, hash, hit, allowlist_size} for the given email."""
    h = hash_email(email)
    return {
        "email": email,
        "hash": h,
        "hit": h in allowlist,
        "allowlist_size": len(allowlist),
    }


DEFAULT_FELLOWS_DB = "/opt/fellows/deploy/dist/fellows.db"


def fetch_fellow_emails_from_prod(
    host: str,
    port: str,
    user: str,
    db_path: str = DEFAULT_FELLOWS_DB,
) -> list[dict]:
    """SSH + remote Python to pull fellow records with contact emails.

    Prod droplet runs the app on Python, so ``python3`` + stdlib ``sqlite3`` is
    always available. The ``sqlite3`` CLI binary is NOT installed (it's not a
    fellows-pwa dep) so we use Python directly — one-liner, JSON out.

    Same path as the allowlist (group-readable, no sudo needed). Returns a list
    of ``{"record_id", "name", "email"}`` dicts with email lowercased+trimmed,
    matching the build_pwa hashing recipe.
    """
    py_code = (
        "import json, sqlite3; "
        f"c = sqlite3.connect({db_path!r}); "
        "c.row_factory = sqlite3.Row; "
        "rows = c.execute("
        "\"SELECT record_id, name, lower(trim(contact_email)) AS email "
        "FROM fellows WHERE contact_email IS NOT NULL "
        "AND trim(contact_email) != ''\""
        ").fetchall(); "
        "print(json.dumps([dict(r) for r in rows]))"
    )
    remote_cmd = f"python3 -c {shlex.quote(py_code)}"
    cmd = ["ssh", "-o", "BatchMode=yes", "-p", str(port), f"{user}@{host}", remote_cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if r.returncode != 0:
        raise RuntimeError(
            f"ssh/python3 query failed (exit {r.returncode}): "
            + (r.stderr.strip() or "no stderr")
        )
    if not r.stdout.strip():
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"sqlite3 JSON parse failed: {e}")
    return data if isinstance(data, list) else []


def dump_allowlist_report(host: str, port: str, user: str) -> dict:
    """Cross-reference allowlist hashes against the fellows DB.

    Returns a structured summary and writes a human-readable report to stdout.
    Flags two invariants:
      - every fellow with a contact_email should have their hash on the allowlist
      - every hash on the allowlist should map back to at least one fellow email
    Both should be true whenever build_pwa.py runs over the same DB. Drift
    means the allowlist and DB were built from different sources.
    """
    allow = fetch_allowlist_from_prod(host, port, user)
    fellows = fetch_fellow_emails_from_prod(host, port, user)

    fellow_hash_to_fellow: dict[str, dict] = {}
    for f in fellows:
        email = (f.get("email") or "").strip().lower()
        if not email:
            continue
        fellow_hash_to_fellow.setdefault(hash_email(email), f)

    fellow_hashes = set(fellow_hash_to_fellow.keys())

    missing_from_allowlist = [
        fellow_hash_to_fellow[h] for h in fellow_hashes if h not in allow
    ]
    orphans_in_allowlist = sorted(allow - fellow_hashes)

    summary = {
        "allowlist_size": len(allow),
        "fellows_with_email": len(fellows),
        "fellow_distinct_email_hashes": len(fellow_hashes),
        "missing_from_allowlist": missing_from_allowlist,
        "orphans_in_allowlist": orphans_in_allowlist,
        "in_sync": not missing_from_allowlist and not orphans_in_allowlist,
    }
    return summary


def format_dump_report(host: str, summary: dict) -> str:
    lines = [f"Allowlist state on {host}:"]
    lines.append(f"  Allowlist hashes:             {summary['allowlist_size']}")
    lines.append(f"  Fellows with contact_email:   {summary['fellows_with_email']}")
    lines.append(
        f"  Distinct email hashes from DB: {summary['fellow_distinct_email_hashes']}"
    )
    if summary["in_sync"]:
        lines.append("  ✓ In sync — every email hash is on the allowlist and vice versa.")
        return "\n".join(lines) + "\n"

    lines.append("  ✗ Drift detected.")
    missing = summary["missing_from_allowlist"]
    orphans = summary["orphans_in_allowlist"]
    if missing:
        lines.append("")
        lines.append(
            f"  Fellows with email NOT on allowlist ({len(missing)}) — they can't get magic links:"
        )
        for f in missing[:50]:
            lines.append(f"    {f.get('name', '?')}  <{f.get('email', '?')}>")
        if len(missing) > 50:
            lines.append(f"    … {len(missing) - 50} more")
    if orphans:
        lines.append("")
        lines.append(
            f"  Hashes on allowlist with no matching fellow email ({len(orphans)}):"
        )
        for h in orphans[:20]:
            lines.append(f"    {h[:16]}…")
        if len(orphans) > 20:
            lines.append(f"    … {len(orphans) - 20} more")
    lines.append("")
    lines.append(
        "  Drift usually means allowed_emails.json and fellows.db were "
        "generated from different sources. Rebuild both together via "
        "`python build/build_pwa.py` and redeploy."
    )
    return "\n".join(lines) + "\n"


def fetch_postmark_token_from_prod(
    host: str,
    port: str,
    user: str,
    sudo_password: str,
    env_file: str = DEFAULT_ENV_FILE,
) -> str:
    """SSH + `sudo -S cat` the prod env file, return FELLOWS_POSTMARK_TOKEN.

    Raises RuntimeError on any failure (ssh, sudo, missing key). Caller
    should catch and fall through to a clear error message.
    """
    remote_cmd = f"sudo -S -p '' cat {shlex.quote(env_file)}"
    cmd = ["ssh", "-p", str(port), f"{user}@{host}", remote_cmd]
    r = subprocess.run(
        cmd,
        input=sudo_password + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"ssh/sudo cat failed (exit {r.returncode}): "
            + (r.stderr.strip() or "no stderr")
        )
    for line in r.stdout.splitlines():
        if line.startswith("FELLOWS_POSTMARK_TOKEN="):
            val = line.split("=", 1)[1].strip()
            # Strip surrounding quotes if any.
            if len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
                val = val[1:-1]
            if not val:
                raise RuntimeError("FELLOWS_POSTMARK_TOKEN is set to an empty value on prod")
            return val
    raise RuntimeError(f"FELLOWS_POSTMARK_TOKEN not found in {env_file}")


def resolve_postmark_token(
    args,
    sudo_password: str | None,
) -> tuple[str | None, str]:
    """Determine the Postmark token to use, per the documented priority.

    Returns (token_or_None, source_label). Never raises — caller inspects
    token to decide whether to error or proceed without Postmark resolution.
    """
    tok = (args.postmark_token or "").strip()
    if tok:
        return tok, "--postmark-token"
    tok = os.environ.get("FELLOWS_POSTMARK_TOKEN", "").strip()
    if tok:
        return tok, "FELLOWS_POSTMARK_TOKEN env"
    if sudo_password is not None:
        try:
            tok = fetch_postmark_token_from_prod(
                args.host, args.port, args.user, sudo_password
            )
            return tok, "auto-fetched from prod env file"
        except RuntimeError as e:
            sys.stderr.write(f"(Postmark token auto-fetch failed: {e})\n")
            return None, "auto-fetch failed"
    return None, "no source"


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


def _format_allowlist_status(chk: dict) -> list[str]:
    """Render the allowlist check block for the human-readable report."""
    out = ["Allowlist status:"]
    hp = chk["hash"][:16]
    if chk["hit"]:
        out.append(
            f"  HIT — {chk['email']} (hash {hp}…) is in the {chk['allowlist_size']}-entry allowlist."
        )
    else:
        out.append(
            f"  MISS — {chk['email']} (hash {hp}…) is NOT in the {chk['allowlist_size']}-entry allowlist."
        )
        out.append(
            "  The server silently returns {sent: true} for non-allowlisted emails"
        )
        out.append(
            "  (anti-enumeration). No send event is ever logged. This explains"
        )
        out.append(
            "  'no events found' for this address."
        )
    return out


def format_report(
    events: list[dict],
    postmark_lookups: dict[str, dict],
    header_meta: dict,
    allowlist_check: dict | None = None,
) -> str:
    """Human-readable report. Newest-first events + summary."""
    lines: list[str] = []
    lines.append(f"Email delivery report · {header_meta['host']}")
    lines.append(f"Window: since {header_meta['since']!r}  (unit={UNIT})")
    if header_meta.get("filter_desc"):
        lines.append(f"Filter: {header_meta['filter_desc']}")
    lines.append("")
    if allowlist_check is not None:
        lines.extend(_format_allowlist_status(allowlist_check))
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resolve Postmark MessageIDs via the Messages API (default: on). "
        "Token resolution order: --postmark-token > FELLOWS_POSTMARK_TOKEN env "
        "> auto-fetch from prod env file via ssh+sudo (requires --sudo). Pass "
        "--no-postmark to skip entirely.",
    )
    ap.add_argument(
        "--postmark-token",
        metavar="TOKEN",
        help="Postmark Server API token. Alternative to FELLOWS_POSTMARK_TOKEN env "
        "and to auto-fetching from the prod env file.",
    )
    ap.add_argument(
        "--sudo",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run journalctl under sudo on the remote (default: on). Prompts "
        "locally for the password via getpass, then pipes to `sudo -S`. Needed "
        "when the operator isn't in adm / systemd-journal — journalctl silently "
        "hides other users' unit logs otherwise. Pass --no-sudo only if you've "
        "added the operator to the systemd-journal group on prod.",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Echo the SSH command to stderr before running (doesn't include "
        "the sudo password — that's piped in separately).",
    )
    ap.add_argument(
        "--dump-allowlist",
        action="store_true",
        help="Dump the allowlist and cross-reference against the fellows DB on "
        "prod. Doesn't fetch journal events; doesn't need --sudo. Flags drift "
        "(fellow emails missing from allowlist, or allowlist hashes without a "
        "matching fellow email) — both are invariants that should never hold "
        "if allowed_emails.json and fellows.db were built from the same DB.",
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

    if args.dump_allowlist:
        # Short-circuit: no journal fetch, no sudo, no Postmark. Just the
        # allowlist ↔ DB consistency report.
        try:
            summary = dump_allowlist_report(args.host, args.port, args.user)
        except RuntimeError as e:
            sys.stderr.write(f"dump failed: {e}\n")
            return 1
        if args.json:
            print(json.dumps(summary, indent=2, default=str))
        else:
            sys.stdout.write(format_dump_report(args.host, summary))
        return 0 if summary["in_sync"] else 1

    prefix = None
    email_desc = None
    if args.email:
        full = hash_email(args.email)
        prefix = full[:12]
        email_desc = f"{prefix}… ({args.email})"
    elif args.email_hash_prefix:
        prefix = args.email_hash_prefix.lower().strip()
        email_desc = f"{prefix}…"

    # Prompt once for the sudo password if --sudo is set; reuse for both the
    # journalctl fetch and (if needed) the Postmark token auto-fetch, so the
    # user never types it twice.
    sudo_password = None
    if args.sudo:
        sudo_password = getpass.getpass(f"sudo password for {args.user}@{args.host}: ")

    raw = ssh_journal(
        args.host,
        args.port,
        args.user,
        args.since,
        use_sudo=args.sudo,
        verbose=args.verbose,
        sudo_password=sudo_password,
    )
    events = parse_events(raw)
    events = filter_events(events, email_hash_prefix=prefix, result=args.result)
    if args.limit > 0:
        events = events[-args.limit :]

    # Allowlist check: cheap (no sudo, group-readable file) and answers the
    # single most common "no events, no email, why?" question directly.
    allowlist_check: dict | None = None
    if args.email:
        try:
            allow = fetch_allowlist_from_prod(args.host, args.port, args.user)
            allowlist_check = check_allowlist(args.email, allow)
        except RuntimeError as e:
            sys.stderr.write(f"(allowlist check skipped: {e})\n")

    postmark_lookups: dict[str, dict] = {}
    if args.postmark:
        token, source = resolve_postmark_token(args, sudo_password)
        if not token:
            sys.stderr.write(
                "Postmark resolution needs a token. Options:\n"
                "  - pass --postmark-token <TOKEN>\n"
                "  - set FELLOWS_POSTMARK_TOKEN in env\n"
                "  - run with --sudo to auto-fetch from the prod env file\n"
                "  - pass --no-postmark to skip Postmark resolution entirely\n"
            )
            return 2
        if args.verbose:
            sys.stderr.write(f"[verbose] Postmark token source: {source}\n")
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
            "allowlist": allowlist_check,
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
            allowlist_check=allowlist_check,
        )
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
