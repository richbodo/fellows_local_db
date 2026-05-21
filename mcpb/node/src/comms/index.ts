#!/usr/bin/env node
/**
 * Communications MCP server (Node port of ../../mcp_servers/comms.py).
 *
 * Exposes two tools to AI clients via stdio:
 *
 *  - stage_email   Build a mailto: URL + payload preview. Returns
 *                  staging_id, URL, and warnings (URL-length, missing
 *                  recipients, addresses-visible nudge).
 *  - get_staged    Echo a previously staged composition by id (in-memory).
 *
 * Architectural posture (AC-MCP-B — PNA Spec § Universal architectural
 * commitments): the MCP server proposes, the workspace disposes. This
 * server never launches a transport itself. It returns a mailto: URL
 * that the user's mail client opens with the composition pre-populated;
 * the user reviews and clicks Send.
 *
 * State posture: staged compositions live in-memory only. Process exit
 * clears them. Nothing on disk — no logs of who you emailed, no draft
 * persistence. That belongs to the workspace (PR-2 record_comms_history
 * in the PNA spec — opt-in, off by default).
 *
 * Behavioral parity with mcp_servers/comms.py is asserted by
 * tests/test_mcpb_parity.py per the dual-codebase governance in
 * plans/easy_mcp_install.md § 6.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { randomBytes } from "node:crypto";

// Unconditional startup line — appears in Claude Desktop's per-server
// log so any future startup failure has a trace.
process.stderr.write(`comms: boot node=${process.version}\n`);

const MAILTO_URL_WARN_BYTES = 2000;
const STAGED_MAX = 100;

interface StagedRecord {
  mailto_url: string;
  preview: {
    recipients: { to: string[]; cc: string[]; bcc: string[]; total: number };
    subject: string;
    body: string;
    url_byte_length: number;
  };
  warnings: string[];
}

const STAGED: Map<string, StagedRecord> = new Map();

function newStagingId(): string {
  return randomBytes(12).toString("base64url").slice(0, 16);
}

function cleanEmail(addr: string | null | undefined): string {
  return (addr ?? "").trim();
}

function dedupeEmails(addrs: ReadonlyArray<string> | null | undefined): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const a of addrs ?? []) {
    const c = cleanEmail(a);
    if (!c) continue;
    const key = c.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(c);
  }
  return out;
}

const UTF8 = new TextEncoder();

function pyQuote(s: string, safe: string): string {
  const safeSet = new Set<number>();
  for (const ch of safe) safeSet.add(ch.charCodeAt(0));
  let out = "";
  for (const ch of s) {
    const code = ch.codePointAt(0)!;
    const isUnreserved =
      (code >= 0x30 && code <= 0x39) ||
      (code >= 0x41 && code <= 0x5a) ||
      (code >= 0x61 && code <= 0x7a) ||
      code === 0x5f || code === 0x2e || code === 0x2d || code === 0x7e;
    if (isUnreserved || (code < 0x80 && safeSet.has(code))) {
      out += ch;
    } else {
      for (const b of UTF8.encode(ch)) {
        out += "%" + b.toString(16).toUpperCase().padStart(2, "0");
      }
    }
  }
  return out;
}

function buildMailto(
  to: string[],
  cc: string[],
  bcc: string[],
  subject: string,
  body: string,
): string {
  const path = to.map((addr) => pyQuote(addr, "@")).join(",");
  const params: Array<[string, string]> = [];
  if (cc.length) params.push(["cc", cc.join(",")]);
  if (bcc.length) params.push(["bcc", bcc.join(",")]);
  if (subject) params.push(["subject", subject]);
  if (body) params.push(["body", body]);
  if (params.length === 0) return `mailto:${path}`;
  const qs = params.map(([k, v]) => `${k}=${pyQuote(v, "@,")}`).join("&");
  return `mailto:${path}?${qs}`;
}

function store(record: StagedRecord): string {
  const sid = newStagingId();
  if (STAGED.size >= STAGED_MAX) {
    const oldest = STAGED.keys().next().value;
    if (oldest !== undefined) STAGED.delete(oldest);
  }
  STAGED.set(sid, record);
  return sid;
}

const server = new McpServer({ name: "comms", version: "0.1.0" });

server.registerTool(
  "stage_email",
  {
    description:
      "Stage an email composition for the user to review and send. Builds a mailto: URL that the user's mail client opens with everything pre-populated. The MCP server never sends — opening the URL is what the user does to hand the composition off to the mail client. For groups, prefer bcc over to so individual addresses aren't visible in everyone's To: header. Recipients are deduplicated case-insensitively; empty addresses are silently dropped.",
    inputSchema: {
      subject: z
        .string()
        .describe("The email subject. Required (empty string allowed)."),
      body: z
        .string()
        .describe("The email body. Required (empty string allowed)."),
      to: z
        .array(z.string())
        .nullish()
        .describe(
          "Visible primary recipients. Optional; pass an empty list or omit for BCC-only group sends.",
        ),
      cc: z.array(z.string()).nullish().describe("Carbon-copied recipients."),
      bcc: z
        .array(z.string())
        .nullish()
        .describe("Blind-carbon-copied recipients."),
    },
  },
  async ({ subject, body, to, cc, bcc }) => {
    const toClean = dedupeEmails(to);
    const ccClean = dedupeEmails(cc);
    const bccClean = dedupeEmails(bcc);
    const safeSubject = subject ?? "";
    const safeBody = body ?? "";

    const mailtoUrl = buildMailto(
      toClean,
      ccClean,
      bccClean,
      safeSubject,
      safeBody,
    );
    const urlBytes = Buffer.byteLength(mailtoUrl, "utf-8");
    const total = toClean.length + ccClean.length + bccClean.length;

    const warnings: string[] = [];
    if (total === 0) {
      warnings.push(
        "No recipients — the mail client will open but won't have anyone to send to.",
      );
    }
    if (urlBytes > MAILTO_URL_WARN_BYTES) {
      warnings.push(
        `mailto: URL is ${urlBytes} bytes; some mail clients (Outlook, Gmail-via-mailto) start truncating around ${MAILTO_URL_WARN_BYTES} bytes. Consider splitting the recipient list, or paste the body into the mail composer after it opens.`,
      );
    }
    if (toClean.length && total > 1 && bccClean.length === 0) {
      warnings.push(
        "Multiple recipients in `to`. Consider moving them to `bcc` so addresses aren't visible to everyone on the thread.",
      );
    }

    const preview = {
      recipients: {
        to: toClean,
        cc: ccClean,
        bcc: bccClean,
        total,
      },
      subject: safeSubject,
      body: safeBody,
      url_byte_length: urlBytes,
    };
    const record: StagedRecord = {
      mailto_url: mailtoUrl,
      preview,
      warnings,
    };
    const sid = store(record);
    const payload = { staging_id: sid, ...record };

    return {
      content: [{ type: "text", text: JSON.stringify(payload) }],
    };
  },
);

server.registerTool(
  "get_staged",
  {
    description:
      "Look up a previously staged composition by id. Useful when the user asks 'what did you draft a minute ago?'. Returns null when the id isn't known (process restart, eviction, or never staged). Staged records live in memory only; nothing persists across restarts.",
    inputSchema: {
      staging_id: z.string().describe("The id returned by stage_email."),
    },
  },
  async ({ staging_id }) => {
    const sid = (staging_id ?? "").trim();
    let result: unknown = null;
    if (sid) {
      const rec = STAGED.get(sid);
      if (rec) result = { staging_id: sid, ...rec };
    }
    return {
      content: [{ type: "text", text: JSON.stringify(result) }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
