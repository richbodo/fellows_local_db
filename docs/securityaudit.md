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

### Fixed in this pass (2026-05-30 hardening — PR #224)

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

### Fixed in the follow-up pass (2026-05-30 — PR #225)

In-repo completion of the remaining checklist (operator console actions for
CAA / HSTS / crt.sh tracked below):

- ✅ **User-guide hygiene section** — "Your device is now the directory" added to
  `docs/users_manual.md` (full-disk encryption, screen lock, browser updates,
  retiring/lending a device, no-remote-wipe). Ships to users via the About-page
  link.
- ✅ **`--dump-allowlist` rewritten** for the HMAC/DB-derived model
  (`scripts/debug_email_delivery.py`). No more `allowed_emails.json` assumption;
  reports distinct-email count (= allowlist), fellows with no contact_email,
  duplicate emails, and a "fellows.db newer than the running server" staleness
  warning (the only drift that can still exist). The `--email` HIT/MISS check
  now resolves membership against the DB email set (no HMAC key needed).
- ✅ **`scripts/check_ct_log.py` + `just ct-check`** — on-demand Certificate
  Transparency check via crt.sh; flags any issuer that isn't Let's Encrypt.
- ✅ **CAA guardrail** — `just check-env` (`scripts/check_deploy_env.sh`) now
  warns when no CAA record is effective for the host or when it doesn't
  authorize Let's Encrypt; DevOps.md CAA/HSTS sections corrected (see finding).
- ✅ **`sign_bundle.py` polish** — clean `Aborted.` on Ctrl-C; wrong-passphrase
  prompt mentions Ctrl-C.

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
- ✅ **CAA DNS records for `fellows.globaldonut.com`** (done 2026-05-31). Three
  records added in Cloudflare (`issue "letsencrypt.org"`, `issuewild ";"`, `iodef
  "mailto:richbodo@gmail.com"`), scoped to the `fellows` subdomain. Verified live:
  `dig` returns exactly those three (no Cloudflare-injected extras, since
  `fellows` is DNS-only), apex/`pitch` CAA untouched, `just check-env` → "OK:
  Let's Encrypt is authorized." Caddy pinned to LE to match (see below).
- ✅ **Pin Caddy to Let's Encrypt** (in the open Caddy/HSTS PR). Caddy's default
  is LE + a ZeroSSL (Sectigo) fallback that the new CAA would block anyway;
  `acme_ca` now pins issuance to LE so Caddy's behaviour matches the CAA. Applies
  via `just bootstrap`.
- ⊘ **HSTS preload — considered and declined** (decided 2026-05-31). hstspreload.org
  only accepts whole registrable domains, so the only option was preloading the
  entire `globaldonut.com` zone — a permanent, zone-wide HTTPS-only commitment
  binding third-party subdomains (`pitch`, `notify.pitch`) and outliving this
  soon-to-retire app. Marginal benefit is small (HTTPS magic-link entry, browsers
  default HTTPS-first, header already covers repeat visits, CAA + signed bundles
  cover integrity). **Header retained; not submitted.** Full rationale +
  revisit condition in `docs/DevOps.md` § HSTS preload submission.
- ☐ **crt.sh email-alert signup** (operator console). The in-repo half is done
  (`just ct-check`); remaining is the push-alert subscription for same-day
  notice of any new issuance.
- ☐ **App-layer encryption of `relationships.db`** — *owner-scheduled, deferred.*
  Device-side "lock my user data" toggle (lock-on-quit + off switch, covers OPFS
  backups). Honest threat-model copy required (file theft yes, live malware no).
- ☐ **Risk-doc rewrite** — *owner-scheduled, deferred.* Evolve
  [`local_vs_saas_risk.md`](./local_vs_saas_risk.md) into a forward-looking
  stakeholder decision record: the accepted-risk statement weighed against the
  cost and appetite of keeping a donation-funded SaaS directory alive.

> **Zone finding (`just ct-check`, 2026-05-30):** the `globaldonut.com` zone is
> **not** Let's-Encrypt-only — `pitch.globaldonut.com` uses Google Trust
> Services and the apex has appeared with a Sectigo cert. Consequences (now
> reflected in `docs/DevOps.md`): **(a)** CAA was scoped to
> `fellows.globaldonut.com` — an apex Let's-Encrypt-only record would break those
> other CAs' renewals; **(b)** HSTS preload was **declined** — the list only
> accepts the whole `globaldonut.com` apex, and apex + `includeSubDomains` would
> force every zone subdomain (including the third-party ones) HTTPS-only,
> permanently, for little marginal gain. Re-run `just ct-check` periodically.

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
