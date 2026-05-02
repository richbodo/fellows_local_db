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

# Print LAN URL for testing on a real phone over Wi-Fi, then start server.
[group('dev')]
serve-lan:
    #!/usr/bin/env bash
    set -euo pipefail
    ip=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
    if [ -z "${ip:-}" ]; then
        echo "Could not auto-detect LAN IP. Try: ifconfig | grep 'inet '"
    else
        echo "LAN URL:  http://$ip:{{port}}/"
        echo "(phone must be on the same Wi-Fi network)"
    fi
    ./run.sh start


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

# DB + API + prod-stats only (skip Playwright; ~10x faster).
[group('test')]
test-fast:
    ./scripts/ensure_port_8765_free.sh tests/test_database.py tests/test_api.py tests/test_prod_stats.py -v

# Mobile screenshot harness across device matrix → tests/e2e/mobile/current_state/.
# The committed baselines under __snapshots__/ are a visual reference, not a
# regression gate; review captures by eye after meaningful UI changes.
[group('test')]
test-mobile *args="tests/e2e/mobile/ -v":
    ./scripts/ensure_port_8765_free.sh {{args}}

# Promote the latest mobile captures to baselines. Run after deliberate UI
# changes; review the visual diff in git before committing.
[group('test')]
test-mobile-promote:
    cp tests/e2e/mobile/current_state/*.png tests/e2e/mobile/__snapshots__/
    @echo "Baselines updated. Review the diff in git, then commit."


# ---- build / deploy ------------------------------------------------------

# Assemble deploy/dist/ (runs build/build_pwa.py).
[group('build')]
build:
    python3 build/build_pwa.py

# Print deploy/dist/build-meta.json.
[group('build')]
build-meta:
    @if [ -f deploy/dist/build-meta.json ]; then cat deploy/dist/build-meta.json; else echo "No deploy/dist/build-meta.json — run 'just build' first."; fi

# Bump CACHE_VERSION (sw.js) and FELLOWS_UI_DIAG (app.js) and commit.
#
# The diag string becomes <YYYY-MM-DD>-<short-sha>[-<label>]. Examples:
#   just bump                    -> '2026-05-02-7b5f548'
#   just bump groups-fab         -> '2026-05-02-7b5f548-groups-fab'
#
# Requires a clean working tree so the bump commit is just the version
# files. The bump commit message starts with 'chore(version):' so the
# deploy guard can find it via git log --grep.
#
# Bump versions and commit so 'just deploy' will let you ship.
[group('build')]
bump label="":
    #!/usr/bin/env bash
    set -euo pipefail
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "ERROR: working tree has uncommitted changes."
        echo "Commit or stash first; 'just bump' should be its own commit."
        exit 1
    fi
    sha=$(git rev-parse --short HEAD)
    today=$(date +%Y-%m-%d)
    label="{{label}}"
    if [ -n "${label}" ]; then
        new_diag="${today}-${sha}-${label}"
    else
        new_diag="${today}-${sha}"
    fi
    cur_n=$(grep -oE "CACHE_VERSION = 'v[0-9]+'" app/static/sw.js | grep -oE '[0-9]+' | head -1)
    if [ -z "${cur_n}" ]; then
        echo "ERROR: could not parse CACHE_VERSION from app/static/sw.js"
        exit 1
    fi
    new_n=$((cur_n + 1))
    new_cache="v${new_n}"
    sed -i.bak -E "s|CACHE_VERSION = 'v[0-9]+'|CACHE_VERSION = '${new_cache}'|" app/static/sw.js
    sed -i.bak -E "s|var FELLOWS_UI_DIAG = '[^']*'|var FELLOWS_UI_DIAG = '${new_diag}'|" app/static/app.js
    rm -f app/static/sw.js.bak app/static/app.js.bak
    grep -F "CACHE_VERSION = '${new_cache}'" app/static/sw.js >/dev/null || { echo "ERROR: sw.js bump did not apply"; exit 1; }
    grep -F "FELLOWS_UI_DIAG = '${new_diag}'" app/static/app.js >/dev/null || { echo "ERROR: app.js bump did not apply"; exit 1; }
    git add app/static/sw.js app/static/app.js
    git commit -m "chore(version): bump to ${new_diag} (cache ${new_cache})"
    echo
    echo "Bumped to: ${new_diag}"
    echo "         CACHE_VERSION = ${new_cache}"
    echo "         FELLOWS_UI_DIAG = ${new_diag}"
    echo "         commit $(git rev-parse --short HEAD)"
    echo
    echo "Push when ready:  git push"

# Internal: refuse to deploy if HEAD has commits past the most recent
# 'chore(version):' commit. Bypass with BUMP_GUARD=skip for emergencies
# (e.g. a hotfix where you accept the version label staying behind).
_bump-guard:
    #!/usr/bin/env bash
    set -uo pipefail
    if [ "${BUMP_GUARD:-}" = "skip" ]; then
        echo "WARN: bump guard skipped via BUMP_GUARD=skip"
        exit 0
    fi
    bump=$(git log --grep='^chore(version):' -1 --format=%H 2>/dev/null || true)
    if [ -z "${bump}" ]; then
        echo "ERROR: no chore(version) commit found in history."
        echo "Run:  just bump [<label>]"
        echo "Override: BUMP_GUARD=skip just deploy"
        exit 1
    fi
    n=$(git rev-list "${bump}..HEAD" --count)
    if [ "${n}" -gt 0 ]; then
        echo "ERROR: ${n} commit(s) on HEAD past last version bump (${bump:0:7})."
        echo "Run:  just bump [<label>]   to bump versions to current HEAD."
        echo "      just whats-running    to see drift detail."
        echo "Override: BUMP_GUARD=skip just deploy"
        exit 1
    fi
    echo "[bump-guard] OK: HEAD is the latest version bump."

# Deploy to prod (build + ansible + HTTPS smoke, via ansible/deploy_pwa.yml).
[group('deploy')]
deploy: _bump-guard
    ./scripts/deploy_pwa.sh --ask-become-pass

# Deploy, reusing existing deploy/dist/ (skips the build step).
[group('deploy')]
deploy-fast: _bump-guard
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

# Show local HEAD, on-disk CACHE_VERSION + FELLOWS_UI_DIAG, the most
# recent 'chore(version):' commit, prod's build-meta, and a refresh
# cheat-sheet for the SW shell-cache gotcha.
#
# Show local + prod build versions and refresh tips.
[group('prod')]
whats-running:
    #!/usr/bin/env bash
    set -uo pipefail
    head_sha=$(git rev-parse --short HEAD)
    head_subject=$(git log -1 --format=%s HEAD)
    cache_v=$(grep -oE "CACHE_VERSION = 'v[0-9]+'" app/static/sw.js | grep -oE 'v[0-9]+' | head -1)
    diag=$(grep -E "var FELLOWS_UI_DIAG = '[^']*'" app/static/app.js | head -1 | sed -E "s|.*'([^']*)'.*|\\1|")
    last_bump=$(git log --grep='^chore(version):' -1 --format='%h %ci %s' 2>/dev/null || echo "(none)")
    drift_n=$(if [ -n "$(git log --grep='^chore(version):' -1 --format=%H 2>/dev/null)" ]; then git rev-list "$(git log --grep='^chore(version):' -1 --format=%H)..HEAD" --count; else echo "?"; fi)
    echo "Local"
    echo "  HEAD:                ${head_sha} ${head_subject}"
    echo "  CACHE_VERSION:       ${cache_v}"
    echo "  FELLOWS_UI_DIAG:     ${diag}"
    echo "  Last version bump:   ${last_bump}"
    echo "  Commits past bump:   ${drift_n}"
    echo
    echo "Prod ({{base_url}})"
    if curl -sf "{{base_url}}/build-meta.json" -o /tmp/_fellows_bm.json 2>/dev/null; then
        prod_sha=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_bm.json')).get('git_sha','?'))" 2>/dev/null || echo '?')
        prod_built=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_bm.json')).get('built_at','?'))" 2>/dev/null || echo '?')
        echo "  git_sha:             ${prod_sha}"
        echo "  built_at:            ${prod_built}"
        rm -f /tmp/_fellows_bm.json
    else
        echo "  (could not fetch /build-meta.json)"
    fi
    echo
    echo "Browser refresh tips"
    echo "  - Cmd-Shift-R (Ctrl-Shift-R on Linux/Win) bypasses the SW shell cache."
    echo "  - Clear App Cache & Reload: cookie + IndexedDB + caches go; OPFS"
    echo "    (groups, settings, fellows.db) survives by design."
    echo "  - Incognito window: nuclear-clean baseline (no SW, no OPFS, no cookie)."

# Compare prod's git SHA to local HEAD and origin/main, side-by-side.
# All three lines have the same shape — <sha> <iso-timestamp> <subject>
# — so a glance tells you whether prod, your laptop, and the remote are
# in sync. Reads /build-meta.json for the prod SHA (the X-Fellows-Build
# response header is still set on every API response for DevTools /
# journald correlation; this recipe just doesn't use it).
[group('prod')]
drift:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "Prod ({{base_url}}):"
    if curl -sf "{{base_url}}/build-meta.json" -o /tmp/_fellows_drift_bm.json 2>/dev/null; then
        prod_sha=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_drift_bm.json')).get('git_sha','?'))" 2>/dev/null || echo '?')
        prod_built=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_drift_bm.json')).get('built_at','?'))" 2>/dev/null || echo '?')
        prod_subj=$(git log -1 --format=%s "${prod_sha}" 2>/dev/null || echo '(commit not in local clone — git fetch?)')
        echo "  ${prod_sha} ${prod_built}  ${prod_subj}"
        rm -f /tmp/_fellows_drift_bm.json
    else
        echo "  (could not fetch /build-meta.json — prod down or unreachable?)"
    fi
    echo
    echo "Local HEAD:"
    git log -1 --format='  %h %cI  %s' HEAD
    echo "origin/main:"
    git log -1 --format='  %h %cI  %s' origin/main 2>/dev/null || echo "  (no origin/main)"

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

# 4xx/5xx counters and the 10 most recent error access lines (default 24h).
[group('prod')]
prod-errors since="24 hours ago":
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "/opt/fellows/bin/prod_stats --errors-only --since '{{since}}'"

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
