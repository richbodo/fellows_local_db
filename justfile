# Fellows Local DB — command runner. See docs/justfile.md.
# Run `just` with no args to see the menu.

set shell := ["bash", "-euo", "pipefail", "-c"]

db         := "app/fellows.db"
db_backup  := "app/fellows.db.backup.2026-04-08"
port       := "8765"
venv       := ".venv"
pytest     := venv / "bin/pytest"
host       := env_var_or_default("FELLOWS_HOST", "fellows.globaldonut.com")
ssh_port   := env_var_or_default("FELLOWS_SSH_PORT", "52221")
ssh_user   := env_var_or_default("FELLOWS_SSH_USER", "rsb")
base_url   := env_var_or_default("FELLOWS_BASE_URL", "https://fellows.globaldonut.com")
opener     := if os() == "macos" { "open" } else { "xdg-open" }

# Show the recipe menu.
default:
    @just --list


# ---- setup ---------------------------------------------------------------

# Create .venv, install dev deps + Playwright + ansible collections, build DB.
[group('setup')]
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d {{venv}} ]; then
        python3 -m venv {{venv}}
    fi
    {{venv}}/bin/pip install --upgrade pip
    {{venv}}/bin/pip install -r requirements-dev.txt
    {{venv}}/bin/playwright install chromium
    ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections
    if [ ! -f {{db}} ]; then
        python3 build/restore_from_knack_scrapefile.py
    fi
    echo "Setup complete."

# Sanity-check the dev environment.
[group('setup')]
doctor:
    #!/usr/bin/env bash
    set -uo pipefail
    ok=1
    chk() { if "$@" >/dev/null 2>&1; then echo "  OK   $*"; else echo "  FAIL $*"; ok=0; fi; }
    echo "venv:"
    chk test -x {{pytest}}
    echo "DB:"
    chk test -f {{db}}
    echo "Playwright:"
    chk {{venv}}/bin/python -c "import playwright"
    echo "Ansible collections:"
    chk test -d ansible/collections/ansible_collections/ansible/posix
    echo "Port {{port}}:"
    if lsof -ti:{{port}} >/dev/null 2>&1; then
        pid=$(lsof -ti:{{port}} | head -1)
        echo "  WARN port {{port}} in use (PID $pid) — run 'just port' to free"
    else
        echo "  OK   port {{port}} free"
    fi
    if [ "$ok" = "1" ]; then echo "All checks passed."; else echo "One or more checks failed."; exit 1; fi

# Stop server and remove .venv (leaves data alone).
[group('setup')]
clean: stop
    rm -rf {{venv}}
    @echo "Removed {{venv}}. Data (app/fellows.db, final_fellows_set/) left in place."


# ---- dev server ----------------------------------------------------------

# Start dev server in background, open browser.
[group('dev')]
serve:
    ./run.sh start

# Start dev server in foreground (Ctrl-C to stop).
[group('dev')]
serve-fg:
    python3 app/server.py

# Stop the background dev server.
[group('dev')]
stop:
    ./run.sh stop

# Show dev server status.
[group('dev')]
status:
    ./run.sh status

# Stop + start.
[group('dev')]
restart: stop serve

# Stop, canonical DB rebuild (with backup), start.
[group('dev')]
reset: stop db-rebuild serve

# Free port 8765.
[group('dev')]
port:
    ./scripts/ensure_port_8765_free.sh

# Open http://localhost:8765/?gate=1 (force email gate for auth testing).
[group('dev')]
gate:
    {{opener}} "http://localhost:{{port}}/?gate=1"


# ---- db / data -----------------------------------------------------------

# Canonical rebuild from Knack dump (auto-backup first).
[group('db')]
db-rebuild: data-backup
    python3 build/restore_from_knack_scrapefile.py
    @just db-stats

# Bytewise-diff app/fellows.db against the Apr 8 reference backup.
[group('db')]
db-verify:
    python3 build/diff_fellows_db.py {{db}} {{db_backup}}

# Bytewise-diff app/fellows.db against OTHER.
[group('db')]
db-diff other:
    python3 build/diff_fellows_db.py {{db}} {{other}}

# Row / email / image counts.
[group('db')]
db-stats:
    #!/usr/bin/env bash
    set -euo pipefail
    rows=$(sqlite3 {{db}} 'SELECT COUNT(*) FROM fellows;')
    emails=$(sqlite3 {{db}} "SELECT COUNT(*) FROM fellows WHERE contact_email IS NOT NULL AND trim(contact_email) != '';")
    images=$(sqlite3 {{db}} 'SELECT COUNT(*) FROM fellows WHERE has_image = 1;')
    echo "Rows:    $rows"
    echo "Emails:  $emails"
    echo "Images:  $images"

# Open app/fellows.db in sqlite3.
[group('db')]
db-open:
    sqlite3 {{db}}

# Download missing profile images from Knack S3.
[group('db')]
images-fetch:
    python3 build/fetch_missing_images.py

# Print what images WOULD be fetched (--dry-run).
[group('db')]
images-fetch-dry:
    python3 build/fetch_missing_images.py --dry-run


# ---- backup / restore ----------------------------------------------------

# Snapshot DB + source JSONs + images → backup/*.zip.
[group('data')]
data-backup:
    ./scripts/backup_fellows_data.sh

# Restore from backup zip (pass a path or --latest; default --latest).
[group('data')]
data-restore zip="--latest":
    ./scripts/restore_fellows_data.sh {{zip}}

# Dry-run restore: print manifest + file list, don't touch anything.
[group('data')]
data-restore-dry zip="--latest":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{zip}}" = "--latest" ]; then
        target=$(ls -t backup/fellows_data_*.zip 2>/dev/null | head -1)
        if [ -z "$target" ]; then echo "No backups in backup/"; exit 1; fi
        ./scripts/restore_fellows_data.sh --dry-run "$target"
    else
        ./scripts/restore_fellows_data.sh --dry-run {{zip}}
    fi


# ---- tests ---------------------------------------------------------------

# Free port and run pytest. Extra args pass through (use `--` before flags).
[group('test')]
test *args="tests/ -v":
    ./scripts/ensure_port_8765_free.sh {{args}}

# DB unit tests only (no server needed).
[group('test')]
test-db:
    {{pytest}} tests/test_database.py -v

# HTTP API tests (frees port first).
[group('test')]
test-api:
    ./scripts/ensure_port_8765_free.sh tests/test_api.py -v

# Playwright e2e tests (FILTER maps to pytest -k).
[group('test')]
test-e2e filter="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{filter}}" ]; then
        ./scripts/ensure_port_8765_free.sh tests/e2e/ -v
    else
        ./scripts/ensure_port_8765_free.sh tests/e2e/ -v -k "{{filter}}"
    fi

# DB + API only (skip Playwright; ~10x faster).
[group('test')]
test-fast:
    ./scripts/ensure_port_8765_free.sh tests/test_database.py tests/test_api.py -v


# ---- build / deploy ------------------------------------------------------

# Assemble deploy/dist/ (runs build/build_pwa.py).
[group('build')]
build:
    python3 build/build_pwa.py

# Print deploy/dist/build-meta.json.
[group('build')]
build-meta:
    @if [ -f deploy/dist/build-meta.json ]; then cat deploy/dist/build-meta.json; else echo "No deploy/dist/build-meta.json — run 'just build' first."; fi

# Deploy to prod (build + ansible + HTTPS smoke, via ansible/deploy_pwa.yml).
[group('deploy')]
deploy:
    ./scripts/deploy_pwa.sh --ask-become-pass

# Deploy, reusing existing deploy/dist/ (skips the build step).
[group('deploy')]
deploy-fast:
    ansible-playbook ansible/deploy_pwa.yml --ask-become-pass --extra-vars "fellows_skip_build=true"

# Ansible --check (dry run, no changes made).
[group('deploy')]
deploy-check:
    ansible-playbook ansible/deploy_pwa.yml --ask-become-pass --check

# Full ship: test-fast → deploy (ansible does build + deploy + smoke).
[group('deploy')]
ship: test-fast deploy

# Fast ship: deploy-fast → smoke (skip tests and rebuild).
[group('deploy')]
ship-fast: deploy-fast smoke

# First-time bootstrap: ansible site.yml --tags bootstrap.
[group('deploy')]
bootstrap:
    ansible-playbook ansible/site.yml --tags bootstrap --ask-become-pass

# Install ansible collections (once per machine).
[group('deploy')]
ansible-collections:
    ansible-galaxy collection install -r ansible/collections/requirements.yml -p ansible/collections

# Quick reachability check (no sudo).
[group('deploy')]
ansible-ping:
    ANSIBLE_BECOME=false ansible fellows -m ping


# ---- production ops ------------------------------------------------------

# HTTPS smoke check (pass URL to override the default prod base).
[group('prod')]
smoke url="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{url}}" ]; then
        ./scripts/smoke_prod.sh
    else
        FELLOWS_BASE_URL="{{url}}" ./scripts/smoke_prod.sh
    fi

# DNS + TLS sanity check against FELLOWS_HOST (default fellows.globaldonut.com).
[group('prod')]
check-env:
    ./scripts/check_deploy_env.sh

# Compare local HEAD to prod's X-Fellows-Build header.
[group('prod')]
drift:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "Prod X-Fellows-Build:"
    curl -sSI {{base_url}}/api/auth/status 2>/dev/null | awk 'BEGIN{IGNORECASE=1} /^x-fellows-build/ {print "  " $0}' | tr -d '\r' || true
    echo
    echo "Local HEAD:"
    git log -1 --format='  %ci %h %s' HEAD
    echo "origin/main:"
    git log -1 --format='  %ci %h %s' origin/main 2>/dev/null || echo "  (no origin/main)"

# Tail journald for UNIT (default fellows-pwa).
[group('prod')]
prod-logs unit="fellows-pwa":
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "journalctl -u {{unit}} -f"

# Production stats summary (page views, magic links, disk) for SINCE.
[group('prod')]
prod-stats since="24 hours ago":
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "/opt/fellows/bin/prod_stats --since '{{since}}'"

# Full-history stats + plaintext recipient list for every magic-link send.
[group('prod')]
prod-stats-long:
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "/opt/fellows/bin/prod_stats --include-emails"

# systemctl status fellows-pwa caddy.
[group('prod')]
prod-status:
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "systemctl status fellows-pwa caddy --no-pager"

# Dump remote /etc/fellows/fellows-pwa.env (prompts for sudo password).
[group('prod')]
prod-env:
    ./scripts/show_server_env.sh

# Interactive first-time / rotate setup of the prod env file.
[group('prod')]
prod-configure-env:
    ./scripts/configure_email_auth_env.sh

# Reference repair for a malformed /etc/fellows/fellows-pwa.env.
[group('prod')]
prod-repair-env:
    ./scripts/repair_email_auth_env.sh

# Read-only diagnostic for rsync permission issues under /opt/fellows/.
[group('prod')]
prod-diag-perms host="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{host}}" ]; then
        ./scripts/diagnose_deploy_perms.sh
    else
        ./scripts/diagnose_deploy_perms.sh {{host}}
    fi

# Debug magic-link send flow (SINCE default '24 hours ago', EMAIL optional).
[group('prod')]
email-debug since="24 hours ago" email="":
    #!/usr/bin/env bash
    set -euo pipefail
    args=(--since "{{since}}")
    if [ -n "{{email}}" ]; then
        args+=(--email "{{email}}")
    fi
    scripts/debug_email_delivery.py "${args[@]}"
