#!/usr/bin/env bash
# Restore a fellows data snapshot from a zip produced by backup_fellows_data.sh.
#
# Unzips into the repo, overwriting app/fellows.db, final_fellows_set/, etc.
# Prints the manifest first so you can see what you're about to overwrite.
# Use --dry-run to see the manifest + file list without touching anything.
#
# Usage:
#   ./scripts/restore_fellows_data.sh backup/fellows_data_20260420-120000_abc1234.zip
#   ./scripts/restore_fellows_data.sh --dry-run backup/fellows_data_20260420-120000_abc1234.zip
#   ./scripts/restore_fellows_data.sh --latest       (picks newest backup)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${FELLOWS_BACKUP_DIR:-${ROOT}/backup}"

DRY_RUN=0
ZIP=""
case "${1:-}" in
  --dry-run) DRY_RUN=1; shift ;;
  --latest)
    ZIP="$(ls -t "$BACKUP_DIR"/fellows_data_*.zip 2>/dev/null | head -1 || true)"
    if [[ -z "$ZIP" ]]; then
      echo "No backups in $BACKUP_DIR" >&2
      exit 1
    fi
    shift
    ;;
  "" )
    echo "Usage: $(basename "$0") [--dry-run] <backup.zip>" >&2
    echo "       $(basename "$0") --latest" >&2
    exit 2
    ;;
esac

if [[ -z "$ZIP" ]]; then
  ZIP="${1:-}"
fi

if [[ ! -f "$ZIP" ]]; then
  echo "Backup not found: $ZIP" >&2
  exit 1
fi

echo "Restoring from: $ZIP"
echo
echo "=== MANIFEST ==="
unzip -p "$ZIP" MANIFEST.json 2>/dev/null | python3 -m json.tool || echo "(no MANIFEST.json found)"
echo
echo "=== FILE LIST ==="
unzip -l "$ZIP" | head -30

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "(dry run — no changes made)"
  exit 0
fi

echo
read -r -p "Overwrite current files from this backup? [y/N] " ans
case "$ans" in
  y|Y|yes|YES) ;;
  *) echo "Aborted."; exit 1 ;;
esac

unzip -o -q "$ZIP" -d "$ROOT"
echo "Restored. Verify with:"
echo "  sqlite3 app/fellows.db 'SELECT COUNT(*) FROM fellows;'"
