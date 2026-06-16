# Security Policy

## Reporting a vulnerability

The maintainer is reachable at **richbodo@gmail.com** with a subject line beginning `Fellows directory security:`. If a PGP-encrypted exchange is needed for the disclosure, ask via that mailbox and a key will be exchanged before sensitive detail is sent.

For ordinary bugs that aren't security-sensitive, use GitHub Issues at <https://github.com/richbodo/fellows_local_db/issues>.

## Supported versions

Only `main` is supported. The deployed bundle is whatever the current `HEAD` of `main` would build (`just whats-running` shows the local-vs-prod diff; `just drift` is the SHA-aligned three-way comparison). Older branches and forks are out of scope.

---

## What this project is — context for evaluating reports

The Fellows directory is a **single-user, local-first PWA**. The production server at <https://fellows.globaldonut.com> is a **delivery channel, not a service**: it authenticates a magic-link request, delivers the bundle + `fellows.db`, and steps back. After install, the app runs against a local OPFS copy indefinitely.

This stance is documented in:

- `README.md` § Design Stance: Local-Only, Not SaaS
- `docs/Architecture.md` § Design constraint: local-only, not SaaS
- `docs/email_gate.md` (auth-flow behavioural spec, including invariant 10 on stale-session resilience)

Every design decision below flows from those contracts.

---

## Architectural security decisions on the record

### 1. The archival-directory model — distribution is short-lived

This app exists to disseminate a directory snapshot to ~500 fellows of a fellowship organisation, then get out of the way. The maintainer **plans to shut the distribution server down** once dissemination is complete; the app then continues running on the devices that already installed it, indefinitely.

This is the single most load-bearing design constraint in the project, and it determines several of the trade-offs below. The relevant operational facts:

- The bundle and `fellows.db` must be **fully self-contained**. After install, the app must keep working with no further server contact.
- Any feature whose value depends on the server being alive is suspect.
- Revocation, server-side audit, fresh-data pulls, opt-in re-attestation — **none of these survive the eventual shutdown**.

The trade-off this locks in:

| What we accept | What we gain in return |
|---|---|
| Every device holds the full contact-book persistently, including phones / emails. | The app's most useful function — composing email to a saved group — works **offline, forever, even after the maintainer is gone**. |
| Ex-fellows retain the contact-book forever; we cannot revoke. | The data survives the maintainer / the org / the server. The directory cannot disappear in a single SaaS shutdown event. |
| A compromised device leaks the full contact-book of N≈515 fellows, not a subset. | Local data lives at the **social-contract level** — what every fellow signed up to share with every other fellow when joining the directory. |

**This pattern recurs whenever an organisation wants to decentralise an archival directory before winding down its central infrastructure.** If you're picking this codebase up to do the same for another community, the contracts above are the load-bearing ones; security follows them, not the other way around.

### 2. "Strip sensitive fields, serve on-demand" — considered and rejected

The original threat analysis (now published as [`docs/local_vs_saas_risk.md`](docs/local_vs_saas_risk.md)) proposed stripping `contact_email` and `mobile_number` from the bundle and serving them via a new authenticated `GET /api/fellow-private/<slug>` endpoint. A device compromise would then leak the directory roster but not the contact-book.

Cut, for four reasons that compound:

1. **Never-SaaS bright line.** Adding a per-fellow authenticated read endpoint is exactly the move that turns this from a delivery channel into a service. Crossing that line isn't free — the contract forbids it.
2. **Offline-first broken.** Group export composes a `mailto:` from `contact_email`s; without those fields on-device, every export needs a live server round-trip.
3. **Distribution shutdown becomes data loss.** The moment the maintainer shuts the distribution server down, the contact-book disappears from every installed device. The archival-directory model rules this out.
4. **Social contract.** `contact_email` and `mobile_number` are the only fields in `fellows.db` that aren't already public among fellows by the EHF social contract. Persisting them on every device *is* the deal; persistence is not the flaw.

The escalation path for sensitive-data classes that don't fit this app's contract is **a different app**, not an online endpoint inside this one.

### 3. Other improvements deliberately not implemented

- **Server-side revocation list keyed by email hash, distributed via `/build-meta.json`.** Would bound ex-user retention by triggering `clearEverything()` on a stolen device when it next comes online. Introduces per-user state on the server (revocation list); blurs the "no per-user resources on the server" bright line. Also weak: relies on the device reaching the server before an attacker images OPFS, and stops working entirely once distribution shuts down. **Cut.**
- **Freshness re-auth (90-day TTL on local data).** Would bound ex-user retention to N days. Breaks `email_gate.md` invariant 9 (URL-just-works for returning visitors) and the README's "install once, works forever" promise. Materially changes the UX contract for active users to bound a tail-risk for ex-users; the trade is bad at this scale. Also stops working once distribution shuts down. **Cut.**

---

## Defensive controls currently in place

| Layer | Control | Implemented in |
|---|---|---|
| Response headers (all responses, dev + prod) | Strict CSP (`script-src 'self' 'wasm-unsafe-eval'`, no inline, no third-party), Permissions-Policy (all unused capabilities `=()`), Cross-Origin-Resource-Policy: same-origin, Referrer-Policy: strict-origin-when-cross-origin, X-Content-Type-Options: nosniff | `app/server.py:end_headers`, `deploy/server.py:_security_headers` |
| Cross-origin isolation | Cross-Origin-Opener-Policy: same-origin, Cross-Origin-Embedder-Policy: require-corp (set by Caddy at the edge AND both Python servers) | `ansible/roles/caddy/templates/Caddyfile.j2`, both Python servers |
| Script integrity | SHA-384 SRI on `app.js` and `vendor/jspdf-...js` in `index.html`. Build-time and dev-server-time substitution produce byte-identical integrity values | `build/build_pwa.py:stamp_sri_attributes`, `app/server.py` index.html handler |
| Allowlist privacy | HMAC-SHA256 of normalised `contact_email`, built in memory at server startup from `fellows.db`; no `allowed_emails.json` file ships in `dist/`; the HMAC key (`FELLOWS_ALLOWLIST_HMAC_KEY`) lives only in `/etc/fellows/fellows-pwa.env` on the production server | `deploy/magic_link_auth.py:load_allowlist_from_db`, `deploy/server.py:init_auth` |
| Session binding | v3 cookie format carries a `session_id` registered server-side in `AuthState.sessions`. A leaked `FELLOWS_SESSION_SECRET` alone cannot mint working cookies — the attacker would also need write access to in-memory state on the running server | `deploy/magic_link_auth.py:sign_session_value` / `verify_session_value` |
| Transport | HSTS preloaded, TLS 1.3 via Caddy + Let's Encrypt | `ansible/roles/caddy/templates/Caddyfile.j2` |
| Client-error sink | `/api/client-errors` with strict sanitiser (email + slug + magic-link-token redaction, kind allow-list, 16 KB body cap, per-IP rate limit). Always 204 — no oracle, no echo | `deploy/client_error_sanitizer.py`, `deploy/server.py:_handle_client_errors` |
| Static-file boundary | `dist/allowed_emails.json` no longer exists; the build pipeline does not write it. Defence-in-depth 404 stub stays on the route in case a future routing change resurrects the file | `build/build_pwa.py`, `deploy/server.py` |
| systemd hardening | `User=fellows` (nologin), `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp/Devices`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`, `MemoryDenyWriteExecute=yes`, `RestrictNamespaces/SUIDSGID`, `LockPersonality=yes`, `ReadWritePaths=/opt/fellows/deploy/dist` | `ansible/roles/fellows_app/templates/fellows-pwa.service.j2` |

See `docs/email_gate.md` for the auth-flow behavioural spec (cookie format, install window, client-error reporting schema, anti-abuse posture) and `docs/Architecture.md` § Tech Stack for the headers regime in context.

---

## Keeping secrets and PII out of the repository

The contact data is never committed (`fellows.db`, `relationships.db`, and
`final_fellows_set/` are gitignored — see README § Data Note). Two automated
guards back that rule so a secret or a stray bit of PII can't slip into a commit:

- **gitleaks** — scans for secrets (keys, tokens, private keys). Authoritative
  in CI (`.github/workflows/secret-scan.yml`); also runs in the pre-commit hook
  when installed locally (`brew install gitleaks`). The repo allowlist — the
  committed dev-only signing key, vendored libraries, `*.example` templates — is
  `.gitleaks.toml`.
- **`scripts/check_pii.py`** — stdlib, no install. Scans the *added lines* of a
  change (not the whole tree, so pre-existing benign matches are grandfathered)
  for email addresses outside an allowlist, local home paths that leak a
  username, and force-added data files. Runs in the same CI job and always in
  the pre-commit hook. This is the guard for the "an AI wrote a report against my
  machine and pasted in `/Users/<me>/…` or a fellow's email" class of leak.

Activate the pre-commit hook with `just hooks` (also done by `just setup` and
`scripts/wt-setup.sh`; it points `core.hooksPath` at `.githooks/`). Scan a
branch on demand with `just secret-scan`. A false positive can be allowlisted
(`.gitleaks.toml` for secrets, a `.pii-allowlist` regex file for PII) or a
single commit bypassed deliberately with `git commit --no-verify`.

---

## Data retention

There is **no per-user storage on the server** — no account, profile, or saved
state; all user-authored private data lives in `relationships.db` in the
browser on the user's own device and never reaches prod. What the server does
keep is operational only: **journald events** (auth/diagnostic logs, carrying
hash prefixes and UAs — never a raw email in the log line), **files on disk**
(`fellows.db` contact mirror, `/etc/fellows/fellows-pwa.env` secrets, the static
`dist/` bundle), and **in-memory state** lost on every restart (token,
rate-limit, and session registries). journald runs Ubuntu's default
**size-capped** rotation (no fixed time window; oldest-vacuumed-when-full), as
no retention override is set in Ansible.

Full accounting — every event and its fields, the on-disk and in-memory
inventories, the retention window, and the Postmark third-party note — is in
[`docs/data_retention.md`](docs/data_retention.md). The user-side removal paths
(Clear App Cache / Reset Everything / browser-level deletion) are in
[`docs/users_manual.md` § Clearing app data](docs/users_manual.md#clearing-app-data).

---

## What's in the security backlog

Currently in flight or queued:

- **Out-of-band signed bundles + SW signature verify.** Closes the single-maintainer / single-VPS supply-chain SPOF. Particularly relevant for the archival-directory model: a signed-bundle install gives users a way to verify any **future** update (or refuse one) against an out-of-band-published key, even after the maintainer is no longer actively running the service.
- **Optional "lock my user data" toggle.** User-driven encryption-at-rest for `relationships.db` and its OPFS backups, surfaced as a "lock on quit?" prompt with an off-toggle. Not forced — peace-of-mind for paranoid moments (airport, lending the laptop, retiring a device).
- **Operational hardening.** Maintainer workstation hardening doc, user-guide hygiene section ("your device is now the directory"), HSTS preload submission status check.

The live recommendations checklist (done / outstanding / deliberately-not-done) is [`docs/securityaudit.md`](docs/securityaudit.md).

---

## Threat model — one-paragraph summary

The threat model assumes:

- The server is a delivery channel, not an attack target worth defending forever.
- Every installed device holds a full copy of the directory and is the primary place where data lives long-term.
- Compromise of a single fellow's device is the dominant breach event by frequency; expected exposure of N≈515 records per such event.
- Compromise of the maintainer's deploy pipeline is the worst plausible breach event by **impact** (poisoned bundle reaches all users); signed bundles are the partial answer.
- Once distribution shuts down, "server compromise" stops being a category at all — the only remaining attack surface is the per-device installed app.

For the full analysis with quantified estimates and a comparison to the SaaS alternative, see [`docs/local_vs_saas_risk.md`](docs/local_vs_saas_risk.md).
