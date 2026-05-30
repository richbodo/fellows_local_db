# Security Audit — recommendations checklist

This is the **living checklist of security-audit recommendations** for the
Fellows directory: what's been done, what's outstanding, and what's been
deliberately *not* done. It supersedes the tracking that used to live in the
gitignored `security_review/` folder.

Two companion docs carry the parts that don't belong here:

- [`SECURITY.md`](../SECURITY.md) — the public-facing, stable statement of the
  project's architectural security decisions and reporting path. Doesn't track
  in-flight work.
- [`docs/local_vs_saas_risk.md`](./local_vs_saas_risk.md) — the analysis of the
  *accepted* risk of decentralising a directory into a local-first app vs. a
  centralised SaaS. Those are decisions already made, not items to fix; this
  checklist points at them so an auditor doesn't re-litigate them as bugs.

**Scope reminder (read before filing anything as a vuln):** the production
server is a *delivery channel, not a service*. It authenticates a magic-link
request, hands over the bundle + `fellows.db`, and steps back; the maintainer
plans to shut it down once dissemination is complete. Several "weaknesses" are
load-bearing trade-offs of that model — see `local_vs_saas_risk.md` and
`SECURITY.md` § Architectural security decisions before classifying them.

Legend: ✅ done · ☐ outstanding · ✗ deliberately not done (needs a different app)

---

## Latest audit pass — 2026-05-30

A high-level audit focused on **logical risks from the intentional design** and
**risks to PII held on the production server**. Method: review of the prod
server / auth helpers / Caddy + systemd + Ansible hardening, plus live
non-destructive probing of the droplet (listening sockets, file permissions on
`fellows.db` and the secrets env file, journald contents, the auth gate, public
endpoint reachability, edge headers, `systemd-analyze security`, brute-force
protections, on-disk backup sweep).

**Headline:** the design holds up well. The server persists exactly one
sensitive asset class (`fellows.db`) and three secrets; there is no
`relationships.db` and no DB backups on the box. The dominant threat to PII is
**not the app** — it's whoever holds the operator SSH key (see B2). The auth
gate, header regime, and secret-handling all verified correct in production.

### Fixed in this pass (2026-05-30 hardening PR)

- ✅ **C1 — Raw recipient email removed from journald.** The `send_unlock_email`
  event logged the full Postmark response, including the raw recipient address
  (`meta["to"]` / `meta["raw"]["To"]`), accumulating a plaintext roster of
  everyone who ever requested a link — contradicting the `email_hash_prefix`
  scheme used everywhere else. Now logs a PII-free subset. **No capability
  lost:** `just prod-stats-long` and `just installed-versions` reconstruct the
  plaintext recipient by joining the 12-hex `email_hash_prefix` against
  `fellows.db`, not from the log; `just email-debug --postmark` resolves
  recipients via the Postmark API. (`deploy/server.py`)
- ✅ **B3 — Caddy admin API disabled (`admin off`).** The unauthenticated admin
  control plane on `127.0.0.1:2019` let any local process (e.g. an RCE'd app
  running as the `fellows` user) extract TLS keys or rewrite routing
  post-foothold. Config is fully static, so the API isn't needed; the caddy
  reload handler switched to a full restart to match.
  (`ansible/roles/caddy/`)
- ✅ **B4 — `UMask=0077` on the service unit.** Was the only finding dropping
  `systemd-analyze security fellows-pwa` below an otherwise-clean score (files
  the service creates — sqlite WAL/journal — defaulted world-readable).
  (`ansible/roles/fellows_app/templates/fellows-pwa.service.j2`)
- ✅ **B5 — Public diagnostics endpoint trimmed.** `/api/debug/diagnostics` is
  unauthenticated by design (the smoke check probes it to catch a
  silently-broken send path). It disclosed the exact roster size
  (`allowlistHashCount`) and an internal filesystem path (`distRoot`) — pure
  recon, read by no tooling. Now emits config-presence booleans only
  (`allowlistConfigured`). Mirrored in the dev server for parity.
  (`deploy/server.py`, `app/server.py`)
- ✅ **B1 — fail2ban for SSH.** Defence-in-depth on the operator key. Password
  auth is already off so brute force can't succeed; fail2ban bans
  scanners/credential-stuffers early and keeps the auth log clean
  (`backend=systemd`, jail bound to the non-standard SSH port).
  (`ansible/roles/common/`)

### Outstanding — ranked

- ☐ **B2 — Operator SSH key / maintainer workstation hardening (highest
  leverage).** The operator key is the single most powerful credential in the
  system: it can read `fellows.db` (full PII), read the secrets env file (both
  via the `fellows` group), become root (sudo), and push a new bundle to all
  users. There is no second factor. The maintainer workstation that holds the
  key + the signing key is effectively inside the trust boundary. Recommended:
  hardware-backed FIDO2/`sk-` SSH key; signed commits; the secrets env file
  never on the laptop in plaintext; a documented recovery path if the laptop
  holding the (encrypted) signing key is lost. *(Was Tier-3 in the prior
  tracking; promoted here because live probing confirmed it is threat #1.)*
- ☐ **CAA DNS records** for `fellows.globaldonut.com` (`issue
  "letsencrypt.org"`, `issuewild ";"`, `iodef "mailto:richbodo@gmail.com"`).
  ~10 min operator task; documented in `docs/DevOps.md` § Signing keys.
- ☐ **HSTS preload submission** at <https://hstspreload.org/?domain=fellows.globaldonut.com>.
  The header already advertises `preload`; the registry submission is the
  remaining step (~5 min; inclusion lags weeks).
- ☐ **CT-log monitoring** via crt.sh alerts for the domain — early warning on a
  mis-issued certificate. Optional, ~5 min.
- ☐ **User-guide hygiene section** in `docs/users_manual.md`: "your device is
  now the directory" — full-disk encryption, screen lock, retiring a device
  (Reset Everything → factory reset). The user-facing complement to
  `SECURITY.md` § 1; raises endpoint baseline at zero technical cost.
- ☐ **Fix `scripts/debug_email_delivery.py --dump-allowlist`** — broken since
  the HMAC/DB-derived allowlist landed (PR #139); the old plaintext-file
  assumption no longer holds.
- ☐ **`scripts/sign_bundle.py` polish** — catch `KeyboardInterrupt` for a clean
  "Aborted." exit; have the wrong-passphrase path mention Ctrl-C.
- ☐ **App-layer encryption of `relationships.db`** ("lock my user data"
  toggle) — user-driven lock-on-quit with an off switch, covering OPFS backups.
  This is a *device-side* control, not server-side; tracked here for
  completeness. Honest threat-model copy required (file-level theft yes, live
  malware no).

### Deliberately not done — would need a different app

These deliver real wins but only under contracts this app doesn't hold. They
belong in a sibling/successor app for higher-sensitivity data, not here. Full
reasoning in `SECURITY.md` § 2–3 and `local_vs_saas_risk.md`.

- ✗ **Strip sensitive fields from the bundle; serve on-demand.** Adds a
  per-fellow authenticated read endpoint — the bright line `README.md` § Design
  Stance forbids. Also breaks offline `mailto:` group export.
- ✗ **Server-side revocation list / freshness re-auth (N-day TTL).** Introduce
  per-user server state and/or break "install once, works forever"; both stop
  working once distribution shuts down anyway.

---

## Accepted risks (decided — do not file as bugs)

These are the load-bearing trade-offs of the local-first / Never-SaaS model.
The full analysis is in [`local_vs_saas_risk.md`](./local_vs_saas_risk.md);
the short list:

- **The system is only as secure as each fellow's email account.** A
  compromised inbox → magic link → full `fellows.db`. Structural ceiling of
  magic-link delivery; nothing server-side raises it.
- **Every installed device holds the full directory, forever, unrevocably.**
  Device compromise = full-directory leak. The offline-forever payoff.
- **The operator is fully trusted with both PII and secrets.** The `fellows`
  group read access to `fellows.db` and the env file is the deploy model. B2
  hardens the *credential*; it doesn't change the trust model.
- **`contact_email` / `mobile_number` ship in the bundle.** They're the social
  contract every fellow accepted on joining the directory; persistence is the
  deal, not the flaw.

---

## Previously shipped (2026-05, Tier 1–2)

Context for auditors so already-closed items aren't re-reported: strict CSP on
both servers; Permissions-Policy / CORP / Referrer-Policy / nosniff on every
response; COOP/COEP at the edge + both servers; removed `allowed_emails.json`
(allowlist now HMAC'd in memory from `fellows.db`); v3 session cookies bound to
a server-side `session_id` registry (a leaked session secret alone can't mint
cookies); SRI on `index.html` scripts; out-of-band **signed bundles** with SW
signature verification + public-key fingerprint in the magic-link email; systemd
hardening (`ProtectSystem=strict`, `ProtectHome`, `MemoryDenyWriteExecute`,
etc.). See `SECURITY.md` § Defensive controls for the current table.
