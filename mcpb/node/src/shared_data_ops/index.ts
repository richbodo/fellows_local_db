#!/usr/bin/env node
/**
 * Shared Data Ops MCP server — Node port of
 * ../../../mcp_servers/shared_data_ops.py.
 *
 * Read-only MCP access to the Shared DB (fellows.db). Exposes four tools
 * to AI clients via stdio:
 *
 *  - search_fellows       FTS5 full-text search.
 *  - get_fellow           Single record by slug or record_id, full shape.
 *  - list_fellows         Structured-filter list with pagination.
 *  - get_directory_stats  Aggregates for "what's in this directory" questions.
 *
 * Storage scope: the Shared DB only (fellows.db). The Private DB
 * (relationships.db) is the future Private Data Ops bundle's surface.
 * See plans/easy_mcp_install.md § 5 (OPFS handoff) and
 * docs/Architecture.md § Two-DB architecture for why these are split.
 *
 * Read-only-ness is enforced at the SQLite layer (readOnly: true on the
 * node:sqlite connection, same posture as Python's mode=ro URI flag).
 * Even a buggy tool can't mutate the directory snapshot.
 *
 * Uses Node's built-in `node:sqlite` (stable since Node 24) so the bundle
 * has zero native dependencies — Claude Desktop ships Electron with
 * Node 24, and a native better-sqlite3 binding would not survive any
 * Node version skew between the build machine and Claude Desktop.
 *
 * DB path resolution mirrors the Python server: CLI --db, then env
 * FELLOWS_DB_PATH, then ${__dirname}/../data/fellows.db (the path inside
 * an installed .mcpb where fellows.db is bundled at build time).
 *
 * Behavioral parity with mcp_servers/shared_data_ops.py is asserted by
 * tests/test_mcpb_parity.py per plans/easy_mcp_install.md § 6.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { existsSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

import {
  getFellowBySlugOrId,
  getStats,
  rowToFellow,
  searchFellows,
  type FellowsRow,
} from "../_shared/fellows_queries.js";

const SEARCH_LIMIT_DEFAULT = 25;
const SEARCH_LIMIT_MAX = 100;
const LIST_LIMIT_DEFAULT = 50;
const LIST_LIMIT_MAX = 100;

function parseCliDb(argv: ReadonlyArray<string>): string | null {
  // Match argparse: --db PATH  or  --db=PATH
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--db" && i + 1 < argv.length) return argv[i + 1] ?? null;
    if (a.startsWith("--db=")) return a.slice("--db=".length);
  }
  return null;
}

function resolveDbPath(argv: ReadonlyArray<string>): string {
  const cli = parseCliDb(argv);
  if (cli) return resolve(cli);
  const env = process.env.FELLOWS_DB_PATH;
  if (env) return resolve(env);
  // Default: ${__dirname}/../data/fellows.db. This is where build_mcpb.py
  // places fellows.db inside the staged bundle. For local dev / standalone
  // runs (without a built .mcpb), point at the repo's app/fellows.db
  // via --db or FELLOWS_DB_PATH instead.
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "data", "fellows.db");
}

// Unconditional startup line — appears in Claude Desktop's per-server
// log (~/Library/Logs/Claude/mcp-server-<name>.log on macOS) so any
// future startup failure has a trace of what was tried, not just
// "Server transport closed unexpectedly".
process.stderr.write(
  `shared-data-ops: boot node=${process.version} cwd=${process.cwd()}\n`,
);

const DB_PATH = resolveDbPath(process.argv.slice(2));
process.stderr.write(`shared-data-ops: resolved db=${DB_PATH}\n`);
if (!existsSync(DB_PATH) || !statSync(DB_PATH).isFile()) {
  process.stderr.write(
    `shared-data-ops: fellows.db not found at ${DB_PATH}\n`,
  );
  process.exit(1);
}

const db = new DatabaseSync(DB_PATH, { readOnly: true });
// Sanity check before handing control to the stdio loop — fail fast with
// a useful stderr message rather than a cryptic JSON-RPC error on the
// first tool call.
try {
  db.prepare("SELECT 1 FROM fellows LIMIT 1").get();
} catch (err) {
  process.stderr.write(
    `shared-data-ops: cannot read ${DB_PATH}: ${(err as Error).message}\n`,
  );
  process.exit(1);
}

function toSummary(fellow: Record<string, unknown>): Record<string, unknown> {
  return {
    record_id: fellow.record_id ?? null,
    slug: fellow.slug ?? null,
    name: fellow.name ?? null,
    fellow_type: fellow.fellow_type ?? null,
    cohort: fellow.cohort ?? null,
    currently_based_in: fellow.currently_based_in ?? null,
    bio_tagline: fellow.bio_tagline ?? null,
    has_contact_email: Boolean(fellow.contact_email),
  };
}

function clampInt(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(Math.floor(value), max));
}

const server = new McpServer({ name: "shared-data-ops", version: "0.1.0" });

server.registerTool(
  "search_fellows",
  {
    description:
      "Full-text search across name, bio, cohort, fellow type, search tags, and key links. Uses SQLite FTS5; pass natural keywords (FTS5 also accepts operators like 'climate OR healthcare' and prefix matches like 'auck*').",
    inputSchema: {
      query: z.string().describe("Search keywords. Must be non-empty."),
      limit: z
        .number()
        .int()
        .nullish()
        .describe("Max results to return. Default 25, capped at 100."),
    },
  },
  async ({ query, limit }) => {
    const q = (query ?? "").trim();
    if (!q) {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ query: "", total: 0, results: [] }),
          },
        ],
      };
    }
    const lim = clampInt(limit ?? SEARCH_LIMIT_DEFAULT, 1, SEARCH_LIMIT_MAX);
    const rows = searchFellows(db, q);
    const total = rows.length;
    const results = rows.slice(0, lim).map(toSummary);
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ query: q, total, results }),
        },
      ],
    };
  },
);

server.registerTool(
  "get_fellow",
  {
    description:
      "Fetch one fellow's full record by slug or record_id. Returns the full shape — all DB columns plus extra_json fields merged (ventures, career_highlights, mobile_number, skills_to_give, etc.). Returns null if no such record exists.",
    inputSchema: {
      id: z
        .string()
        .describe("A fellow's slug (e.g. 'jane-doe') or record_id."),
    },
  },
  async ({ id }) => {
    const key = (id ?? "").trim();
    let result: unknown = null;
    if (key) result = getFellowBySlugOrId(db, key);
    return {
      content: [{ type: "text", text: JSON.stringify(result) }],
    };
  },
);

server.registerTool(
  "list_fellows",
  {
    description:
      "List fellows by structured filters (use search_fellows for full-text). Filters AND together. The region filter matches against global_regions_currently_based_in (comma-separated), so a fellow in 'Asia Pacific, Americas' matches either value.",
    inputSchema: {
      fellow_type: z
        .string()
        .nullish()
        .describe("Exact match on fellow_type."),
      cohort: z.string().nullish().describe("Exact match on cohort."),
      region: z
        .string()
        .nullish()
        .describe(
          "Substring-match against global_regions_currently_based_in.",
        ),
      primary_citizenship: z
        .string()
        .nullish()
        .describe("Exact match on primary_citizenship."),
      has_contact_email: z
        .boolean()
        .nullish()
        .describe(
          "True for fellows with a contact email; false for those without; null for no filter.",
        ),
      limit: z
        .number()
        .int()
        .nullish()
        .describe("Max results to return. Default 50, capped at 100."),
      offset: z
        .number()
        .int()
        .nullish()
        .describe(
          "Number of results to skip before returning (for pagination).",
        ),
    },
  },
  async ({
    fellow_type,
    cohort,
    region,
    primary_citizenship,
    has_contact_email,
    limit,
    offset,
  }) => {
    const lim = clampInt(limit ?? LIST_LIMIT_DEFAULT, 1, LIST_LIMIT_MAX);
    const off = Math.max(0, Math.floor(offset ?? 0));
    const where: string[] = [];
    const params: Array<string | number> = [];
    if (fellow_type) {
      where.push("fellow_type = ?");
      params.push(fellow_type);
    }
    if (cohort) {
      where.push("cohort = ?");
      params.push(cohort);
    }
    if (region) {
      where.push("global_regions_currently_based_in LIKE ?");
      params.push(`%${region}%`);
    }
    if (primary_citizenship) {
      where.push("primary_citizenship = ?");
      params.push(primary_citizenship);
    }
    if (has_contact_email === true) {
      where.push("contact_email IS NOT NULL AND contact_email != ''");
    } else if (has_contact_email === false) {
      where.push("(contact_email IS NULL OR contact_email = '')");
    }
    const whereSql = where.length ? " WHERE " + where.join(" AND ") : "";

    const total = (
      db
        .prepare(`SELECT COUNT(*) as c FROM fellows${whereSql}`)
        .get(...params) as { c: number }
    ).c;
    const rows = db
      .prepare(
        `SELECT * FROM fellows${whereSql} ORDER BY name ASC LIMIT ? OFFSET ?`,
      )
      .all(...params, lim, off) as FellowsRow[];
    const results = rows.map(rowToFellow).map(toSummary);

    const filtersAppliedRaw: Record<string, unknown> = {
      fellow_type: fellow_type ?? null,
      cohort: cohort ?? null,
      region: region ?? null,
      primary_citizenship: primary_citizenship ?? null,
      has_contact_email: has_contact_email ?? null,
    };
    const filtersApplied: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(filtersAppliedRaw)) {
      if (v !== null && v !== undefined) filtersApplied[k] = v;
    }

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({
            total,
            offset: off,
            limit: lim,
            filters_applied: filtersApplied,
            results,
          }),
        },
      ],
    };
  },
);

server.registerTool(
  "get_directory_stats",
  {
    description:
      "Aggregate statistics for 'what's in this directory' questions. Same shape as the dev HTTP server's GET /api/stats response: total count, breakdowns by fellow type / cohort / region, plus field-completeness counts (how many fellows have a non-empty value for each column or extra_json key).",
    inputSchema: {},
  },
  async () => {
    const stats = getStats(db);
    return {
      content: [{ type: "text", text: JSON.stringify(stats) }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
