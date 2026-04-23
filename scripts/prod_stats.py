#!/usr/bin/env python3
"""Production stats summary for fellows-pwa.

Reads journald for the fellows-pwa unit, tallies requests and structured
events over a time window, adds disk usage, prints to stdout. Stdlib only
so it runs on the droplet without a venv.

Usage:
    prod_stats [--since "24 hours ago"] [--unit fellows-pwa] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter


# Matches the request-line fragment BaseHTTPRequestHandler writes into every
# access-log line, e.g. '"GET /api/fellows?full=1 HTTP/1.1" 200 -'. The path
# group includes the query string, which is exactly what we want when
# distinguishing /api/fellows from /api/fellows/<slug>.
ACCESS_RE = re.compile(
    r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/\d\.\d" (?P<status>\d{3})'
)


def journal_messages(unit: str, since: str) -> list:
    """Return MESSAGE strings from journalctl for (unit, since).

    Returns [] on any journalctl failure, after printing a hint on stderr.
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
    messages = []
    for line in proc.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("MESSAGE")
        if isinstance(msg, str):
            messages.append(msg)
    return messages


def tally(messages) -> dict:
    """Count request categories and structured events from MESSAGE strings."""
    shell_loads = 0
    api_fellows = 0
    db_downloads = 0
    verify_ok = 0
    verify_fail = 0
    errors_5xx: Counter = Counter()
    links_sent = 0
    links_send_failed: Counter = Counter()

    for m in messages:
        # Structured JSON events (emitted on stderr from deploy/server.py).
        if m.startswith("{") and "send_unlock_email" in m:
            try:
                evt = json.loads(m)
            except json.JSONDecodeError:
                evt = None
            if isinstance(evt, dict) and evt.get("event") == "send_unlock_email":
                result = evt.get("result")
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


def print_human(stats: dict, disk: dict, since: str, unit: str) -> None:
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", default="24 hours ago",
        help="Time window passed to journalctl --since (default: '24 hours ago')",
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
    args = parser.parse_args(argv)

    messages = journal_messages(args.unit, args.since)
    stats = tally(messages)
    disk = disk_usage(args.disk_path)

    if args.as_json:
        print(json.dumps({
            "unit": args.unit,
            "since": args.since,
            "requests": stats,
            "disk": disk,
        }, sort_keys=True))
    else:
        print_human(stats, disk, args.since, args.unit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
