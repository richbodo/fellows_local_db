#!/usr/bin/env bash
# Build deploy/dist, deploy to the fellows host via Ansible, run HTTPS smoke checks.
# Run from the repository root (same as other ansible commands).
#
# Usage:
#   ./scripts/deploy_pwa.sh
#   ./scripts/deploy_pwa.sh --ask-become-pass
#   ./scripts/deploy_pwa.sh --extra-vars 'fellows_skip_build=true'
#
# Forwards all arguments to ansible-playbook.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec ansible-playbook ansible/deploy_pwa.yml "$@"
