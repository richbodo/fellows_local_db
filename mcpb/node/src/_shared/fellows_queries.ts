/**
 * Pure-logic query helpers over fellows.db — Node port of
 * ../../../../app/fellows_queries.py.
 *
 * Shared between mcpb/node/src/shared_data_ops/ (and any future Node
 * server that reads the directory snapshot) so all of them surface
 * identical record shapes to AI clients. No transport, no framework —
 * just SQL helpers and the rowToFellow shape that merges ``extra_json``
 * overflow keys into the record.
 *
 * Conforms to mcp-shared-data-ops.schema.json from the PNA spec.
 * Behavioral parity with the Python helper is asserted by
 * tests/test_mcpb_parity.py per plans/easy_mcp_install.md § 6.
 */
import type Database from "better-sqlite3";

export const FELLOW_COLUMNS = [
  "record_id",
  "slug",
  "name",
  "bio_tagline",
  "fellow_type",
  "cohort",
  "contact_email",
  "key_links",
  "key_links_urls",
  "image_url",
  "currently_based_in",
  "search_tags",
  "fellow_status",
  "gender_pronouns",
  "ethnicity",
  "primary_citizenship",
  "global_regions_currently_based_in",
  "has_image",
] as const;

export type FellowsRow = Record<string, unknown>;

/**
 * Convert a DB row to the API fellow object: parse key_links_urls JSON
 * and merge extra_json overflow keys. Mirrors row_to_fellow in
 * app/fellows_queries.py byte-for-byte (including the silent fallback
 * on malformed JSON).
 */
export function rowToFellow(row: FellowsRow): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of FELLOW_COLUMNS) {
    const val = row[key] ?? null;
    if (key === "key_links_urls" && val !== null && typeof val === "string") {
      try {
        out[key] = JSON.parse(val);
      } catch {
        out[key] = val;
      }
    } else {
      out[key] = val;
    }
  }
  const extra = row["extra_json"];
  if (extra && typeof extra === "string") {
    try {
      const parsed = JSON.parse(extra);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        Object.assign(out, parsed);
      }
    } catch {
      // Silent fallback matches Python.
    }
  }
  return out;
}

export function getFellowBySlugOrId(
  db: Database.Database,
  slugOrId: string,
): Record<string, unknown> | null {
  const row = db
    .prepare("SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1")
    .get(slugOrId, slugOrId) as FellowsRow | undefined;
  return row ? rowToFellow(row) : null;
}

export function searchFellows(
  db: Database.Database,
  q: string,
): Array<Record<string, unknown>> {
  const trimmed = (q ?? "").trim();
  if (!trimmed) return [];
  // Python caps query length at 200 chars before passing to FTS5 — match.
  const capped = trimmed.length > 200 ? trimmed.slice(0, 200) : trimmed;
  const rows = db
    .prepare(
      `
      SELECT f.* FROM fellows f
      WHERE f.rowid IN (
        SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?
      )
      ORDER BY f.name ASC
      `,
    )
    .all(capped) as FellowsRow[];
  return rows.map(rowToFellow);
}

/**
 * Get aggregate directory stats. Mirrors get_stats in
 * app/fellows_queries.py.
 */
export function getStats(db: Database.Database): Record<string, unknown> {
  const total = (
    db.prepare("SELECT COUNT(*) as c FROM fellows").get() as { c: number }
  ).c;

  const groupCounts = (sql: string): Array<{ label: string; count: number }> =>
    (db.prepare(sql).all() as Array<{ label: string; count: number }>).map(
      (r) => ({ label: r.label, count: r.count }),
    );

  // Region splitting: comma-separated values stored as one field per row;
  // expand and tally. Order is most-common-first (Python uses
  // Counter.most_common which preserves insertion order for ties).
  const regionCounter = new Map<string, number>();
  const regionRows = db
    .prepare(
      `SELECT global_regions_currently_based_in FROM fellows
       WHERE global_regions_currently_based_in IS NOT NULL
       AND global_regions_currently_based_in != ''`,
    )
    .all() as Array<{ global_regions_currently_based_in: string }>;
  for (const r of regionRows) {
    for (const part of r.global_regions_currently_based_in.split(",")) {
      const region = part.trim();
      if (region) {
        regionCounter.set(region, (regionCounter.get(region) ?? 0) + 1);
      }
    }
  }
  // Sort descending by count; ties preserve first-seen order (matches
  // Python Counter.most_common stability).
  const byRegion = Array.from(regionCounter.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);

  const fieldCounts: Array<{ label: string; count: number }> = [];
  const colLabels: Record<string, string> = {
    name: "Name",
    bio_tagline: "Bio / Tagline",
    fellow_type: "Fellow Type",
    cohort: "Cohort",
    contact_email: "Contact Email",
    key_links: "Key Links",
    image_url: "Image URL",
    currently_based_in: "Currently Based In",
    search_tags: "Search Tags",
    fellow_status: "Fellow Status",
    gender_pronouns: "Gender / Pronouns",
    ethnicity: "Ethnicity",
    primary_citizenship: "Primary Citizenship",
    global_regions_currently_based_in: "Global Regions Based In",
  };
  for (const [col, label] of Object.entries(colLabels)) {
    const count = (
      db
        .prepare(
          `SELECT COUNT(*) as c FROM fellows WHERE ${col} IS NOT NULL AND ${col} != ''`,
        )
        .get() as { c: number }
    ).c;
    fieldCounts.push({ label, count });
  }
  const extraLabels: Record<string, string> = {
    all_citizenships: "All Citizenships",
    ventures: "Ventures",
    industries: "Industries",
    career_highlights: "Career Highlights",
    key_networks: "Key Networks",
    how_im_looking_to_support_the_nz_ecosystem: "How Supporting NZ Ecosystem",
    what_is_your_main_mode_of_working: "Main Mode of Working",
    do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories:
      "Investor Categories",
    mobile_number: "Mobile Number",
    five_things_to_know: "Five Things to Know",
    skills_to_give: "Skills to Give",
    skills_to_receive: "Skills to Receive",
  };
  const extraStmt = db.prepare(
    `SELECT COUNT(*) as c FROM fellows WHERE extra_json IS NOT NULL
     AND json_extract(extra_json, ?) IS NOT NULL
     AND json_extract(extra_json, ?) != ''`,
  );
  for (const [key, label] of Object.entries(extraLabels)) {
    const path = `$.${key}`;
    const count = (extraStmt.get(path, path) as { c: number }).c;
    fieldCounts.push({ label, count });
  }
  fieldCounts.sort((a, b) => b.count - a.count);

  return {
    total,
    by_fellow_type: groupCounts(
      `SELECT fellow_type as label, COUNT(*) as count FROM fellows
       WHERE fellow_type IS NOT NULL
       GROUP BY fellow_type ORDER BY COUNT(*) DESC`,
    ),
    by_cohort: groupCounts(
      `SELECT cohort as label, COUNT(*) as count FROM fellows
       WHERE cohort IS NOT NULL
       GROUP BY cohort ORDER BY COUNT(*) DESC`,
    ),
    by_region: byRegion,
    field_completeness: fieldCounts,
  };
}
