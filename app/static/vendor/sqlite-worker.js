// EHF Fellows local DB — sqlite-wasm worker (sole OPFS owner).
//
// Runs sqlite-wasm + OPFS-SAH-Pool in dedicated-worker scope and is the
// only context in the app permitted to call navigator.storage.getDirectory
// or open a FileSystemSyncAccessHandle. The main thread is an RPC client
// per plans/local_first_worker_architecture.md (Phase 1) and
// docs/Architecture.md § Worker-owned OPFS.
//
// Two databases live here:
//   - relationships.db (read-write user-authored data: groups, members,
//     fellow_tags, fellow_notes, settings)
//   - fellows.db (read-only contact data; cached locally, refreshed by the
//     page-driven ensureFellowsDb RPC; SHA-keyed refresh ships in Phase 3)
//
// Protocol:
//   main → worker: { id, op, args }
//   worker → main: { id, ok: true,  result }
//                  { id, ok: false, error, errorName?, stack? }
//
// First message must be op='init'. The init response is a handshake blob:
//   { ok, workerRpcVersion, schemaVersion, buildLabel,
//     opfsCapable, hasFellowsDb, hasRelationshipsDb,
//     poolFiles, trace }
// The page reads workerRpcVersion + schemaVersion and refuses mutating
// RPCs on mismatch (passive — the SW's existing reload banner is the
// canonical update affordance).

'use strict';

// Sibling import — this file lives in /vendor/ alongside sqlite3.js.
// The relative path is what makes sqlite-wasm's scriptDirectory resolve
// to /vendor/, so its internal locateFile('sqlite3.wasm') finds the
// companion /vendor/sqlite3.wasm.
importScripts('./sqlite3.js');

// ===== Compatibility constants ==============================================
// Bumped only when the request/response shape of any RPC changes (parameters,
// return shape, error semantics). A pure code refactor that preserves the
// wire shape leaves it alone. Page reads this in the init handshake and
// refuses mutating RPCs on mismatch.
//
// v2 (Phase 3): ensureFellowsDb({serverSha}) gained an optional serverSha
// arg and SHA-keyed refresh semantics. Page bumps its expected value in
// lockstep; a stale page paired with this worker (or vice versa) refuses
// mutations and waits for the SW's "New version available" reload banner.
var WORKER_RPC_VERSION = 2;

// Same value as relationships.db's PRAGMA user_version. Bumped only on
// schema migrations. Mirrored from app/relationships.py:SCHEMA_VERSION.
var RELATIONSHIPS_SCHEMA_VERSION = 1;

// Substituted at build time by build/build_pwa.py and at serve time by
// app/server.py (same substitution path as app.js / sw.js). If you ever
// see the literal `__FELLOWS_UI_DIAG__` in diagnostics, the build pipeline
// didn't touch this file.
var BUILD_LABEL = '__FELLOWS_UI_DIAG__';

// ===== Schema (mirrored from app.js — keep in sync) =========================

var RELATIONSHIPS_SCHEMA_SQL =
  'CREATE TABLE IF NOT EXISTS groups (' +
  '  id INTEGER PRIMARY KEY,' +
  '  name TEXT NOT NULL,' +
  '  note TEXT NOT NULL DEFAULT \'\',' +
  '  created_at TEXT NOT NULL,' +
  '  updated_at TEXT NOT NULL' +
  ');' +
  'CREATE TABLE IF NOT EXISTS group_members (' +
  '  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,' +
  '  fellow_record_id TEXT NOT NULL,' +
  '  PRIMARY KEY (group_id, fellow_record_id)' +
  ');' +
  'CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members(group_id);' +
  'CREATE TABLE IF NOT EXISTS fellow_tags (' +
  '  fellow_record_id TEXT NOT NULL,' +
  '  tag TEXT NOT NULL,' +
  '  created_at TEXT NOT NULL,' +
  '  PRIMARY KEY (fellow_record_id, tag)' +
  ');' +
  'CREATE INDEX IF NOT EXISTS idx_fellow_tags_tag ON fellow_tags(tag);' +
  'CREATE TABLE IF NOT EXISTS fellow_notes (' +
  '  fellow_record_id TEXT PRIMARY KEY,' +
  '  body TEXT NOT NULL,' +
  '  updated_at TEXT NOT NULL' +
  ');' +
  'CREATE TABLE IF NOT EXISTS settings (' +
  '  key TEXT PRIMARY KEY,' +
  '  value TEXT' +
  ');';

// ===== Fellows.db column / label tables (mirrored from app/server.py) =======

var FELLOW_COLUMNS = [
  'record_id', 'slug', 'name', 'bio_tagline', 'fellow_type', 'cohort',
  'contact_email', 'key_links', 'key_links_urls', 'image_url',
  'currently_based_in', 'search_tags', 'fellow_status', 'gender_pronouns',
  'ethnicity', 'primary_citizenship', 'global_regions_currently_based_in',
  'has_image'
];

// Friendly labels used by getStats — mirror app/server.py:get_stats.
var COL_LABELS = {
  name: 'Name',
  bio_tagline: 'Bio / Tagline',
  fellow_type: 'Fellow Type',
  cohort: 'Cohort',
  contact_email: 'Contact Email',
  key_links: 'Key Links',
  image_url: 'Image URL',
  currently_based_in: 'Currently Based In',
  search_tags: 'Search Tags',
  fellow_status: 'Fellow Status',
  gender_pronouns: 'Gender / Pronouns',
  ethnicity: 'Ethnicity',
  primary_citizenship: 'Primary Citizenship',
  global_regions_currently_based_in: 'Global Regions Based In'
};

var EXTRA_LABELS = {
  all_citizenships: 'All Citizenships',
  ventures: 'Ventures',
  industries: 'Industries',
  career_highlights: 'Career Highlights',
  key_networks: 'Key Networks',
  how_im_looking_to_support_the_nz_ecosystem: 'How Supporting NZ Ecosystem',
  what_is_your_main_mode_of_working: 'Main Mode of Working',
  do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories: 'Investor Categories',
  mobile_number: 'Mobile Number',
  five_things_to_know: 'Five Things to Know',
  skills_to_give: 'Skills to Give',
  skills_to_receive: 'Skills to Receive'
};

// ===== Backup / staging / meta-file constants ===============================

var BACKUP_PREFIX = 'relationships.db.bak.';
// Per Phase 0 Q-C resolution: rotation increased from 3 to 5 (files are
// tiny — tens of KB even for an active user). Rationale lives in
// docs/persistence_and_upgrades.md § Auto-backup of `relationships.db`.
var BACKUP_KEEP = 5;
// Per Phase 0 Q-C: skip the per-boot snapshot if the most recent
// backup is younger than this. Keeps debug-session reloads from
// thrashing the rotation.
var BACKUP_DEBOUNCE_MS = 60 * 60 * 1000;

// One-time cleanup target. The pre-Phase-1 main-thread auto-backup wrote
// this sentinel; the worker-owned debounce derives its trigger from the
// newest bak.<ISO> filename instead. Kept so we can removeEntry() it on
// the first boot of a P1+ build.
var LEGACY_SENTINEL = 'last_seen_sha.txt';

// SAH-pool VFS internally canonicalizes filenames to leading-slash form,
// so importDb('foo') stores under 'foo' but new OpfsSAHPoolDb('foo')
// opens '/foo'. The mismatch silently allocates a fresh empty SAH for
// '/foo', and the imported bytes are unreachable. Use leading-slash
// names consistently so importDb and OpfsSAHPoolDb hit the same SAH.
var RELATIONSHIPS_DB_SLOT = '/relationships.db';
var FELLOWS_DB_SLOT = '/fellows.db';
var RESTORE_STAGING_SLOT = '/relationships.db.restore-staging';
var FELLOWS_STAGING_SLOT = '/fellows.db.staging';
// Distinct from FELLOWS_STAGING_SLOT — the boot-path ensureFellowsDb
// staging slot is short-lived (open, validate, swap, close in one tick)
// while the user-driven swap can sit pending across the confirm dialog.
// Using separate slots avoids any chance of one path stomping the other,
// even though under the opt-in policy ensureFellowsDb only fires at cold
// start.
var FELLOWS_SWAP_STAGING_SLOT = '/fellows.db.swap-staging';
var FELLOWS_META_FILE = 'fellows.db.meta.json';

var REQUIRED_RESTORE_TABLES = ['groups', 'group_members', 'fellow_tags', 'fellow_notes', 'settings'];

// ===== State ================================================================

var sqlite3 = null;
var poolUtil = null;
var relDb = null;
var fellowsDb = null;
var bootTrace = [];

// User-driven directory-data update, between previewFellowsDbSwap and
// applyFellowsDbSwap / cancelFellowsDbSwap. Holds the SHA + an opaque
// stagingId that the page must echo back. Bytes live in the staging
// slot, not in JS memory.
var pendingFellowsDbSwap = null;

function trace(msg) { bootTrace.push(new Date().toISOString() + ' ' + String(msg)); }

// Recognize the SAH ownership-conflict failure that
// installOpfsSAHPoolVfs() throws when another tab's worker already holds
// the pool's capacity-file SAHs. Detection is name-first (Chrome surfaces
// it as DOMException 'NoModificationAllowedError') with a message-substring
// fallback for engines that haven't standardized the name yet. Conservative
// — anything not matching falls through as a generic init failure.
function isOwnershipConflictError(e) {
  if (!e) return false;
  if (e.name === 'NoModificationAllowedError') return true;
  var msg = String((e && e.message) || e || '');
  return /another open (?:Access Handle|Writable stream)/i.test(msg) ||
         /Access Handles? cannot be created/i.test(msg);
}

// ===== SQL helpers ==========================================================

function dbSelectAll(db, sql, bind) {
  var st = db.prepare(sql);
  var out = [];
  try {
    if (bind !== undefined && bind !== null) st.bind(bind);
    while (st.step()) out.push(st.get({}));
  } finally { st.finalize(); }
  return out;
}

function dbSelectOne(db, sql, bind) {
  var rows = dbSelectAll(db, sql, bind);
  return rows.length ? rows[0] : null;
}

function dbRun(db, sql, bind) {
  var st = db.prepare(sql);
  try {
    if (bind !== undefined && bind !== null) st.bind(bind);
    st.step();
  } finally { st.finalize(); }
}

function bootstrapRelationshipsSchema(db) {
  // PRAGMA foreign_keys is per-connection and defaults OFF. Without it,
  // group_members.group_id's `ON DELETE CASCADE` is silently inert and
  // deleteGroup leaves orphan rows in OPFS forever. Mirrors
  // app/relationships.py:296. Must run on every relDb open (init +
  // post-restore importRelationshipsBytes) since this resets each time
  // a connection is closed.
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec(RELATIONSHIPS_SCHEMA_SQL);
  db.exec('PRAGMA user_version = ' + RELATIONSHIPS_SCHEMA_VERSION);
}

function nowIsoSecond() {
  return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
}

function dedupeRecordIds(ids) {
  var seen = {}, out = [];
  if (!ids) return out;
  for (var i = 0; i < ids.length; i++) {
    var rid = ids[i];
    if (typeof rid !== 'string') continue;
    var s = rid.replace(/^\s+|\s+$/g, '');
    if (!s || seen[s]) continue;
    seen[s] = 1;
    out.push(s);
  }
  return out;
}

// Mirrors app/server.py:row_to_fellow. Parses the key_links_urls JSON
// column and merges extra_json into the top-level object so the API
// returns all original fields without per-field schema knowledge.
function rowToFellow(row) {
  var out = {};
  for (var i = 0; i < FELLOW_COLUMNS.length; i++) {
    var key = FELLOW_COLUMNS[i];
    var val = row[key];
    if (key === 'key_links_urls' && val !== null && val !== undefined) {
      try { out[key] = JSON.parse(val); } catch (e) { out[key] = val; }
    } else {
      out[key] = val !== undefined ? val : null;
    }
  }
  if (row.extra_json) {
    try {
      var extra = JSON.parse(row.extra_json);
      if (extra && typeof extra === 'object' && !Array.isArray(extra)) {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) out[k] = extra[k];
        }
      }
    } catch (e2) {}
  }
  return out;
}

// ===== OPFS root file helpers ===============================================

async function _opfsRoot() { return await self.navigator.storage.getDirectory(); }

async function _opfsReadText(name) {
  try {
    var root = await _opfsRoot();
    var fh = await root.getFileHandle(name);
    var f = await fh.getFile();
    return await f.text();
  } catch (e) { return null; }
}

async function _opfsWriteText(name, content) {
  var root = await _opfsRoot();
  var fh = await root.getFileHandle(name, { create: true });
  var w = await fh.createWritable();
  await w.write(content);
  await w.close();
}

async function _opfsWriteBinary(name, bytes) {
  var root = await _opfsRoot();
  var fh = await root.getFileHandle(name, { create: true });
  var w = await fh.createWritable();
  await w.write(bytes);
  await w.close();
}

async function _opfsReadBinary(name) {
  var root = await _opfsRoot();
  var fh = await root.getFileHandle(name);
  var f = await fh.getFile();
  return new Uint8Array(await f.arrayBuffer());
}

async function _opfsRemoveEntry(name) {
  try {
    var root = await _opfsRoot();
    await root.removeEntry(name);
    return true;
  } catch (e) {
    return false;
  }
}

async function listRelationshipsBackups() {
  try {
    var root = await _opfsRoot();
    var out = [];
    for await (var entry of root.values()) {
      if (entry.kind === 'file' && entry.name.indexOf(BACKUP_PREFIX) === 0) {
        var f = await entry.getFile();
        out.push({ name: entry.name, size: f.size, lastModified: f.lastModified });
      }
    }
    out.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
    return out;
  } catch (e) { return []; }
}

async function _rotateRelationshipsBackups() {
  var backups = await listRelationshipsBackups();
  var root = await _opfsRoot();
  while (backups.length > BACKUP_KEEP) {
    var oldest = backups.shift();
    try {
      await root.removeEntry(oldest.name);
      trace('backup: rotated out ' + oldest.name);
    } catch (e) {
      trace('backup: rotate removeEntry failed for ' + oldest.name);
    }
  }
}

// ===== Auto-backup (debounced per-boot) =====================================

// Per Phase 0 Q-C: trigger flips from "build-SHA differs" to "newest
// bak.<ISO> older than 1 hour." Recovery use case ("undo what I just
// did") is keyed to user-edit cadence, not deploy cadence. The
// last_seen_sha.txt sentinel is retired; debounce reads the most recent
// bak filename's timestamp instead.
async function maybeBackupRelationshipsDb() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) === -1) {
    trace('backup: skipped (no relationships.db yet — first install)');
    return { backedUp: false, reason: 'first install' };
  }
  var backups = await listRelationshipsBackups();
  if (backups.length) {
    var newest = backups[backups.length - 1];
    var ageMs = Date.now() - newest.lastModified;
    if (ageMs >= 0 && ageMs < BACKUP_DEBOUNCE_MS) {
      trace('backup: skipped (newest ' + newest.name + ' is ' +
            Math.round(ageMs / 1000) + 's old, debounce ' +
            Math.round(BACKUP_DEBOUNCE_MS / 1000) + 's)');
      return { backedUp: false, reason: 'debounced' };
    }
  }
  var bytes;
  try { bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT); }
  catch (e) {
    trace('backup: exportFile failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'export failed' };
  }
  if (!bytes || !bytes.byteLength) {
    return { backedUp: false, reason: 'empty file' };
  }
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _opfsWriteBinary(backupName, bytes); }
  catch (e) {
    trace('backup: write failed: ' + (e && e.message || e));
    return { backedUp: false, reason: 'write failed' };
  }
  await _rotateRelationshipsBackups();
  trace('backup: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes)');
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

async function snapshotRelationshipsDbToBackup() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(RELATIONSHIPS_DB_SLOT) === -1) {
    return { backedUp: false, reason: 'no relationships.db' };
  }
  var bytes;
  try { bytes = poolUtil.exportFile(RELATIONSHIPS_DB_SLOT); }
  catch (e) { return { backedUp: false, reason: 'export failed: ' + (e && e.message || e) }; }
  if (!bytes || !bytes.byteLength) return { backedUp: false, reason: 'empty file' };
  var ts = new Date().toISOString().replace(/[:.]/g, '-');
  var backupName = BACKUP_PREFIX + ts;
  try { await _opfsWriteBinary(backupName, bytes); }
  catch (e) { return { backedUp: false, reason: 'write failed: ' + (e && e.message || e) }; }
  await _rotateRelationshipsBackups();
  trace('snapshot: wrote ' + backupName + ' (' + bytes.byteLength + ' bytes)');
  return { backedUp: true, name: backupName, size: bytes.byteLength };
}

// ===== fellows.db.meta.json (freshness sidecar) =============================
// Sibling of fellows.db at the OPFS root, outside the SAH-pool dir, so a
// relationships.db restore can't desync fellows.db freshness. The page
// passes the server-reported `fellows_db_sha` (read from /build-meta.json)
// into ensureFellowsDb; the worker compares it to `meta.sha` to decide
// whether to re-fetch.

async function readFellowsMeta() {
  var raw = await _opfsReadText(FELLOWS_META_FILE);
  if (!raw) return null;
  try {
    var obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') return obj;
  } catch (e) {}
  return null;
}

async function writeFellowsMeta(meta) {
  await _opfsWriteText(FELLOWS_META_FILE, JSON.stringify(meta));
}

// SubtleCrypto digest of `bytes` as lowercase hex. Identical output to the
// build pipeline's `hashlib.sha256(...).hexdigest()` — the comparison hinges
// on byte-for-byte agreement between the dist DB and what the worker
// fetches over the wire, so the digest function on both sides has to round
// to the same string.
async function _sha256Hex(bytes) {
  var buf = await crypto.subtle.digest('SHA-256', bytes);
  var view = new Uint8Array(buf);
  var hex = '';
  for (var i = 0; i < view.length; i++) {
    var b = view[i];
    hex += (b < 16 ? '0' : '') + b.toString(16);
  }
  return hex;
}

// ===== Inspect bytes (used by import + listRelationshipsBackups) =============

async function inspectBytes(bytes) {
  if (!poolUtil) return { valid: false, error: 'pool util unavailable' };
  if (!bytes || !bytes.byteLength) return { valid: false, error: 'File is empty.' };
  var hdr = 'SQLite format 3\0';
  if (bytes.byteLength < hdr.length) {
    return { valid: false, error: 'File is too small to be a SQLite database.' };
  }
  for (var i = 0; i < hdr.length; i++) {
    if (bytes[i] !== hdr.charCodeAt(i)) {
      return { valid: false, error: 'File does not look like a SQLite database.' };
    }
  }
  var tmp = null;
  try {
    poolUtil.importDb(RESTORE_STAGING_SLOT, bytes);
    tmp = new poolUtil.OpfsSAHPoolDb(RESTORE_STAGING_SLOT);
    var qc = dbSelectOne(tmp, 'PRAGMA quick_check', null);
    var qcResult = qc && (qc.quick_check || qc['quick_check']);
    if (qcResult !== 'ok') {
      return { valid: false, error: 'SQLite integrity check failed: ' + (qcResult || 'unknown') };
    }
    var tableRows = dbSelectAll(tmp, "SELECT name FROM sqlite_master WHERE type='table'", null);
    var tableNames = tableRows.map(function (r) { return r.name; });
    var missing = REQUIRED_RESTORE_TABLES.filter(function (t) { return tableNames.indexOf(t) === -1; });
    if (missing.length) {
      return {
        valid: false,
        error: 'File is missing expected tables: ' + missing.join(', ') +
          '. Is this a relationships.db backup?'
      };
    }
    return {
      valid: true,
      counts: {
        groups: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM groups', null).n,
        members: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM group_members', null).n,
        tags: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
        notes: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
        settings: dbSelectOne(tmp, 'SELECT COUNT(*) AS n FROM settings', null).n
      }
    };
  } catch (e) {
    return { valid: false, error: (e && e.message) || String(e) };
  } finally {
    if (tmp) { try { tmp.close(); } catch (e2) {} }
  }
}

// ===== fellows.db lifecycle =================================================

function _openFellowsDbIfPresent() {
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e) {}
  if (poolFiles.indexOf(FELLOWS_DB_SLOT) === -1) {
    return false;
  }
  try {
    fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
    trace('fellows.db: open OK');
    return true;
  } catch (e) {
    trace('fellows.db: open failed (' + (e && e.message || e) + ')');
    fellowsDb = null;
    return false;
  }
}

// ===== RPC handlers =========================================================

var handlers = {};

handlers.init = async function () {
  trace('init: starting (build=' + BUILD_LABEL + ')');
  if (typeof globalThis.sqlite3InitModule !== 'function') {
    throw new Error('sqlite3InitModule missing in worker (vendor/sqlite3.js failed to load?)');
  }
  sqlite3 = await globalThis.sqlite3InitModule();
  trace('sqlite3InitModule: OK');
  if (typeof sqlite3.installOpfsSAHPoolVfs !== 'function') {
    throw new Error('sqlite3.installOpfsSAHPoolVfs missing in worker build');
  }
  try {
    poolUtil = await sqlite3.installOpfsSAHPoolVfs();
    trace('installOpfsSAHPoolVfs: OK');
  } catch (poolErr) {
    // The SAH-pool VFS opens a fixed pool of OPFS capacity files via
    // FileSystemFileHandle.createSyncAccessHandle(). If another tab or
    // window of this app is already running, its worker holds those
    // handles and ours can't acquire them — Chrome throws a
    // NoModificationAllowedError DOMException with message "Access
    // Handles cannot be created if there is another open Access Handle
    // or Writable stream associated with the same file."
    //
    // Tag that case with code='OWNERSHIP_CONFLICT' so the page can
    // render a specific "directory is open in another tab" panel
    // instead of the misleading "your browser doesn't support this"
    // copy. Other init failures stay generic. See
    // plans/multi_tab_ownership_takeover.md for the full coordinated
    // takeover this is the cheap-fix predecessor of.
    if (isOwnershipConflictError(poolErr)) {
      trace('installOpfsSAHPoolVfs: OWNERSHIP_CONFLICT (' + ((poolErr && poolErr.message) || String(poolErr)) + ')');
      var conflictErr = new Error(
        'Could not acquire OPFS lock — another tab or window of this app is already open. ' +
        'Original: ' + ((poolErr && poolErr.message) || String(poolErr))
      );
      conflictErr.code = 'OWNERSHIP_CONFLICT';
      conflictErr.name = (poolErr && poolErr.name) || 'NoModificationAllowedError';
      throw conflictErr;
    }
    trace('installOpfsSAHPoolVfs: FAILED (' + ((poolErr && poolErr.message) || String(poolErr)) + ')');
    throw poolErr;
  }

  // One-time cleanup of the pre-P1 build-SHA sentinel (now retired).
  // No-op on profiles that never had it (clean installs, post-P1 boots).
  var sentinelRemoved = await _opfsRemoveEntry(LEGACY_SENTINEL);
  if (sentinelRemoved) trace('cleanup: removed legacy ' + LEGACY_SENTINEL);

  // Auto-backup runs before opening relationships.db for app use, so the
  // snapshot reflects the user's last-saved state, not anything mutated
  // this session. Failure is non-fatal — logged via bootTrace.
  await maybeBackupRelationshipsDb();

  var hasRelationshipsDb = false;
  try {
    relDb = new poolUtil.OpfsSAHPoolDb(RELATIONSHIPS_DB_SLOT);
    bootstrapRelationshipsSchema(relDb);
    hasRelationshipsDb = true;
    trace('relationships.db: open + schema OK');
  } catch (relErr) {
    trace('relationships.db: open failed (' + (relErr && relErr.message || relErr) + ')');
    relDb = null;
  }

  // Open fellows.db if it's already on disk. Cold-start fetch is the
  // page-driven ensureFellowsDb RPC, gated behind directory-mode commit
  // (per L4a). Init is network-free.
  var hasFellowsDb = _openFellowsDbIfPresent();

  return {
    ok: true,
    workerRpcVersion: WORKER_RPC_VERSION,
    schemaVersion: RELATIONSHIPS_SCHEMA_VERSION,
    buildLabel: BUILD_LABEL,
    opfsCapable: true,
    hasRelationshipsDb: hasRelationshipsDb,
    relDbOpen: hasRelationshipsDb,
    hasFellowsDb: hasFellowsDb,
    poolFiles: (function () { try { return poolUtil.getFileNames(); } catch (e) { return []; } })(),
    trace: bootTrace.slice()
  };
};

// ----- Relationships (groups + settings) ------------------------------------

handlers.listGroups = async function () {
  if (!relDb) throw new Error('relationships db not open');
  return dbSelectAll(
    relDb,
    'SELECT g.id, g.name, g.note, g.created_at, g.updated_at, ' +
      'COUNT(gm.fellow_record_id) AS count ' +
      'FROM groups g LEFT JOIN group_members gm ON gm.group_id = g.id ' +
      'GROUP BY g.id ORDER BY g.updated_at DESC, g.id DESC',
    null
  );
};

handlers.getGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var row = dbSelectOne(relDb, 'SELECT * FROM groups WHERE id = ?', [id]);
  if (!row) return null;
  // Members come back as record_ids only; main thread resolves names from
  // its in-memory cache (populated by getList/getFull).
  var members = dbSelectAll(
    relDb, 'SELECT fellow_record_id AS record_id FROM group_members WHERE group_id = ?', [id]
  );
  row.members = members;
  return row;
};

handlers.createGroup = async function (data) {
  if (!relDb) throw new Error('relationships db not open');
  var name = data && data.name;
  var note = (data && typeof data.note === 'string') ? data.note : '';
  var ids = dedupeRecordIds(data && data.fellow_record_ids);
  var now = nowIsoSecond();
  relDb.exec('BEGIN');
  try {
    dbRun(relDb, 'INSERT INTO groups(name, note, created_at, updated_at) VALUES (?, ?, ?, ?)',
          [name, note, now, now]);
    var idRow = dbSelectOne(relDb, 'SELECT last_insert_rowid() AS id', null);
    var gid = idRow && idRow.id;
    for (var i = 0; i < ids.length; i++) {
      dbRun(relDb, 'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)', [gid, ids[i]]);
    }
    relDb.exec('COMMIT');
    return await handlers.getGroup({ id: gid });
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
};

handlers.updateGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var patch = (args && args.patch) || {};
  var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
  if (!existing) return null;
  var sets = ['updated_at = ?'];
  var params = [nowIsoSecond()];
  if (typeof patch.name === 'string') { sets.push('name = ?'); params.push(patch.name); }
  if (typeof patch.note === 'string') { sets.push('note = ?'); params.push(patch.note); }
  params.push(id);
  relDb.exec('BEGIN');
  try {
    dbRun(relDb, 'UPDATE groups SET ' + sets.join(', ') + ' WHERE id = ?', params);
    if (Array.isArray(patch.fellow_record_ids)) {
      dbRun(relDb, 'DELETE FROM group_members WHERE group_id = ?', [id]);
      var ids = dedupeRecordIds(patch.fellow_record_ids);
      for (var i = 0; i < ids.length; i++) {
        dbRun(relDb, 'INSERT INTO group_members(group_id, fellow_record_id) VALUES (?, ?)', [id, ids[i]]);
      }
    }
    relDb.exec('COMMIT');
    return await handlers.getGroup({ id: id });
  } catch (e) {
    try { relDb.exec('ROLLBACK'); } catch (e2) {}
    throw e;
  }
};

handlers.deleteGroup = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var id = args && args.id;
  var existing = dbSelectOne(relDb, 'SELECT 1 AS x FROM groups WHERE id = ?', [id]);
  if (!existing) return false;
  dbRun(relDb, 'DELETE FROM groups WHERE id = ?', [id]);
  return true;
};

handlers.getSetting = async function (args) {
  if (!relDb) return null;
  var row = dbSelectOne(relDb, 'SELECT value FROM settings WHERE key = ?', [args && args.key]);
  return row ? row.value : null;
};

handlers.getSettings = async function () {
  if (!relDb) return {};
  var rows = dbSelectAll(relDb, 'SELECT key, value FROM settings', null);
  var bag = {};
  rows.forEach(function (r) { bag[r.key] = r.value; });
  return bag;
};

handlers.setSetting = async function (args) {
  if (!relDb) throw new Error('relationships db not open');
  var key = args && args.key;
  var value = args && args.value;
  if (value === null || value === undefined || value === '') {
    dbRun(relDb, 'DELETE FROM settings WHERE key = ?', [key]);
  } else {
    dbRun(
      relDb,
      'INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
      [key, value]
    );
  }
  return { key: key, value: value };
};

// ----- Backup / restore -----------------------------------------------------

handlers.exportRelationshipsBytes = async function () {
  if (!poolUtil) throw new Error('pool util unavailable');
  return poolUtil.exportFile(RELATIONSHIPS_DB_SLOT);
};

handlers.inspectRelationshipsBytes = async function (args) {
  return inspectBytes(args && args.bytes);
};

handlers.countRelationships = async function () {
  if (!relDb) return null;
  return {
    groups: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM groups', null).n,
    members: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM group_members', null).n,
    tags: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_tags', null).n,
    notes: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM fellow_notes', null).n,
    settings: dbSelectOne(relDb, 'SELECT COUNT(*) AS n FROM settings', null).n
  };
};

handlers.importRelationshipsBytes = async function (args) {
  if (!poolUtil) throw new Error('pool util unavailable');
  var bytes = args && args.bytes;
  var inspection = await inspectBytes(bytes);
  if (!inspection.valid) {
    var err = new Error(inspection.error || 'invalid relationships.db file');
    err.invalidBackup = true;
    throw err;
  }
  var snap = await snapshotRelationshipsDbToBackup();
  if (relDb) {
    try { relDb.close(); } catch (e) {}
    relDb = null;
  }
  poolUtil.importDb(RELATIONSHIPS_DB_SLOT, bytes);
  relDb = new poolUtil.OpfsSAHPoolDb(RELATIONSHIPS_DB_SLOT);
  bootstrapRelationshipsSchema(relDb);
  return {
    counts: inspection.counts,
    preRestoreSnapshot: snap && snap.backedUp ? snap.name : null
  };
};

handlers.listRelationshipsBackups = async function () {
  if (!poolUtil) return [];
  var raw = await listRelationshipsBackups();
  var out = [];
  // Sequential — staging slot is shared across inspects.
  for (var i = 0; i < raw.length; i++) {
    var entry = raw[i];
    try {
      var bytes = await _opfsReadBinary(entry.name);
      var insp = await inspectBytes(bytes);
      out.push({
        name: entry.name, size: entry.size, lastModified: entry.lastModified,
        counts: insp.valid ? insp.counts : null,
        invalid: !insp.valid,
        error: insp.valid ? null : insp.error
      });
    } catch (e) {
      out.push({
        name: entry.name, size: entry.size, lastModified: entry.lastModified,
        counts: null, invalid: true, error: (e && e.message) || String(e)
      });
    }
  }
  return out;
};

handlers.restoreRelationshipsBackup = async function (args) {
  if (!poolUtil) throw new Error('pool util unavailable');
  var name = args && args.name;
  var backups = await listRelationshipsBackups();
  var match = null;
  for (var i = 0; i < backups.length; i++) {
    if (backups[i].name === name) { match = backups[i]; break; }
  }
  if (!match) throw new Error('Backup not found: ' + name);
  var bytes = await _opfsReadBinary(name);
  return await handlers.importRelationshipsBytes({ bytes: bytes });
};

// ----- fellows.db query handlers (sole local read source post-cutover) ------

function _requireFellowsDb() {
  if (!fellowsDb) {
    var err = new Error('fellows.db not open — page must call ensureFellowsDb first');
    err.code = 'fellows_db_not_open';
    throw err;
  }
  return fellowsDb;
}

handlers.getList = async function () {
  var db = _requireFellowsDb();
  var rows = dbSelectAll(
    db,
    'SELECT record_id, slug, name, ' +
      "CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END " +
      'AS has_contact_email FROM fellows ORDER BY name ASC',
    null
  );
  return rows.map(function (r) {
    return {
      record_id: r.record_id,
      slug: r.slug,
      name: r.name,
      has_contact_email: !!r.has_contact_email
    };
  });
};

handlers.getFull = async function () {
  var db = _requireFellowsDb();
  var rows = dbSelectAll(db, 'SELECT * FROM fellows ORDER BY name ASC', null);
  return rows.map(rowToFellow);
};

handlers.getOne = async function (args) {
  var db = _requireFellowsDb();
  var slugOrId = args && args.slug;
  if (!slugOrId) return null;
  var row = dbSelectOne(
    db,
    'SELECT * FROM fellows WHERE slug = ? OR record_id = ? LIMIT 1',
    [slugOrId, slugOrId]
  );
  return row ? rowToFellow(row) : null;
};

handlers.search = async function (args) {
  var db = _requireFellowsDb();
  var q = args && args.q;
  if (!q || !q.replace(/^\s+|\s+$/g, '')) return [];
  q = q.replace(/^\s+|\s+$/g, '');
  if (q.length > 200) q = q.slice(0, 200);
  var rows = dbSelectAll(
    db,
    'SELECT f.* FROM fellows f WHERE f.rowid IN (' +
      'SELECT rowid FROM fellows_fts WHERE fellows_fts MATCH ?' +
      ') ORDER BY f.name ASC',
    [q]
  );
  return rows.map(rowToFellow);
};

handlers.getStats = async function () {
  var db = _requireFellowsDb();
  var total = dbSelectOne(db, 'SELECT COUNT(*) AS n FROM fellows', null).n;

  function groupCounts(sql) {
    return dbSelectAll(db, sql, null).map(function (r) {
      // sqlite-wasm returns objects keyed by column expression string when
      // there's no alias. Pull the first non-COUNT key as the label.
      var keys = Object.keys(r);
      var labelKey = null;
      var countKey = null;
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (k.toUpperCase().indexOf('COUNT') === 0) countKey = k;
        else labelKey = k;
      }
      return { label: r[labelKey], count: r[countKey] };
    });
  }

  // Region counts: split comma-separated global_regions_currently_based_in
  // so dual-region fellows are counted in each region.
  var regionRows = dbSelectAll(
    db,
    'SELECT global_regions_currently_based_in AS regions FROM fellows ' +
      "WHERE global_regions_currently_based_in IS NOT NULL " +
      "AND global_regions_currently_based_in != ''",
    null
  );
  var regionCounter = {};
  for (var i = 0; i < regionRows.length; i++) {
    var parts = String(regionRows[i].regions).split(',');
    for (var j = 0; j < parts.length; j++) {
      var region = parts[j].replace(/^\s+|\s+$/g, '');
      if (region) regionCounter[region] = (regionCounter[region] || 0) + 1;
    }
  }
  var byRegion = Object.keys(regionCounter)
    .map(function (r) { return { label: r, count: regionCounter[r] }; })
    .sort(function (a, b) { return b.count - a.count; });

  // Field completeness: count non-empty values for each DB column and
  // each known extra_json key.
  var fieldCounts = [];
  var colKeys = Object.keys(COL_LABELS);
  for (var ci = 0; ci < colKeys.length; ci++) {
    var col = colKeys[ci];
    // Column names come from a controlled allow-list (COL_LABELS keys), so
    // string concat is safe — same pattern as app/server.py:get_stats.
    var n = dbSelectOne(
      db,
      'SELECT COUNT(*) AS n FROM fellows WHERE ' + col + ' IS NOT NULL AND ' + col + ' != \'\'',
      null
    ).n;
    fieldCounts.push({ label: COL_LABELS[col], count: n });
  }
  var extraKeys = Object.keys(EXTRA_LABELS);
  for (var ei = 0; ei < extraKeys.length; ei++) {
    var ekey = extraKeys[ei];
    var jsonPath = '$.' + ekey;
    var n2 = dbSelectOne(
      db,
      'SELECT COUNT(*) AS n FROM fellows WHERE extra_json IS NOT NULL ' +
        "AND json_extract(extra_json, ?) IS NOT NULL " +
        "AND json_extract(extra_json, ?) != ''",
      [jsonPath, jsonPath]
    ).n;
    fieldCounts.push({ label: EXTRA_LABELS[ekey], count: n2 });
  }
  fieldCounts.sort(function (a, b) { return b.count - a.count; });

  return {
    total: total,
    by_fellow_type: groupCounts(
      'SELECT fellow_type, COUNT(*) FROM fellows ' +
        'WHERE fellow_type IS NOT NULL ' +
        'GROUP BY fellow_type ORDER BY COUNT(*) DESC'
    ),
    by_cohort: groupCounts(
      'SELECT cohort, COUNT(*) FROM fellows ' +
        'WHERE cohort IS NOT NULL ' +
        'GROUP BY cohort ORDER BY COUNT(*) DESC'
    ),
    by_region: byRegion,
    field_completeness: fieldCounts
  };
};

// ----- ensureFellowsDb (page-driven cold-start fetch — opt-in policy) ------
// Page calls this on every boot, only after the gate decision tree
// resolves to directory mode. The boot path is install-only by design
// (plans/opt_in_directory_data_updates.md): on a returning visitor with
// fellows.db already on disk, the worker never auto-fetches, regardless
// of SHA. The user has to explicitly request a refresh via the About
// page → previewFellowsDbSwap → applyFellowsDbSwap RPCs.
//
//   - args.mode: 'install-only' (default) — fetch only when fellowsDb
//     is not open (cold start, post-Reset Everything). Returns the
//     existing handle untouched otherwise. SHA is ignored in this mode
//     beyond an informational trace.
//   - args.mode: 'refresh' — pre-PR-#113 behavior, kept for the
//     applyFellowsDbSwap RPC's internal use only. Fetch + validate +
//     atomic replace + meta update. `args.serverSha`, if provided, is
//     stamped into the trace; the actual SHA written to meta is the
//     digest of the bytes we received.
//   - Unknown / missing mode coerces to 'install-only'.
//
// On fetch / validation failure, `meta.last_failure_at` and
// `last_failure_reason` are recorded; the previously-live fellows.db
// stays open. The error is also thrown so the page can surface a soft
// warning, but `relationships.db` operations remain unaffected (G3 / L5).

async function _writeMetaFailure(reason) {
  var existing = (await readFellowsMeta()) || {
    sha: null,
    fetched_at: null,
    last_failure_at: null,
    last_failure_reason: null
  };
  existing.last_failure_at = new Date().toISOString();
  existing.last_failure_reason = String(reason || '');
  try { await writeFellowsMeta(existing); }
  catch (we) { trace('ensureFellowsDb: meta-failure write failed: ' + (we && we.message || we)); }
  return existing;
}

// Fetch /fellows.db, validate, atomically replace the live slot, write
// meta. Throws on any failure with a code-tagged Error; on throw the
// previously-live fellowsDb stays open and meta records the failure.
// Used by both ensureFellowsDb's cold-start branch and (via raw bytes
// already on disk) applyFellowsDbSwap.
async function _fetchValidateAndImportFellowsDb(serverShaHint, kind) {
  trace('fellows.db ' + kind + ': fetch /fellows.db'
    + (serverShaHint ? ' (serverSha=' + serverShaHint.slice(0, 12) + '…)' : ''));

  var resp;
  try {
    resp = await fetch('/fellows.db', { credentials: 'include', cache: 'no-store' });
  } catch (e) {
    var netReason = 'network: ' + (e && e.message || e);
    var failedMeta = await _writeMetaFailure(netReason);
    var nerr = new Error('Network fetch /fellows.db failed: ' + (e && e.message || e));
    nerr.code = 'fellows_db_fetch_network';
    nerr.meta = failedMeta;
    throw nerr;
  }
  if (!resp.ok) {
    var httpReason = 'HTTP ' + resp.status;
    var failedMetaH = await _writeMetaFailure(httpReason);
    var herr = new Error('GET /fellows.db returned HTTP ' + resp.status);
    herr.code = 'fellows_db_fetch_http';
    herr.httpStatus = resp.status;
    herr.meta = failedMetaH;
    throw herr;
  }
  var buf = await resp.arrayBuffer();
  var bytes = new Uint8Array(buf);
  if (!bytes.byteLength) {
    var emptyMeta = await _writeMetaFailure('empty response');
    var eerr = new Error('Empty /fellows.db response');
    eerr.code = 'fellows_db_fetch_empty';
    eerr.meta = emptyMeta;
    throw eerr;
  }

  // Validate the fetched bytes in a staging slot before touching the live
  // slot. If validation fails, the previous fellowsDb is still open and
  // the error path leaves it untouched.
  var verifyDb = null;
  try {
    poolUtil.importDb(FELLOWS_STAGING_SLOT, bytes);
    verifyDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_STAGING_SLOT);
    var qc = dbSelectOne(verifyDb, 'PRAGMA quick_check', null);
    var qcResult = qc && (qc.quick_check || qc['quick_check']);
    if (qcResult !== 'ok') {
      throw new Error('quick_check failed: ' + (qcResult || 'unknown'));
    }
  } catch (verr) {
    if (verifyDb) { try { verifyDb.close(); } catch (e2) {} }
    var invalidReason = 'invalid bytes: ' + (verr && verr.message || verr);
    var invalidMeta = await _writeMetaFailure(invalidReason);
    var ierr = new Error('Validation of fetched fellows.db failed: ' + (verr && verr.message || verr));
    ierr.code = 'fellows_db_invalid';
    ierr.meta = invalidMeta;
    throw ierr;
  }
  if (verifyDb) { try { verifyDb.close(); } catch (e3) {} }

  // Compute the digest of what we actually got. This is the value that
  // ends up in meta.sha — not the hint — so a server that lies about
  // its SHA can't desync the local copy.
  var fetchedSha = await _sha256Hex(bytes);

  // Promote staging → live slot. importDb requires the live slot's SAH
  // to be released first, so close the current handle (if any).
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e4) {}
    fellowsDb = null;
  }
  poolUtil.importDb(FELLOWS_DB_SLOT, bytes);
  fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
  trace('fellows.db ' + kind + ': imported ' + bytes.byteLength + ' bytes, sha=' + fetchedSha.slice(0, 12) + '…');

  var newMeta = {
    sha: fetchedSha,
    fetched_at: new Date().toISOString(),
    last_failure_at: null,
    last_failure_reason: null
  };
  try { await writeFellowsMeta(newMeta); }
  catch (we) { trace('fellows.db ' + kind + ': meta write failed: ' + (we && we.message || we)); }
  return { bytes: bytes, sha: fetchedSha, meta: newMeta };
}

handlers.ensureFellowsDb = async function (args) {
  args = args || {};
  var mode = args.mode === 'refresh' ? 'refresh' : 'install-only';
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  var localMeta = await readFellowsMeta();

  // Install-only is the boot-path policy under
  // plans/opt_in_directory_data_updates.md: never auto-refresh a
  // returning visitor's fellows.db, regardless of SHA. The user opts
  // in via previewFellowsDbSwap → applyFellowsDbSwap.
  if (mode === 'install-only' && fellowsDb) {
    return { hasFellowsDb: true, refreshed: false, meta: localMeta || null };
  }

  // Cold-start (no local fellows.db) under either mode: fetch.
  // Refresh under either condition: fetch.
  var kind = fellowsDb ? 'refresh' : 'cold-start';
  var imported = await _fetchValidateAndImportFellowsDb(serverSha, kind);
  return { hasFellowsDb: true, refreshed: true, meta: imported.meta };
};

// ----- Opt-in directory-data update flow ------------------------------------
// plans/opt_in_directory_data_updates.md. Flow:
//   1. compareFellowsDbSha({serverSha}) → quick read of meta.sha vs server.
//   2. previewFellowsDbSwap({serverSha}) → fetch + validate + write to
//      swap-staging slot. Compute affected group members. Return.
//   3. applyFellowsDbSwap({stagingId}) → promote staging → live slot.
//      OR cancelFellowsDbSwap({stagingId}) → discard.
//
// The staging slot persists between (2) and (3) so the dialog can sit
// open without holding bytes in JS memory. `pendingFellowsDbSwap` holds
// the metadata + an opaque id the page must echo back; a stale id
// (page reloaded, worker restarted) makes apply 400.

function _newStagingId() {
  // 16 hex chars from crypto.getRandomValues — opaque, unguessable enough
  // for a same-process correlation handle.
  var arr = new Uint8Array(8);
  crypto.getRandomValues(arr);
  var hex = '';
  for (var i = 0; i < arr.length; i++) {
    var b = arr[i];
    hex += (b < 16 ? '0' : '') + b.toString(16);
  }
  return hex;
}

function _clearSwapStagingSlot() {
  if (!poolUtil) return;
  try {
    if (typeof poolUtil.unlink === 'function') {
      poolUtil.unlink(FELLOWS_SWAP_STAGING_SLOT);
    }
  } catch (e) { /* slot may not exist; non-fatal */ }
}

handlers.compareFellowsDbSha = async function (args) {
  args = args || {};
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  var meta = await readFellowsMeta();
  var localSha = (meta && typeof meta.sha === 'string') ? meta.sha : null;
  // dataUpdateAvailable is only true when we have a local DB AND a
  // local SHA AND a server SHA AND they differ. Cold-start (no local
  // DB) is not an "update" — that's the install path. Server unreachable
  // (serverSha null) returns null so the UI can show "couldn't check"
  // distinctly from "up to date".
  var dataUpdateAvailable = false;
  if (!serverSha) {
    dataUpdateAvailable = null;
  } else if (fellowsDb && localSha) {
    dataUpdateAvailable = (localSha !== serverSha);
  }
  return {
    hasFellowsDb: !!fellowsDb,
    localSha: localSha,
    serverSha: serverSha,
    fetchedAt: (meta && meta.fetched_at) || null,
    dataUpdateAvailable: dataUpdateAvailable
  };
};

handlers.previewFellowsDbSwap = async function (args) {
  args = args || {};
  var serverSha = (typeof args.serverSha === 'string' && args.serverSha) ? args.serverSha : null;
  if (!fellowsDb) {
    var nerr = new Error('No local fellows.db to swap from');
    nerr.code = 'no_local_fellows_db';
    throw nerr;
  }
  // A previous pending swap is implicitly discarded: we only support one
  // outstanding swap at a time. Later attempts re-fetch.
  if (pendingFellowsDbSwap) {
    _clearSwapStagingSlot();
    pendingFellowsDbSwap = null;
  }

  // Fetch into the swap-staging slot. Reuse the validation path by writing
  // to the existing staging slot first, but copy into the swap-staging
  // slot afterwards so the boot-path slot stays free for any future
  // ensureFellowsDb call.
  trace('previewFellowsDbSwap: fetch /fellows.db'
    + (serverSha ? ' (serverSha=' + serverSha.slice(0, 12) + '…)' : ''));
  var resp;
  try {
    resp = await fetch('/fellows.db', { credentials: 'include', cache: 'no-store' });
  } catch (e) {
    var nferr = new Error('Network fetch /fellows.db failed: ' + (e && e.message || e));
    nferr.code = 'fellows_db_fetch_network';
    throw nferr;
  }
  if (!resp.ok) {
    var herr = new Error('GET /fellows.db returned HTTP ' + resp.status);
    herr.code = 'fellows_db_fetch_http';
    herr.httpStatus = resp.status;
    throw herr;
  }
  var buf = await resp.arrayBuffer();
  var bytes = new Uint8Array(buf);
  if (!bytes.byteLength) {
    var eerr = new Error('Empty /fellows.db response');
    eerr.code = 'fellows_db_fetch_empty';
    throw eerr;
  }

  // Validate by importing into the swap-staging slot directly and running
  // PRAGMA quick_check + a fellows-table sanity probe.
  var stagingDb = null;
  var fetchedSha;
  var stagedIdSet; // map: record_ids present in the staged fellows.db
  try {
    poolUtil.importDb(FELLOWS_SWAP_STAGING_SLOT, bytes);
    stagingDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_SWAP_STAGING_SLOT);
    var qc = dbSelectOne(stagingDb, 'PRAGMA quick_check', null);
    var qcResult = qc && (qc.quick_check || qc['quick_check']);
    if (qcResult !== 'ok') {
      throw new Error('quick_check failed: ' + (qcResult || 'unknown'));
    }
    // Smoke-check the schema. A zero-row DB is technically valid SQLite
    // but would silently orphan every existing group member; reject it.
    var totalRow = dbSelectOne(stagingDb, 'SELECT COUNT(*) AS n FROM fellows', null);
    if (!totalRow || !totalRow.n) {
      throw new Error('staged fellows.db has zero rows');
    }
    fetchedSha = await _sha256Hex(bytes);

    // Compute affected group members: every record_id in group_members
    // that has no matching record in the staged fellows.db. We need
    // (a) the set of record_ids in the staged DB (b) every (member,
    // group) pair from relationships.db (c) human-readable names from
    // the *live* fellows.db so the dialog can show "Alice Smith" not
    // a record_id.
    var stagedIdsRows = dbSelectAll(stagingDb, 'SELECT record_id FROM fellows', null);
    stagedIdSet = {};
    for (var i = 0; i < stagedIdsRows.length; i++) stagedIdSet[stagedIdsRows[i].record_id] = true;
  } catch (verr) {
    if (stagingDb) { try { stagingDb.close(); } catch (e2) {} }
    _clearSwapStagingSlot();
    var ierr = new Error('Validation of staged fellows.db failed: ' + (verr && verr.message || verr));
    ierr.code = 'fellows_db_invalid';
    throw ierr;
  }
  try { stagingDb.close(); } catch (e3) {}

  // Resolve affected members from the page's perspective. Read
  // group_members + group names from relationships.db, drop any whose
  // record_id is in the staged set, then look up display names in the
  // *live* fellows.db.
  var affected = []; // [{ recordId, name, groups: [{id, name}] }]
  if (relDb) {
    var memberRows = dbSelectAll(
      relDb,
      'SELECT gm.fellow_record_id AS rid, gm.group_id AS gid, g.name AS gname ' +
        'FROM group_members gm JOIN groups g ON g.id = gm.group_id',
      null
    );
    var byRid = {};
    for (var m = 0; m < memberRows.length; m++) {
      var row = memberRows[m];
      if (stagedIdSet[row.rid]) continue; // still present after swap
      if (!byRid[row.rid]) byRid[row.rid] = { recordId: row.rid, name: null, groups: [] };
      byRid[row.rid].groups.push({ id: row.gid, name: row.gname });
    }
    var ridKeys = Object.keys(byRid);
    if (ridKeys.length && fellowsDb) {
      // Resolve names from the live DB. Bind one at a time — the count is
      // expected to be small (members lost between consecutive deploys).
      for (var rk = 0; rk < ridKeys.length; rk++) {
        var rid = ridKeys[rk];
        var nrow = dbSelectOne(fellowsDb, 'SELECT name FROM fellows WHERE record_id = ?', [rid]);
        byRid[rid].name = (nrow && nrow.name) || null;
        affected.push(byRid[rid]);
      }
      affected.sort(function (a, b) {
        var an = (a.name || '').toLowerCase();
        var bn = (b.name || '').toLowerCase();
        return an < bn ? -1 : an > bn ? 1 : 0;
      });
    }
  }

  var stagingId = _newStagingId();
  pendingFellowsDbSwap = {
    stagingId: stagingId,
    sha: fetchedSha,
    fetchedAt: new Date().toISOString(),
    serverShaHint: serverSha
  };
  trace('previewFellowsDbSwap: staged sha=' + fetchedSha.slice(0, 12) +
    '… affectedMembers=' + affected.length + ' stagingId=' + stagingId);

  return {
    stagingId: stagingId,
    newSha: fetchedSha,
    affectedGroups: affected
  };
};

handlers.applyFellowsDbSwap = async function (args) {
  args = args || {};
  var stagingId = args.stagingId;
  if (!pendingFellowsDbSwap || !stagingId || pendingFellowsDbSwap.stagingId !== stagingId) {
    var serr = new Error('No matching pending swap (stagingId mismatch or expired)');
    serr.code = 'staging_id_mismatch';
    throw serr;
  }
  var pending = pendingFellowsDbSwap;
  // Read bytes back from the staging slot. exportFile returns a fresh
  // Uint8Array; importDb-into-live releases the SAH after we close the
  // current live handle.
  var bytes;
  try {
    bytes = poolUtil.exportFile(FELLOWS_SWAP_STAGING_SLOT);
  } catch (e) {
    pendingFellowsDbSwap = null;
    _clearSwapStagingSlot();
    var rerr = new Error('Could not read staged bytes: ' + (e && e.message || e));
    rerr.code = 'staging_export_failed';
    throw rerr;
  }
  if (!bytes || !bytes.byteLength) {
    pendingFellowsDbSwap = null;
    _clearSwapStagingSlot();
    var berr = new Error('Staged bytes are empty');
    berr.code = 'staging_empty';
    throw berr;
  }
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e2) {}
    fellowsDb = null;
  }
  poolUtil.importDb(FELLOWS_DB_SLOT, bytes);
  fellowsDb = new poolUtil.OpfsSAHPoolDb(FELLOWS_DB_SLOT);
  var newMeta = {
    sha: pending.sha,
    fetched_at: pending.fetchedAt,
    last_failure_at: null,
    last_failure_reason: null
  };
  try { await writeFellowsMeta(newMeta); }
  catch (we) { trace('applyFellowsDbSwap: meta write failed: ' + (we && we.message || we)); }
  pendingFellowsDbSwap = null;
  _clearSwapStagingSlot();
  trace('applyFellowsDbSwap: live slot promoted to sha=' + pending.sha.slice(0, 12) + '…');
  return { ok: true, newSha: pending.sha, meta: newMeta };
};

handlers.cancelFellowsDbSwap = async function (args) {
  args = args || {};
  var stagingId = args.stagingId;
  // Be lenient on cancel — if the page sends a stale id, just clear
  // anyway. The intent ("don't apply the staged update") is unambiguous.
  if (pendingFellowsDbSwap && stagingId && pendingFellowsDbSwap.stagingId !== stagingId) {
    trace('cancelFellowsDbSwap: stagingId mismatch — clearing pending anyway');
  }
  pendingFellowsDbSwap = null;
  _clearSwapStagingSlot();
  return { ok: true };
};

// Soft scan invoked once on first boot of the new code (gated by the
// `orphan_scan_done` setting on the page side). Returns the same shape
// as previewFellowsDbSwap.affectedGroups so the same UI patterns apply.
handlers.findOrphanedGroupMembers = async function () {
  if (!relDb || !fellowsDb) return { orphans: [] };
  var memberRows = dbSelectAll(
    relDb,
    'SELECT gm.fellow_record_id AS rid, gm.group_id AS gid, g.name AS gname ' +
      'FROM group_members gm JOIN groups g ON g.id = gm.group_id',
    null
  );
  if (!memberRows.length) return { orphans: [] };
  var fellowRows = dbSelectAll(fellowsDb, 'SELECT record_id FROM fellows', null);
  var existing = {};
  for (var i = 0; i < fellowRows.length; i++) existing[fellowRows[i].record_id] = true;
  var byRid = {};
  for (var j = 0; j < memberRows.length; j++) {
    var r = memberRows[j];
    if (existing[r.rid]) continue;
    if (!byRid[r.rid]) byRid[r.rid] = { recordId: r.rid, name: null, groups: [] };
    byRid[r.rid].groups.push({ id: r.gid, name: r.gname });
  }
  var orphans = [];
  var keys = Object.keys(byRid);
  for (var k = 0; k < keys.length; k++) orphans.push(byRid[keys[k]]);
  orphans.sort(function (a, b) {
    return a.recordId < b.recordId ? -1 : a.recordId > b.recordId ? 1 : 0;
  });
  return { orphans: orphans };
};

// ----- Diagnostics ----------------------------------------------------------

handlers.getTrace = async function () { return bootTrace.slice(); };

handlers.getVersions = async function () {
  return {
    workerRpcVersion: WORKER_RPC_VERSION,
    schemaVersion: RELATIONSHIPS_SCHEMA_VERSION,
    buildLabel: BUILD_LABEL
  };
};

// Read-only view of fellows.db.meta.json for diagnostics + the About
// page's "Last update check" line. Pure read — never triggers a fetch
// or import; that's ensureFellowsDb's job. Returns null when the meta
// file doesn't exist yet (cold-start before first ensureFellowsDb).
handlers.getFellowsDbMeta = async function () {
  return await readFellowsMeta();
};

// Reset Everything's nuclear path. Closes both DB handles, tears down the
// SAH-pool VFS via removeVfs() (which releases every SAH and recursively
// removes the pool's opaque storage dir), then sweeps sibling files we
// create at OPFS root (relationships.db.bak.*, fellows.db.meta.json, any
// orphaned LEGACY_SENTINEL). Caller is expected to reload the page after
// — the worker is unusable post-wipe (poolUtil reset to null).
//
// Restores the pre-cutover Reset Everything semantics: L1 forbids the
// page from opening OPFS, so the page can't iterate the root itself.
// This op is the worker-side replacement.
handlers.wipeAll = async function () {
  if (relDb) {
    try { relDb.close(); } catch (e) {}
    relDb = null;
  }
  if (fellowsDb) {
    try { fellowsDb.close(); } catch (e) {}
    fellowsDb = null;
  }
  var removedVfs = false;
  if (poolUtil) {
    try { removedVfs = await poolUtil.removeVfs(); }
    catch (e) { trace('wipeAll: removeVfs failed: ' + (e && e.message || e)); }
  }
  var rootEntriesRemoved = [];
  var rootEntriesFailed = [];
  try {
    var root = await self.navigator.storage.getDirectory();
    var names = [];
    for await (var entry of root.values()) names.push(entry.name);
    for (var i = 0; i < names.length; i++) {
      try {
        await root.removeEntry(names[i], { recursive: true });
        rootEntriesRemoved.push(names[i]);
      } catch (e2) {
        rootEntriesFailed.push({ name: names[i], error: (e2 && e2.message) || String(e2) });
        trace('wipeAll: removeEntry ' + names[i] + ' failed: ' + (e2 && e2.message || e2));
      }
    }
  } catch (e3) {
    trace('wipeAll: root iteration failed: ' + (e3 && e3.message || e3));
  }
  poolUtil = null;
  trace('wipeAll: removedVfs=' + removedVfs + ' rootRemoved=' + rootEntriesRemoved.length +
        ' rootFailed=' + rootEntriesFailed.length);
  return {
    removedVfs: removedVfs,
    rootEntriesRemoved: rootEntriesRemoved,
    rootEntriesFailed: rootEntriesFailed
  };
};

// Returns a snapshot of every OPFS root entry plus the SAH-pool slot
// inventory. Used by the ?diag=1 panel post-Phase-1 so the maintainer
// can see exactly what's on disk without main-thread OPFS access.
handlers.getOpfsInventory = async function () {
  var rootEntries = [];
  try {
    var root = await _opfsRoot();
    for await (var entry of root.values()) {
      var item = { name: entry.name, kind: entry.kind };
      if (entry.kind === 'file') {
        try {
          var f = await entry.getFile();
          item.size = f.size;
          item.lastModified = f.lastModified;
        } catch (fe) {}
      }
      rootEntries.push(item);
    }
    rootEntries.sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; });
  } catch (e) {}
  var poolFiles = [];
  try { poolFiles = poolUtil.getFileNames(); } catch (e2) {}
  return { root: rootEntries, poolFiles: poolFiles };
};

// ===== Dispatcher ===========================================================

self.onmessage = async function (ev) {
  var data = ev.data || {};
  var id = data.id;
  var op = data.op;
  var args = data.args;
  var handler = handlers[op];
  if (!handler) {
    self.postMessage({ id: id, ok: false, error: 'unknown op: ' + op });
    return;
  }
  try {
    var result = await handler(args);
    self.postMessage({ id: id, ok: true, result: result });
  } catch (e) {
    self.postMessage({
      id: id, ok: false,
      error: (e && e.message) || String(e),
      errorName: e && e.name,
      errorCode: e && e.code,
      httpStatus: e && e.httpStatus,
      // ensureFellowsDb attaches the post-failure meta blob (with
      // last_failure_at / last_failure_reason populated) so the page
      // can surface a soft warning without a second RPC roundtrip.
      meta: e && e.meta,
      stack: e && e.stack
    });
  }
};
