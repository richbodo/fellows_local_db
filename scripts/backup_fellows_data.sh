#!/usr/bin/env bash
# Snapshot the entire fellows data pipeline into a timestamped zip under ./backup/.
#
# Contents:
#   - app/fellows.db                                    (current built DB)
#   - final_fellows_set/ehf_fellow_profiles_deduped.json  (if present)
#   - final_fellows_set/knack_api_detail_dump.json        (source of truth)
#   - final_fellows_set/knack_api_raw_dump.json           (supplementary)
#   - final_fellows_set/ehf_fellow_profiles_knack_api.json (if present)
#   - final_fellows_set/fellow_profile_images_by_name/    (photos directory)
#   - MANIFEST.json                                     (timestamp, git sha, counts)
#
# Run before any data-changing operation (rebuilding the DB, running a new
# scrape, etc.). Rotation: keeps the N newest, deletes older (default 10,
# override with FELLOWS_BACKUP_KEEP env).
#
# Usage:
#   ./scripts/backup_fellows_data.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${FELLOWS_BACKUP_DIR:-${ROOT}/backup}"
KEEP="${FELLOWS_BACKUP_KEEP:-10}"

mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%d-%H%M%S)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
ZIP_NAME="fellows_data_${TS}_${GIT_SHA}.zip"
ZIP_PATH="${BACKUP_DIR}/${ZIP_NAME}"

# Stage a manifest so the zip is self-describing.
TMP_MANIFEST="$(mktemp -t fellows_backup_manifest.XXXXXX.json)"
trap 'rm -f "$TMP_MANIFEST"' EXIT

ROW_COUNT="?"
EMAIL_COUNT="?"
IMAGE_COUNT="?"
if [[ -f app/fellows.db ]]; then
  ROW_COUNT="$(sqlite3 app/fellows.db 'SELECT COUNT(*) FROM fellows;' 2>/dev/null || echo '?')"
  EMAIL_COUNT="$(sqlite3 app/fellows.db "SELECT COUNT(*) FROM fellows WHERE contact_email IS NOT NULL AND trim(contact_email) != '';" 2>/dev/null || echo '?')"
  IMAGE_COUNT="$(sqlite3 app/fellows.db 'SELECT COUNT(*) FROM fellows WHERE has_image = 1;' 2>/dev/null || echo '?')"
fi

cat > "$TMP_MANIFEST" <<JSON
{
  "created_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "git_sha": "$GIT_SHA",
  "host": "$(hostname)",
  "row_count": $ROW_COUNT,
  "email_count": $EMAIL_COUNT,
  "image_count": $IMAGE_COUNT
}
JSON

FILES=()
[[ -f app/fellows.db ]] && FILES+=("app/fellows.db")
for f in ehf_fellow_profiles_deduped.json knack_api_detail_dump.json \
         knack_api_raw_dump.json ehf_fellow_profiles_knack_api.json; do
  [[ -f "final_fellows_set/$f" ]] && FILES+=("final_fellows_set/$f")
done
[[ -d final_fellows_set/fellow_profile_images_by_name ]] && FILES+=("final_fellows_set/fellow_profile_images_by_name")

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Nothing to back up (no app/fellows.db, no final_fellows_set/ files)." >&2
  exit 1
fi

# Include the manifest inside the zip under a stable name.
MANIFEST_STAGE="${BACKUP_DIR}/.MANIFEST_stage_$$.json"
cp "$TMP_MANIFEST" "$MANIFEST_STAGE"
FILES+=("$(python3 -c 'import os,sys;print(os.path.relpath(sys.argv[1]))' "$MANIFEST_STAGE")")
MANIFEST_REL="$(python3 -c 'import os,sys;print(os.path.relpath(sys.argv[1]))' "$MANIFEST_STAGE")"

# Create zip with MANIFEST.json at archive root.
zip -r -q "$ZIP_PATH" "${FILES[@]}" >/dev/null
# Rename the staged manifest inside the archive to MANIFEST.json
python3 - "$ZIP_PATH" "$MANIFEST_REL" <<'PYEOF'
import sys, zipfile, os
zip_path = sys.argv[1]
staged = sys.argv[2]
# Read all entries, rewrite staged to MANIFEST.json
import shutil, tempfile
tmpd = tempfile.mkdtemp()
with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall(tmpd)
os.rename(os.path.join(tmpd, staged), os.path.join(tmpd, "MANIFEST.json"))
os.remove(zip_path)
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk(tmpd):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, tmpd))
shutil.rmtree(tmpd)
PYEOF
rm -f "$MANIFEST_STAGE"

# Rotate: keep only KEEP newest.
ls -t "$BACKUP_DIR"/fellows_data_*.zip 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

SIZE="$(du -sh "$ZIP_PATH" | awk '{print $1}')"
COUNT="$(ls "$BACKUP_DIR"/fellows_data_*.zip 2>/dev/null | wc -l | tr -d ' ')"
echo "Wrote $ZIP_PATH ($SIZE)"
echo "Rotation: $COUNT backup(s) retained (max $KEEP)"
echo "Contents: $ROW_COUNT fellows, $EMAIL_COUNT with email, $IMAGE_COUNT with image"
