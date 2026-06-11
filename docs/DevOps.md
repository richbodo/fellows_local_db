# DevOps

How the production VPS is laid out, who runs what, and how routine work happens. This document is the source of truth for the deployment architecture. The root `README.md` links here; `ansible/README.md` covers mechanical Ansible details (tags, logs, `--syntax-check`).

## Architecture at a glance

One Ubuntu 24.04 droplet, serving `https://fellows.globaldonut.com/`. Caddy on `:443` reverse-proxies to a Python stdlib HTTP server on `127.0.0.1:8765`. A single human operator runs Ansible from a Mac; there is no CI.

```
Operator (Mac)                 VPS
──────────────                 ───────────────────────────
ansible-playbook ──SSH (rsb)─▶ sudo: apt, ufw, systemd, /etc/*
rsync dist/ ─────SSH (rsb)───▶ /opt/fellows/deploy/dist/   (fellows:fellows 2775)
                               │
                               │ reads
                               ▼
                               fellows-pwa.service (User=fellows, nologin)
                               │ systemd hardening (ProtectSystem=strict,…)
                               │
                      127.0.0.1:8765
                               ▲
                               │ reverse_proxy
                               │
                               Caddy :443 (Let's Encrypt)
                               ▲
                               │ HTTPS
                               │
                          Public Internet
```

Caddy and any reverse proxy in front of the Python server **must
preserve** the `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` headers that the Python
server sets on every response. These are load-bearing: the
OPFS-SAH-Pool VFS that holds `relationships.db` and `fellows.db` in
the browser refuses to install without `crossOriginIsolated=true`.
If a future deploy switches reverse proxies and the headers don't
make it through, the silent symptom is "Settings page has no
backup/restore section" — diagnosable via `?diag=1` showing
`dataProvider.kind: api+idb` instead of `worker`. Caddy in the
default `reverse_proxy` config passes them through; explicit
`header_down` directives that strip them are the failure path to
look for.

## Unix identities

Two accounts — one for the human, one for the daemon. This is the smallest separation that lets a code-exec bug in the service not become a code-rewrite opportunity.

| Account  | Shell         | SSH? | Sudo?                        | Runs what? |
|----------|---------------|------|------------------------------|------------|
| `rsb`    | `/bin/bash`   | yes  | yes, full, **password**'d    | interactive ops, Ansible playbooks, rsync |
| `fellows`| `/usr/sbin/nologin` | no | no                           | `fellows-pwa.service` (daemon) |

`rsb` is also a member of the `fellows` group. This is what lets the operator rsync into `/opt/fellows/deploy/` without sudo: the tree is mode `2775` (setgid + group-writable), so new files inherit `group=fellows` and the operator's group write bit applies. The service user keeps read-only access to its own code because **systemd's `ProtectSystem=strict`** enforces that regardless of mode bits.

### Why no separate "deploy" account?

Small-team / single-maintainer apps don't need a third identity. The classic "deploy user with narrow NOPASSWD sudoers" pattern makes sense when a CI system pushes code without a human; here, the human with regular sudo fills that role. Adding a `deploy` account in this setup only creates ambiguity about which identity owns what.

If CI is added later, the right move is to introduce a `deploy` account then — separate from `fellows`, keyed for the CI runner, with narrow NOPASSWD sudoers for whatever the pipeline needs.

## Filesystem layout

| Path | Owner:Group | Mode | Purpose |
|------|-------------|------|---------|
| `/opt/fellows/` | `fellows:fellows` | `2775` | app root |
| `/opt/fellows/deploy/` | `fellows:fellows` | `2775` | Python server + helpers |
| `/opt/fellows/deploy/dist/` | `fellows:fellows` | `2775` | static bundle, `fellows.db`, images (operator rsyncs here) |
| `/etc/fellows/` | `root:fellows` | `0750` | operator-provisioned config dir |
| `/etc/fellows/fellows-pwa.env` | `root:fellows` | `0640` | Magic-link auth secrets (`FELLOWS_SESSION_SECRET`, `FELLOWS_POSTMARK_TOKEN`, …) |
| `/etc/systemd/system/fellows-pwa.service` | `root:root` | `0644` | unit file (managed by Ansible) |
| `/etc/systemd/system/fellows-pwa.service.d/10-env-file.conf` | `root:root` | `0644` | drop-in that points `EnvironmentFile=` at `/etc/fellows/fellows-pwa.env` |
| `/etc/caddy/Caddyfile` | `root:root` | `0644` | Caddy site config (managed by Ansible) |
| `/etc/sudoers.d/*` | `root:root` | `0440` | only distro defaults + anything added manually — no per-service file |

The `2775` mode on `/opt/fellows/*` is two things at once: the sticky `2` bit (setgid) means new files under the directory inherit its group (`fellows`), and `775` means `owner rwx, group rwx, other r-x`. Combined with operator membership in `fellows`, the operator can push code without sudo.

**Gotcha: group write ≠ utime or chmod.** Being in the group lets you create, modify, and delete files, but setting timestamps (`utime`) or permissions (`chmod`) on a file you don't own requires ownership or `CAP_FOWNER` — group-write is not enough. This matters for `rsync -a`, which tries to preserve both directory mtimes and perms. The Ansible synchronize task therefore passes `--omit-dir-times` and `--no-perms` (via `perms: false`). File mtimes are still preserved (rsync-created files are operator-owned and can be `utime`'d), and new files get umask-default perms (644/755) which matches what we want. `--no-perms` is also load-bearing for a second reason: if rsync preserved perms, it would `chmod` `dist/.` from the target's `2775` down to the source's `755`, silently stripping the setgid bit and breaking group inheritance for new files.

## systemd hardening

`fellows-pwa.service` runs with the following directives. Most are cheap — costs zero at runtime, closes whole classes of exploitation if the Python server is ever compromised:

```ini
User=fellows
Group=fellows
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
ReadWritePaths=/opt/fellows/deploy/dist
MemoryHigh=550M
MemoryMax=700M
OOMScoreAdjust=500
```

`ProtectSystem=strict` remounts the entire filesystem read-only for the service except `/dev`, `/proc`, `/sys` (handled separately), and anything in `ReadWritePaths`. `dist/` is explicitly writable only as a safety net for SQLite journal files — the server's SQL path is SELECT-only in practice. If you later switch the Python code to open the DB with `?mode=ro`, you can drop `ReadWritePaths` entirely.

`MemoryMax` / `MemoryHigh` / `OOMScoreAdjust` are **availability guardrails**, not security hardening (added for the wider 2026-06 rollout). The droplet is 1 vCPU / ~960 MB; `deploy/server.py` is a `ThreadingHTTPServer` (one thread per connection, no pool — bounded only by `TasksMax`), so a connection/thread pile-up under a burst, or a future bug, could exhaust RAM and OOM the **whole box**, taking Caddy + sshd with it (the resource-starvation "all-ports outage" failure mode). `MemoryMax=700M` caps the service's own cgroup so a runaway is OOM-killed as just `fellows-pwa` (and `Restart=on-failure` revives it) while Caddy + sshd survive; `OOMScoreAdjust=500` biases the global OOM killer toward this service if the box as a whole runs short. Normal usage is ~16–150 MB (file page cache is reclaimable and not held against the cap), so these never fire under legitimate load. Pair with the kernel listen backlog raised to 128 in `deploy/server.py` (stdlib default is 5) so a short connection spike queues instead of resetting. **Raise all three if the droplet is ever resized.**

## Network and firewall

- Inbound (UFW): `52221/tcp` (ssh), `80/tcp`, `443/tcp`. Everything else denied.
- Outbound: default allow (needed for Let's Encrypt, Postmark, apt).
- The Python server binds `127.0.0.1:8765` only; it is unreachable from the public Internet. Caddy is the only listener on `:443`.

## Ansible model

- Inventory: `ansible_user=rsb`, `ansible_port=52221`. Forever.
- `ansible.cfg`: `become=true`, `become_method=sudo`. Playbook runs use `--ask-become-pass` once per invocation.
- Roles: `common` (service account, UFW, SSH hardening) → `caddy` → `fellows_app` (directories, file copies, rsync, systemd unit).
- Tags: `bootstrap` runs the whole first-time flow. `deploy` runs only the `fellows_app` tasks needed to push a new build.

Adhoc commands that don't need root require `ANSIBLE_BECOME=false` (because become is on by default in `ansible.cfg`). For example: `ANSIBLE_BECOME=false ansible fellows -m ping`.

## Routine operations

The standard "ship current main to prod" flow is one command:

```bash
git checkout main && git pull         # confirm merges are local
just ship                             # build + test + deploy + smoke (one shot)
just whats-running                    # confirm prod's git_sha matches HEAD
```

`just ship` runs `test-fast` → `deploy`, and `just deploy` itself runs the full ansible playbook (build → rsync → restart → HTTPS smoke). The build step (`build/build_pwa.py`) stamps the current `git rev-parse --short HEAD` into the `FELLOWS_UI_DIAG` and `CACHE_VERSION` placeholders in `app/static/app.js` and `app/static/sw.js` as it copies them to `deploy/dist/`. Format: `<YYYY-MM-DD>-<short-sha>`. Result: every deploy carries a unique label tied to the code being shipped — no manual bump step, no `chore(version):` commits cluttering `main`.

What's deployed lives in the response, not in `git log`. Use `just drift` for the local-vs-prod SHA comparison (reads `/build-meta.json` on prod) and `just whats-running` for a side-by-side snapshot.

The other deploy recipes:

```bash
just deploy             # build + ansible + smoke (no test step)
just deploy-fast        # ansible + smoke, reusing the existing deploy/dist/
just ship-fast          # deploy-fast + smoke (skip rebuild AND tests)
just deploy-check       # ansible --check mode: what would change, no writes
```

**`just ship` / `just deploy` only roll the `fellows_app` role.** Changes to `ansible/roles/caddy/templates/Caddyfile.j2`, anything in the `common` role (users / packages / UFW / SSH hardening), or any other system-wide template land on disk via the bootstrap path — not the deploy path. To pick those up on the droplet, run `just bootstrap` (idempotent — safe to re-run; rolls every role and fires the `Reload caddy` / restart handlers as needed). If `curl -s -I https://fellows.globaldonut.com/ | grep -i <header>` doesn't show a header you just added to `Caddyfile.j2`, this is the cause.

Under the hood `just deploy` calls `./scripts/deploy_pwa.sh --ask-become-pass`, which runs the `ansible/deploy_pwa.yml` playbook. Equivalent manual form:

```bash
python build/build_pwa.py
ansible-playbook ansible/site.yml --tags deploy --ask-become-pass
```

The deploy path touches:
1. `/opt/fellows/deploy/` — `server.py`, `sqlite_api_support.py`, `magic_link_auth.py` (via `ansible.builtin.copy`, become: true).
2. `/opt/fellows/deploy/dist/` — rsync'd as the operator, no sudo.
3. `/etc/systemd/system/fellows-pwa.service` — only rewritten if the template changed.
4. Handler: `systemctl restart fellows-pwa` (via sudo).

Post-deploy smoke:

```bash
just smoke              # /healthz, /manifest.webmanifest, /api/debug/diagnostics
just check-env          # DNS + TLS + healthz
just prod-status        # systemctl status fellows-pwa caddy (over SSH)
just drift              # prod git SHA vs local HEAD + origin/main (SHA-aligned)
just prod-stats                # 24h: page loads, magic-link sends/verifies, install funnel, 5xx, disk
just prod-stats '7 days ago'   # weekly view (any "since" that journalctl accepts)
just prod-stats-long           # full retained journal + plaintext recipient list (every magic-link send)
```

Lower-level equivalents (what each recipe runs):

```bash
./scripts/smoke_prod.sh
./scripts/check_deploy_env.sh
ssh -p 52221 rsb@fellows.globaldonut.com 'systemctl status fellows-pwa caddy --no-pager'
```

## Bootstrapping a fresh droplet

If you're forking this repo for your own org, this is the section you want. The flow has four phases — provision + DNS, bootstrap + secrets, signing activation, and trust hardening — and each leaves the deployment more capable than the last. Follow them top to bottom; the later steps assume the earlier ones have landed.

```bash
# ── Phase 1: provision + DNS ──────────────────────────────────────────
# 1.  Provision Droplet, assign Reserved IP (e.g. 170.64.243.67),
#     create DNS A record for your hostname.
# 1a. Add CAA records to DNS so only Let's Encrypt may issue certs
#     for your hostname. See § Signing keys → Supporting DNS: CAA records
#     below for the exact records and a `dig` verification step.
# 2.  Put your SSH key in /home/<operator>/.ssh/authorized_keys on the droplet.
# 3.  Edit ansible/inventory/hosts.ini and ansible/group_vars/fellows.yml
#     from the .example templates (host, port, user, key path,
#     caddy_admin_email).

# ── Phase 2: bootstrap + secrets ──────────────────────────────────────
# 4.  From the repo root — install Ansible collections, run the
#     site playbook. Writes the hardened systemd unit, creates the
#     `fellows` service account, starts the service.
just ansible-collections    # one-time per workstation
just bootstrap              # ansible site.yml --tags bootstrap --ask-become-pass
# 5.  Install required env vars (session secret, allowlist HMAC key,
#     Postmark token, mail-from, public origin).
just prod-configure-env     # interactive; writes /etc/fellows/fellows-pwa.env

# ── Phase 3: signing activation + first deploy ────────────────────────
# 6.  Generate the prod signing keypair (one-time, kept off the
#     droplet). Then paste the printed public-key hex into
#     app/static/sw.js's PROD_PUBLIC_KEY_HEX constant, commit, push.
#     See § Signing keys → One-time setup for the backup procedure —
#     you do NOT want to skip the off-laptop backup.
just keygen
# 7.  First signed deploy. Chains test-fast → build → sign → push →
#     smoke. The `sign` step prompts once for the passphrase you
#     just chose at step 6.
just ship

# ── Phase 4: trust hardening ──────────────────────────────────────────
# 8.  Submit to https://hstspreload.org/?domain=<your-host> so first-
#     time visitors are HTTPS-only from the very first request,
#     before HSTS headers can take effect. See § Signing keys → HSTS
#     preload submission. Inclusion lags ~6–10 weeks per browser
#     release cycle.
# 9.  (Recommended) Subscribe to https://crt.sh/?domain=<your-host>
#     email alerts so any future CA misissuance generates a same-day
#     notification. See § Signing keys → Certificate Transparency
#     monitoring.
# 10. Cross-check the signing-key fingerprint shown on /#/about
#     against what `just keygen` printed at step 6. They MUST match.
#     If they don't, stop — something between your laptop and the
#     served bundle has drifted; investigate before letting any
#     user install.
```

Under the hood for step 4:

```bash
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

That run creates the `fellows` system user, adds the operator to the `fellows` group, writes the hardened systemd unit, and starts the service. If a legacy `deploy` account is present from a pre-migration droplet, the second play in `site.yml` removes it. The service starts but **does not yet have its env vars** — auth status reports `authEnabled: false`, no magic links can be issued — until step 5 runs.

**What happens if you skip a phase:**

- Skip phase 1a (CAA records): Let's Encrypt still issues your cert, but any other CA in the world could too. A phishing-style domain-validation attack at a rogue CA could mint a fraudulent cert. Closing this attack costs ten minutes of DNS work.
- Skip phase 3 (signing): the deploy works, the SW installs, the directory serves correctly. But you have no cryptographic protection against a compromised deploy pipeline pushing a poisoned bundle. Anyone who can write to `/opt/fellows/deploy/dist/` can push arbitrary JS to every installed device on the next SW update. The whole point of `security/signed-bundles` is to close this — don't skip it.
- Skip phase 4 step 8 (HSTS preload): your existing users are protected once they've been to the site once; brand-new users on hostile networks are not protected on their very first visit.
- Skip phase 4 step 10 (fingerprint cross-check): you might deploy a bundle whose `PROD_PUBLIC_KEY_HEX` doesn't actually match the private key you intended to use — every subsequent install fails verification, no further updates can ship until you republish a bundle with the correct key. Cross-check once at first deploy and again any time you've rotated the signing key.

## Required environment variables

`fellows-pwa.service` reads its env from `/etc/fellows/fellows-pwa.env` (mode `0640`, owned `root:fellows`). The interactive script (`just prod-configure-env` → `scripts/configure_email_auth_env.sh`) prompts for the four every operator sets; re-run it only when a secret rotates.

Canonical shape:

```env
# Hard-required. The auth gate disables itself if any are unset.
FELLOWS_SESSION_SECRET=...
FELLOWS_ALLOWLIST_HMAC_KEY=...
FELLOWS_POSTMARK_TOKEN=...

# Required in practice. Code has fallbacks but they're fragile.
FELLOWS_MAIL_FROM=EHF Directory App <admin@fellows.globaldonut.com>
FELLOWS_PUBLIC_ORIGIN=https://fellows.globaldonut.com

# Optional.
FELLOWS_REPLY_TO=you+fellows@example.com
```

Generate a session secret or allowlist HMAC key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Variable | Tier | Purpose | What breaks if unset or wrong |
|---|---|---|---|
| `FELLOWS_SESSION_SECRET` | hard-required | HMAC key (≥48 chars) for the session cookie. | `deploy/server.py` logs "auth disabled" at startup; `/api/auth/status` returns `authEnabled: false` for every request; nobody can sign in. Rotation invalidates every outstanding session. |
| `FELLOWS_ALLOWLIST_HMAC_KEY` | hard-required | HMAC key used to derive the in-memory allowlist from `contact_email` rows in `fellows.db`. The previous flow shipped an `allowed_emails.json` file in `dist/`; the new flow keeps the key off-disk and the allowlist exists only in process memory. | Auth disables itself with a startup warning. Rotation requires every fellow to log in again only if you also rotate the session secret — the allowlist itself is rebuilt on the next start regardless. |
| `FELLOWS_POSTMARK_TOKEN` | hard-required | Postmark Server API token. | `POST /api/send-unlock` raises; users see the anti-enumeration "we'll send a link if it's allowed" reply but no email goes out. journald logs `event=send_unlock_email result=error`. |
| `FELLOWS_MAIL_FROM` | required for non-canonical deploys | Sender on outgoing magic-link emails. In-code default `EHF Directory App <admin@fellows.globaldonut.com>` works for the canonical deploy; **forks must override**. | If set as a bare address (no `Display Name <addr>`), most clients render the local-part as the sender — reads as spam. If unset on a fork, sends as the canonical domain and fails Postmark sender verification. |
| `FELLOWS_PUBLIC_ORIGIN` | required in practice | Base origin for magic-link URLs in email bodies. | Server falls back to inferring from `X-Forwarded-Proto`/`Host`. Works when Caddy forwards both headers; produces malformed links when either is missing. Set it to take the risk off the table. |
| `FELLOWS_REPLY_TO` | optional | Sets the email's `Reply-To` header. Use when the From address isn't a human inbox. | Replies fall through to `FELLOWS_MAIL_FROM`. |

**Migration note (one-time, after `security/tier1-hardening` lands):** an existing droplet's `/etc/fellows/fellows-pwa.env` will not have `FELLOWS_ALLOWLIST_HMAC_KEY`. After deploying the new bundle, the service starts with auth disabled until you add the key. Re-run `just prod-configure-env` (which now prompts for it and offers to generate one) or append the line manually with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and `sudo systemctl restart fellows-pwa`. Every fellow's session also re-logs once on this deploy because cookies bumped from v2 to v3 (server-side session registry).

**Dev-only.** `FELLOWS_COOKIE_INSECURE=1` drops the `Secure` flag from the session cookie so it works over plain HTTP. Used by the in-process test fixture; never set on prod. `FELLOWS_DIST_ROOT` overrides the static-root path the prod server reads from (default `<deploy>/dist`) — useful for staging deploys, not in the bootstrap script.

**Rotating a value:**

```bash
ssh -p 52221 rsb@fellows.globaldonut.com 'sudo nano /etc/fellows/fellows-pwa.env'
ssh -p 52221 rsb@fellows.globaldonut.com 'sudo systemctl restart fellows-pwa'
just prod-env             # confirm new value (paste-ready)
```

`just prod-repair-env` is the documented playbook for a malformed env file. Full operator runbook (Postmark sender setup, debugging, journald event schema): [`docs/email_system_management.md`](email_system_management.md).

## Signing keys and bundle verification

The service worker refuses to install a new bundle unless the manifest signature verifies against the prod public key embedded in `app/static/sw.js` (`PROD_PUBLIC_KEY_HEX`). The trust anchor is therefore the SW that's already on the user's device — a compromise of the prod box after a user installs cannot push a malicious update to that user, because the SW won't accept it.

This section covers: (1) one-time keypair generation; (2) per-deploy signing; (3) the out-of-band fingerprint publication that closes the TOFU gap on first install; (4) the supporting DNS records (CAA) and HSTS preload submission.

### One-time setup — generate the prod signing keypair

Run on your laptop (NOT on the prod droplet):

```bash
just keygen
```

This generates an ECDSA P-256 keypair, prompts for a passphrase, writes the encrypted private key to `~/.fellows/signing-key.enc.pem` (mode `0600`), and prints the public key in two forms:

- **130-char hex** (raw uncompressed point) — paste this into `app/static/sw.js`'s `PROD_PUBLIC_KEY_HEX` constant, replacing the literal `'__PROD_PUBLIC_KEY_HEX__'` placeholder. Commit and push.
- **96-char SHA-384 fingerprint** — print this. Tape it to your monitor. Email it to yourself. This is the value users will compare against the About page on first install (see § Out-of-band fingerprint publication below).

After committing the public key, the next `just ship` signs the bundle automatically.

**Back up the encrypted private key.** If you lose this file you cannot push further updates — users keep running their currently-installed version forever. In the archival-directory model that's a survivable failure (`SECURITY.md` § 1), but it should be a deliberate decision, not an accident. Recommended:

- Copy to a USB stick stored at a different physical location.
- Optionally, also export the encrypted private key into a printed QR (a single P-256 PEM is ~250 bytes — fits trivially in a printable QR).
- Verify a backup by running `python scripts/sign_bundle.py --dry-run --key <backup-path>` on a fresh machine.

The unencrypted private key is **never** written to disk by the keygen tool. The passphrase is read interactively so it never lands in shell history.

### Per-deploy signing

Every `just deploy` and `just ship` now chains `build` → `sign` → push:

```bash
just ship
```

Internally this is `deploy-preflight → test-fast → deploy`, where `deploy` is `build sign deploy-fast`. The `sign` step prompts for the passphrase once (`Passphrase for /Users/.../.fellows/signing-key.enc.pem:`), produces `deploy/dist/manifest.sig`, and the ansible playbook rsyncs it to prod alongside `manifest.json`. The post-deploy smoke check confirms HTTPS reachability; the SW signature verify runs the next time any browser fetches a new `sw.js`.

For automated re-deploys where you've already built and signed locally (e.g. retrying after a transient ansible failure), use:

```bash
just ship-fast       # deploy-fast → smoke; skips build AND sign
```

The ansible playbook has a trip-wire that refuses to rsync if `deploy/dist/manifest.sig` is missing — it fails loud with a "Run `just sign`" message rather than silently shipping an unsigned bundle.

### Migration path — first time signing is enabled

The PR that introduces signing (`security/signed-bundles`) ships with `PROD_PUBLIC_KEY_HEX = '__PROD_PUBLIC_KEY_HEX__'` as a placeholder. Until the operator runs `just keygen` and replaces the constant, prod SW installs **will fail signature verification**.

Failure mode is safe: the *old* SW on every installed device keeps serving the old shell. New users arriving during the migration window don't get an SW (no offline cache) but the page itself still loads — script tags fetch directly from the server.

**Order of operations for activation:**

1. Run `just keygen` on your laptop. Choose a passphrase. Back up the encrypted private key.
2. Edit `app/static/sw.js`: replace the `'__PROD_PUBLIC_KEY_HEX__'` placeholder with the hex the keygen tool printed.
3. Commit and merge that change to `main`.
4. `just ship`. The build will succeed, the sign step prompts for the passphrase, the deploy rolls out.
5. Watch `just prod-logs` for `event=client_error` entries with `kind=sw` — those are SW install failures, which during the activation window should drop to zero as new bundles roll out across users.
6. (Recommended) Test from a fresh incognito window: open `https://fellows.globaldonut.com/`, request a magic link, install. Open DevTools → Application → Service Worker — confirm a fresh SW is active and there are no integrity errors.

### Out-of-band fingerprint publication (closes the TOFU gap)

The trust anchor (`PROD_PUBLIC_KEY_HEX` in `sw.js`) is established on first install. If an attacker intercepts that *first* install, they can plant their own key. Three channels carry the public-key fingerprint so a security-conscious fellow can cross-check:

1. **The magic-link email body** (automatic). After signing is configured, every magic-link email includes a "Public key fingerprint" block. A compromised HTTPS server *cannot also forge the email body* unless the attacker has also stolen the Postmark token — a separate compromise that requires SSH access to the droplet's `/etc/fellows/fellows-pwa.env`.
2. **The About page in the installed app** (`#/about` → "Signing key" row). Users compare what the app shows against what arrived in the email.
3. **The git repo** (`app/static/sw.js`). Independent auditors can compute the fingerprint from `PROD_PUBLIC_KEY_HEX` and compare to what the served bundle reports. The maintainer is encouraged to also paste the fingerprint into a high-visibility second host (a public Gist, the README, social media) so paranoid users have a third comparison path.

All three should match. Mismatch on any pair = stop installing and report.

### Supporting DNS: CAA records

CAA is **hierarchical**: the most-specific CAA record set found walking up from a name is authoritative, and it does *not* merge with ancestor records. That matters here — the `globaldonut.com` zone is **not** Let's-Encrypt-only. Other subdomains legitimately use other CAs (e.g. `pitch.globaldonut.com` → Google Trust Services), and the apex itself has appeared with a Sectigo cert. So a Let's-Encrypt-only CAA on the **apex** would forbid those CAs and break their renewals.

**Scope the records to `fellows.globaldonut.com`**, not the apex. A record at the subdomain overrides the (absent or different) apex policy for that name only, protecting the app's cert without touching the rest of the zone. In RFC 8659 zone-file form:

```
fellows.globaldonut.com.  CAA  0 issue "letsencrypt.org"
fellows.globaldonut.com.  CAA  0 issuewild ";"
fellows.globaldonut.com.  CAA  0 iodef "mailto:richbodo@gmail.com"
```

In the **Cloudflare** dashboard (DNS → Records → Add record), each is **Type `CAA`**, **Name `fellows`** (Cloudflare appends `.globaldonut.com`), **TTL Auto**. Selecting `CAA` reveals a **Flags** field, a **Tag** dropdown, and a value field:

| Tag (raw) | Cloudflare dropdown label | Flags | Value field |
|---|---|---|---|
| `issue` | "Only allow specific hostnames" | `0` | CA domain name: `letsencrypt.org` |
| `issuewild` | "Only allow wildcards" | `0` | CA domain name: `;` (a single semicolon = no CA may issue a wildcard) |
| `iodef` | "Send violation reports to URL" | `0` | Value: `mailto:richbodo@gmail.com` |

Notes: CAA is a DNS-only record type, so **no proxy toggle appears** (expected). The `issuewild ";"` row is optional hardening — Caddy only ever requests the exact name; if the UI rejects a bare `;`, omit that row and wildcard issuance simply follows the `issue` rule (Let's Encrypt only).

Tells every CA: "Only Let's Encrypt may issue certificates for `fellows.globaldonut.com`. Wildcard certs are forbidden. Report attempted misissuance to this mailbox." A rogue CA (or one tricked by a phishing-style domain-validation attack) is required by RFC 8659 to refuse — this raises the bar substantially against a fraudulent-cert MITM at first install.

> **Cloudflare proxy caveat.** `fellows.globaldonut.com` is **DNS-only** today (grey cloud) — browsers get Caddy's Let's Encrypt cert from the droplet directly, so `issue "letsencrypt.org"` is correct. If you ever enable the orange-cloud **proxy** on the `fellows` record, Cloudflare terminates TLS at its edge with *its own* CA — you must then **also** add a CAA `issue` record for Cloudflare's issuer (e.g. `issue "pki.goog"` for Google Trust Services, whichever Cloudflare currently uses) or proxied TLS will break.

> **Apex-wide alternative (only if you want it).** If you later want a single zone-wide policy, put CAA on the apex but enumerate **every** CA actually in use across the zone (`letsencrypt.org` + Google Trust's `pki.goog` + whatever issues the apex), not Let's Encrypt alone — otherwise you break `pitch.globaldonut.com` and the apex. Run `just ct-check` first to see the full issuer list before doing this.

Verify after publication (`just check-env` also runs this check and warns if it's missing):

```bash
dig +short CAA fellows.globaldonut.com   # expect the three lines above
```

### HSTS preload submission — considered and declined

Caddy already sets `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` on both `fellows.globaldonut.com` and the `globaldonut.com` apex. The header alone protects every **returning** visitor (the browser enforces HTTPS for a year after any one HTTPS visit). The `preload` directive additionally closes the **first-visit** window — but only for sites baked into the browsers' preload list, which requires a submission at <https://hstspreload.org/>.

**Decision (2026-05-31): do not submit to the preload list. Keep the header.**

The reasoning:

- **You cannot preload just the subdomain.** hstspreload.org rejects subdomain submissions outright ("`fellows.globaldonut.com` is a subdomain. Please preload `globaldonut.com` instead") — the list only accepts whole registrable domains. So the only available action is preloading the **entire `globaldonut.com` zone** with `includeSubDomains`.
- **That's a permanent, zone-wide commitment for unrelated services.** `just ct-check` shows the zone hosts third-party properties the app doesn't control — `pitch.globaldonut.com` (Pitch, Google Trust certs), `notify.pitch.globaldonut.com` (delegated to `lovable.cloud`). Preloading the apex forces those, and every future subdomain, to be HTTPS-only forever; removal from the list takes months to propagate.
- **The marginal benefit here is small.** The app's entry point is an **HTTPS** magic-link in email, modern browsers already default to HTTPS-first for typed addresses, the HSTS header already covers repeat visits, and CAA + signed bundles + the email fingerprint already defend cert mis-issuance and install integrity. Preload would only close a narrow "user manually types `http://` on a hostile network, on their very first contact, in a browser that doesn't do HTTPS-first" gap.
- **The distribution server is temporary by design.** A preload entry on `globaldonut.com` would **outlive** the fellows app (which is meant to be wound down) and keep encumbering the apex and its other subdomains indefinitely. Encumbering the whole personal domain, semi-permanently, to harden a soon-to-retire delivery channel is a bad trade.

The `preload` token is left in the header (it's inert without a list submission and keeps the door open). **Revisit only if** `globaldonut.com` ever becomes a single-owner, all-HTTPS zone with no third-party subdomains — then preloading the apex would be low-risk.

### Certificate Transparency monitoring (optional but recommended)

Two complementary checks:

- **On-demand:** `just ct-check` (`scripts/check_ct_log.py`) queries crt.sh for every logged certificate covering the domain and flags any issuer that isn't Let's Encrypt. Run it any time, or wire it into a periodic job. Read-only, stdlib only.
- **Push alerts:** subscribe to crt.sh notifications so any *new* cert issuance — by Let's Encrypt or anyone else — generates an email the same day, rather than waiting for the next `just ct-check`. Free signup: <https://crt.sh/?domain=globaldonut.com> → click the email-monitor link.

If a cert appears that you didn't trigger (e.g. an attacker tricked a CA into issuing one despite the CAA records), either path surfaces it.

### What gets signed and what doesn't

The signed manifest at `dist/manifest.json` covers every shell file the SW precaches:

- `index.html`, `app.js`, `sw.js`, `styles.css`, `manifest.webmanifest`
- `vendor/jspdf-2.5.1.umd.min.js`, `vendor/sqlite-worker.js`, `vendor/sqlite3.js`, `vendor/sqlite3.wasm`
- All icons under `icons/`
- `build-meta.json` (which itself carries `fellows_db_sha`, so `fellows.db` integrity flows transitively)

Not in the manifest:

- `fellows.db` — verified transitively via `build-meta.json:fellows_db_sha`; the sqlite worker does that check independently.
- `/images/*` — ~250 profile photos; not security-critical, would balloon the manifest.

If a future change adds a new script or worker to the bundle, **add it to `MANIFEST_INCLUDE_PATHS`** in `build/build_pwa.py`. There's a test (`test_write_bundle_manifest_covers_security_critical_paths`) that pins the must-have entries, but it's an allow-list — it won't catch a newly-introduced file that should be in the list.

## Debugging

- **Service**: `just prod-logs` (`journalctl -u fellows-pwa -f`) streams structured JSON (`event=auth_status`, `event=send_unlock_email`, `event=build_meta`). Pass a different unit with `just prod-logs caddy`.
- **Activity summary**: `just prod-stats` reads journald on the droplet and prints a tally of page loads, directory-API hits, DB downloads, magic-link sends/verifies, the **install funnel** (denominator `landing_shown` + per-step counts down through `app_installed` and `use_in_tab_clicked`, with per-platform splits on `outcome_*` accept/dismiss), 5xx errors, client error reports, and disk usage. Default window is `24 hours ago`; pass any string `journalctl --since` accepts. Common examples: `just prod-stats` for a daily check, `just prod-stats '7 days ago'` for a weekly view (more useful for the install funnel since installs are sparse — answers "of N landing visits this week, what fraction installed vs. timed out vs. used the in-tab escape hatch?"). `just prod-stats-long` extends the window to the full retained journal and lists the plaintext email of every magic-link recipient (joined against `/opt/fellows/deploy/dist/fellows.db` on the droplet). The remote binary is `/opt/fellows/bin/prod_stats` (source: `scripts/prod_stats.py`, deployed by the `fellows_app` Ansible role). No sudo needed — journal-read access is granted by the `systemd-journal` and `adm` group memberships that the `common` role adds to the operator. If `just prod-stats` starts returning all zeros (and the script also prints a "journalctl returned 0 entries" warning on stderr), that membership has drifted; re-run `just bootstrap` to re-apply it.
- **Bundle drift**: `just drift` shows prod's `X-Fellows-Build` alongside local `HEAD` and `origin/main`. The browser's Diagnostics panel (`?diag=1`) shows the same header plus auth state and Cache API contents. Pair with `just prod-logs` to confirm client and server are on the same build.
- **Send-flow failures**: `just email-debug` mines recent `event=send_unlock_email` entries from journald and optionally resolves Postmark `MessageID`s.
- **Deploy failures**: `ansible-playbook … -vvv` for SSH/module detail. Log path is `ansible/ansible.log` relative to the repo root.
- **Permissions on `/opt/fellows`**: `just prod-diag-perms` (a read-only audit) reports group membership, mode bits, setgid inheritance, and runs rsync write probes. If rsync fails with "Permission denied," confirm the operator is in the `fellows` group (`id rsb` should list it) and that a fresh SSH session picked it up (logout/login or the Ansible `reset_connection` step).

## What we explicitly did not build

- No separate CI deploy account. Not needed with one maintainer; revisit when CI arrives.
- No Ansible Vault for secrets. The env-file approach is sufficient; Vault becomes compelling when a team shares the repo.
- No per-command NOPASSWD sudoers for the operator. `--ask-become-pass` once per playbook run is cheap.
- No bastion / jumpbox. One droplet, direct SSH.
- No AppArmor/SELinux profiles. systemd hardening covers the realistic threat model at this scale.
