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
# Force the default stdout callback explicitly: ansible-core 2.20.x
# (Homebrew's current stable) sometimes emits only deprecation warnings on
# stdout while task progress and PLAY RECAP go silently into ansible/ansible.log.
# Setting the callback explicitly restores the familiar "TASK [...]" +
# "PLAY RECAP" output at the terminal. Keep the log_path behavior; both
# channels carry the same info.
export ANSIBLE_STDOUT_CALLBACK="${ANSIBLE_STDOUT_CALLBACK:-default}"
export ANSIBLE_FORCE_COLOR="${ANSIBLE_FORCE_COLOR:-1}"
exec ansible-playbook ansible/deploy_pwa.yml "$@"
