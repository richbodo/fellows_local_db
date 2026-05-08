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
```

`ProtectSystem=strict` remounts the entire filesystem read-only for the service except `/dev`, `/proc`, `/sys` (handled separately), and anything in `ReadWritePaths`. `dist/` is explicitly writable only as a safety net for SQLite journal files — the server's SQL path is SELECT-only in practice. If you later switch the Python code to open the DB with `?mode=ro`, you can drop `ReadWritePaths` entirely.

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

If you're forking this repo for your own org, this is the section you want. Bootstrap is **two phases**: provision/playbook, then secrets. Both are required before the email gate works — the service starts after step 4 below but won't be able to send magic links or verify sessions until step 5 lands the secrets.

```bash
# 1. Provision Droplet, assign Reserved IP (170.64.243.67), create DNS A record.
# 2. Ensure your SSH key is in /home/<operator>/.ssh/authorized_keys on the droplet.
# 3. Edit ansible/inventory/hosts.ini and ansible/group_vars/fellows.yml from the
#    .example templates (host, port, user, key path, caddy_admin_email).
# 4. From the repo root:
just ansible-collections    # one-time per workstation
just bootstrap              # ansible site.yml --tags bootstrap --ask-become-pass
# 5. Install required env vars (Postmark token, session secret, public origin):
just prod-configure-env     # interactive; writes /etc/fellows/fellows-pwa.env
# 6. Verify:
just smoke                  # /healthz, /manifest.webmanifest, /api/debug/diagnostics
```

Under the hood for step 4:

```bash
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

That run creates the `fellows` system user, adds the operator to the `fellows` group, writes the hardened systemd unit, and starts the service. If a legacy `deploy` account is present from a pre-migration droplet, the second play in `site.yml` removes it. The service starts but **does not yet have its env vars** — auth status reports `authEnabled: false`, no magic links can be issued — until step 5 runs.

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
