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

From the repo root:

```bash
# Rebuild the static bundle and push to the droplet (most common flow).
./scripts/deploy_pwa.sh --ask-become-pass

# Equivalent manual form:
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
./scripts/smoke_prod.sh       # /healthz, /manifest.webmanifest
./scripts/check_deploy_env.sh # DNS + TLS
ssh -p 52221 rsb@fellows.globaldonut.com 'systemctl status fellows-pwa caddy --no-pager'
```

## Bootstrapping a fresh droplet

```bash
# 1. Provision Droplet, assign Reserved IP (170.64.243.67), create DNS A record.
# 2. Ensure your SSH key is in /home/rsb/.ssh/authorized_keys on the droplet.
# 3. From the repo root:
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

The first run creates the `fellows` system user, adds `rsb` to the `fellows` group, writes the hardened systemd unit, and starts the service. If a legacy `deploy` account is present from a pre-migration droplet, the second play in `site.yml` removes it.

## Magic-link env file

After bootstrap, install Postmark + session secrets once:

```bash
./scripts/configure_email_auth_env.sh
```

The script prompts for `FELLOWS_MAIL_FROM`, `FELLOWS_PUBLIC_ORIGIN`, `FELLOWS_POSTMARK_TOKEN`, `FELLOWS_SESSION_SECRET`, then SSHes to the droplet and creates `/etc/fellows/fellows-pwa.env` (`root:fellows 0640`) and the systemd drop-in. Re-run only when a secret rotates.

## Debugging

- **Service**: `journalctl -u fellows-pwa -f` streams structured JSON (`event=auth_status`, `event=send_unlock_email`, `event=build_meta`).
- **Bundle drift**: the browser has a Diagnostics panel (`?diag=1`) that shows `X-Fellows-Build`, auth state, and Cache API contents. Pair with `journalctl` to confirm client and server are on the same build.
- **Deploy failures**: `ansible-playbook … -vvv` for SSH/module detail. Log path is `ansible/ansible.log` relative to the repo root.
- **Permissions on `/opt/fellows`**: if rsync fails with "Permission denied," confirm the operator is in the `fellows` group (`id rsb` should list it) and that a fresh SSH session picked it up (logout/login or the Ansible `reset_connection` step).

## What we explicitly did not build

- No separate CI deploy account. Not needed with one maintainer; revisit when CI arrives.
- No Ansible Vault for secrets. The env-file approach is sufficient; Vault becomes compelling when a team shares the repo.
- No per-command NOPASSWD sudoers for the operator. `--ask-become-pass` once per playbook run is cheap.
- No bastion / jumpbox. One droplet, direct SSH.
- No AppArmor/SELinux profiles. systemd hardening covers the realistic threat model at this scale.
