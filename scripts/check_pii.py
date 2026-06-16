#!/usr/bin/env python3
"""Block PII and gitignored data from entering commits — the always-on,
stdlib-only half of this repo's leak guard (the secret half is gitleaks).

WHY a custom check on top of gitleaks: gitleaks finds *secrets* (keys,
tokens) by signature, but says nothing about *PII* — fellow emails, or a
local path that leaks your username/home layout (the classic "an AI wrote a
report against my machine and pasted in /Users/<me>/..." leak). This catches
that class, plus a force-added data file (fellows.db, final_fellows_set/),
which the README says must never be committed.

SCOPE = ADDED LINES IN A DIFF, not the whole tree. The repo already contains
benign matches that we deliberately grandfather (jsPDF vendor author emails,
@example.com test fixtures, a couple of /Users/... paths in plans/). Scanning
only what a change *introduces* keeps the signal high and the noise near zero.

Usage:
  scripts/check_pii.py --staged             # pre-commit hook: staged changes
  scripts/check_pii.py --range BASE..HEAD    # CI: everything a branch adds
  scripts/check_pii.py                       # defaults to --staged

Exit 0 = clean, 1 = findings (printed with file:line, value redacted).

Escape hatches (use deliberately):
  - git commit --no-verify                   # bypass the whole pre-commit hook
  - add a regex line to .pii-allowlist       # permanently ignore a pattern
"""
import os
import re
import subprocess
import sys

# Emails whose domain (or exact address) is known-safe in this repo: test
# fixtures, the project's own domain, the maintainer's *public* contact, and
# the commit-footer co-author. A real fellow email won't be on this list.
ALLOW_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "example.co.uk",
    "globaldonut.com", "fellows.globaldonut.com", "anthropic.com",
}
ALLOW_EMAIL_ADDRS = {"richbodo@gmail.com"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# A literal home directory with a real-looking user segment. We allow the
# redacted/placeholder forms (/Users/.../, $HOME, ~) since those leak nothing.
HOME_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([A-Za-z0-9._\-]+)")
HOME_PLACEHOLDERS = {
    "...", "user", "username", "<user>", "<username>", "<you>", "you",
    "youruser", "your-user", "name", "me",
}

# File PATHS that must never be committed (the README's "data is never
# committed" rule). These are gitignored, so they only land via `git add -f`.
DATA_PATH_RES = [
    re.compile(r"(^|/)final_fellows_set/"),
    re.compile(r"\.db$"),
    re.compile(r"(^|/)ehf_fellow_profiles.*\.json$"),
]

# Files whose *content* we don't scan: third-party libraries and minified
# bundles carry author emails that are not our PII.
CONTENT_SKIP_RES = [
    re.compile(r"(^|/)app/static/vendor/"),
    re.compile(r"\.min\.js$"),
    re.compile(r"(^|/)scripts/check_pii\.py$"),  # don't scan the checker itself
]


def _run(args):
    return subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, text=True, errors="replace",
    ).stdout


def _load_extra_allow():
    """Optional .pii-allowlist: one regex per line (blank / #comment ignored)."""
    path = os.path.join(_repo_root(), ".pii-allowlist")
    pats = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        pats.append(re.compile(line))
                    except re.error:
                        pass
    return pats


def _repo_root():
    root = _run(["git", "rev-parse", "--show-toplevel"]).strip()
    return root or os.getcwd()


def _diff_text(mode, rng):
    if mode == "range":
        return _run(["git", "diff", "--unified=0", "--no-color", rng])
    return _run(["git", "diff", "--cached", "--unified=0", "--no-color"])


def iter_added(diff_text):
    """Yield (path, lineno, added_text) for each '+' line in a unified diff,
    and collect the set of target file paths touched."""
    path = None
    lineno = 0
    paths = set()
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            tgt = line[4:].strip()
            if tgt == "/dev/null":
                path = None
            else:
                path = tgt[2:] if tgt.startswith("b/") else tgt
                paths.add(path)
            continue
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
            continue
        if line.startswith("+") and not line.startswith("+++"):
            yield ("line", path, lineno, line[1:])
            lineno += 1
        # with --unified=0 there are no context lines; removed lines ('-') do
        # not advance the new-file line number.
    yield ("paths", None, 0, paths)


def _skip_content(path):
    return path is None or any(r.search(path) for r in CONTENT_SKIP_RES)


def _redact_email(addr):
    local, _, dom = addr.partition("@")
    return (local[:1] or "?") + "***@***." + dom.rsplit(".", 1)[-1]


def main(argv):
    mode, rng = "staged", None
    if "--range" in argv:
        i = argv.index("--range")
        mode, rng = "range", argv[i + 1] if i + 1 < len(argv) else None
        if not rng:
            print("check_pii: --range needs BASE..HEAD", file=sys.stderr)
            return 2
    elif argv and argv[0] not in ("--staged",):
        print(__doc__)
        return 0

    extra_allow = _load_extra_allow()
    findings = []
    for kind, path, lineno, payload in iter_added(_diff_text(mode, rng)):
        if kind == "paths":
            for p in sorted(payload):
                if any(r.search(p) for r in DATA_PATH_RES):
                    findings.append((p, 0, "data file must not be committed "
                                     "(gitignored; contains/derives from PII)"))
            continue
        if _skip_content(path):
            continue
        if any(r.search(payload) for r in extra_allow):
            continue
        for addr in EMAIL_RE.findall(payload):
            dom = addr.rsplit("@", 1)[-1].lower()
            if addr.lower() in ALLOW_EMAIL_ADDRS or dom in ALLOW_EMAIL_DOMAINS:
                continue
            findings.append((path, lineno, "email address (" + _redact_email(addr) + ")"))
        for seg in HOME_RE.findall(payload):
            if seg.lower() in HOME_PLACEHOLDERS:
                continue
            if not re.search(r"[A-Za-z0-9]", seg):
                continue
            findings.append((path, lineno, "local home path leaks a username "
                             "(use $HOME, ~, or redact)"))

    if not findings:
        return 0
    print("✖ check_pii: potential PII / data in added changes:\n", file=sys.stderr)
    for p, ln, why in findings:
        loc = (p or "?") + (":" + str(ln) if ln else "")
        print("  - {}: {}".format(loc, why), file=sys.stderr)
    print("\n  Fix the lines above. If a match is a false positive, add a regex "
          "to .pii-allowlist,\n  or bypass once with: git commit --no-verify",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
