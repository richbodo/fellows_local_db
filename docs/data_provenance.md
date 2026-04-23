# Data Provenance

How `app/fellows.db` is built, where every field comes from, and how to
recover if anything goes wrong.

## What data we have

The canonical source is the **Knack REST-API extraction of 2026-04-08**,
performed via the API before EHF's Knack SaaS instance was shut down. All
data in the repo derives from that extraction.

| File                                                    | Kind    | Row count | Purpose |
|---------------------------------------------------------|---------|----------:|---------|
| `final_fellows_set/knack_api_detail_dump.json`          | source  | 515       | **Primary source of truth.** Detail-view records keyed by Knack `record_id`; 86 fields per record (Knack `field_XXX` codes). |
| `final_fellows_set/knack_api_raw_dump.json`             | source  | 515       | Supplementary. Three Knack list views (`public`, `alumni`, `search`). Used for a handful of fields that the detail view omits (notably `field_649` → `fellow_type` for 8 fellows). |
| `final_fellows_set/ehf_fellow_profiles_knack_api.json`  | source  | 515       | Flat Knack export; no contact emails. Not used by the current ETL — kept for historical reference. |
| `final_fellows_set/ehf_fellow_profiles_deduped.json.bak.2026-04-08` | source | 442 | **Lossy demo subset** — fellows with no profile photo stripped, emails stripped from remainder. Retained only as a cautionary tale; never use as a rebuild source. |
| `final_fellows_set/fellow_profile_images_by_name/`      | source  | 251 files | Profile photos, filenames `<slug>.jpg`. One per fellow who uploaded a photo. The ~264 fellows without photos never uploaded one. |
| `app/fellows.db`                                        | built   | 515       | SQLite DB produced from the above. **Gitignored**; rebuild via the script below. |
| `app/fellows.db.backup.2026-04-08`                      | source-of-last-resort | 515 | A known-good pre-built DB. If the ETL is broken, `scripts/restore_fellows_data.sh` can put it back. |

## How to rebuild `app/fellows.db` from source

```bash
python build/restore_from_knack_scrapefile.py
```

> `just db-rebuild` wraps this and auto-snapshots via `scripts/backup_fellows_data.sh` first — see [`justfile.md`](justfile.md).

Defaults to `final_fellows_set/knack_api_detail_dump.json` as input. Pass a
different path if you ever run the scrape again:

```bash
python build/restore_from_knack_scrapefile.py /path/to/newer_detail_dump.json
```

The script:
1. Reads the detail dump (dict keyed by `record_id`).
2. Reads `knack_api_raw_dump.json` alongside it (automatic) for fields the
   detail dump lacks.
3. Writes `app/fellows.db` with the canonical 18-column schema + an FTS5 index.
4. Prints counts so you can sanity-check (515 / 515 / 251 at time of writing).

To verify bytewise equivalence against the reference backup:

```bash
python build/diff_fellows_db.py app/fellows.db app/fellows.db.backup.2026-04-08
```

Expected: `✓ bytewise match on all columns`.

## Column-by-column provenance

| Schema column                              | Source                                           | Normalisation |
|--------------------------------------------|--------------------------------------------------|---------------|
| `record_id`                                | `id` (detail dump)                                | verbatim |
| `slug`                                     | derived from `name`                              | lowercase, non-alphanum → `_`, dedup with `_1` / `_2` suffixes |
| `name`                                     | `field_10_raw.full`                              | preserves internal whitespace (e.g. "Daniel  Price") |
| `bio_tagline`                              | `field_319`                                      | `<br />` → `\n` |
| `fellow_type`                              | `field_720` \| `raw_dump:field_649` (fallback)   | plain |
| `cohort`                                   | `field_311`                                      | strip `<span>` |
| `contact_email`                            | `field_776_raw.email`                            | clean email string |
| `key_links`                                | derived from `field_710` (anchor labels)         | `Label1, Label2` |
| `key_links_urls`                           | derived from `field_710` (href attrs)            | JSON array of URLs |
| `image_url`                                | `field_299` (`<img src="…"/>`)                   | URL only |
| `currently_based_in`                       | `field_617_raw[*].full`                          | join with `\n`, strip outer whitespace |
| `search_tags`                              | `field_402`                                      | plain |
| `fellow_status`                            | `field_648`                                      | plain |
| `gender_pronouns`                          | `field_740`                                      | plain |
| `ethnicity`                                | `field_722`                                      | inner text of each `<span>`, `, `-join |
| `primary_citizenship`                      | `field_646`                                      | strip `<span>` |
| `global_regions_currently_based_in`        | `field_645`                                      | inner text of each `<span>`, `, `-join |
| `has_image`                                | derived from image filename presence             | `1` if `fellow_profile_images_by_name/<slug>.{jpg,png}` exists |
| `extra_json`                               | bag of ~24 keys; see next table                  | JSON-encoded |

### `extra_json` keys

| Key                                                                         | Source      | Normalisation |
|-----------------------------------------------------------------------------|-------------|---------------|
| `mobile_number`                                                             | `field_738` | verbatim (preserves rare trailing space) |
| `all_citizenships`                                                          | `field_393` | multi-span, `, `-join |
| `primary_global_region_of_citizenship`                                      | `field_647` | strip `<span>` |
| `global_networks`                                                           | `field_403` | multi-span, `, `-join |
| `ventures`                                                                  | `field_858` | extract `<a>` label or plain string per item, `, `-join |
| `industries`                                                                | `field_349` | multi-span, `, `-join |
| `industries_other`                                                          | `field_652_raw` | plain string |
| `what_is_your_main_mode_of_working`                                         | `field_755_raw[*].identifier` | `, `-join |
| `do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories`   | `field_758_raw[*].identifier` | `, `-join |
| `what_are_the_main_types_of_organisations_you_serve`                        | `field_810_raw[*].identifier` | `, `-join |
| `career_highlights`                                                         | `field_812_raw` | plain string |
| `how_im_looking_to_support_the_nz_ecosystem`                                | `field_400_raw` | plain string |
| `key_networks`                                                              | `field_397_raw` | plain string |
| `impact_goals_nz`                                                           | `field_398_raw` | plain string |
| `how_to_support_my_work`                                                    | `field_399_raw` | plain string |
| `five_things_to_know`                                                       | `field_300_raw` | plain string |
| `anything_else_to_share`                                                    | `field_775_raw` | plain string |
| `other_fellows_in_team`                                                     | `field_654` | multi-span, `, `-join |
| `how_fellows_can_connect`                                                   | `field_766_raw[*].identifier` | `, `-join |
| `skills_to_give`                                                            | `field_770_raw[*].identifier` | `, `-join |
| `skills_to_receive`                                                         | `field_771_raw[*].identifier` | `, `-join |
| `sdgs`                                                                      | `field_396_raw[*].identifier` | `, `-join |
| `this_profile_last_updated`                                                 | `field_449_raw.date_formatted` + `time_formatted` | `DD/MM/YYYY HH:MMam` |
| `contact_email_urls`                                                        | `[mailto:<contact_email>]` | Python list |
| `_slug`                                                                     | same as `slug` | duplicate of top-level column |

The full mapping lives in `build/restore_from_knack_scrapefile.py` as two
module-level lists (`KNACK_FIELD_MAP_COLS` and `KNACK_FIELD_MAP_EXTRA`). If
you change the mapping, update this table too.

## Backup workflow

`scripts/backup_fellows_data.sh` snapshots the current state — DB + all
source JSONs + image dir + manifest — into `backup/fellows_data_<ts>_<sha>.zip`.

Run it:
- Before any rebuild (`restore_from_knack_scrapefile.py`)
- Before any manual SQL on `app/fellows.db`
- Before any new scrape

Restore from a snapshot with `scripts/restore_fellows_data.sh <zip>` (or
`--latest`). See [`backup/README.md`](../backup/README.md) for details.

## Rollback / recovery

Three recovery paths, in order of safety:

1. **From a recent local snapshot**. Fastest:
   ```bash
   ./scripts/restore_fellows_data.sh --latest
   ```
2. **From the reference backup DB**. If snapshots are gone or corrupted,
   the Apr 8 backup DB is the fixed point in time:
   ```bash
   cp app/fellows.db.backup.2026-04-08 app/fellows.db
   ```
   Note: this DB predates the `has_image` column (added in PR #19). The
   ETL adds it on rebuild; if you restore the backup directly, re-run
   `python build/restore_from_knack_scrapefile.py` afterwards to get the
   modern schema + image-index backfill.
3. **From raw Knack dumps**. The full rebuild:
   ```bash
   python build/restore_from_knack_scrapefile.py
   ```
   Produces the same DB as the Apr 8 backup, bytewise (verify with
   `diff_fellows_db.py`).

## Why `build/filter_demo_data.py` and the `.bak` JSON are DANGEROUS

The `.bak.2026-04-08` JSON file in `final_fellows_set/` is the output of
`build/filter_demo_data.py` — a script that strips fellows without profile
photos AND loses their contact emails in the process. It was intended for
generating a sanitised demo dataset but **has accidentally been used as a
rebuild source at least once**, demoting `fellows.db` from 515 / 515
(fellows / emails) to 442 / 268. That's the "richbodo@gmail.com not on
allowlist" bug the user hit the morning of 2026-04-20.

**Never pass the `.bak` JSON to any ETL as the source of truth.** The ETL
exits with a hard error if it's pointed at a file whose row count drops
below a sanity threshold — see the regression test
`test_email_coverage_ratio_catches_demo_filter_regression` in
`tests/test_database.py`.
