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

## 4) Verify

```bash
./scripts/smoke_prod.sh
ssh -p 52221 deploy@170.64.243.67 'systemctl status fellows-pwa caddy --no-pager'
```
