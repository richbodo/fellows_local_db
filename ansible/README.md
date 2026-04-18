# Ansible Deploy Notes

Mechanical details for running Ansible against the fellows droplet. For the unix architecture (service account, operator privileges, systemd hardening) see [`docs/DevOps.md`](../docs/DevOps.md). For routine ops (deploy, smoke, bootstrap a new droplet) start there as well — this file only covers Ansible-specific mechanics.

## Run from the repository root

Ansible resolves paths from your **current working directory**. The repo has an **`ansible.cfg` at the project root** so inventory is picked up automatically.

```bash
cd /path/to/fellows_local_db

ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

If you run the same command from `~` (home), Ansible looks for `ansible/site.yml` **under your home directory** and fails with "playbook could not be found", and it will not use this repo's inventory (so you also see the default **SSH port 22**).

If you still see **port 22** from the repo root, your `ansible/inventory/hosts.ini` is probably missing **`ansible_port=52221`** under `[fellows:vars]` (older copy). Either add that line or re-copy from `hosts.ini.example`. The committed file `ansible/inventory/group_vars/fellows.yml` also sets the port for this inventory directory.

### Controller prerequisites (one-time)

The **deploy** role uses **`ansible.posix.synchronize`** (rsync over SSH). **`ansible-galaxy`** is a **separate CLI** (it ships with Ansible); it is **not** part of `ansible-playbook`. Install the collection once per clone or after changing `requirements.yml`:

```bash
cd /path/to/fellows_local_db
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
```

If the command prints **"Nothing to do. All requested collections are already installed."**, that is normal—you already have the collection and can go straight to **`ansible-playbook`**.

Use the install command again after cloning on a new machine. Installed files live under `ansible/collections/ansible_collections/` (gitignored); only `ansible/collections/requirements.yml` is committed.

The **managed node** must have the **`rsync`** package. It is installed on **`--tags bootstrap`**.

### Playbook log file (control machine)

The repo root **`ansible.cfg`** sets **`log_path = ansible/ansible.log`**. Ansible appends to that file on **the computer where you run `ansible-playbook`** (your Mac), not on the VPS.

Run playbooks from the **repository root** so the path resolves correctly — for example **`/path/to/fellows_local_db/ansible/ansible.log`**. If you start Ansible from another directory, the log may be created relative to that working directory instead.

## How Ansible reaches the server

- Ansible **opens an SSH session** as `ansible_user` (the human operator — see `docs/DevOps.md`), using your SSH key.
- Tasks that need root use **privilege escalation**: `become: true` in this repo's `ansible.cfg` uses **`sudo`** (not `su`).
- `--ask-become-pass` prompts for **the operator's sudo password** when passwordless sudo is not configured.
- **Adhoc commands** that don't need root (`ping`, `setup`) require `ANSIBLE_BECOME=false` because `ansible.cfg` sets `become = true` globally:

  ```bash
  ANSIBLE_BECOME=false ansible fellows -m ping
  ```

## Tags and plays

`site.yml` is two plays. The first runs three roles; the second is a one-time migration cleanup that retires a legacy `deploy` account on droplets provisioned before the current model.

- `--tags bootstrap` — everything: packages, service account, UFW, SSH hardening, Caddy, app dirs, systemd unit, service start, legacy-account cleanup.
- `--tags deploy` — only the `fellows_app` tasks needed to push a new build (file copies + rsync + restart handler).

## First-run checklist

```bash
cp ansible/inventory/hosts.ini.example ansible/inventory/hosts.ini
cp ansible/group_vars/fellows.yml.example ansible/group_vars/fellows.yml
# edit ansible_host, ansible_port, ansible_user, key path, caddy_admin_email
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

On first run, the `common` role adds the operator (e.g. `rsb`) to the `fellows` group and then runs `meta: reset_connection` so subsequent tasks in the same playbook see the new group membership. If you ever see rsync errors about permission on `/opt/fellows/deploy/dist/`, the most likely cause is that the operator is not yet in the `fellows` group — run `--tags bootstrap` once.

## Routine deploy

```bash
./scripts/deploy_pwa.sh --ask-become-pass
```

Equivalent manual flow:

```bash
python build/build_pwa.py
ansible-playbook ansible/site.yml --tags deploy --ask-become-pass
```

Extra-vars supported by `ansible/deploy_pwa.yml`:

| Variable | Purpose |
|----------|---------|
| `fellows_skip_build=true` | Skip `build_pwa.py` when `deploy/dist/` is already up to date. |
| `fellows_smoke=false` | Skip HTTPS checks (offline controller, or no outbound access). |
| `fellows_smoke_url=https://…` | Override the default `https://fellows.globaldonut.com` smoke target. |

## Verify

```bash
./scripts/smoke_prod.sh
./scripts/check_deploy_env.sh
ssh -p 52221 rsb@170.64.243.67 'systemctl status fellows-pwa caddy --no-pager'
```

`check_deploy_env.sh` runs `dig` for the `A` record and `curl` against `https://<host>/` and `/healthz` (set `FELLOWS_HOST` if not using `fellows.globaldonut.com`).

## Debugging slow or stuck deploys

- **Verbose output:** add `-vvv` to `ansible-playbook` (or `-v` / `-vv`). That shows SSH and module activity on the terminal.
- **Log file:** see **[Playbook log file (control machine)](#playbook-log-file-control-machine)** above. Override the path for one shell with `export ANSIBLE_LOG_PATH=/tmp/ansible.log`. There is no automatic Ansible log file on the VPS — only on the control machine.
- **Rsync errors: `Permission denied` / `failed to set times` on `/opt/fellows/deploy/dist`:** operator is not in the `fellows` group, or a fresh SSH session has not picked up the group membership. Confirm with `id rsb` on the droplet (must show `fellows`). Re-run `--tags bootstrap` to (re-)join the group and flush the connection.
- **Test rsync outside Ansible** (paths match the playbook; substitute host, port, and user from `ansible/inventory/hosts.ini`):

  ```bash
  rsync -avzn --delete \
    "$(pwd)/deploy/dist/" "rsb@170.64.243.67:/opt/fellows/deploy/dist/" \
    -e "ssh -p 52221 -i ~/.ssh/id_ed25519"
  ```

  `-n` is a dry run. Drop `-n` to perform the sync. If this hangs or errors, the issue is SSH / rsync / network — not Ansible's YAML.
- **Partial `deploy/dist` on the server:** the role uses rsync with `--delete`, which reconciles the tree. Re-run `--tags deploy` after `python build/build_pwa.py`. To reset aggressively: `sudo rm -rf /opt/fellows/deploy/dist/*` on the server, then redeploy.

## Magic-link env

The deploy bundle includes `allowed_emails.json` (from `build/build_pwa.py`). To turn on the browser gate, the `fellows-pwa` service needs env vars `FELLOWS_SESSION_SECRET` and `FELLOWS_POSTMARK_TOKEN`. Run `./scripts/configure_email_auth_env.sh` from the repo root to install `/etc/fellows/fellows-pwa.env` (`root:fellows 0640`) and the systemd `EnvironmentFile=` drop-in. Without these, `deploy/server.py` serves without the email gate.

See [`docs/email_system_management.md`](../docs/email_system_management.md) for full operator runbook, Postmark debugging, and journald event schema.
