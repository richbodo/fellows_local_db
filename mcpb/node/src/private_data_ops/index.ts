#!/usr/bin/env node
/**
 * Private Data Ops MCP server — Node port of
 * ../../../mcp_servers/private_data_ops.py.
 *
 * Read-only MCP access to the Private DB (relationships.db) with the
 * Shared DB (fellows.db) ATTACHed read-only for cross-DB joins.
 * Exposes three tools to AI clients via stdio:
 *
 *  - list_groups        All groups + member counts, newest-touched first.
 *  - find_group         Case-insensitive substring match on group name.
 *  - get_group_members  One group plus its members, joined to fellows.db
 *                       for names + emails (single round-trip).
 *
 * Privacy posture (AC-MCP-A — see PNA Spec § Universal architectural
 * commitments): this server *does* return Private DB rows (your groups
 * and the fellows in them). Per AC-MCP-A, cloud AI clients should
 * require explicit per-call consent before seeing this data. v1 does
 * not implement that gate — it documents the boundary and trusts the
 * user's choice of MCP client. See mcp_servers/README.md § Cloud LLM
 * caveat and plans/easy_mcp_install.md § 7 (PWA preamble) for the
 * user-facing disclosure path.
 *
 * Read-only-ness is enforced at the SQLite layer (readOnly:true on
 * relationships.db; URI mode=ro on the ATTACHed fellows.db) — even a
 * buggy tool can't mutate either store.
 *
 * DB path resolution (matches Python's argparse semantics):
 *  - --db FLAG       → relationships.db path
 *  - --fellows-db    → fellows.db path
 *  - FELLOWS_RELATIONSHIPS_DB_PATH env → relationships.db
 *  - FELLOWS_DB_PATH env             → fellows.db
 *  - defaults: ${__dirname}/../data/{relationships,fellows}.db inside
 *    the installed .mcpb. relationships.db default in dev is
 *    repo/app/relationships.db; in production install Claude Desktop
 *    fills the path from the bundle's user_config prompt (per plan
 *    § 5 OPFS handoff).
 *
 * Behavioral parity with mcp_servers/private_data_ops.py is asserted
 * by tests/test_mcpb_parity.py per plans/easy_mcp_install.md § 6.
 *
 * Uses Node's built-in `node:sqlite` (stable since Node 24) to avoid
 * native dependencies; see docs/ac_decisions_log.md
 * § 2026-05-21 — `.mcpb` bundles do not ship native Node dependencies.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { existsSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

process.stderr.write(
  `private-data-ops: boot node=${process.version} cwd=${process.cwd()}\n`,
);

const LIST_LIMIT_DEFAULT = 100;
const LIST_LIMIT_MAX = 500;

function parseCliArg(
  argv: ReadonlyArray<string>,
  flag: string,
): string | null {
  // Match argparse semantics: --flag VALUE  or  --flag=VALUE
  const eq = `${flag}=`;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === flag && i + 1 < argv.length) return argv[i + 1] ?? null;
    if (a.startsWith(eq)) return a.slice(eq.length);
  }
  return null;
}

function resolveRelDbPath(argv: ReadonlyArray<string>): string {
  const cli = parseCliArg(argv, "--db");
  if (cli) return resolve(cli);
  const env = process.env.FELLOWS_RELATIONSHIPS_DB_PATH;
  if (env) return resolve(env);
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "data", "relationships.db");
}

function resolveFellowsDbPath(argv: ReadonlyArray<string>): string {
  const cli = parseCliArg(argv, "--fellows-db");
  if (cli) return resolve(cli);
  const env = process.env.FELLOWS_DB_PATH;
  if (env) return resolve(env);
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "data", "fellows.db");
}

const REL_DB_PATH = resolveRelDbPath(process.argv.slice(2));
const FELLOWS_DB_PATH = resolveFellowsDbPath(process.argv.slice(2));
process.stderr.write(
  `private-data-ops: rel_db=${REL_DB_PATH} fellows_db=${FELLOWS_DB_PATH}\n`,
);

if (!existsSync(REL_DB_PATH) || !statSync(REL_DB_PATH).isFile()) {
  process.stderr.write(
    `private-data-ops: relationships.db not found at ${REL_DB_PATH}\n` +
      "Open the Fellows app, go to Settings → Download a backup, and " +
      "point the integration at that file.\n",
  );
  process.exit(1);
}
if (!existsSync(FELLOWS_DB_PATH) || !statSync(FELLOWS_DB_PATH).isFile()) {
  process.stderr.write(
    `private-data-ops: fellows.db not found at ${FELLOWS_DB_PATH}\n`,
  );
  process.exit(1);
}

const db = new DatabaseSync(REL_DB_PATH, { readOnly: true });
// URI ATTACH with mode=ro mirrors Python's _path_to_ro_uri+ATTACH
// pattern. Confirmed in a local probe to enforce read-only at the
// SQLite layer (CREATE TABLE on f.* throws "attempt to write a
// readonly database"). The path is escaped against single quotes
// because we interpolate it into a SQL literal.
const fellowsUri = `file:${FELLOWS_DB_PATH.replace(/'/g, "''")}?mode=ro`;
try {
  db.exec(`ATTACH DATABASE '${fellowsUri}' AS f`);
} catch (err) {
  process.stderr.write(
    `private-data-ops: ATTACH fellows.db failed: ${(err as Error).message}\n`,
  );
  process.exit(1);
}

// Sanity-check both schemas before the stdio loop starts.
try {
  db.prepare("SELECT 1 FROM groups LIMIT 1").get();
  db.prepare("SELECT 1 FROM f.fellows LIMIT 1").get();
} catch (err) {
  process.stderr.write(
    `private-data-ops: schema check failed: ${(err as Error).message}\n`,
  );
  process.exit(1);
}

interface GroupRow {
  id: number;
  name: string;
  note: string;
  created_at: string;
  updated_at: string;
  member_count: number;
}

interface MemberRow {
  record_id: string;
  slug: string | null;
  name: string | null;
  contact_email: string | null;
  fellow_type: string | null;
  currently_based_in: string | null;
}

function toGroupSummary(row: GroupRow): Record<string, unknown> {
  return {
    group_id: row.id,
    name: row.name,
    note: row.note,
    member_count: row.member_count,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function toMember(row: MemberRow): Record<string, unknown> {
  return {
    record_id: row.record_id,
    slug: row.slug,
    name: row.name,
    contact_email: row.contact_email,
    fellow_type: row.fellow_type,
    currently_based_in: row.currently_based_in,
  };
}

function clampInt(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(Math.floor(value), max));
}

const server = new McpServer({ name: "private-data-ops", version: "0.1.0" });

server.registerTool(
  "list_groups",
  {
    description:
      "List all groups in your Private DB, newest-touched first. Returns { total, results: [GroupSummary] } where GroupSummary is { group_id, name, note, member_count, created_at, updated_at }.",
    inputSchema: {
      limit: z
        .number()
        .int()
        .nullish()
        .describe("Max groups to return. Default 100, capped at 500."),
    },
  },
  async ({ limit }) => {
    const lim = clampInt(limit ?? LIST_LIMIT_DEFAULT, 1, LIST_LIMIT_MAX);
    const total = (
      db.prepare("SELECT COUNT(*) as c FROM groups").get() as { c: number }
    ).c;
    const rows = db
      .prepare(
        `SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                COUNT(gm.fellow_record_id) AS member_count
         FROM groups g
         LEFT JOIN group_members gm ON gm.group_id = g.id
         GROUP BY g.id
         ORDER BY g.updated_at DESC, g.id DESC
         LIMIT ?`,
      )
      .all(lim) as unknown as GroupRow[];
    const results = rows.map(toGroupSummary);
    return {
      content: [{ type: "text", text: JSON.stringify({ total, results }) }],
    };
  },
);

server.registerTool(
  "find_group",
  {
    description:
      "Find groups whose name contains the given substring (case-insensitive). Useful when the user asks for 'the climate group' — substring match, return whatever's there. If multiple match, the AI client can disambiguate. Returns { query, total, results: [GroupSummary] }.",
    inputSchema: {
      name: z
        .string()
        .describe(
          "Substring to match against group names. Empty string returns no results.",
        ),
      limit: z
        .number()
        .int()
        .nullish()
        .describe("Max groups to return. Default 100, capped at 500."),
    },
  },
  async ({ name, limit }) => {
    const q = (name ?? "").trim();
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
    const lim = clampInt(limit ?? LIST_LIMIT_DEFAULT, 1, LIST_LIMIT_MAX);
    const pattern = `%${q}%`;
    const total = (
      db
        .prepare(
          "SELECT COUNT(*) as c FROM groups WHERE name LIKE ? COLLATE NOCASE",
        )
        .get(pattern) as { c: number }
    ).c;
    const rows = db
      .prepare(
        `SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                COUNT(gm.fellow_record_id) AS member_count
         FROM groups g
         LEFT JOIN group_members gm ON gm.group_id = g.id
         WHERE g.name LIKE ? COLLATE NOCASE
         GROUP BY g.id
         ORDER BY g.updated_at DESC, g.id DESC
         LIMIT ?`,
      )
      .all(pattern, lim) as unknown as GroupRow[];
    const results = rows.map(toGroupSummary);
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
  "get_group_members",
  {
    description:
      "Fetch one group plus its members, joined to fellows.db for names + emails. Single round-trip — the AI doesn't need to chain to shared-data-ops to resolve names for the common case (drafting a group email). Members with a record_id that no longer resolves in fellows.db come back with null name / contact_email (orphan after a Shared DB re-mirror). Returns { group, members: [Member] } or null if no group with that id exists.",
    inputSchema: {
      group_id: z
        .number()
        .int()
        .describe("The numeric group id from list_groups / find_group."),
    },
  },
  async ({ group_id }) => {
    const gid = Math.floor(group_id);
    const groupRow = db
      .prepare(
        `SELECT g.id, g.name, g.note, g.created_at, g.updated_at,
                (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id)
                  AS member_count
         FROM groups g
         WHERE g.id = ?`,
      )
      .get(gid) as unknown as GroupRow | undefined;
    if (!groupRow) {
      return { content: [{ type: "text", text: JSON.stringify(null) }] };
    }
    const group = toGroupSummary(groupRow);
    const memberRows = db
      .prepare(
        `SELECT gm.fellow_record_id AS record_id,
                fl.slug AS slug,
                fl.name AS name,
                fl.contact_email AS contact_email,
                fl.fellow_type AS fellow_type,
                fl.currently_based_in AS currently_based_in
         FROM group_members gm
         LEFT JOIN f.fellows fl ON fl.record_id = gm.fellow_record_id
         WHERE gm.group_id = ?
         ORDER BY COALESCE(fl.name, gm.fellow_record_id) ASC`,
      )
      .all(gid) as unknown as MemberRow[];
    const members = memberRows.map(toMember);
    return {
      content: [
        { type: "text", text: JSON.stringify({ group, members }) },
      ],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
