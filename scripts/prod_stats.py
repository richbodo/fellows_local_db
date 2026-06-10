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
from collections.abc import Iterator
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


def journal_entries(unit: str, since: str) -> Iterator[dict]:
    """Yield journalctl -o json entries (dicts) for (unit, since), one at a time.

    Streams the subprocess output line-by-line rather than buffering the whole
    journal into memory. The full-history scan (`--since @0`, what
    --include-emails forces) is >100 MB of JSON across >100k lines on a
    long-lived host; the old `capture_output=True` + `.splitlines()` +
    list-of-dicts approach peaked at ~700 MB of resident Python objects and
    was OOM-killed on the 1 GB / no-swap prod droplet — surfacing as a
    messageless `ssh` exit 255. Streaming keeps peak memory flat regardless
    of journal size; ``tally`` consumes this generator in a single pass.

    Emits a stderr warning when the call succeeds but yields zero entries —
    almost always the SSH user isn't in systemd-journal/adm and journalctl
    is silently withholding the unit's logs. Previously this failure mode
    was indistinguishable from a real zero-activity window.
    """
    try:
        proc = subprocess.Popen(
            ["journalctl", "-u", unit, "--since", since, "-o", "json", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print("journalctl not found (not a systemd host?)", file=sys.stderr)
        return
    count = 0
    # proc.stdout is a line-iterable text stream; each line is one JSON entry.
    for line in proc.stdout:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        count += 1
        yield entry
    proc.stdout.close()
    # journalctl writes little to stderr (warnings only), so reading it after
    # stdout is drained won't deadlock in practice.
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    returncode = proc.wait()
    if returncode != 0:
        print(f"journalctl failed (exit {returncode}): {stderr.strip()}",
              file=sys.stderr)
        return
    if count == 0:
        print(
            f"WARNING: journalctl returned 0 entries for {unit}.\n"
            "  Almost always this means the SSH user isn't in the\n"
            "  systemd-journal (or adm) group. Run `id` on this host;\n"
            "  if neither group appears, re-run `just bootstrap` from\n"
            "  the operator workstation to re-apply the common role.",
            file=sys.stderr,
        )


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


RECENT_ERRORS_CAP = 10


def tally(entries) -> dict:
    """Count request categories, structured events, and per-hash send events."""
    shell_loads = 0
    api_fellows = 0
    db_downloads = 0
    verify_ok = 0
    verify_fail = 0
    errors_4xx: Counter = Counter()
    errors_5xx: Counter = Counter()
    # User-submitted client-error reports (POST /api/client-errors). The
    # server already sanitizes before emitting (deploy/client_error_sanitizer.py)
    # so anything reaching us here is safe to surface in the triage view.
    client_errors_count = 0
    # Install-funnel events nested inside client_error payloads
    # (kind=install). Bucketed by `msg` so the operator can read off
    # the funnel without parsing JSON. Platform breakdowns for outcome_*
    # come from the event's `extra` field.
    install_funnel: Counter = Counter()
    install_outcome_platforms: dict = {}  # msg -> Counter[platform]
    # All 4xx/5xx access lines + client_error events, captured verbatim for
    # `--errors-only` recall. We over-collect here and trim at the end so
    # the order of the input stream doesn't matter.
    recent_errors_buf: list = []
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

        # Client-error reports (POST /api/client-errors → event=client_error).
        # Sort key uses status=0 so they cluster behind same-ts access lines
        # without disturbing the existing "newest 4xx/5xx first" ordering.
        if m.startswith("{") and "client_error" in m:
            try:
                evt = json.loads(m)
            except json.JSONDecodeError:
                evt = None
            if isinstance(evt, dict) and evt.get("event") == "client_error":
                client_errors_count += 1
                # Install-funnel events ride inside the client_error
                # payload as nested `events` items with kind=install.
                # The sanitizer already validated the kind allowlist
                # server-side, so we trust what we see here.
                for inner in evt.get("events") or []:
                    if not isinstance(inner, dict):
                        continue
                    if inner.get("kind") != "install":
                        continue
                    msg = inner.get("msg")
                    if not isinstance(msg, str):
                        continue
                    install_funnel[msg] += 1
                    if msg.startswith("outcome_"):
                        platform = (inner.get("extra") or "").strip() or "(none)"
                        install_outcome_platforms.setdefault(msg, Counter())[platform] += 1
                recent_errors_buf.append((ts or "", 0, m, "client_error"))
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
        elif status >= 400:
            errors_4xx[f"{status} {method} {path_no_query}"] += 1
        if status >= 400:
            recent_errors_buf.append((ts or "", status, m, "access"))

    # Newest first, capped. Sorts on ts then status so a tie on missing ts
    # still gives a stable order rather than relying on input order.
    recent_errors_buf.sort(key=lambda t: (t[0], t[1]), reverse=True)
    recent_errors = [
        {"ts": t, "status": s, "message": msg, "kind": k}
        for (t, s, msg, k) in recent_errors_buf[:RECENT_ERRORS_CAP]
    ]

    return {
        "shell_loads": shell_loads,
        "api_fellows": api_fellows,
        "db_downloads": db_downloads,
        "magic_links_sent": links_sent,
        "magic_links_send_failed": dict(links_send_failed),
        "magic_links_verified": verify_ok,
        "magic_links_verify_failed": verify_fail,
        "errors_4xx": dict(errors_4xx),
        "errors_5xx": dict(errors_5xx),
        "client_errors": client_errors_count,
        "install_funnel": dict(install_funnel),
        "install_outcome_platforms": {
            k: dict(v) for k, v in install_outcome_platforms.items()
        },
        "recent_errors": recent_errors,
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
    errors_only: bool = False,
) -> None:
    print(f"== {unit} — since {since} ==")
    if not errors_only:
        print(f"  App-shell loads:         {stats['shell_loads']}")
        print(f"  Directory API hits:      {stats['api_fellows']}")
        print(f"  DB downloads:            {stats['db_downloads']}")
        print(f"  Magic links sent:        {stats['magic_links_sent']}")
        for result, count in sorted(stats["magic_links_send_failed"].items()):
            print(f"    └─ send {result:12s} {count}")
        print(f"  Magic links verified:    {stats['magic_links_verified']}")
        if stats["magic_links_verify_failed"]:
            print(f"  Magic links rejected:    {stats['magic_links_verify_failed']}")
    total_4xx = sum(stats.get("errors_4xx", {}).values())
    print(f"  4xx errors:              {total_4xx}")
    for line, count in sorted(stats.get("errors_4xx", {}).items(), key=lambda kv: -kv[1])[:5]:
        print(f"    └─ {line}: {count}")
    total_5xx = sum(stats["errors_5xx"].values())
    print(f"  5xx errors:              {total_5xx}")
    for line, count in sorted(stats["errors_5xx"].items(), key=lambda kv: -kv[1])[:5]:
        print(f"    └─ {line}: {count}")
    client_errors = int(stats.get("client_errors", 0) or 0)
    print(f"  Client error reports:    {client_errors}")
    if not errors_only:
        _print_install_funnel(stats)
    if errors_only:
        recent = stats.get("recent_errors") or []
        print("")
        print(f"-- {len(recent)} most recent error entry(ies) --")
        if not recent:
            print("  (none in window)")
        else:
            for r in recent:
                ts = r.get("ts") or "—"
                kind = r.get("kind") or "access"
                tag = "[client_error] " if kind == "client_error" else ""
                print(f"  [{ts}] {tag}{r.get('message', '')}")
        return
    print(
        f"  Disk ({disk['path']}):  "
        f"{disk['used_gib']:.1f} / {disk['total_gib']:.1f} GiB used "
        f"({disk['pct_used']:.1f}%, {disk['free_gib']:.1f} GiB free)"
    )
    if recipients is not None:
        _print_recipients(recipients)


# Display order for the install funnel — chronological-ish through the
# happy path, then the alternate ("escape hatch") and edge cases.
# Names not in this list still surface, after the named ones, in
# alphabetical order.
_INSTALL_FUNNEL_DISPLAY_ORDER = [
    "landing_shown",
    "ios_safari_advised",
    "before_prompt_fired",
    "before_prompt_never_arrived",
    "button_clicked",
    "button_clicked_no_prompt",
    "outcome_accepted",
    "outcome_dismissed",
    "outcome_unknown",
    "outcome_error",
    "app_installed",
    "use_in_tab_clicked",
]


def _print_install_funnel(stats: dict) -> None:
    """Render the install-funnel section if there are any events to show.

    No data → no section, to avoid noise on hosts that haven't seen any
    install activity in the window. The denominator (`landing_shown`) is
    surfaced first; per-step counts follow in the canonical happy-path
    order. `outcome_*` events get a parenthetical platform breakdown
    when the client supplied one in `extra` (typically `web` for
    Chrome/Edge desktop or Android).
    """
    funnel = stats.get("install_funnel") or {}
    if not funnel:
        return
    platforms = stats.get("install_outcome_platforms") or {}

    print("  Install funnel:")
    seen = set()
    for name in _INSTALL_FUNNEL_DISPLAY_ORDER:
        count = funnel.get(name)
        if not count:
            continue
        seen.add(name)
        plat = platforms.get(name)
        plat_suffix = ""
        if plat:
            parts = [f"{p}:{c}" for p, c in sorted(plat.items(), key=lambda kv: -kv[1])]
            plat_suffix = "  (" + ", ".join(parts) + ")"
        print(f"    {name:32s} {count}{plat_suffix}")
    # Anything the client started reporting that we don't know about yet.
    extras = sorted(name for name in funnel.keys() if name not in seen)
    for name in extras:
        print(f"    {name:32s} {funnel[name]}")


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
    parser.add_argument(
        "--errors-only", action="store_true",
        help="Print only 4xx/5xx counters and the most recent error access "
        "lines. Useful for triaging a user-reported error code.",
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
        print_human(
            public_stats, disk, args.since, args.unit,
            recipients=recipients, errors_only=args.errors_only,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
