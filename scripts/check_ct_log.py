#!/usr/bin/env python3
"""Certificate Transparency spot-check for a domain via crt.sh.

Lists every logged certificate covering ``<domain>`` and its subdomains and
flags any issued by a CA other than the expected one (Let's Encrypt). A cert
you didn't trigger — e.g. one a rogue CA issued despite the CAA records — shows
up here the same day it's logged, rather than after a user reports a problem.

Read-only. Python stdlib only. Complements the crt.sh *email* alerts documented
in docs/DevOps.md § Certificate Transparency monitoring: this is the on-demand
half (`just ct-check`); the email subscription is the push half.

Usage:
    scripts/check_ct_log.py                          # default domain globaldonut.com
    scripts/check_ct_log.py --domain example.com
    scripts/check_ct_log.py --allow-issuer "Let's Encrypt" --allow-issuer "Google Trust"
    scripts/check_ct_log.py --json

Exit status: 0 if every cert is from an allowed issuer (or the lookup couldn't
run), 1 if any cert is from an unexpected issuer.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

CRT_SH = "https://crt.sh/"
DEFAULT_DOMAIN = "globaldonut.com"
DEFAULT_ALLOWED = ["Let's Encrypt"]
DISPLAY_LIMIT = 25


def fetch_crtsh(query: str, timeout: int = 30) -> list[dict]:
    """GET crt.sh JSON for one identity query. Returns [] on any failure
    (with a stderr note) so the caller can degrade gracefully rather than
    crash on a slow/rate-limited crt.sh."""
    url = CRT_SH + "?" + urllib.parse.urlencode({"q": query, "output": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "fellows-ct-check/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as e:
        sys.stderr.write(f"crt.sh query failed for {query!r}: {e}\n")
        return []
    if not body.strip():
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # crt.sh occasionally returns an HTML error/rate-limit page with a 200.
        sys.stderr.write(f"crt.sh returned non-JSON for {query!r} (rate-limited?).\n")
        return []
    return data if isinstance(data, list) else []


def collect_certs(domain: str) -> list[dict]:
    """Fetch certs for the apex and its subdomains, de-duplicated by crt.sh id.

    crt.sh identity matching is exact, so we query both the bare domain (apex
    certs) and the ``%.`` wildcard form (subdomain certs, including the fellows
    host) and merge.
    """
    merged: dict = {}
    for q in (domain, "%." + domain):
        for row in fetch_crtsh(q):
            cid = row.get("id")
            key = cid if cid is not None else json.dumps(row, sort_keys=True)
            merged[key] = row
    rows = list(merged.values())
    # Newest first by not_before (string ISO sorts chronologically).
    rows.sort(key=lambda r: r.get("not_before") or "", reverse=True)
    return rows


def issuer_allowed(issuer_name: str, allowed: list[str]) -> bool:
    n = (issuer_name or "").lower()
    return any(a.lower() in n for a in allowed)


def analyze(rows: list[dict], allowed: list[str]) -> dict:
    unexpected = [r for r in rows if not issuer_allowed(r.get("issuer_name", ""), allowed)]
    return {
        "total": len(rows),
        "unexpected_count": len(unexpected),
        "unexpected": unexpected,
        "rows": rows,
    }


def _issuer_short(issuer_name: str) -> str:
    # issuer_name is an RFC4514-ish DN, e.g. "C=US, O=Let's Encrypt, CN=R11".
    parts = dict(
        p.split("=", 1) for p in issuer_name.split(", ") if "=" in p
    ) if issuer_name else {}
    return parts.get("O") or issuer_name or "(unknown)"


def print_human(domain: str, result: dict, allowed: list[str]) -> None:
    rows = result["rows"]
    print(f"== Certificate Transparency check · {domain} (and subdomains) ==")
    print(f"Allowed issuer(s): {', '.join(allowed)}")
    print(f"Certificates logged: {result['total']}")
    if not rows:
        print("  (no certs found — crt.sh may be unreachable, or the domain is new)")
        return
    shown = rows[:DISPLAY_LIMIT]
    print(f"\nMost recent {len(shown)} (newest first):")
    for r in shown:
        flag = "" if issuer_allowed(r.get("issuer_name", ""), allowed) else "  ⚠ UNEXPECTED ISSUER"
        name = (r.get("common_name") or (r.get("name_value") or "").splitlines()[0] or "?")
        print(
            f"  {r.get('not_before','?')[:10]} → {r.get('not_after','?')[:10]}  "
            f"{name:38.38s}  [{_issuer_short(r.get('issuer_name',''))}]{flag}"
        )
    if len(rows) > DISPLAY_LIMIT:
        print(f"  … {len(rows) - DISPLAY_LIMIT} older not shown")
    print("")
    if result["unexpected_count"]:
        print(
            f"✗ {result['unexpected_count']} certificate(s) from an unexpected issuer. "
            "If you did not request these, a CA may have mis-issued — investigate now."
        )
    else:
        print("✓ Every logged certificate is from an allowed issuer.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"Domain to check (default: {DEFAULT_DOMAIN}).")
    ap.add_argument(
        "--allow-issuer",
        action="append",
        default=None,
        help="Issuer-name substring to treat as expected (repeatable). "
        "Default: \"Let's Encrypt\".",
    )
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of the formatted report.")
    args = ap.parse_args(argv)
    allowed = args.allow_issuer or DEFAULT_ALLOWED

    rows = collect_certs(args.domain)
    result = analyze(rows, allowed)

    if args.json:
        print(json.dumps(
            {"domain": args.domain, "allowed_issuers": allowed, **result},
            indent=2, default=str,
        ))
    else:
        print_human(args.domain, result, allowed)

    return 1 if result["unexpected_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
