# Fellows Local DB — command runner. See docs/justfile.md.
# Run `just` with no args to see the menu.

set shell := ["bash", "-euo", "pipefail", "-c"]

db         := "app/fellows.db"
db_backup  := "app/fellows.db.backup.2026-04-08"
port       := "8765"
venv       := ".venv"
pytest     := venv / "bin/pytest"
# Pick the venv's Python when it's been materialised by `just setup`,
# fall back to system `python3` (fresh clone, pre-setup). Evaluated at
# parse time on every `just` invocation, so the first run after setup
# automatically switches over — no shell re-source needed. Recipes
# that historically used bare `python3` (serve-fg, build, db-*, etc.)
# silently picked up system Python and missed venv-installed deps
# like `cryptography` (added in PR #146 for SW signature verify); this
# variable removes that footgun without forcing users to `source .venv/bin/activate`.
python     := `if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi`
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
        {{venv}}/bin/python build/restore_from_knack_scrapefile.py
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
    {{python}} app/server.py

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
    {{python}} build/restore_from_knack_scrapefile.py
    @just db-stats

# Bytewise-diff app/fellows.db against the Apr 8 reference backup.
[group('db')]
db-verify:
    {{python}} build/diff_fellows_db.py {{db}} {{db_backup}}

# Bytewise-diff app/fellows.db against OTHER.
[group('db')]
db-diff other:
    {{python}} build/diff_fellows_db.py {{db}} {{other}}

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
    {{python}} build/fetch_missing_images.py

# Print what images WOULD be fetched (--dry-run).
[group('db')]
images-fetch-dry:
    {{python}} build/fetch_missing_images.py --dry-run


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

# DB + API + prod-stats + installed-versions only (skip Playwright; ~10x faster).
[group('test')]
test-fast:
    ./scripts/ensure_port_8765_free.sh tests/test_database.py tests/test_api.py tests/test_prod_stats.py tests/test_installed_versions.py -v

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


# ---- MCP servers ---------------------------------------------------------

mcp_venv   := "mcp_servers/.venv"
mcp_python := mcp_venv / "bin/python"
mcp_pytest := mcp_venv / "bin/pytest"

# Create mcp_servers/.venv and install the mcp SDK (separate from the
# project venv to keep app/'s strict no-deps boundary clean).
[group('mcp')]
mcp-install-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d {{mcp_venv}} ]; then
        python3 -m venv {{mcp_venv}}
    fi
    {{mcp_venv}}/bin/pip install --upgrade pip
    {{mcp_venv}}/bin/pip install -r mcp_servers/requirements.txt
    echo "MCP venv ready at {{mcp_venv}}. See mcp_servers/README.md for Claude Desktop config."

# Run the Shared Data Ops MCP server over stdio against app/fellows.db.
# By itself this just blocks waiting for JSON-RPC frames on stdin — useful
# for piping into a test harness, not for interactive use. For real use,
# register it with Claude Desktop (see mcp_servers/README.md).
[group('mcp')]
shared-data-ops:
    {{mcp_python}} mcp_servers/shared_data_ops.py --db {{db}}

# Run the Shared Data Ops MCP server's unit tests via mcp_servers/.venv.
[group('mcp')]
test-shared-data-ops:
    {{mcp_pytest}} tests/test_shared_data_ops.py -v

rel_db     := "app/relationships.db"

# Run the Private Data Ops MCP server over stdio against relationships.db
# (RO) with fellows.db ATTACHed (RO). See `shared-data-ops` recipe header
# for the same note about test harnesses vs. real Claude Desktop use.
[group('mcp')]
private-data-ops:
    {{mcp_python}} mcp_servers/private_data_ops.py --db {{rel_db}} --fellows-db {{db}}

# Run the Communications MCP server (stage-only, in-memory). Pure stdio
# server; no DB. See mcp_servers/README.md for Claude Desktop wiring.
[group('mcp')]
comms:
    {{mcp_python}} mcp_servers/comms.py

# Run the Private Data Ops MCP server's unit tests.
[group('mcp')]
test-private-data-ops:
    {{mcp_pytest}} tests/test_private_data_ops.py -v

# Run the Communications MCP server's unit tests.
[group('mcp')]
test-comms:
    {{mcp_pytest}} tests/test_comms.py -v

# Run every MCP server's tests at once.
[group('mcp')]
test-mcp: test-shared-data-ops test-private-data-ops test-comms


# ---- MCPB bundles (Claude Desktop install path) --------------------------
# See plans/easy_mcp_install.md and mcpb/node/README.md.

# Build all available .mcpb Desktop Extension bundles into
# deploy/dist/mcpb/. Runs npm install in mcpb/node/ on first call,
# compiles TS via tsc, then runs `npx @anthropic-ai/mcpb pack` per
# bundle. Pass a name to build just one (e.g. `just build-mcpb comms`).
[group('mcpb')]
build-mcpb *NAMES:
    python3 build/build_mcpb.py {{NAMES}}

# Run the dual-codebase parity test: same inputs through the Python
# servers in mcp_servers/ and the Node servers in mcpb/node/, assert
# structurally-equal output against the PNA spec contracts. Required
# to pass before any change to either implementation merges.
# See plans/easy_mcp_install.md § 6.
[group('mcpb')]
test-mcpb-parity:
    {{mcp_pytest}} tests/test_mcpb_parity.py -v


# ---- build / deploy ------------------------------------------------------

# Assemble deploy/dist/ (runs build/build_pwa.py).
[group('build')]
build:
    {{python}} build/build_pwa.py

# Generate the prod ECDSA P-256 signing keypair (one-time, per maintainer).
# Prompts for a passphrase, writes ~/.fellows/signing-key.enc.pem, prints
# the public key hex to paste into app/static/sw.js's PROD_PUBLIC_KEY_HEX.
# See docs/DevOps.md § Signing keys and bundle verification.
[group('build')]
keygen:
    {{venv}}/bin/python scripts/keygen_signing_key.py

# Sign deploy/dist/manifest.json with the prod private key. Writes
# deploy/dist/manifest.sig. Run after `just build`, before `just deploy`.
# Reads ~/.fellows/signing-key.enc.pem; prompts for the passphrase
# interactively unless FELLOWS_SIGNING_PASSPHRASE is exported.
[group('build')]
sign:
    {{venv}}/bin/python scripts/sign_bundle.py

# Print deploy/dist/build-meta.json.
[group('build')]
build-meta:
    @if [ -f deploy/dist/build-meta.json ]; then cat deploy/dist/build-meta.json; else echo "No deploy/dist/build-meta.json — run 'just build' first."; fi

# Pre-deploy sanity check. Warns (and prompts) if the working tree is
# in an unusual state for a deploy: branch != main, HEAD differs from
# origin/main, or there are uncommitted changes. Prompts y/N so a
# side-branch deploy remains possible when intentional. Set
# FELLOWS_DEPLOY_SKIP_PREFLIGHT=1 to bypass.
#
# `deploy` and `deploy-fast` depend on this; `ship` / `ship-fast` list
# it first so the check happens before the (slow) test step.
[group('deploy')]
deploy-preflight:
    #!/usr/bin/env bash
    set -uo pipefail
    if [ "${FELLOWS_DEPLOY_SKIP_PREFLIGHT:-0}" = "1" ]; then
        echo "Deploy preflight: skipped (FELLOWS_DEPLOY_SKIP_PREFLIGHT=1)."
        exit 0
    fi
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')
    head_sha=$(git rev-parse --short HEAD 2>/dev/null || echo '?')
    origin_main_sha=$(git rev-parse --short origin/main 2>/dev/null || echo '')
    dirty=$(git status --porcelain 2>/dev/null | head -c 1)
    warnings=()
    if [ "$branch" != "main" ]; then
        warnings+=("on branch '$branch' (not main) — prod will run this branch")
    fi
    if [ -n "$origin_main_sha" ] && [ "$head_sha" != "$origin_main_sha" ]; then
        ahead=$(git rev-list "origin/main..HEAD" --count 2>/dev/null || echo '?')
        behind=$(git rev-list "HEAD..origin/main" --count 2>/dev/null || echo '?')
        warnings+=("HEAD ($head_sha) differs from origin/main ($origin_main_sha): ahead $ahead, behind $behind")
    fi
    if [ -n "$dirty" ]; then
        warnings+=("working tree is dirty — uncommitted changes will be bundled but the SHA won't reflect them")
    fi
    if [ ${#warnings[@]} -eq 0 ]; then
        echo "Deploy preflight: $branch @ $head_sha — clean, matches origin/main. OK."
        exit 0
    fi
    echo "Deploy preflight — heads up:"
    for w in "${warnings[@]}"; do
        echo "  - $w"
    done
    echo
    printf "Deploy %s @ %s anyway? [y/N] " "$branch" "$head_sha"
    read -r reply || reply=""
    case "$reply" in
        y|Y|yes|YES) echo "Continuing." ;;
        *) echo "Deploy aborted."; exit 1 ;;
    esac

# Deploy to prod (build + ansible + HTTPS smoke, via ansible/deploy_pwa.yml).
#
# The build step (build/build_pwa.py) stamps the current git short SHA into
# FELLOWS_UI_DIAG and CACHE_VERSION as it copies to deploy/dist/, so every
# deploy automatically gets a unique label tied to HEAD — no manual bump
# step. See docs/DevOps.md for the routine flow and `just whats-running`
# for the local-vs-prod label snapshot.
[group('deploy')]
deploy: deploy-preflight build sign
    ansible-playbook ansible/deploy_pwa.yml --ask-become-pass --extra-vars "fellows_skip_build=true"

# Deploy, reusing existing deploy/dist/ (skips build AND sign).
# For re-pushing a bundle that's already been built and signed locally
# (e.g. after a transient deploy failure). Surprising if HEAD has moved
# since the last build/sign — the deployed manifest still points at
# the old bytes. Run `just deploy` for the rebuild-and-resign path.
[group('deploy')]
deploy-fast: deploy-preflight
    ansible-playbook ansible/deploy_pwa.yml --ask-become-pass --extra-vars "fellows_skip_build=true fellows_skip_sign=true"

# Ansible --check (dry run, no changes made).
[group('deploy')]
deploy-check:
    ansible-playbook ansible/deploy_pwa.yml --ask-become-pass --check

# Full ship: preflight → test-fast → deploy. Preflight runs first so a
# wrong-branch/dirty-tree deploy is caught before sitting through the
# test suite. `deploy` also depends on preflight; just dedupes within a
# single invocation.
[group('deploy')]
ship: deploy-preflight test-fast deploy

# Fast ship: preflight → deploy-fast → smoke (skip tests and rebuild).
[group('deploy')]
ship-fast: deploy-preflight deploy-fast smoke

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

# Show local HEAD, the build label that the next 'just build' would
# stamp into the bundle, prod's build-meta, and a refresh cheat-sheet
# for the SW shell-cache gotcha.
#
# Show local + prod build versions and refresh tips.
[group('prod')]
whats-running:
    #!/usr/bin/env bash
    set -uo pipefail
    head_sha=$(git rev-parse --short HEAD)
    head_subject=$(git log -1 --format=%s HEAD)
    today=$(date -u +%Y-%m-%d)
    next_label="${today}-${head_sha}"
    echo "Local"
    echo "  HEAD:                ${head_sha} ${head_subject}"
    echo "  Build label (next):  ${next_label}"
    echo "                       (auto-stamped into FELLOWS_UI_DIAG + CACHE_VERSION"
    echo "                        by build/build_pwa.py on the next 'just build' or 'just deploy')"
    echo
    echo "Prod ({{base_url}})"
    if curl -sf "{{base_url}}/build-meta.json" -o /tmp/_fellows_bm.json 2>/dev/null; then
        prod_sha=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_bm.json')).get('git_sha','?'))" 2>/dev/null || echo '?')
        prod_built=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_bm.json')).get('built_at','?'))" 2>/dev/null || echo '?')
        prod_label=$(python3 -c "import json,sys; print(json.load(open('/tmp/_fellows_bm.json')).get('build_label','?'))" 2>/dev/null || echo '?')
        echo "  build_label:         ${prod_label}"
        echo "  git_sha:             ${prod_sha}"
        echo "  built_at:            ${prod_built}"
        rm -f /tmp/_fellows_bm.json
        if [ "${prod_sha}" != "?" ]; then
            ./scripts/show_prod_drift.sh "${prod_sha}" "${head_sha}" "  drift:              "
        fi
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
    echo
    if [ -n "${prod_sha:-}" ] && [ "${prod_sha}" != "?" ]; then
        head_sha=$(git rev-parse --short HEAD 2>/dev/null || echo '')
        ./scripts/show_prod_drift.sh "${prod_sha}" "${head_sha}" "Drift:"
    fi

# Interactive SSH into the prod droplet (uses FELLOWS_HOST / FELLOWS_SSH_PORT / FELLOWS_SSH_USER).
[group('prod')]
prod-ssh:
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}}

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

# Per-email install vs currently-running build (joins verify_token + kind=boot).
# Plaintext-confidential output (joins to fellow emails). See
# plans/install_version_telemetry.md.
[group('prod')]
installed-versions since="30 days ago":
    ssh -p {{ssh_port}} {{ssh_user}}@{{host}} "/opt/fellows/bin/installed_versions --since '{{since}}'"

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

# Launch claude yolo on a new worktree
wt branch_name:
    ./scripts/wt-claude.sh {{branch_name}}
    
# Clean up a finished worktree
wtclean branch_name:
    wt remove {{branch_name}}
