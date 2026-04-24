#!/usr/bin/env python3
"""Production stats summary for fellows-pwa.

Reads journald for the fellows-pwa unit, tallies requests and structured
events over a time window, adds disk usage, prints to stdout. Stdlib only
so it runs on the droplet without a venv.

Usage:
    prod_stats [--since "24 hours ago"] [--unit fellows-pwa] [--json]
    prod_stats --include-emails   # full-history + plaintext recipient list
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone


# Matches the request-line fragment BaseHTTPRequestHandler writes into every
# access-log line, e.g. '"GET /api/fellows?full=1 HTTP/1.1" 200 -'. The path
# group includes the query string, which is exactly what we want when
# distinguishing /api/fellows from /api/fellows/<slug>.
ACCESS_RE = re.compile(
    r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/\d\.\d" (?P<status>\d{3})'
)

# Plaintext-recipient resolution reads the same sqlite DB the app serves.
# Group-readable (mode 2775, fellows:fellows) so no sudo needed when rsb runs.
FELLOWS_DB_PATH = "/opt/fellows/deploy/dist/fellows.db"


def journal_entries(unit: str, since: str) -> list:
    """Return journalctl -o json entries (dicts) for (unit, since).

    Emits a stderr warning when the call succeeds but returns zero lines —
    almost always the SSH user isn't in systemd-journal/adm and journalctl
    is silently withholding the unit's logs. Previously this failure mode
    was indistinguishable from a real zero-activity window.
    """
    try:
        proc = subprocess.run(
            ["journalctl", "-u", unit, "--since", since, "-o", "json", "--no-pager"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("journalctl not found (not a systemd host?)", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(f"journalctl failed (exit {proc.returncode}): {proc.stderr.strip()}",
              file=sys.stderr)
        return []
    entries = []
    for line in proc.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(entry)
    if not entries:
        print(
            f"WARNING: journalctl returned 0 entries for {unit}.\n"
            "  Almost always this means the SSH user isn't in the\n"
            "  systemd-journal (or adm) group. Run `id` on this host;\n"
            "  if neither group appears, re-run `just bootstrap` from\n"
            "  the operator workstation to re-apply the common role.",
            file=sys.stderr,
        )
    return entries


def _entry_message(entry: dict) -> str | None:
    msg = entry.get("MESSAGE")
    # journalctl can emit MESSAGE as a byte array for non-UTF8 payloads;
    # the fellows-pwa server never emits those, so skip.
    return msg if isinstance(msg, str) else None


def _entry_ts(entry: dict) -> str | None:
    raw = entry.get("__REALTIME_TIMESTAMP")
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


def tally(entries) -> dict:
    """Count request categories, structured events, and per-hash send events."""
    shell_loads = 0
    api_fellows = 0
    db_downloads = 0
    verify_ok = 0
    verify_fail = 0
    errors_5xx: Counter = Counter()
    links_sent = 0
    links_send_failed: Counter = Counter()
    # hash_prefix -> {"events": [{"ts", "result"}, ...]}
    email_events: dict = {}

    for entry in entries:
        m = _entry_message(entry)
        if m is None:
            continue
        ts = _entry_ts(entry)

        # Structured JSON events (emitted on stderr from deploy/server.py).
        if m.startswith("{") and "send_unlock_email" in m:
            try:
                evt = json.loads(m)
            except json.JSONDecodeError:
                evt = None
            if isinstance(evt, dict) and evt.get("event") == "send_unlock_email":
                result = evt.get("result")
                prefix = evt.get("email_hash_prefix")
                if prefix:
                    bucket = email_events.setdefault(prefix, {"events": []})
                    bucket["events"].append({"ts": ts, "result": result})
                if result == "sent":
                    links_sent += 1
                elif isinstance(result, str):
                    links_send_failed[result] += 1
                continue

        # HTTP access log lines.
        match = ACCESS_RE.search(m)
        if not match:
            continue
        method = match.group("method")
        path = match.group("path")
        status = int(match.group("status"))

        path_no_query = path.split("?", 1)[0]

        if method == "GET" and path_no_query in ("/", "/index.html"):
            shell_loads += 1
        if method == "GET" and path_no_query.startswith("/api/fellows"):
            api_fellows += 1
        if method == "GET" and path_no_query == "/fellows.db":
            db_downloads += 1
        if method == "POST" and path_no_query == "/api/verify-token":
            if status == 200:
                verify_ok += 1
            else:
                verify_fail += 1
        if status >= 500:
            errors_5xx[f"{status} {method} {path_no_query}"] += 1

    return {
        "shell_loads": shell_loads,
        "api_fellows": api_fellows,
        "db_downloads": db_downloads,
        "magic_links_sent": links_sent,
        "magic_links_send_failed": dict(links_send_failed),
        "magic_links_verified": verify_ok,
        "magic_links_verify_failed": verify_fail,
        "errors_5xx": dict(errors_5xx),
        "email_events_by_prefix": email_events,
    }


def disk_usage(path: str = "/") -> dict:
    total, used, free = shutil.disk_usage(path)
    pct_used = round(100 * used / total, 1) if total else 0.0
    return {
        "path": path,
        "total_gib": round(total / 2 ** 30, 1),
        "used_gib": round(used / 2 ** 30, 1),
        "free_gib": round(free / 2 ** 30, 1),
        "pct_used": pct_used,
    }


def build_email_hash_index(db_path: str = FELLOWS_DB_PATH) -> dict:
    """Map sha256(lower(trim(contact_email))) → {'email','name'} for every fellow.

    Empty dict on any error (plus a stderr note) so the caller can still
    emit a recipient list with '<unknown>' placeholders.
    """
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        print(f"Cannot open fellows DB {db_path}: {exc}", file=sys.stderr)
        return {}
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT name, lower(trim(contact_email)) AS email "
            "FROM fellows WHERE contact_email IS NOT NULL "
            "AND trim(contact_email) != ''"
        )
        out: dict = {}
        for row in cur.fetchall():
            email = row["email"]
            if not email:
                continue
            h = hashlib.sha256(email.encode("utf-8")).hexdigest()
            out[h] = {"email": email, "name": row["name"] or ""}
        return out
    finally:
        conn.close()


def resolve_recipients(email_events: dict, hash_index: dict) -> list:
    """Join hash prefixes to plaintext emails. Sorted newest-last-sent first."""
    rows = []
    for prefix, data in email_events.items():
        events = data.get("events", [])
        matches = [(h, hash_index[h]) for h in hash_index if h.startswith(prefix)]
        result_counter: Counter = Counter()
        timestamps = []
        for e in events:
            r = e.get("result") or "unknown"
            result_counter[r] += 1
            if e.get("ts"):
                timestamps.append(e["ts"])
        timestamps.sort()
        first_ts = timestamps[0] if timestamps else None
        last_ts = timestamps[-1] if timestamps else None

        base = {
            "prefix": prefix,
            "sent": result_counter.get("sent", 0),
            "results": dict(result_counter),
            "first_ts": first_ts,
            "last_ts": last_ts,
        }
        if not matches:
            rows.append({**base, "email": None, "name": None, "collisions": 0})
        else:
            for _h, meta in matches:
                rows.append({**base, "email": meta["email"], "name": meta["name"],
                             "collisions": len(matches) - 1})

    rows.sort(key=lambda r: (r["last_ts"] or ""), reverse=True)
    return rows


def print_human(
    stats: dict, disk: dict, since: str, unit: str,
    recipients: list | None = None,
) -> None:
    print(f"== {unit} — since {since} ==")
    print(f"  App-shell loads:         {stats['shell_loads']}")
    print(f"  Directory API hits:      {stats['api_fellows']}")
    print(f"  DB downloads:            {stats['db_downloads']}")
    print(f"  Magic links sent:        {stats['magic_links_sent']}")
    for result, count in sorted(stats["magic_links_send_failed"].items()):
        print(f"    └─ send {result:12s} {count}")
    print(f"  Magic links verified:    {stats['magic_links_verified']}")
    if stats["magic_links_verify_failed"]:
        print(f"  Magic links rejected:    {stats['magic_links_verify_failed']}")
    total_5xx = sum(stats["errors_5xx"].values())
    print(f"  5xx errors:              {total_5xx}")
    for line, count in sorted(stats["errors_5xx"].items(), key=lambda kv: -kv[1])[:5]:
        print(f"    └─ {line}: {count}")
    print(
        f"  Disk ({disk['path']}):  "
        f"{disk['used_gib']:.1f} / {disk['total_gib']:.1f} GiB used "
        f"({disk['pct_used']:.1f}%, {disk['free_gib']:.1f} GiB free)"
    )
    if recipients is not None:
        _print_recipients(recipients)


def _print_recipients(recipients: list) -> None:
    print("")
    print("-- Magic-link recipients (plaintext; confidential) --")
    if not recipients:
        print("  (no send events in window)")
        return
    noun = "recipient" if len(recipients) == 1 else "recipients"
    print(f"  {len(recipients)} unique {noun}, most recent first:")
    for r in recipients:
        who = r["email"] or f"<unknown prefix={r['prefix']}>"
        name = f"  ({r['name']})" if r.get("name") else ""
        sent = r["sent"]
        others = {k: v for k, v in (r.get("results") or {}).items() if k != "sent"}
        extra = "  " + " ".join(f"{k}:{v}" for k, v in sorted(others.items())) if others else ""
        last = r.get("last_ts") or "—"
        print(f"  {who:40s} sent:{sent:<3d} last:{last}{extra}{name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", default=None,
        help="Time window passed to journalctl --since. "
        "Default: '24 hours ago' (or '@0' when --include-emails is set).",
    )
    parser.add_argument(
        "--unit", default="fellows-pwa",
        help="Systemd unit to read (default: fellows-pwa)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit machine-readable JSON instead of human text",
    )
    parser.add_argument(
        "--disk-path", default="/",
        help="Path for disk usage (default: /)",
    )
    parser.add_argument(
        "--include-emails", action="store_true",
        help="List plaintext recipient email for every magic-link send event "
        "(joined against /opt/fellows/deploy/dist/fellows.db). When set and "
        "--since is omitted, the window defaults to '@0' (full journal).",
    )
    args = parser.parse_args(argv)

    if args.since is None:
        args.since = "@0" if args.include_emails else "24 hours ago"

    entries = journal_entries(args.unit, args.since)
    stats = tally(entries)
    disk = disk_usage(args.disk_path)

    recipients = None
    if args.include_emails:
        hash_index = build_email_hash_index()
        recipients = resolve_recipients(stats["email_events_by_prefix"], hash_index)

    # Keep the public JSON shape stable — strip the internal per-prefix bucket.
    public_stats = {k: v for k, v in stats.items() if k != "email_events_by_prefix"}

    if args.as_json:
        payload = {
            "unit": args.unit,
            "since": args.since,
            "requests": public_stats,
            "disk": disk,
        }
        if args.include_emails:
            payload["recipients"] = recipients
        print(json.dumps(payload, sort_keys=True))
    else:
        print_human(public_stats, disk, args.since, args.unit, recipients=recipients)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
