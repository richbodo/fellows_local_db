# `backup/` — local snapshots of the fellows data pipeline

Contains timestamped zip archives produced by `scripts/backup_fellows_data.sh`.

## Contents of each zip

```
fellows_data_<YYYYMMDD-HHMMSS>_<git-sha>.zip
├── MANIFEST.json                                 # timestamp, git sha, counts
├── app/fellows.db                                # current built DB
├── final_fellows_set/
│   ├── ehf_fellow_profiles_deduped.json          # (if present)
│   ├── knack_api_detail_dump.json                # primary source of truth
│   ├── knack_api_raw_dump.json                   # supplementary (fellow_type)
│   ├── ehf_fellow_profiles_knack_api.json        # flat Knack export (if present)
│   └── fellow_profile_images_by_name/            # 251 profile photos
```

## When to snapshot

Before any operation that mutates data in the repo:

- Before a DB rebuild (`just db-rebuild` does this for you automatically; snapshot manually before raw `python build/restore_from_knack_scrapefile.py`).
- Before any manual SQL on `app/fellows.db`.
- Before a new Knack scrape (or anything that writes to `final_fellows_set/`).
- Before merging a PR that changes the ETL or its inputs.

## How to use

```bash
just data-backup                            # snapshot the current state
just data-restore-dry                       # list what's in the newest backup, don't touch anything
just data-restore-dry path/to/backup.zip    # same, for a specific zip
just data-restore                           # restore from --latest (prompts for confirmation)
just data-restore path/to/backup.zip        # restore from a specific zip
```

Under the hood — the scripts each recipe wraps:

```bash
# Snapshot the current state.
./scripts/backup_fellows_data.sh

# List what's in a backup without restoring.
./scripts/restore_fellows_data.sh --dry-run backup/fellows_data_20260420-120000_abc1234.zip

# Restore (prompts for confirmation).
./scripts/restore_fellows_data.sh backup/fellows_data_20260420-120000_abc1234.zip

# Restore the newest backup.
./scripts/restore_fellows_data.sh --latest
```

See [`../docs/justfile.md`](../docs/justfile.md) for the full recipe reference.

## Rotation

`scripts/backup_fellows_data.sh` keeps the 10 newest backups and deletes older
ones automatically. Override with `FELLOWS_BACKUP_KEEP=20 ./scripts/backup_fellows_data.sh`.

## Storage

This directory is gitignored — backups are local-only by design. A typical
snapshot with images is ~30–40 MB zipped. If you need offsite durability,
copy zips out of here manually (e.g. to a cloud bucket you control).
