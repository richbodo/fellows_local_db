# Ansible Deploy Notes

This directory bootstraps and deploys the Fellows PWA host on Ubuntu.

## Run from the repository root

Ansible resolves paths from your **current working directory**. The repo has an **`ansible.cfg` at the project root** so inventory is picked up automatically.

```bash
cd /path/to/fellows_local_db

ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

If you run the same command from `~` (home), Ansible looks for `ansible/site.yml` **under your home directory** and fails with “playbook could not be found”, and it will not use this repo’s inventory (so you also see the default **SSH port 22**).

If you still see **port 22** from the repo root, your `ansible/inventory/hosts.ini` is probably missing **`ansible_port=52221`** under `[fellows:vars]` (older copy). Either add that line or re-copy from `hosts.ini.example`. The committed file `ansible/inventory/group_vars/fellows.yml` also sets the port for this inventory directory.

### Controller prerequisites (one-time)

The **deploy** role uses **`ansible.posix.synchronize`** (rsync over SSH). **`ansible-galaxy`** is a **separate CLI** (it ships with Ansible); it is **not** part of `ansible-playbook`. Install the collection once per clone or after changing `requirements.yml`:

```bash
cd /path/to/fellows_local_db
ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
```

If the command prints **“Nothing to do. All requested collections are already installed.”**, that is normal—you already have the collection and can go straight to **`ansible-playbook`**.

Use the install command again after cloning on a new machine. Installed files live under `ansible/collections/ansible_collections/` (gitignored); only `ansible/collections/requirements.yml` is committed.

The **managed node** must have the **`rsync`** package. It is installed on **`--tags bootstrap`**. If the server predates that task, run `sudo apt install rsync` once on the host.

**`ansible_user` vs `deploy` and rsync:** The **`synchronize`** task runs **`rsync` on your Mac** and opens **SSH to the droplet** using the connection user. The **remote** side of rsync runs **as that SSH user**. App files under **`/opt/fellows/deploy`** are owned by **`deploy`**. If **`ansible_user`** in **`hosts.ini`** is still **`rsb`**, **`rsb` cannot create files there** (mode `0755`), and you see **`Permission denied`** / **`failed to set times`** even when directories look “fine” as root. The **`fellows_app`** role sets **`ansible_user: "{{ deploy_user }}"`** (usually **`deploy`**) **only on the rsync task**, so you can keep **`rsb`** in inventory for other work. Ensure your SSH public key is in **`/home/deploy/.ssh/authorized_keys`** (bootstrap does this). For a manual test that matches Ansible after the fix:

```bash
rsync -avz --delete --partial \
  "$(pwd)/deploy/dist/" "deploy@<ansible_host>:/opt/fellows/deploy/dist/" \
  -e "ssh -p <ansible_port>"
```

If that works but **`rsync … rsb@…`** does not, the diagnosis is the same.

### Playbook log file (control machine)

The repo root **`ansible.cfg`** sets **`log_path = ansible/ansible.log`**. Ansible appends to that file on **the computer where you run `ansible-playbook`** (your Mac), not on the VPS.

Run playbooks from the **repository root** so the path resolves correctly—for example **`/path/to/fellows_local_db/ansible/ansible.log`**. If you start Ansible from another directory, the log may be created relative to that working directory instead.

## How Ansible reaches the server

- Ansible **opens an SSH session** as `ansible_user` from your inventory (by default using your SSH key, same as `ssh`).
- Tasks that need root use **privilege escalation**: `become: true` in this repo’s `ansible.cfg` uses **`sudo`** (Ansible’s default for `become_method` here — not `su`).
- `--ask-become-pass` prompts for **that user’s sudo password** when passwordless sudo is not configured. If `rsb` already has passwordless sudo, you can omit `--ask-become-pass`.

The file you showed on the VM (`/etc/ssh/ssh_config`) is the **SSH client** defaults for outbound connections from that machine. It does **not** set which port **sshd** listens on. Ansible’s port comes from inventory: **`ansible_port=52221`**.

## 1) Prepare local files

```bash
cp ansible/inventory/hosts.ini.example ansible/inventory/hosts.ini
cp ansible/group_vars/fellows.yml.example ansible/group_vars/fellows.yml
```

Adjust `ansible_host`, `ansible_port`, `ansible_user`, and `ansible_ssh_private_key_file` as needed. For this droplet, inventory uses **`rsb`** on port **`52221`** until you switch to `deploy`.

## 2) Bootstrap server (first run as `rsb`)

```bash
ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass
```

This creates `deploy`, installs your SSH key, applies limited sudo, enables UFW (including **`ssh_listen_port`** from `group_vars`, default 52221 in the example), installs Caddy, deploys the app service, and hardens SSH (`PasswordAuthentication no` for sshd).

## 3) Switch inventory to deploy user

After bootstrap, update `ansible/inventory/hosts.ini`:

- `ansible_user=deploy`
- keep `ansible_port=52221` (unless you change sshd)
- keep `ansible_ssh_private_key_file` pointing to your private key

Then run deploy updates:

```bash
python build/build_pwa.py
ansible-playbook ansible/site.yml --tags deploy --ask-become-pass
```

### One-command build, deploy, and HTTPS smoke

From the repository root, this runs **`build/build_pwa.py` on your laptop** (Ansible controller), syncs `deploy/` to the host with the **`fellows_app`** role (same as `--tags deploy`), then hits **`/healthz`** and **`/manifest.webmanifest`** on the public URL via **`ansible.builtin.uri`**:

```bash
./scripts/deploy_pwa.sh --ask-become-pass
```

Equivalent:

```bash
ansible-playbook ansible/deploy_pwa.yml --ask-become-pass
```

**Extra variables:**

| Variable | Purpose |
|----------|---------|
| `fellows_skip_build=true` | Skip `build_pwa.py` when `deploy/dist/` is already up to date. |
| `fellows_smoke=false` | Skip HTTPS checks (offline controller, or no outbound access). |
| `fellows_smoke_url=https://…` | Override the default `https://fellows.globaldonut.com` smoke target. |

Example:

```bash
ansible-playbook ansible/deploy_pwa.yml --extra-vars "fellows_skip_build=true" --ask-become-pass
```

### Phase 4 (magic link) on the server

The deploy bundle includes **`allowed_emails.json`** (from `build/build_pwa.py`). To turn on the browser gate, the **`fellows-pwa`** service needs environment variables **`FELLOWS_SESSION_SECRET`** and **`FELLOWS_POSTMARK_TOKEN`** (see **`ansible/group_vars/fellows.yml.example`** comments). Use a **systemd drop-in** or **`EnvironmentFile=`** pointing at a root-only file on the droplet; do not commit secrets. Without them, **`deploy/server.py`** behaves like Phase 3 (no email gate).

## 4) Verify

```bash
./scripts/smoke_prod.sh
./scripts/check_deploy_env.sh
ssh -p 52221 deploy@170.64.243.67 'systemctl status fellows-pwa caddy --no-pager'
```

`check_deploy_env.sh` runs `dig` for the `A` record and `curl` against `https://<host>/` and `/healthz` (set `FELLOWS_HOST` if not using `fellows.globaldonut.com`).

## Debugging slow or stuck deploys

- **Verbose output:** add `-vvv` to `ansible-playbook` (or `-v` / `-vv`). That shows SSH and module activity on the terminal.
- **Log file:** see **[Playbook log file (control machine)](#playbook-log-file-control-machine)** above. You can override the path for one shell with **`export ANSIBLE_LOG_PATH=/tmp/ansible.log`**. There is no automatic Ansible log file on the VPS—only on the control machine.
- **Rsync errors: `Permission denied` / `failed to set times` on `/opt/fellows/deploy/dist`:** (1) **Wrong SSH user:** see **[ansible_user vs deploy and rsync](#controller-prerequisites-one-time)**—if Ansible connects as **`rsb`**, the remote rsync process is **`rsb`**, which cannot write **`deploy`**-owned paths. The role forces **`deploy`** for the rsync task only. (2) **Wrong ownership:** leftover **root**-owned files under **`dist/`**—the role runs **`chown -R deploy`** on **`{{ app_root }}/deploy`** before rsync; you can also run **`sudo chown -R deploy:deploy /opt/fellows/deploy`** on the server once.
- **Test rsync outside Ansible** (paths match the playbook; substitute host, port, and user from `ansible/inventory/hosts.ini`):

  ```bash
  rsync -avzn --delete \
    "$(pwd)/deploy/dist/" "deploy@YOUR_HOST:/opt/fellows/deploy/dist/" \
    -e "ssh -p YOUR_SSH_PORT -i ~/.ssh/YOUR_KEY"
  ```

  `-n` is a dry run (no writes). Drop `-n` to perform the sync. If this hangs or errors, the issue is SSH/rsync/network—not Ansible’s YAML.
- **Partial `deploy/dist` on the server:** If an old **`copy`** run stopped mid-way, you might see only a handful of files on disk. The role now uses **rsync with `--delete`**, which reconciles the tree. Re-run **`--tags deploy`** after `python build/build_pwa.py`. To reset aggressively: move or delete `/opt/fellows/deploy/dist` on the server (the playbook recreates it) and deploy again.
