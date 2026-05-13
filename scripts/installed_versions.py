#!/usr/bin/env python3
"""Installed-version inventory for fellows-pwa, joined to plaintext email.

Reads journald for two structured events plus one
``event=send_unlock_email`` join hop:

  * ``event=verify_token result=ok``        → ``token_prefix → (build_label, ua, ts)``
  * ``event=send_unlock_email result=sent`` → ``token_prefix → email_hash_prefix``
  * ``event=client_error`` w/ ``kind=boot`` → ``lastSubmitHashPrefix → (build, ua, ts, extra)``

Joins ``email_hash_prefix`` → plaintext ``contact_email`` via
``/opt/fellows/deploy/dist/fellows.db`` (prefix match on
``sha256(lower(trim(email)))[:12]`` — the same scheme
``deploy/server.py`` uses when emitting ``email_hash_prefix``).

Output answers: *for every fellow with attributed activity, what build
did they install on, what build is their PWA currently running, and how
long ago did we last see them?* The gap between ``installed_build`` and
``seen_build`` is the load-bearing diagnostic — equal == healthy, drift
== a SW update path that didn't take.

Stdlib only so it runs on the droplet without a venv. Same
``systemd-journal``/``adm`` group membership as ``prod_stats`` —
operator runs it without sudo.

Usage:
    installed_versions [--since "30 days ago"] [--unit fellows-pwa]
                       [--json]

Output is plaintext-confidential — the recipient list joins back to
emails. Same posture as ``prod_stats --include-emails``.

See ``plans/install_version_telemetry.md`` for the full A→B→C plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


# Group-readable (mode 2775, fellows:fellows) — no sudo needed when rsb runs.
FELLOWS_DB_PATH = "/opt/fellows/deploy/dist/fellows.db"

# Default window. 30 days is the right starting point: long enough that
# most installed users have opened the app at least once and emitted a
# kind=boot event; short enough that the journald scan is fast even on
# a small droplet. Operator can widen with --since '@0' for full history.
DEFAULT_SINCE = "30 days ago"


def journal_entries(unit: str, since: str) -> list:
    """Run ``journalctl -o json`` and return a list of parsed entries.

    Mirrors ``prod_stats.journal_entries`` — emits a stderr hint when
    the call succeeds with zero entries (almost always a group-membership
    miss on systemd-journal / adm).
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
        print(
            f"journalctl failed (exit {proc.returncode}): {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    entries = []
    for line in proc.stdout.splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
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


def _parse_struct_event(message: str, expected: str) -> dict | None:
    """Return the parsed event dict iff ``MESSAGE`` is a JSON line whose
    ``event`` field equals ``expected``. Cheap pre-filter via substring
    test keeps the JSON-decode off the hot path."""
    if not message.startswith("{") or expected not in message:
        return None
    try:
        evt = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(evt, dict) or evt.get("event") != expected:
        return None
    return evt


def collect(entries: list) -> dict:
    """Bucketize the three event kinds we care about. Returns a dict with:

      ``send_token_to_email_prefix``: ``token_prefix → email_hash_prefix``
          (12 hex). Built from ``send_unlock_email result=sent``. Used
          to translate verify_token records into the canonical email
          key. Most-recent send wins on collision (token_prefix is
          random 12 hex; collisions are vanishingly rare).
      ``verify_by_token_prefix``: ``token_prefix → {build_label, ua, ts}``
          Most-recent verify_token result=ok wins on the same key.
      ``boot_by_email_prefix``: ``lastSubmitHashPrefix → {build, ua, ts, extra}``
          Most-recent kind=boot client_error wins on the same key.
      ``anonymous_boots``: list of ``{build, ua, ts}`` for boots with
          no ``lastSubmitHashPrefix`` (Clear App Cache'd, never gated).
    """
    send_token_to_email_prefix: dict = {}
    verify_by_token_prefix: dict = {}
    boot_by_email_prefix: dict = {}
    anonymous_boots: list = []

    for entry in entries:
        m = _entry_message(entry)
        if m is None:
            continue
        ts = _entry_ts(entry) or ""

        evt = _parse_struct_event(m, "send_unlock_email")
        if evt is not None:
            if evt.get("result") == "sent":
                tp = evt.get("token_prefix")
                ep = evt.get("email_hash_prefix")
                if tp and ep:
                    # Most-recent send wins. The same token_prefix
                    # shouldn't appear twice (random 12-hex), but if it
                    # did we want the freshest binding.
                    prev = send_token_to_email_prefix.get(tp)
                    if prev is None or ts >= prev.get("ts", ""):
                        send_token_to_email_prefix[tp] = {"email_prefix": ep, "ts": ts}
            continue

        evt = _parse_struct_event(m, "verify_token")
        if evt is not None:
            if evt.get("result") == "ok":
                tp = evt.get("token_prefix")
                if tp:
                    prev = verify_by_token_prefix.get(tp)
                    if prev is None or ts >= prev.get("ts", ""):
                        verify_by_token_prefix[tp] = {
                            "build_label": evt.get("build_label") or "",
                            "ua": evt.get("user_agent") or "",
                            "ts": ts,
                        }
            continue

        evt = _parse_struct_event(m, "client_error")
        if evt is not None:
            inner_events = evt.get("events") or []
            if not (isinstance(inner_events, list) and inner_events):
                continue
            first = inner_events[0]
            if not isinstance(first, dict) or first.get("kind") != "boot":
                continue
            build = evt.get("build") or ""
            ua = evt.get("ua") or ""
            extra = first.get("extra") or ""
            email_prefix = evt.get("lastSubmitHashPrefix")
            record = {"build": build, "ua": ua, "ts": ts, "extra": extra}
            if isinstance(email_prefix, str) and email_prefix:
                prev = boot_by_email_prefix.get(email_prefix)
                if prev is None or ts >= prev.get("ts", ""):
                    boot_by_email_prefix[email_prefix] = record
            else:
                anonymous_boots.append(record)
            continue

    return {
        "send_token_to_email_prefix": send_token_to_email_prefix,
        "verify_by_token_prefix": verify_by_token_prefix,
        "boot_by_email_prefix": boot_by_email_prefix,
        "anonymous_boots": anonymous_boots,
    }


def build_email_hash_index(db_path: str = FELLOWS_DB_PATH) -> dict:
    """Map ``sha256(lower(trim(contact_email)))`` → ``{'email','name'}``.

    Empty dict on any error (plus a stderr note). Kept local so this
    script stays single-file. The existence check is necessary because
    ``sqlite3.connect`` creates an empty DB on a missing path rather
    than raising — the failure would surface much later as
    ``OperationalError: no such table: fellows``.
    """
    if not os.path.isfile(db_path):
        print(f"Cannot open fellows DB {db_path}: not a file", file=sys.stderr)
        return {}
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        print(f"Cannot open fellows DB {db_path}: {exc}", file=sys.stderr)
        return {}
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT name, lower(trim(contact_email)) AS email "
                "FROM fellows WHERE contact_email IS NOT NULL "
                "AND trim(contact_email) != ''"
            )
        except sqlite3.OperationalError as exc:
            print(f"fellows.db schema mismatch ({db_path}): {exc}", file=sys.stderr)
            return {}
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


def attribute(collected: dict, hash_index: dict) -> dict:
    """Build the per-email attribution table from the bucketed events.

    Returns a dict with:
      ``rows``: list of per-email rows, each carrying both
        ``installed_*`` (from verify_token via send_unlock_email) and
        ``seen_*`` (from kind=boot). Sorted by ``last_activity`` desc.
      ``anonymous_count``: int — boots we can't attribute to an email.
      ``anonymous_builds``: ``build_label → count`` — useful even
        without identity ("23 anonymous users on 2026-05-08-abc").
    """
    # Step 1: translate verify_token records into per-email-prefix records.
    # The same email may have multiple verify_token events across different
    # tokens (each magic-link click is a new token); we keep the most
    # recent per email_prefix.
    verify_by_email_prefix: dict = {}
    for token_prefix, vrec in collected["verify_by_token_prefix"].items():
        join = collected["send_token_to_email_prefix"].get(token_prefix)
        if not join:
            # verify_token without a matching send: the original send is
            # outside the journald window. Skip — we can't attribute it.
            continue
        email_prefix = join["email_prefix"]
        prev = verify_by_email_prefix.get(email_prefix)
        if prev is None or vrec["ts"] >= prev["ts"]:
            verify_by_email_prefix[email_prefix] = vrec

    # Step 2: union of email prefixes that have ANY attributed signal.
    all_prefixes: set = set(verify_by_email_prefix.keys()) | set(
        collected["boot_by_email_prefix"].keys()
    )

    rows = []
    for prefix in all_prefixes:
        verify = verify_by_email_prefix.get(prefix)
        boot = collected["boot_by_email_prefix"].get(prefix)

        # Prefix-match join to fellows.db (same scheme prod_stats uses).
        matches = [(h, meta) for h, meta in hash_index.items() if h.startswith(prefix)]

        installed_build = verify["build_label"] if verify else ""
        installed_ts = verify["ts"] if verify else ""
        installed_ua = verify["ua"] if verify else ""

        seen_build = boot["build"] if boot else ""
        seen_ts = boot["ts"] if boot else ""
        seen_ua = boot["ua"] if boot else ""
        seen_extra = boot["extra"] if boot else ""

        # Last activity = max(installed_ts, seen_ts). Drives table sort.
        last_activity = max(installed_ts, seen_ts)
        # Display UA = whichever signal is fresher (or whichever exists).
        if seen_ts and seen_ts >= installed_ts:
            last_ua = seen_ua
        else:
            last_ua = installed_ua

        # Healthy = installed_build matches seen_build OR one side is
        # absent (data we can't compare). Mismatch = stale shell.
        stuck = bool(installed_build and seen_build and installed_build != seen_build)

        base = {
            "email_prefix": prefix,
            "installed_build": installed_build,
            "installed_ts": installed_ts,
            "installed_ua": installed_ua,
            "seen_build": seen_build,
            "seen_ts": seen_ts,
            "seen_ua": seen_ua,
            "seen_extra": seen_extra,
            "last_activity": last_activity,
            "last_ua": last_ua,
            "stuck": stuck,
        }
        if not matches:
            rows.append({**base, "email": None, "name": None, "collisions": 0})
        else:
            collisions = len(matches) - 1
            for _h, meta in matches:
                rows.append({
                    **base,
                    "email": meta["email"],
                    "name": meta["name"],
                    "collisions": collisions,
                })

    rows.sort(key=lambda r: r["last_activity"], reverse=True)

    # Histogram of anonymous boots by build, useful for "N people on X".
    anonymous_builds: dict = {}
    for rec in collected["anonymous_boots"]:
        b = rec.get("build") or "(unknown)"
        anonymous_builds[b] = anonymous_builds.get(b, 0) + 1

    return {
        "rows": rows,
        "anonymous_count": len(collected["anonymous_boots"]),
        "anonymous_builds": anonymous_builds,
    }


def _fmt_build(s: str) -> str:
    return s or "—"


def _fmt_ts(s: str) -> str:
    """Trim a Z-suffixed ISO timestamp to its date portion for readability."""
    if not s:
        return "—"
    return s.split("T", 1)[0]


def _fmt_ua(s: str, cap: int = 60) -> str:
    if not s:
        return "—"
    if len(s) <= cap:
        return s
    return s[: cap - 1] + "…"


def print_human(attribution: dict, since: str, unit: str) -> None:
    rows = attribution["rows"]
    print(f"== installed-versions — since {since} (plaintext; confidential) ==")
    print(f"  unit: {unit}")
    print("")
    if not rows:
        print("  (no attributed verify_token / kind=boot events in window)")
    else:
        noun = "fellow" if len(rows) == 1 else "fellows"
        print(f"  {len(rows)} attributed {noun}, most-recent activity first:")
        print("")
        for r in rows:
            who = r["email"] or f"<unknown prefix={r['email_prefix']}>"
            name = f"  ({r['name']})" if r.get("name") else ""
            collisions = (
                f"  (prefix collides with {r['collisions']} other fellow(s))"
                if r.get("collisions")
                else ""
            )
            stuck_tag = "  ⚠ STUCK" if r.get("stuck") else ""
            print(f"  {who}{name}{collisions}{stuck_tag}")
            print(
                f"    installed: {_fmt_build(r['installed_build']):24s}"
                f"  {_fmt_ts(r['installed_ts']):10s}"
                f"  ua: {_fmt_ua(r['installed_ua'])}"
            )
            seen_extra = f"  ({r['seen_extra']})" if r.get("seen_extra") else ""
            print(
                f"    seen:      {_fmt_build(r['seen_build']):24s}"
                f"  {_fmt_ts(r['seen_ts']):10s}"
                f"  ua: {_fmt_ua(r['seen_ua'])}{seen_extra}"
            )

    anon_count = attribution["anonymous_count"]
    if anon_count:
        print("")
        plural = "" if anon_count == 1 else "s"
        print(f"-- Anonymous boots (no gate submit in localStorage): {anon_count} event{plural} --")
        for build, count in sorted(
            attribution["anonymous_builds"].items(), key=lambda kv: -kv[1]
        ):
            print(f"  {build:32s} {count}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"journalctl --since window (default: '{DEFAULT_SINCE}'). "
        "'@0' for full retained journal.",
    )
    parser.add_argument(
        "--unit",
        default="fellows-pwa",
        help="Systemd unit to read (default: fellows-pwa).",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human table.",
    )
    args = parser.parse_args(argv)

    entries = journal_entries(args.unit, args.since)
    collected = collect(entries)
    hash_index = build_email_hash_index()
    attribution = attribute(collected, hash_index)

    if args.as_json:
        payload = {
            "unit": args.unit,
            "since": args.since,
            "rows": attribution["rows"],
            "anonymous_count": attribution["anonymous_count"],
            "anonymous_builds": attribution["anonymous_builds"],
        }
        print(json.dumps(payload, sort_keys=True))
    else:
        print_human(attribution, args.since, args.unit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
